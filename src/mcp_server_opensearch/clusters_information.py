# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import logging
import os
import yaml
from pydantic import BaseModel
from typing import Dict, Optional


class ClusterInfo(BaseModel):
    """Model representing OpenSearch cluster configuration."""

    opensearch_url: str
    iam_arn: Optional[str] = None
    aws_region: Optional[str] = None
    opensearch_username: Optional[str] = None
    opensearch_password: Optional[str] = None
    profile: Optional[str] = None
    is_serverless: Optional[bool] = None
    timeout: Optional[int] = None
    opensearch_no_auth: Optional[bool] = None
    ssl_verify: Optional[bool] = None
    opensearch_header_auth: Optional[bool] = None
    opensearch_ca_cert_path: Optional[str] = None
    opensearch_client_cert_path: Optional[str] = None
    opensearch_client_key_path: Optional[str] = None
    max_response_size: Optional[int] = None


# Global dictionary to store cluster information
# Key: string name (cluster identifier)
# Value: ClusterInfo object containing cluster configuration
cluster_registry: Dict[str, ClusterInfo] = {}


def add_cluster(name: str, cluster_info: ClusterInfo) -> None:
    """Add a cluster configuration to the global registry.

    Args:
        name: String identifier for the cluster
        cluster_info: ClusterInfo object containing cluster configuration
    """
    cluster_registry[name] = cluster_info


def get_cluster(name: str) -> Optional[ClusterInfo]:
    """Retrieve cluster configuration by name.

    Args:
        name: String identifier for the cluster

    Returns:
        ClusterInfo: Cluster configuration or None if not found
    """
    return cluster_registry.get(name)


async def load_clusters_from_yaml(file_path: str) -> None:
    """Load cluster configurations from a YAML file and populate the global registry.

    Args:
        file_path: Path to the YAML configuration file

    Raises:
        FileNotFoundError: If the YAML file doesn't exist
        PermissionError: If the file cannot be read due to permissions
        yaml.YAMLError: If the YAML file is malformed
        UnicodeDecodeError: If the file has encoding issues
        OSError: For other file system related errors
    """
    if not file_path:
        return

    # Check if file exists
    if not os.path.exists(file_path):
        raise FileNotFoundError(f'YAML file not found: {file_path}')

    result = {'loaded_clusters': [], 'errors': [], 'total_clusters': 0}

    try:
        # Try to open and read the file with proper error handling
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)
        except PermissionError as e:
            raise PermissionError(f'Permission denied reading YAML file {file_path}: {str(e)}')
        except UnicodeDecodeError as e:
            raise UnicodeDecodeError(
                e.encoding,
                e.object,
                e.start,
                e.end,
                f'Encoding error reading YAML file {file_path}: {str(e)}',
            )
        except OSError as e:
            raise OSError(f'OS error reading YAML file {file_path}: {str(e)}')

        # Process clusters
        clusters = config.get('clusters', {})
        result['total_clusters'] = len(clusters)
        logging.info(f'Total clusters found in config file: {result["total_clusters"]}')

        for cluster_name, cluster_config in clusters.items():
            try:
                # Validate required fields
                if 'opensearch_url' not in cluster_config:
                    result['errors'].append(f'Missing opensearch_url for cluster: {cluster_name}')
                    continue
                cluster_info = ClusterInfo(
                    opensearch_url=cluster_config['opensearch_url'],
                    iam_arn=cluster_config.get('iam_arn', None),
                    aws_region=cluster_config.get('aws_region', None),
                    opensearch_username=cluster_config.get('opensearch_username', None),
                    opensearch_password=cluster_config.get('opensearch_password', None),
                    profile=cluster_config.get('profile', None),
                    is_serverless=cluster_config.get('is_serverless', None),
                    timeout=cluster_config.get('timeout', None),
                    opensearch_no_auth=cluster_config.get('opensearch_no_auth', None),
                    ssl_verify=cluster_config.get('ssl_verify', None),
                    opensearch_header_auth=cluster_config.get('opensearch_header_auth', None),
                    opensearch_ca_cert_path=cluster_config.get('opensearch_ca_cert_path', None),
                    opensearch_client_cert_path=cluster_config.get(
                        'opensearch_client_cert_path', None
                    ),
                    opensearch_client_key_path=cluster_config.get(
                        'opensearch_client_key_path', None
                    ),
                    max_response_size=cluster_config.get('max_response_size', None),
                )

                # Add cluster to registry without checking connection
                add_cluster(name=cluster_name, cluster_info=cluster_info)
                result['loaded_clusters'].append(cluster_name)

            except Exception as e:
                result['errors'].append(f"Error processing cluster '{cluster_name}': {str(e)}")

        result['loaded_clusters'] = list(cluster_registry.keys())
        if result['errors']:
            logging.error(f'Loading errors: {result["errors"]}')

        logging.info(f'Loaded clusters: {result["loaded_clusters"]}')
        return

    except yaml.YAMLError as e:
        raise yaml.YAMLError(f'Invalid YAML format in {file_path}: {str(e)}')
