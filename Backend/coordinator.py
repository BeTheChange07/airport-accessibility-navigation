#main only communicates with coordinator
#main handles session management and everything async, passes sessions to coordinator

import Backend.mapping.mapping as mapping, database, main

INFRASTRUCTURE_TABLE_NAME = "infrastructure"
NAVMESH_NODE_TABLE_NAME = "navmeshNodes"
NAVMESH_EDGE_TABLE_NAME = "navmeshEdges"
AMENITY_TABLE_NAME = "amenities"

def start():
    database.connect()
    mapping.populateNavmeshNodes(database.fetchEntireTable(NAVMESH_NODE_TABLE_NAME))
    mapping.populateNavmeshEdges(database.fetchEntireTable(NAVMESH_EDGE_TABLE_NAME))
    mapping.populateAmenities(database.fetchEntireTable(AMENITY_TABLE_NAME))

def stop():
    database.disconnect()

def handle_get(data) -> str: #Receives and returns json object, not string 
    return mapping.navigate(data)

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