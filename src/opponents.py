"""Scripted reference opponents for the benchmark gym.

The builtin ``starter`` is a weak static-planet sniper; beating it 92% tells us
little about LB-grade bots. These three opponents each stress a known failure
class of our agent so local benchmarks produce real signal:

  * ``aggressive`` -- all-in rusher. Throws most ships at the nearest enemy it
    can plausibly take. Punishes a lead we fail to defend (lead-then-collapse).
  * ``expander``   -- neutral-greedy economy bot. Grabs the nearest affordable
    neutral from every planet. Punishes losing the production race.
  * ``turtle``     -- defensive hoarder. Sits on big garrisons, only snaps up
    trivially weak adjacent neutrals. Punishes passive play / slow expansion.

Each returns the raw Kaggle move list ``[[from_planet_id, angle, ships], ...]``.
All three skip sun-crossing shots (those fleets are destroyed) and never launch
more ships than a planet holds.
"""

from __future__ import annotations

import math
from collections import namedtuple

try:
    import geometry
except ModuleNotFoundError:  # pragma: no cover - geometry always on path in benchmark
    geometry = None

Planet = namedtuple("Planet", "id owner x y radius ships production")

CENTER = 50.0
SUN_RADIUS = 10.0


def _parse(obs):
    player = obs.get("player", 0) if isinstance(obs, dict) else getattr(obs, "player", 0)
    raw_planets = obs.get("planets", []) if isinstance(obs, dict) else getattr(obs, "planets", [])
    planets = [Planet(*p) for p in raw_planets]
    return player, planets


def _angle(ax, ay, bx, by):
    return math.atan2(by - ay, bx - ax)


def _dist(ax, ay, bx, by):
    return math.hypot(bx - ax, by - ay)


def _hits_sun(ax, ay, bx, by):
    """True if the straight shot from (ax,ay) to (bx,by) crosses the sun."""
    if geometry is not None:
        return geometry.shot_hits_sun((ax, ay), (bx, by))
    # Fallback: point-segment distance to the sun centre.
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return _dist(ax, ay, CENTER, CENTER) <= SUN_RADIUS
    t = max(0.0, min(1.0, ((CENTER - ax) * dx + (CENTER - ay) * dy) / length_sq))
    cx, cy = ax + t * dx, ay + t * dy
    return _dist(cx, cy, CENTER, CENTER) <= SUN_RADIUS


def aggressive_agent(obs):
    """All-in rusher: hurl most ships at the nearest beatable enemy/neutral."""
    player, planets = _parse(obs)
    targets = [p for p in planets if p.owner != player]
    moves = []
    for mp in planets:
        if mp.owner != player or mp.ships < 5:
            continue
        send = mp.ships - 1  # keep a token garrison
        # Prefer enemy planets we can take outright, then any non-owned planet.
        best = None
        best_key = None
        for t in targets:
            if _hits_sun(mp.x, mp.y, t.x, t.y):
                continue
            if t.ships >= send:
                continue
            d = _dist(mp.x, mp.y, t.x, t.y)
            # enemy first (owner >= 0), then by distance
            key = (0 if t.owner >= 0 else 1, d)
            if best_key is None or key < best_key:
                best_key, best = key, t
        if best is not None:
            moves.append([mp.id, _angle(mp.x, mp.y, best.x, best.y), send])
    return moves


def expander_agent(obs):
    """Economy bot: grab the nearest affordable neutral from each planet."""
    player, planets = _parse(obs)
    neutrals = [p for p in planets if p.owner == -1]
    moves = []
    for mp in planets:
        if mp.owner != player:
            continue
        reserve = max(2, mp.production)
        budget = mp.ships - reserve
        if budget <= 0:
            continue
        best = None
        best_d = float("inf")
        for t in neutrals:
            need = t.ships + 1
            if need > budget:
                continue
            if _hits_sun(mp.x, mp.y, t.x, t.y):
                continue
            d = _dist(mp.x, mp.y, t.x, t.y)
            if d < best_d:
                best_d, best = d, t
        if best is not None:
            moves.append([mp.id, _angle(mp.x, mp.y, best.x, best.y), best.ships + 1])
    return moves


def turtle_agent(obs):
    """Defensive hoarder: only snap up trivially weak adjacent neutrals."""
    player, planets = _parse(obs)
    neutrals = [p for p in planets if p.owner == -1]
    moves = []
    for mp in planets:
        if mp.owner != player or mp.ships < 40:
            continue
        # Only spend the surplus above a deliberately large reserve.
        budget = mp.ships - 30
        best = None
        best_d = float("inf")
        for t in neutrals:
            need = t.ships + 1
            if need > budget or t.ships > 15:
                continue
            d = _dist(mp.x, mp.y, t.x, t.y)
            if d > 35:  # only nearby grabs
                continue
            if _hits_sun(mp.x, mp.y, t.x, t.y):
                continue
            if d < best_d:
                best_d, best = d, t
        if best is not None:
            moves.append([mp.id, _angle(mp.x, mp.y, best.x, best.y), best.ships + 1])
    return moves


GYM = {
    "aggressive": aggressive_agent,
    "expander": expander_agent,
    "turtle": turtle_agent,
}
