# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import anthropic
import pytest
import sys
from unittest.mock import AsyncMock, Mock, patch


JUDGMENT_CREATE_TOOLS = [
    'CreateJudgmentListTool',
    'CreateUBIJudgmentListTool',
    'CreateLLMJudgmentListTool',
]


@pytest.mark.eval
class TestJudgmentToolRouting:
    @classmethod
    def setup_class(cls):
        mock_client = Mock()
        mock_client.info = AsyncMock(return_value={'version': {'number': '3.1.0'}})

        cls.patcher = patch('opensearch.client.initialize_client', return_value=mock_client)
        cls.patcher.start()

        for module in ['tools.tools']:
            if module in sys.modules:
                del sys.modules[module]

        from tools.tools import TOOL_REGISTRY

        cls.tool_definitions = [
            {
                'name': name,
                'description': TOOL_REGISTRY[name]['description'],
                'input_schema': TOOL_REGISTRY[name]['input_schema'],
            }
            for name in JUDGMENT_CREATE_TOOLS
        ]

    @classmethod
    def teardown_class(cls):
        cls.patcher.stop()

    def ask_agent(self, scenario: str) -> anthropic.types.ToolUseBlock:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=512,
            tools=self.tool_definitions,
            tool_choice={'type': 'any'},
            messages=[{'role': 'user', 'content': scenario}],
        )
        tool_uses = [b for b in response.content if b.type == 'tool_use']
        assert len(tool_uses) == 1, f'Expected 1 tool call, got {len(tool_uses)}'
        return tool_uses[0]

    def test_selects_import_tool_for_manual_ratings(self):
        """When a user has manually annotated ratings, the agent should use CreateJudgmentListTool."""
        tool_use = self.ask_agent(
            'I have manually graded search results and want to store them as a judgment list '
            "called 'manual-judgments'. Here are my ratings: "
            '[{"query": "laptop", "ratings": [{"docId": "doc1", "rating": 3}, {"docId": "doc2", "rating": 1}]}]'
        )

        assert tool_use.name == 'CreateJudgmentListTool'
        assert tool_use.input.get('name') == 'manual-judgments'

    def test_selects_ubi_tool_for_click_data(self):
        """When a user wants judgments derived from UBI click data, the agent should use CreateUBIJudgmentListTool."""
        tool_use = self.ask_agent(
            'My search application has been logging user behaviour through User Behavior Insights. '
            "Use that click data to create a judgment list called 'ubi-judgments' "
            'using the COEC click model.'
        )

        assert tool_use.name == 'CreateUBIJudgmentListTool'
        assert tool_use.input.get('name') == 'ubi-judgments'
        assert 'coec' in tool_use.input.get('click_model', '').lower()

    def test_selects_llm_tool_for_ai_generated_ratings(self):
        """When a user wants an LLM to rate documents, the agent should use CreateLLMJudgmentListTool."""
        tool_use = self.ask_agent(
            "Use ML model 'model-abc' to automatically evaluate search results for relevance. "
            "The query set ID is 'qs-123' and the search configuration ID is 'sc-456'. "
            "Create a judgment list called 'ai-judgments'."
        )

        assert tool_use.name == 'CreateLLMJudgmentListTool'
        assert tool_use.input.get('model_id') == 'model-abc'
        assert tool_use.input.get('query_set_id') == 'qs-123'
        assert tool_use.input.get('search_configuration_id') == 'sc-456'
