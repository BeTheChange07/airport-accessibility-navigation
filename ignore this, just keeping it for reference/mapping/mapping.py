from typing import Any #Why is this needed but not import dict

from main import getSession
from NearestNodeFinder import NearestNodeFinder

#nav_nodes



#GPS to node global vars
NearestNodeFinderInstance = None
nearestNodeIndexToNodeID: dict[int, int] = {} #Not going to assume nodeIDs are 0 to N-1, so need mapping from index in NearestNodeFinder's points array

#Node to node global vars
navigationGraph = None
amenities = None
infrastructure = None

#Initial setup methods

def _getAmenityNodeIDs(amenities: list[dict[str, Any]]) -> set[int]:
    #amenities table has:
    #ID: int
    #nodeID: int
    #name: str
    #type: str
    #wheelChairAcessible: bool
    #status: str
    #crowdLevel: int
    return set(amenity["nodeID"] for amenity in amenities)

def populateNavmeshNodes(nodes: list[dict[str, Any]], amenities: list[dict[str, Any]]): #Passed as json TODO
    destinationNodes = _getAmenityNodeIDs(amenities)
    #id: integer
    #latitude: double precision
    #longitude: double precision
    
    #fuck it, worry about infrastructure id to nodeID mapping and node masking later
    
    
    
    
    
    # Make sure to also populate infrastructure dictionary and structure (quadtree? kt-tree?) for finding nearest node to a coordinate
    
    
    
    #Once you have the points as numpy arrays rather than json:
    #global NearestNodeFinderInstance
    #NearestNodeFinderInstance = NearestNodeFinder(coordinates)
    #NearestNodeFinderInstance.set_active_mask(activeMask)
    pass

def populateNavmeshEdges(edges: list[dict[str, Any]]): #Passed as json TODO
    pass

#Update methods, to be copied from coordinator

def updateAmenity(status: dict[str, Any]): #TODO
    pass

def updateInfrastructure(status: dict[str, Any]): #TODO
    pass

#Query methods

def navigate(request: dict[str, Any]) -> dict[str, Any]: #Passed as json, returns json, TODO
    pass