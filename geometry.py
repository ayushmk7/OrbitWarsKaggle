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