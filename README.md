fleet_speed = 1 + (maxSpeed - 1) * log(ships / log(1000)) ^ 1.5

Agent returns list of {from_planet_id, direction_angle, num_ships}

PLAN:
1. Look at trajectory of your fleets
    - If your fleets currently are going to a planet, calculate whether enemy has sent more fleets and if you should send more --> then send more (if you stay within 3/4 bounds of yours)

3. Deciding on taking which planets to take
    - Calculate when a sent fleet will meet them
        - If fleet passes through Sun, do not include
    - If planet's current number + enemy fleets being sent to them is higher than 3/4 of your production, do not include
    - If planet has low production rate, do not include
    - If high production / less distance, put higher in value

2. Send fleets to apt (high-value) neutral planets / enemy planets
