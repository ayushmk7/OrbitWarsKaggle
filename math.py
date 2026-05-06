import math

# finds radius of planet
def radius_finder(production):
    return (1 + math.log(production))

# returns angle given positions of current and target
def trivial_angle_finder_helper(x_target, y_target, x_current, y_current):
    return (math.atan2(y_target - y_current) / (x_target - x_current))

# returns valid range of angles fleets can be sent without Sun crash
def valid_launch_angles_finder_helper(planet):
    angle_to_center = trivial_angle_finder_helper(50, 50, planet[2], planet[3])
    deviation_angle = math.asin2(10, planet[4])
    return {angle_to_center - deviation_angle, angle_to_center + deviation_angle}

# does binary search on a rotating planet to find angle to launch at
    # 1. Starting point (t = 0) has 
    # 2. Ending point (t = k) has 
    # 3. Loop through each midpoint angle
        # i. Find time for fleet to reach midpoint
        # ii. Find time for planet to reach midpoint
        # iii. If same, return this time. Else, do binary search
def estimation_angle_finder_helper(planet_from, planet_to, angular_velocity):
    

# returns angle fleet should be launched at, returns None if Sun crash
def angle_finder(planet_from, planet_to, angular_velocity):
    angle_to_target = trivial_angle_finder_helper(planet_to[2], planet_to[3], planet_from[2], planet_from[3])
    {lower, higher} = valid_launch_angles_finder_helper(planet_from)
    
    # planet_to is static
    if (planet_to[4] + radius_finder(planet_to[6]) >= 50):
        if (lower <= angle_to_target && angle_to_target <= higher):
            return angle_to_target
        else:
            return None
        
    else:
                
        
    
