# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import math
from typing import List, Optional


class ClusterNode:
    def __init__(self, node_id: int, samples: List[int]):
        self.id = node_id
        self.samples = list(samples)
        self.size = len(self.samples)

    @classmethod
    def leaf(cls, node_id: int, sample: int) -> 'ClusterNode':
        return cls(node_id, [sample])

    @classmethod
    def merge(cls, node_id: int, left: 'ClusterNode', right: 'ClusterNode') -> 'ClusterNode':
        return cls(node_id, left.samples + right.samples)


class LinkageMethod:
    SINGLE = 'single'
    COMPLETE = 'complete'
    AVERAGE = 'average'


def calculate_cosine_similarity(a: List[float], b: List[float]) -> float:
    dot_product = 0.0
    norm_a = 0.0
    norm_b = 0.0

    for i in range(len(a)):
        dot_product += a[i] * b[i]
        norm_a += a[i] * a[i]
        norm_b += b[i] * b[i]

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (math.sqrt(norm_a) * math.sqrt(norm_b))


class HierarchicalAgglomerativeClustering:
    def __init__(self, data: List[List[float]]):
        self.data = data
        self.n_samples = len(data)
        self.n_features = len(data[0]) if data else 0
        self.distance_matrix = [[0.0] * self.n_samples for _ in range(self.n_samples)]
        self._compute_cosine_distance_matrix()

    def _compute_cosine_distance_matrix(self):
        norms = [0.0] * self.n_samples
        for i in range(self.n_samples):
            norm = 0.0
            for j in range(self.n_features):
                norm += self.data[i][j] * self.data[i][j]
            norms[i] = math.sqrt(norm)

        for i in range(self.n_samples):
            for j in range(i + 1, self.n_samples):
                similarity = self._cosine_similarity_with_norms(
                    self.data[i], self.data[j], norms[i], norms[j]
                )
                distance = 1.0 - similarity
                self.distance_matrix[i][j] = distance
                self.distance_matrix[j][i] = distance

    @staticmethod
    def _cosine_similarity_with_norms(
        a: List[float], b: List[float], norm_a: float, norm_b: float
    ) -> float:
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        dot_product = sum(a[i] * b[i] for i in range(len(a)))
        return dot_product / (norm_a * norm_b)

    def fit(self, linkage: str, threshold: float) -> List[ClusterNode]:
        if threshold < 0:
            raise ValueError('Distance threshold must be non-negative')

        active_clusters: List[ClusterNode] = []
        for i in range(self.n_samples):
            active_clusters.append(ClusterNode.leaf(i, i))

        next_cluster_id = self.n_samples

        while len(active_clusters) > 1:
            closest_pair = self._find_closest_clusters(active_clusters, linkage, threshold)
            if closest_pair is None:
                break

            i, j = closest_pair
            new_cluster = ClusterNode.merge(
                next_cluster_id, active_clusters[i], active_clusters[j]
            )
            next_cluster_id += 1

            # Remove in reverse order to preserve indices
            active_clusters.pop(max(i, j))
            active_clusters.pop(min(i, j))
            active_clusters.append(new_cluster)

        return active_clusters

    def _find_closest_clusters(
        self, clusters: List[ClusterNode], linkage: str, threshold: float
    ) -> Optional[tuple]:
        min_distance = threshold
        best_i, best_j = -1, -1

        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                distance = self._compute_cluster_distance(clusters[i], clusters[j], linkage)
                if distance < min_distance:
                    min_distance = distance
                    best_i, best_j = i, j

        return (best_i, best_j) if best_i != -1 else None

    def _compute_cluster_distance(
        self, c1: ClusterNode, c2: ClusterNode, linkage: str
    ) -> float:
        if linkage == LinkageMethod.SINGLE:
            return self._single_linkage(c1, c2)
        elif linkage == LinkageMethod.COMPLETE:
            return self._complete_linkage(c1, c2)
        elif linkage == LinkageMethod.AVERAGE:
            return self._average_linkage(c1, c2)
        raise ValueError(f'Unknown linkage method: {linkage}')

    def _single_linkage(self, c1: ClusterNode, c2: ClusterNode) -> float:
        min_dist = float('inf')
        for i in c1.samples:
            for j in c2.samples:
                dist = self.distance_matrix[i][j]
                if dist < min_dist:
                    min_dist = dist
                    if min_dist < 1e-10:
                        return min_dist
        return min_dist

    def _complete_linkage(self, c1: ClusterNode, c2: ClusterNode) -> float:
        max_dist = float('-inf')
        for i in c1.samples:
            for j in c2.samples:
                dist = self.distance_matrix[i][j]
                if dist > max_dist:
                    max_dist = dist
        return max_dist

    def _average_linkage(self, c1: ClusterNode, c2: ClusterNode) -> float:
        sum_dist = 0.0
        count = 0
        for i in c1.samples:
            for j in c2.samples:
                sum_dist += self.distance_matrix[i][j]
                count += 1
        return sum_dist / count if count > 0 else 0.0

    def get_cluster_centroid(self, cluster: ClusterNode) -> int:
        if len(cluster.samples) == 1:
            return cluster.samples[0]

        medoid_index = cluster.samples[0]
        min_total_distance = float('inf')

        for point_i in cluster.samples:
            total_distance = sum(
                self.distance_matrix[point_i][point_j] for point_j in cluster.samples
            )
            if total_distance < min_total_distance:
                min_total_distance = total_distance
                medoid_index = point_i

        return medoid_index
