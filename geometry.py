import math

def distance(planet1, planet2):
    x_distance = (planet1[2] - planet2[2])**2
    y_distance = (planet1[3] - planet2[3])**2
    return math.sqrt(x_distance + y_distance)

def angle_to(source, target):
    dy = source[3] - target[3]
    dx = source[2] - target[2]
    return atan2(dy / dx)

def fleet_speed(ships, max_speed=6.0):
    ships = max(1,ships)
    return 1.0 + ((maxSpeed - 1.0) * math.log(ships / math.log(1000)))**1.5

def turns_to_reach():
    speed = fleet_speed(ships)
    return math.ceil(distance_value / speed)

def segment_intersects_circle(start, end, center, radius): # center is pair
    startX, startY = (start[2], start[3])
    endX, endY = (end[2], end[3])
    centerX, centerY = (center[0], center[1])
    
    dx = endX - startX
    dy = endY - startY
    
    fx = startX - centerX
    fy = startY - centerY
    
    a = dx * dx + dy * dy
    b = 2 * (fx * dx + fy * dy)
    c = (fx * fx + fy * fy) - radius * radius
    
    discriminant = b * b - 4 * a * c
    
    if discriminant < 0:
        return False

    discriminant = math.sqrt(discriminant)
    
    t1 = (-b - discriminant) / (2 * a)
    t2 = (-b + discriminant) / (2 * a)

    return (0 <= t1 <= 1) or (0 <= t2 <= 1)

def shot_hits_sun(source, target, sun_center=(0, 0), sun_radius=10):
    return segment_intersects_circle(
        source,
        target,
        sun_center,
        sun_radius
    )

def is_orbiting(planet):
    orbital_radius = math.sqrt((planet[2] - 50)**2 + (planet[3] - 50)**2)
    planet_radius = planet[4]
    if (orbital_radius + planet_radius < 50):
        return true
    else:
        return false

def predict_orbit_position(initial_planet, angular_velocity, turns):
    cx, cy = (50,50)

    dx = initial_planet[2] - cx
    dy = initial_planet[3] - cy

    radius = math.hypot(dx, dy)

    initial_angle = math.atan2(dy, dx)

    future_angle = initial_angle + angular_velocity * turns

    future_x = cx + radius * math.cos(future_angle)
    future_y = cy + radius * math.sin(future_angle)

    return (future_x, future_y)