import pytest
import tempfile
import os
import yaml
import platform
from unittest.mock import patch, MagicMock, AsyncMock
from mcp_server_opensearch.clusters_information import (
    ClusterInfo,
    add_cluster,
    get_cluster,
    load_clusters_from_yaml,
    cluster_registry,
)


class TestClusterInfo:
    def test_cluster_info_creation_with_required_fields(self):
        """Test creating ClusterInfo with only required fields."""
        cluster = ClusterInfo(opensearch_url='https://localhost:9200')
        assert cluster.opensearch_url == 'https://localhost:9200'
        assert cluster.iam_arn is None
        assert cluster.aws_region is None
        assert cluster.opensearch_username is None
        assert cluster.opensearch_password is None
        assert cluster.profile is None

    def test_cluster_info_creation_with_all_fields(self):
        """Test creating ClusterInfo with all fields."""
        cluster = ClusterInfo(
            opensearch_url='https://localhost:9200',
            iam_arn='arn:aws:iam::123456789012:role/OpenSearchRole',
            aws_region='us-west-2',
            opensearch_username='admin',
            opensearch_password='password123',
            profile='default',
            timeout=30,
            opensearch_no_auth=True,
            opensearch_ca_cert_path='/tmp/ca.pem',
            opensearch_client_cert_path='/tmp/client.pem',
            opensearch_client_key_path='/tmp/client.key',
        )
        assert cluster.opensearch_url == 'https://localhost:9200'
        assert cluster.iam_arn == 'arn:aws:iam::123456789012:role/OpenSearchRole'
        assert cluster.aws_region == 'us-west-2'
        assert cluster.opensearch_username == 'admin'
        assert cluster.opensearch_password == 'password123'
        assert cluster.profile == 'default'
        assert cluster.timeout == 30
        assert cluster.opensearch_no_auth is True
        assert cluster.opensearch_ca_cert_path == '/tmp/ca.pem'
        assert cluster.opensearch_client_cert_path == '/tmp/client.pem'
        assert cluster.opensearch_client_key_path == '/tmp/client.key'

    def test_cluster_info_with_timeout_only(self):
        """Test creating ClusterInfo with timeout parameter."""
        cluster = ClusterInfo(opensearch_url='https://localhost:9200', timeout=60)
        assert cluster.timeout == 60

    def test_cluster_info_with_no_auth_only(self):
        """Test creating ClusterInfo with opensearch_no_auth parameter."""
        cluster = ClusterInfo(opensearch_url='https://localhost:9200', opensearch_no_auth=True)
        assert cluster.opensearch_no_auth is True
        assert cluster.opensearch_url == 'https://localhost:9200'

    def test_cluster_info_no_auth_defaults_to_none(self):
        """Test that opensearch_no_auth defaults to None when not specified."""
        cluster = ClusterInfo(opensearch_url='https://localhost:9200')
        assert cluster.opensearch_no_auth is None

    def test_cluster_info_validation(self):
        """Test that ClusterInfo validates required fields."""
        with pytest.raises(ValueError):
            ClusterInfo()  # Missing required opensearch_url


class TestClusterRegistry:
    def setup_method(self):
        """Clear the cluster registry before each test."""
        cluster_registry.clear()

    def test_add_cluster(self):
        """Test adding a cluster to the registry."""
        cluster = ClusterInfo(opensearch_url='https://localhost:9200')
        add_cluster('test-cluster', cluster)

        assert 'test-cluster' in cluster_registry
        assert cluster_registry['test-cluster'] == cluster

    def test_add_cluster_overwrites_existing(self):
        """Test that adding a cluster with existing name overwrites it."""
        cluster1 = ClusterInfo(opensearch_url='https://localhost:9200')
        cluster2 = ClusterInfo(opensearch_url='https://localhost:9201')

        add_cluster('test-cluster', cluster1)
        add_cluster('test-cluster', cluster2)

        assert cluster_registry['test-cluster'] == cluster2
        assert len(cluster_registry) == 1

    def test_get_cluster_existing(self):
        """Test getting an existing cluster."""
        cluster = ClusterInfo(opensearch_url='https://localhost:9200')
        add_cluster('test-cluster', cluster)

        retrieved = get_cluster('test-cluster')
        assert retrieved == cluster

    def test_get_cluster_nonexistent(self):
        """Test getting a non-existent cluster returns None."""
        retrieved = get_cluster('nonexistent-cluster')
        assert retrieved is None


class TestLoadClustersFromYaml:
    def setup_method(self):
        """Clear the cluster registry before each test."""
        cluster_registry.clear()

    @pytest.mark.asyncio
    async def test_load_clusters_from_yaml_empty_file(self):
        """Test loading from empty YAML file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write('clusters: {}')
            f.flush()

            await load_clusters_from_yaml(f.name)

        os.unlink(f.name)
        assert len(cluster_registry) == 0

    @pytest.mark.asyncio
    async def test_load_clusters_from_yaml_valid_clusters(self):
        """Test loading valid clusters from YAML."""
        yaml_content = """
clusters:
  cluster1:
    opensearch_url: "https://localhost:9200"
    opensearch_username: "admin"
    opensearch_password: "password"
    timeout: 45
    opensearch_ca_cert_path: "/etc/opensearch/ca.pem"
    opensearch_client_cert_path: "/etc/opensearch/tls.crt"
    opensearch_client_key_path: "/etc/opensearch/tls.key"
  cluster2:
    opensearch_url: "https://localhost:9201"
    iam_arn: "arn:aws:iam::123456789012:role/OpenSearchRole"
    aws_region: "us-west-2"
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            await load_clusters_from_yaml(f.name)

        os.unlink(f.name)

        assert len(cluster_registry) == 2
        assert 'cluster1' in cluster_registry
        assert 'cluster2' in cluster_registry

        cluster1 = cluster_registry['cluster1']
        assert cluster1.opensearch_url == 'https://localhost:9200'
        assert cluster1.opensearch_username == 'admin'
        assert cluster1.opensearch_password == 'password'
        assert cluster1.timeout == 45
        assert cluster1.opensearch_ca_cert_path == '/etc/opensearch/ca.pem'
        assert cluster1.opensearch_client_cert_path == '/etc/opensearch/tls.crt'
        assert cluster1.opensearch_client_key_path == '/etc/opensearch/tls.key'

        cluster2 = cluster_registry['cluster2']
        assert cluster2.opensearch_url == 'https://localhost:9201'
        assert cluster2.iam_arn == 'arn:aws:iam::123456789012:role/OpenSearchRole'
        assert cluster2.aws_region == 'us-west-2'
        assert cluster2.timeout is None

    @pytest.mark.asyncio
    async def test_load_clusters_from_yaml_with_no_auth(self):
        """Test loading cluster with opensearch_no_auth from YAML."""
        yaml_content = """
clusters:
  no-auth-cluster:
    opensearch_url: "http://localhost:9200"
    opensearch_no_auth: true
  mixed-cluster:
    opensearch_url: "https://localhost:9201"
    opensearch_username: "admin"
    opensearch_password: "password"
    opensearch_no_auth: false
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            await load_clusters_from_yaml(f.name)

        os.unlink(f.name)

        assert len(cluster_registry) == 2

        # Test no-auth cluster
        no_auth_cluster = cluster_registry['no-auth-cluster']
        assert no_auth_cluster.opensearch_url == 'http://localhost:9200'
        assert no_auth_cluster.opensearch_no_auth is True

        # Test mixed cluster with explicit false
        mixed_cluster = cluster_registry['mixed-cluster']
        assert mixed_cluster.opensearch_url == 'https://localhost:9201'
        assert mixed_cluster.opensearch_username == 'admin'
        assert mixed_cluster.opensearch_password == 'password'
        assert mixed_cluster.opensearch_no_auth is False

    @pytest.mark.asyncio
    async def test_load_clusters_from_yaml_missing_opensearch_url(self):
        """Test loading cluster without required opensearch_url."""
        yaml_content = """
clusters:
  invalid_cluster:
    opensearch_username: "admin"
    opensearch_password: "password"
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            await load_clusters_from_yaml(f.name)

        os.unlink(f.name)

        # Cluster should not be added due to missing opensearch_url
        assert len(cluster_registry) == 0

    @pytest.mark.asyncio
    async def test_load_clusters_from_yaml_without_connection_check(self):
        """Test loading cluster without connection validation."""
        yaml_content = """
clusters:
  unreachable_cluster:
    opensearch_url: "https://unreachable:9200"
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            await load_clusters_from_yaml(f.name)

        os.unlink(f.name)

        # Cluster should be added even if potentially unreachable (no connection check)
        assert len(cluster_registry) == 1
        assert 'unreachable_cluster' in cluster_registry
        assert cluster_registry['unreachable_cluster'].opensearch_url == 'https://unreachable:9200'

    @pytest.mark.asyncio
    async def test_load_clusters_from_yaml_file_not_found(self):
        """Test loading from non-existent file."""
        with pytest.raises(FileNotFoundError):
            await load_clusters_from_yaml('/nonexistent/file.yml')

    @pytest.mark.asyncio
    async def test_load_clusters_from_yaml_invalid_yaml(self):
        """Test loading from invalid YAML file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write('invalid: yaml: content: [')
            f.flush()

            with pytest.raises(yaml.YAMLError):
                await load_clusters_from_yaml(f.name)

        os.unlink(f.name)

    @pytest.mark.asyncio
    async def test_load_clusters_from_yaml_permission_error(self):
        """Test loading from file with permission error."""
        # Skip this test on Windows as os.chmod with 0o000 doesn't work reliably
        if platform.system() == 'Windows':
            pytest.skip('Permission test not reliable on Windows')

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write('clusters: {}')
            f.flush()
            os.chmod(f.name, 0o000)  # Remove all permissions

            with pytest.raises(PermissionError):
                await load_clusters_from_yaml(f.name)

        os.chmod(f.name, 0o644)  # Restore permissions
        os.unlink(f.name)

    @pytest.mark.asyncio
    async def test_load_clusters_from_yaml_empty_path(self):
        """Test loading from empty path."""
        await load_clusters_from_yaml('')
        assert len(cluster_registry) == 0

    @pytest.mark.asyncio
    async def test_load_clusters_from_yaml_none_path(self):
        """Test loading from None path."""
        await load_clusters_from_yaml(None)
        assert len(cluster_registry) == 0
