import numpy as np
from scipy.spatial import KDTree
from typing import List, Tuple, Optional, Union, Iterable

class NearestNodeFinder:
    def __init__(self, points: Union[np.ndarray, List[List[float]]]):
        """
        Initialize the nearest node finder.

        Args:
            points (np.ndarray or list of list of float): Array of shape (N, 2) with [lat, lon] coordinates.
        """
        self.points: np.ndarray = np.array(points)
        self.tree: KDTree = KDTree(self.points)
        # Initially all nodes are active
        self.active_mask: np.ndarray = np.ones(len(points), dtype=bool)

    def deactivate_nodes(self, indices: Iterable[int]) -> None:
        """Mark nodes as inactive. Accepts list, numpy array, or any iterable of indexes."""
        indices_arr = np.asarray(indices)
        self.active_mask[indices_arr] = False

    def activate_nodes(self, indices: Iterable[int]) -> None:
        """Mark nodes as active. Accepts list, numpy array, or any iterable of indexes."""
        indices_arr = np.asarray(indices)
        self.active_mask[indices_arr] = True

    def set_active_mask(self, mask: Union[np.ndarray, List[bool], Iterable[bool]]) -> None:
        """Set the active mask directly (boolean array of length N)."""
        mask_arr = np.asarray(mask, dtype=bool)
        if len(mask_arr) != len(self.points):
            raise ValueError("Mask length must match number of points")
        self.active_mask = mask_arr


    def get_nearest_active_node(
        self, query_point: Union[List[float], np.ndarray], initial_k: int = 10) -> int:
        """
        Find the nearest active node to the query_point, automatically increasing k if necessary.

        Args:
            query_point (list or np.ndarray): [lat, lon] of the query.
            initial_k (int): Starting number of nearest neighbors to query.

        Returns:
            int: index of nearest active node
        """
        N: int = len(self.points)
        k: int = min(initial_k, N)

        while k <= N:
            _, indices = self.tree.query(query_point, k=k)

            # Ensure arrays even if k=1
            if k == 1:
                indices = np.array([indices])

            for idx in indices:
                if self.active_mask[idx]:
                    return idx

            # Increase k for next iteration
            if k == N:
                break
            k = min(k * 2, N)  # Double k but do not exceed N

        # No active node found
        raise ValueError("No active node found for the given query point")


#    def nearest_active_node(
#        self, query_point: Union[List[float], np.ndarray], initial_k: int = 10
#    ) -> Tuple[Optional[int], Optional[float]]:
#        """
#        Find the nearest active node to the query_point, automatically increasing k if necessary.
#
#        Args:
#            query_point (list or np.ndarray): [lat, lon] of the query.
#            initial_k (int): Starting number of nearest neighbors to query.
#
#        Returns:
#            Tuple[Optional[int], Optional[float]]: (index of nearest active node, distance)
#            or (None, None) if no active node exists.
#        """
#        N: int = len(self.points)
#        k: int = min(initial_k, N)
#
#        while k <= N:
#            distances, indices = self.tree.query(query_point, k=k)
#
#            # Ensure arrays even if k=1
#            if k == 1:
#                indices = np.array([indices])
#                distances = np.array([distances])
#
#            for dist, idx in zip(distances, indices):
#                if self.active_mask[idx]:
#                    return idx, dist
#
#            # Increase k for next iteration
#            if k == N:
#                break
#            k = min(k * 2, N)  # Double k but do not exceed N
#
#        # No active node found
#        return None, None