from math import atan2

def all_in(obs, config):
    planets = obs["planets"]
    playerID = obs["player"]
    
    myPlanet = None
    
    # obtain list of neutral planets
    neutralPlanets = []
    
    for currPlanet in planets:
        currPlanetID = currPlanet[1]
        
        if (currPlanetID == -1):
            neutralPlanets.append(currPlanet)
        elif (currPlanetID == playerID):
            myPlanet = currPlanet
            
    # Safety Check
    if (myPlanet is None or len(neutralPlanets) == 0):
        return []
           
    target = neutralPlanets[0]
    
    for currNeutralPlanet in neutralPlanets:
        if (currNeutralPlanet[4] > target[4] and currNeutralPlanet[5] < myPlanet[5]):
            target = currNeutralPlanet
    
    direction_angle = angle_finder(myPlanet, target)
    
    shipsToSend = target[5] + 1
    
    return [[myPlanet[0], direction_angle, shipsToSend]]