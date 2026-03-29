from typing import Any #Why is this needed but not import dict

from main import getSession

#Initial setup methods

def populateNavmeshNodes(nodes: list[dict[str, Any]]): #Passed as json TODO
    # Make sure to also populate infrastructure dictionary and structure (quadtree? kt-tree?) for finding nearest node to a coordinate
    pass

def populateNavmeshEdges(edges: list[dict[str, Any]]): #Passed as json TODO
    pass

def populateAmenities(amenities: list[dict[str, Any]]): #Passed as json TODO
    pass

#Update methods, to be copied from coordinator

def updateAmenity(status: dict[str, Any]): #TODO
    pass

def updateInfrastructure(status: dict[str, Any]): #TODO
    pass

#Query methods

def navigate(request: dict[str, Any]) -> dict[str, Any]: #Passed as json, returns json, TODO
    pass