import numpy as np
from scipy.spatial import KDTree
from typing import List, Tuple, Optional, Union, Iterable

class NearestNodeFinder:
    def __init__(self, points: Union[np.ndarray, List[List[float]]]):
        """Build a KDTree over (N, 2) [lat, lon] points."""
        self.points: np.ndarray = np.array(points)
        self.tree: KDTree = KDTree(self.points)
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
        """Return the index of the nearest active node to query_point."""
        N: int = len(self.points)
        k: int = min(initial_k, N)

        while k <= N:
            _, indices = self.tree.query(query_point, k=k)

            if k == 1:
                indices = np.array([indices])

            for idx in indices:
                if self.active_mask[idx]:
                    return idx

            if k == N:
                break
            k = min(k * 2, N)

        raise ValueError("No active node found for the given query point")