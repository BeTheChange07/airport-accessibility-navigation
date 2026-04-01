#main only communicates with coordinator
#main handles session management and everything async

import Backend.mapping.mapping as mapping, database, main, env

def start():
    env.load()
    mapping.populateNavmeshNodes(database.fetchEntireTable(env.NAVMESH_NODE_TABLE_NAME), database.fetchEntireTable(env.AMENITY_TABLE_NAME))
    mapping.populateNavmeshEdges(database.fetchEntireTable(env.NAVMESH_EDGE_TABLE_NAME))

def stop():
    database.disconnect()

def handle_get(data) -> str: #Receives and returns json object, not string 
    navigationData = mapping.navigate(data)
    amenityData = database.fetchEntireTable(env.AMENITY_TABLE_NAME)
    amenityUnitsData = database.fetchEntireTable(env.AMENITY_UNIT_TABLE_NAME)
    
    return {"navigationData": navigationData, "amenityData": amenityData, "amenityUnitsData": amenityUnitsData}

def handle_patch(data): #Receives and returns json object, not string
    if "updateType" not in data:
        return
    if data["updateType"] == "amenity":
        try:
            database.updateAmenity(data["data"])
            mapping.updateAmenity(data["data"])
        except Exception as e:
            return {"status": "error", "message": f"Failed to update amenity: {str(e)}"}
        return {"status": "success", "message": "Amenity updated successfully"}
    else:
        try:
            database.updateInfrastructure(data["data"])
            mapping.updateInfrastructure(data["data"])
        except Exception as e:
            return {"status": "error", "message": f"Failed to update infrastructure: {str(e)}"}
        return {"status": "success", "message": "Infrastructure updated successfully"}    