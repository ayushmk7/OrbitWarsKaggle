import math


def distance_xy(ax, ay, bx, by):
    return math.hypot(bx - ax, by - ay)


def angle_to_xy(ax, ay, bx, by):
    return math.atan2(by - ay, bx - ax)


def fleet_speed(ships, max_speed=6.0):
    ships = max(1, ships)
    ratio = math.log(ships) / math.log(1000.0)
    speed = 1.0 + (max_speed - 1.0) * ratio**1.5
    return min(max_speed, max(1.0, speed))


def turns_to_reach(distance, ships, max_speed=6.0):
    if distance <= 0:
        return 0
    return math.ceil(distance / fleet_speed(ships, max_speed))


def min_ships_for_arrival(distance, max_arrival_turns, max_speed=6.0, cap=1000):
    """Smallest fleet size that reaches ``distance`` within ``max_arrival_turns``.

    Fleet speed scales with size, so tiny fleets crawl. For distant targets we
    enforce a minimum fleet so it arrives in a reasonable window instead of
    taking 3x longer than a large fleet would. Returns 1 if a single ship is
    already fast enough, or ``cap`` if even the max-speed fleet cannot make it.
    """
    if distance <= 0 or max_arrival_turns <= 0:
        return 1
    if turns_to_reach(distance, 1, max_speed) <= max_arrival_turns:
        return 1
    lo, hi = 1, cap
    while lo < hi:
        mid = (lo + hi) // 2
        if turns_to_reach(distance, mid, max_speed) <= max_arrival_turns:
            hi = mid
        else:
            lo = mid + 1
    return lo


def segment_intersects_circle(ax, ay, bx, by, cx, cy, radius):
    dx = bx - ax
    dy = by - ay
    length_sq = dx * dx + dy * dy

    if length_sq == 0:
        return distance_xy(ax, ay, cx, cy) <= radius

    t = ((cx - ax) * dx + (cy - ay) * dy) / length_sq
    t = min(1.0, max(0.0, t))
    closest_x = ax + t * dx
    closest_y = ay + t * dy
    return distance_xy(closest_x, closest_y, cx, cy) <= radius


def shot_hits_sun(source, target, sun_x=50.0, sun_y=50.0, sun_radius=10.0):
    return segment_intersects_circle(
        source[0],
        source[1],
        target[0],
        target[1],
        sun_x,
        sun_y,
        sun_radius,
    )

def predict_position(r, theta0, omega, t, cx=50, cy=50):
    theta = theta0 + omega * t
    x = cx + r * math.cos(theta)
    y = cy + r * math.sin(theta)
    return x, y

def is_orbiting(planet):
    return (math.sqrt((planet.x - 50)**2 + (planet.y-50)**2) + planet.radius < 50)


def required_reserve(step, planet):
    if step < 50:
        return max(3, planet.production)
    elif step < 150:
        return max(5, planet.production)
    else:
        return 5