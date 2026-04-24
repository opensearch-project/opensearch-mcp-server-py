# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_tool_error, assert_tool_success
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.tools
class TestGenericApiTool:
    # -- Happy paths --

    async def test_get_cluster_health(self, default_client):
        result = await default_client.call_tool(
            'GenericOpenSearchApiTool',
            arguments={'path': '/_cluster/health', 'method': 'GET'},
        )
        assert_tool_success(result, 'OpenSearch API Response')

    async def test_get_cat_indices(self, default_client):
        result = await default_client.call_tool(
            'GenericOpenSearchApiTool',
            arguments={
                'path': '/_cat/indices',
                'method': 'GET',
                'query_params': {'format': 'json'},
            },
        )
        assert_tool_success(result, 'OpenSearch API Response', TEST_INDEX)

    async def test_get_with_query_params(self, default_client):
        result = await default_client.call_tool(
            'GenericOpenSearchApiTool',
            arguments={
                'path': f'/{TEST_INDEX}/_search',
                'method': 'GET',
                'body': {'query': {'match_all': {}}, 'size': 1},
            },
        )
        assert_tool_success(result, 'OpenSearch API Response')

    # -- Bad paths --

    async def test_invalid_http_method(self, default_client):
        result = await default_client.call_tool(
            'GenericOpenSearchApiTool',
            arguments={'path': '/_cat/indices', 'method': 'FOOBAR'},
        )
        assert_tool_error(result, 'Invalid HTTP method')

    async def test_path_without_leading_slash(self, default_client):
        result = await default_client.call_tool(
            'GenericOpenSearchApiTool',
            arguments={'path': 'cat/indices', 'method': 'GET'},
        )
        assert_tool_error(result, 'must start with')
