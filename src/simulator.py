"""Forward game simulator + lookahead search for Orbit Wars.

A faithful re-implementation of the Kaggle ``orbit_wars`` interpreter physics so
the agent can simulate candidate moves several turns ahead and pick the action
set that leads to the best board -- spending the ~99% of the per-turn compute
budget the greedy agent leaves idle.

Fidelity is the contract: ``step`` mirrors the env interpreter's exact tick
order and the collision/combat math is copied verbatim. See
``tests/test_simulator_fidelity.py``.

Data shapes mirror the env for verifiability:
  planet = [id, owner, x, y, radius, ships, production]   (mutable list)
  fleet  = [id, owner, x, y, angle, from_planet_id, ships]
  comet group = {"planet_ids": [...], "paths": [[(x,y), ...], ...], "path_index": int}
"""

from __future__ import annotations

import math

import geometry

BOARD_SIZE = 100.0
CENTER = BOARD_SIZE / 2.0
SUN_RADIUS = 10.0
ROTATION_RADIUS_LIMIT = 50.0
COMET_SPAWN_STEPS = (50, 150, 250, 350, 450)
DEFAULT_MAX_SPEED = 6.0
EPISODE_STEPS = 500


# ---------------------------------------------------------------------------
# Collision helpers -- copied VERBATIM from kaggle_environments orbit_wars.py
# for bit-level parity. Do not "improve" these.
# ---------------------------------------------------------------------------
def _distance(p1, p2):
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def point_to_segment_distance(p, v, w):
    """Minimum distance from point p to line segment v-w."""
    l2 = (v[0] - w[0]) ** 2 + (v[1] - w[1]) ** 2
    if l2 == 0.0:
        return _distance(p, v)
    t = max(
        0, min(1, ((p[0] - v[0]) * (w[0] - v[0]) + (p[1] - v[1]) * (w[1] - v[1])) / l2)
    )
    projection = (v[0] + t * (w[0] - v[0]), v[1] + t * (w[1] - v[1]))
    return _distance(p, projection)


def swept_pair_hit(A, B, P0, P1, r):
    """True iff a fleet moving A->B and a planet moving P0->P1 come within r
    of each other for some t in [0, 1]."""
    d0x, d0y = A[0] - P0[0], A[1] - P0[1]
    dvx = (B[0] - A[0]) - (P1[0] - P0[0])
    dvy = (B[1] - A[1]) - (P1[1] - P0[1])
    a = dvx * dvx + dvy * dvy
    b = 2.0 * (d0x * dvx + d0y * dvy)
    c = d0x * d0x + d0y * d0y - r * r
    if a < 1e-12:
        return c <= 0.0
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return False
    sq = math.sqrt(disc)
    t1 = (-b - sq) / (2.0 * a)
    t2 = (-b + sq) / (2.0 * a)
    return t2 >= 0.0 and t1 <= 1.0


# Planet / fleet field indices (shared [id, owner, x, y, ...] prefix).
P_ID, P_OWNER, P_X, P_Y, P_RADIUS, P_SHIPS, P_PROD = range(7)
F_ID, F_OWNER, F_X, F_Y, F_ANGLE, F_FROM, F_SHIPS = range(7)


def _obs_get(obs, key, default=None):
    return obs.get(key, default) if isinstance(obs, dict) else getattr(obs, key, default)


class GameState:
    """Mutable game state advanced by :meth:`step`.

    ``initial_by_id`` maps planet id -> (init_x, init_y) used for orbit
    rotation; it is read-only per rollout and shared across clones. Comet
    ``paths`` are likewise shared (immutable); only ``path_index`` and
    ``planet_ids`` are copied.
    """

    __slots__ = (
        "planets", "fleets", "comets", "comet_pids", "initial_by_id",
        "angular_velocity", "step", "next_fleet_id", "num_players",
        "max_speed", "episode_steps",
    )

    def __init__(self, planets, fleets, comets, comet_pids, initial_by_id,
                 angular_velocity, step, next_fleet_id, num_players,
                 max_speed=DEFAULT_MAX_SPEED, episode_steps=EPISODE_STEPS):
        self.planets = planets
        self.fleets = fleets
        self.comets = comets
        self.comet_pids = comet_pids
        self.initial_by_id = initial_by_id
        self.angular_velocity = angular_velocity
        self.step = step
        self.next_fleet_id = next_fleet_id
        self.num_players = num_players
        self.max_speed = max_speed
        self.episode_steps = episode_steps

    @classmethod
    def from_obs(cls, obs, max_speed=DEFAULT_MAX_SPEED, episode_steps=EPISODE_STEPS):
        raw_planets = _obs_get(obs, "planets", []) or []
        raw_fleets = _obs_get(obs, "fleets", []) or []
        raw_initial = _obs_get(obs, "initial_planets", None)
        raw_comets = _obs_get(obs, "comets", []) or []
        comet_pids = set(_obs_get(obs, "comet_planet_ids", []) or [])

        planets = [list(p) for p in raw_planets]
        fleets = [list(f) for f in raw_fleets]

        # initial positions for rotation; fall back to current positions if the
        # observation omits initial_planets (synthetic states).
        initial_by_id = {}
        for p in (raw_initial if raw_initial is not None else raw_planets):
            initial_by_id[p[0]] = (p[2], p[3])

        comets = []
        for g in raw_comets:
            comets.append({
                "planet_ids": list(g["planet_ids"]) if isinstance(g, dict) else list(g.planet_ids),
                "paths": g["paths"] if isinstance(g, dict) else g.paths,  # shared, immutable
                "path_index": g["path_index"] if isinstance(g, dict) else g.path_index,
            })

        next_fleet_id = _obs_get(obs, "next_fleet_id", None)
        if next_fleet_id is None:
            next_fleet_id = (max((f[0] for f in fleets), default=-1) + 1)
        step = _obs_get(obs, "step", 0) or 0

        owners = {p[1] for p in planets if p[1] >= 0} | {f[1] for f in fleets if f[1] >= 0}
        num_players = max(2, (max(owners) + 1) if owners else 2)

        return cls(
            planets, fleets, comets, comet_pids, initial_by_id,
            _obs_get(obs, "angular_velocity", 0.0) or 0.0,
            step, next_fleet_id, num_players, max_speed, episode_steps,
        )

    def clone(self) -> "GameState":
        """Copy everything :meth:`step` mutates; share read-only data."""
        return GameState(
            [p[:] for p in self.planets],
            [f[:] for f in self.fleets],
            [{"planet_ids": g["planet_ids"][:], "paths": g["paths"],
              "path_index": g["path_index"]} for g in self.comets],
            set(self.comet_pids),
            self.initial_by_id,          # shared (read-only)
            self.angular_velocity,
            self.step,
            self.next_fleet_id,
            self.num_players,
            self.max_speed,
            self.episode_steps,
        )

    def scores(self) -> list[int]:
        """Ships on owned planets + ships in owned fleets, per player."""
        s = [0] * self.num_players
        for p in self.planets:
            if 0 <= p[P_OWNER] < self.num_players:
                s[p[P_OWNER]] += p[P_SHIPS]
        for f in self.fleets:
            if 0 <= f[F_OWNER] < self.num_players:
                s[f[F_OWNER]] += f[F_SHIPS]
        return s

    def alive_players(self) -> set[int]:
        alive = {p[P_OWNER] for p in self.planets if p[P_OWNER] >= 0}
        alive |= {f[F_OWNER] for f in self.fleets if f[F_OWNER] >= 0}
        return alive

    def is_terminal(self) -> bool:
        return self.step >= self.episode_steps - 2 or len(self.alive_players()) <= 1


# ---------------------------------------------------------------------------
# step(): one tick, mirroring the env interpreter's exact order.
#   expire comets (pre-launch) -> [spawn: SKIPPED, hidden seed] -> launch ->
#   production -> rotation/comet-advance -> fleet movement (swept vs planets,
#   then OOB, then sun) -> apply planet movement -> remove expired comets ->
#   combat -> step += 1
# ---------------------------------------------------------------------------
def _drop_planets(state, expired_set):
    state.planets = [p for p in state.planets if p[P_ID] not in expired_set]
    state.comet_pids -= expired_set
    for g in state.comets:
        g["planet_ids"] = [pid for pid in g["planet_ids"] if pid not in expired_set]
    state.comets = [g for g in state.comets if g["planet_ids"]]


def step(state: GameState, actions_by_player: dict) -> GameState:
    planets = state.planets

    # --- expire comets whose path is already exhausted (pre-launch) ---
    expired = []
    for g in state.comets:
        idx = g["path_index"]
        for i, pid in enumerate(g["planet_ids"]):
            if idx >= len(g["paths"][i]):
                expired.append(pid)
    if expired:
        _drop_planets(state, set(expired))

    # --- comet spawning: SKIPPED. The schedule is seeded and hidden from
    # agents; lookahead under-models future comets (production-1, minor). ---

    # --- fleet launch ---
    by_id = {p[P_ID]: p for p in state.planets}
    for player_id, action in (actions_by_player or {}).items():
        if not action or not isinstance(action, list):
            continue
        for move in action:
            if len(move) != 3:
                continue
            from_id, angle, ships = move[0], move[1], int(move[2])
            fp = by_id.get(from_id)
            if fp is not None and fp[P_OWNER] == player_id and ships > 0 and fp[P_SHIPS] >= ships:
                fp[P_SHIPS] -= ships
                sx = fp[P_X] + math.cos(angle) * (fp[P_RADIUS] + 0.1)
                sy = fp[P_Y] + math.sin(angle) * (fp[P_RADIUS] + 0.1)
                state.fleets.append(
                    [state.next_fleet_id, player_id, sx, sy, angle, from_id, ships]
                )
                state.next_fleet_id += 1

    # --- production: every non-neutral planet (comets included) ---
    for p in state.planets:
        if p[P_OWNER] != -1:
            p[P_SHIPS] += p[P_PROD]

    # --- planet end-of-tick positions (rotation), comets advance along paths ---
    av = state.angular_velocity
    step_n = state.step
    comet_pids = state.comet_pids
    initial_by_id = state.initial_by_id
    planet_paths = {}  # pid -> (old_pos, new_pos, check_collision)

    for p in state.planets:
        if p[P_ID] in comet_pids:
            continue
        old = (p[P_X], p[P_Y])
        new = old
        init = initial_by_id.get(p[P_ID])
        if init is not None:
            dx, dy = init[0] - CENTER, init[1] - CENTER
            r = math.sqrt(dx * dx + dy * dy)
            if r + p[P_RADIUS] < ROTATION_RADIUS_LIMIT:
                ang = math.atan2(dy, dx) + av * step_n
                new = (CENTER + r * math.cos(ang), CENTER + r * math.sin(ang))
        planet_paths[p[P_ID]] = (old, new, True)

    expired_advance = []
    for g in state.comets:
        g["path_index"] += 1
        idx = g["path_index"]
        for i, pid in enumerate(g["planet_ids"]):
            p = by_id.get(pid) or next((q for q in state.planets if q[P_ID] == pid), None)
            if p is None:
                continue
            p_path = g["paths"][i]
            old = (p[P_X], p[P_Y])
            if idx >= len(p_path):
                expired_advance.append(pid)
                planet_paths[pid] = (old, old, True)
            else:
                new = (p_path[idx][0], p_path[idx][1])
                planet_paths[pid] = (old, new, old[0] >= 0)  # off-board first placement

    # --- fleet movement (continuous swept-pair collision) ---
    max_speed = state.max_speed
    remove = [False] * len(state.fleets)
    combat = {p[P_ID]: [] for p in state.planets}

    for fi, fleet in enumerate(state.fleets):
        angle = fleet[F_ANGLE]
        ships = fleet[F_SHIPS]
        speed = 1.0 + (max_speed - 1.0) * (math.log(ships) / math.log(1000)) ** 1.5
        speed = min(speed, max_speed)
        old = (fleet[F_X], fleet[F_Y])
        fleet[F_X] += math.cos(angle) * speed
        fleet[F_Y] += math.sin(angle) * speed
        new = (fleet[F_X], fleet[F_Y])

        hit = False
        for p in state.planets:
            path = planet_paths.get(p[P_ID])
            if path is None or not path[2]:
                continue
            if swept_pair_hit(old, new, path[0], path[1], p[P_RADIUS]):
                combat[p[P_ID]].append(fleet)
                remove[fi] = True
                hit = True
                break
        if hit:
            continue
        if not (0 <= fleet[F_X] <= BOARD_SIZE and 0 <= fleet[F_Y] <= BOARD_SIZE):
            remove[fi] = True
            continue
        if point_to_segment_distance((CENTER, CENTER), old, new) < SUN_RADIUS:
            remove[fi] = True

    # --- apply planet movement ---
    for p in state.planets:
        path = planet_paths.get(p[P_ID])
        if path is not None:
            p[P_X], p[P_Y] = path[1]

    # --- remove comets that expired during advance ---
    if expired_advance:
        _drop_planets(state, set(expired_advance))

    state.fleets = [f for fi, f in enumerate(state.fleets) if not remove[fi]]

    # --- combat resolution ---
    pmap = {p[P_ID]: p for p in state.planets}
    for pid, flist in combat.items():
        if not flist:
            continue
        planet = pmap.get(pid)
        if planet is None:
            continue
        per_owner = {}
        for f in flist:
            per_owner[f[F_OWNER]] = per_owner.get(f[F_OWNER], 0) + f[F_SHIPS]
        if not per_owner:
            continue
        ordered = sorted(per_owner.items(), key=lambda kv: kv[1], reverse=True)
        top_owner, top_ships = ordered[0]
        if len(ordered) > 1:
            second = ordered[1][1]
            survivor = top_ships - second
            if ordered[0][1] == ordered[1][1]:
                survivor = 0
            survivor_owner = top_owner if survivor > 0 else -1
        else:
            survivor_owner, survivor = top_owner, top_ships
        if survivor > 0:
            if planet[P_OWNER] == survivor_owner:
                planet[P_SHIPS] += survivor
            else:
                planet[P_SHIPS] -= survivor
                if planet[P_SHIPS] < 0:
                    planet[P_OWNER] = survivor_owner
                    planet[P_SHIPS] = abs(planet[P_SHIPS])

    state.step += 1
    return state
