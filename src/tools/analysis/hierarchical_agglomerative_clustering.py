# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from typing import List


class ClusterNode:
    """A node in the hierarchical clustering tree."""

    def __init__(self, node_id: int, samples: List[int]):
        """Initialize with node ID and sample indices."""
        self.id = node_id
        self.samples = list(samples)
        self.size = len(self.samples)

    @classmethod
    def leaf(cls, node_id: int, sample: int) -> 'ClusterNode':
        """Create a leaf node with a single sample."""
        return cls(node_id, [sample])


class LinkageMethod:
    """Constants for linkage methods passed to scipy's linkage()."""

    SINGLE = 'single'
    COMPLETE = 'complete'
    AVERAGE = 'average'


class HierarchicalAgglomerativeClustering:
    """Agglomerative clustering using a precomputed cosine distance matrix."""

    def __init__(self, data: List[List[float]]):
        """Initialize with data vectors and precompute distance matrix."""
        self.n_samples = len(data)
        self.n_features = len(data[0]) if data else 0
        self._data_matrix = np.asarray(data, dtype=np.float64)
        self.distance_matrix = self._compute_cosine_distance_matrix()

    def _compute_cosine_distance_matrix(self) -> np.ndarray:
        """Compute pairwise cosine distance matrix using vectorized operations."""
        norms = np.linalg.norm(self._data_matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        normalized = self._data_matrix / norms
        with np.errstate(invalid='ignore', divide='ignore', over='ignore'):
            similarity = np.nan_to_num(normalized @ normalized.T, nan=0.0)
        np.clip(similarity, -1.0, 1.0, out=similarity)
        distance = 1.0 - similarity
        np.fill_diagonal(distance, 0.0)
        return distance

    def fit(self, linkage_method: str, threshold: float) -> List[ClusterNode]:
        """Run clustering until no pair is closer than threshold."""
        if threshold < 0:
            raise ValueError('Distance threshold must be non-negative')

        if self.n_samples == 1:
            return [ClusterNode.leaf(0, 0)]

        condensed = squareform(self.distance_matrix, checks=False)
        Z = linkage(condensed, method=linkage_method)
        labels = fcluster(Z, t=threshold, criterion='distance')

        clusters_map: dict = {}
        for sample_idx, label in enumerate(labels):
            clusters_map.setdefault(label, []).append(sample_idx)

        clusters = []
        for node_id, (_, samples) in enumerate(sorted(clusters_map.items())):
            clusters.append(ClusterNode(node_id, samples))
        return clusters

    def get_cluster_centroid(self, cluster: ClusterNode) -> int:
        """Return the medoid index of the cluster."""
        if len(cluster.samples) == 1:
            return cluster.samples[0]

        samples = cluster.samples
        sub_matrix = self.distance_matrix[np.ix_(samples, samples)]
        total_distances = sub_matrix.sum(axis=1)
        medoid_local = int(np.argmin(total_distances))
        return samples[medoid_local]
