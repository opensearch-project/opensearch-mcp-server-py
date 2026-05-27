# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import logging
import math
from typing import Dict, List, Set

from .hierarchical_agglomerative_clustering import (
    ClusterNode,
    HierarchicalAgglomerativeClustering,
    LinkageMethod,
    calculate_cosine_similarity,
)

logger = logging.getLogger(__name__)


class ClusteringHelper:
    def __init__(self, log_vectors_clustering_threshold: float):
        if log_vectors_clustering_threshold < 0.0 or log_vectors_clustering_threshold > 1.0:
            raise ValueError(
                f'Clustering threshold must be between 0.0 and 1.0, got: {log_vectors_clustering_threshold}'
            )
        self.log_vectors_clustering_threshold = log_vectors_clustering_threshold

    def cluster_log_vectors_and_get_representative(
        self, log_vectors: Dict[str, List[float]]
    ) -> List[str]:
        if not log_vectors:
            return []

        self._validate_log_vectors(log_vectors)
        logger.debug(f'Starting two-phase clustering for {len(log_vectors)} log vectors')

        keys = list(log_vectors.keys())
        vectors = [log_vectors[k] for k in keys]
        index_trace_id_map = {i: keys[i] for i in range(len(keys))}

        # Choose clustering approach based on dataset size
        if len(log_vectors) > 1000:
            final_centroids = self._process_two_phase_clustering_for_large_dataset(
                vectors, index_trace_id_map
            )
        else:
            final_centroids = self._perform_clustering(vectors, index_trace_id_map)

        logger.debug(
            f'Clustering completed: {len(log_vectors)} input -> {len(final_centroids)} representatives'
        )
        return final_centroids

    def _validate_log_vectors(self, log_vectors: Dict[str, List[float]]):
        vector_dimension = -1
        for trace_id, vector in log_vectors.items():
            if not trace_id:
                raise ValueError('Trace ID cannot be null or empty')
            if vector is None:
                raise ValueError(f"Vector for trace ID '{trace_id}' is null")
            if len(vector) == 0:
                raise ValueError(f"Vector for trace ID '{trace_id}' is empty")
            if vector_dimension == -1:
                vector_dimension = len(vector)
            elif len(vector) != vector_dimension:
                raise ValueError(
                    f'Vector dimension mismatch: expected {vector_dimension} '
                    f"but got {len(vector)} for trace ID '{trace_id}'"
                )
            for i in range(len(vector)):
                if math.isnan(vector[i]) or math.isinf(vector[i]):
                    raise ValueError(
                        f"Vector for trace ID '{trace_id}' contains invalid value at index {i}: {vector[i]}"
                    )

    def _process_two_phase_clustering_for_large_dataset(
        self, vectors: List[List[float]], index_trace_id_map: Dict[int, str]
    ) -> List[str]:
        logger.debug(f'Large dataset ({len(vectors)}), applying K-means pre-clustering')
        target_cluster_size = 500
        num_k_means_clusters = (len(vectors) + target_cluster_size - 1) // target_cluster_size

        try:
            k_means_clusters = self._perform_kmeans_clustering(vectors, num_k_means_clusters)
            final_centroids = []
            for cluster_idx, k_means_cluster in enumerate(k_means_clusters):
                cluster_centroids = self._process_cluster(
                    k_means_cluster, vectors, index_trace_id_map, cluster_idx
                )
                final_centroids.extend(cluster_centroids)
            return final_centroids
        except Exception as e:
            logger.warning(
                f'K-means failed, falling back to hierarchical clustering: {e}'
            )
            return self._perform_clustering(vectors, index_trace_id_map)

    def _perform_kmeans_clustering(
        self, vectors: List[List[float]], num_clusters: int
    ) -> List[List[int]]:
        """Simple K-means++ clustering implementation."""
        import random

        if not vectors:
            return []

        num_clusters = max(1, min(num_clusters, len(vectors)))
        n = len(vectors)
        dim = len(vectors[0])

        # K-means++ initialization
        centroids = []
        first_idx = random.randint(0, n - 1)
        centroids.append(list(vectors[first_idx]))

        for _ in range(1, num_clusters):
            distances = []
            for v in vectors:
                min_dist = min(
                    1.0 - calculate_cosine_similarity(v, c) for c in centroids
                )
                distances.append(min_dist * min_dist)
            total = sum(distances)
            if total == 0:
                break
            r = random.random() * total
            cumulative = 0.0
            chosen = 0
            for idx, d in enumerate(distances):
                cumulative += d
                if cumulative >= r:
                    chosen = idx
                    break
            centroids.append(list(vectors[chosen]))

        # K-means iterations
        assignments = [0] * n
        for _ in range(300):
            # Assign
            changed = False
            for i in range(n):
                best_cluster = 0
                best_sim = -1.0
                for c_idx, centroid in enumerate(centroids):
                    sim = calculate_cosine_similarity(vectors[i], centroid)
                    if sim > best_sim:
                        best_sim = sim
                        best_cluster = c_idx
                if assignments[i] != best_cluster:
                    changed = True
                    assignments[i] = best_cluster

            if not changed:
                break

            # Update centroids
            for c_idx in range(len(centroids)):
                members = [i for i in range(n) if assignments[i] == c_idx]
                if members:
                    new_centroid = [0.0] * dim
                    for m in members:
                        for d in range(dim):
                            new_centroid[d] += vectors[m][d]
                    for d in range(dim):
                        new_centroid[d] /= len(members)
                    centroids[c_idx] = new_centroid

        # Build cluster index lists
        result: List[List[int]] = [[] for _ in range(len(centroids))]
        for i in range(n):
            result[assignments[i]].append(i)
        return [c for c in result if c]

    def _process_cluster(
        self,
        k_means_cluster: List[int],
        vectors: List[List[float]],
        index_trace_id_map: Dict[int, str],
        cluster_idx: int,
    ) -> List[str]:
        if not k_means_cluster:
            return []
        if len(k_means_cluster) == 1:
            return [index_trace_id_map[k_means_cluster[0]]]
        if len(k_means_cluster) > 500:
            return self._perform_hierarchical_clustering_of_partition(
                k_means_cluster, vectors, index_trace_id_map
            )

        cluster_vectors = [vectors[i] for i in k_means_cluster]
        cluster_index_map = {j: index_trace_id_map[k_means_cluster[j]] for j in range(len(k_means_cluster))}
        return self._perform_clustering(cluster_vectors, cluster_index_map)

    def _perform_clustering(
        self, vectors: List[List[float]], index_trace_id_map: Dict[int, str]
    ) -> List[str]:
        if not vectors:
            return []
        if len(vectors) == 1:
            return [index_trace_id_map[0]]

        try:
            hac = HierarchicalAgglomerativeClustering(vectors)
            clusters = hac.fit(LinkageMethod.COMPLETE, self.log_vectors_clustering_threshold)
            centroids = []
            for cluster in clusters:
                centroid_index = hac.get_cluster_centroid(cluster)
                centroids.append(index_trace_id_map[centroid_index])
            return centroids
        except Exception as e:
            logger.error(f'Hierarchical clustering failed: {e}')
            return [index_trace_id_map[0]]

    def _perform_hierarchical_clustering_of_partition(
        self,
        k_means_cluster: List[int],
        vectors: List[List[float]],
        index_trace_id_map: Dict[int, str],
    ) -> List[str]:
        partition_size = 500
        partitions = [
            k_means_cluster[i : i + partition_size]
            for i in range(0, len(k_means_cluster), partition_size)
        ]

        vector_res: List[List[float]] = []
        index2_trace: Dict[int, str] = {}

        for part_list in partitions:
            cluster_vectors = [vectors[i] for i in part_list]
            cluster_index_map = {
                j: index_trace_id_map[part_list[j]] for j in range(len(part_list))
            }
            self._process_partition(cluster_vectors, cluster_index_map, vector_res, index2_trace)

        return self._remove_similar_vectors(vector_res, index2_trace)

    def _process_partition(
        self,
        cluster_vectors: List[List[float]],
        cluster_index_map: Dict[int, str],
        vector_res: List[List[float]],
        index2_trace: Dict[int, str],
    ):
        if not cluster_vectors:
            return
        if len(cluster_vectors) == 1:
            vector_res.append(cluster_vectors[0])
            index2_trace[len(vector_res) - 1] = cluster_index_map[0]
            return

        try:
            hac = HierarchicalAgglomerativeClustering(cluster_vectors)
            clusters = hac.fit(LinkageMethod.COMPLETE, self.log_vectors_clustering_threshold)
            for cluster in clusters:
                centroid_index = hac.get_cluster_centroid(cluster)
                vector_res.append(cluster_vectors[centroid_index])
                index2_trace[len(vector_res) - 1] = cluster_index_map[centroid_index]
        except Exception as e:
            logger.error(f'Hierarchical clustering failed: {e}')
            vector_res.append(cluster_vectors[0])
            index2_trace[len(vector_res) - 1] = cluster_index_map[0]

    def _remove_similar_vectors(
        self, vector_res: List[List[float]], index2_trace: Dict[int, str]
    ) -> List[str]:
        to_remove: Set[int] = set()

        for i in range(len(vector_res)):
            if i in to_remove:
                continue
            for j in range(i + 1, len(vector_res)):
                if j in to_remove:
                    continue
                similarity = calculate_cosine_similarity(vector_res[i], vector_res[j])
                if similarity > self.log_vectors_clustering_threshold:
                    to_remove.add(j)

        return [
            index2_trace[i] for i in range(len(vector_res)) if i not in to_remove
        ]
