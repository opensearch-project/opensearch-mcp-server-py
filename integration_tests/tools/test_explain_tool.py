# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_tool_error, assert_tool_success
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.tools
class TestExplainTool:
    async def test_explain_query(self, default_client):
        result = await default_client.call_tool(
            'ExplainTool',
            arguments={
                'index': TEST_INDEX,
                'id': '1',
                'body': '{"query": {"match": {"title": "Test document 1"}}}',
            },
        )
        assert_tool_success(result, '"matched"')

    async def test_explain_nonexistent_doc(self, default_client):
        result = await default_client.call_tool(
            'ExplainTool',
            arguments={
                'index': TEST_INDEX,
                'id': 'nonexistent_id_99999',
                'body': '{"query": {"match_all": {}}}',
            },
        )
        # OpenSearch returns 404 NotFoundError for nonexistent doc IDs
        assert_tool_error(result, 'NotFoundError')
