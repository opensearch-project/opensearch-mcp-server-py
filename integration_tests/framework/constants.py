# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import os


TEST_INDEX = os.environ.get('IT_TEST_INDEX', 'mcp-integration-test')
METRIC_TEST_INDEX = os.environ.get('IT_METRIC_TEST_INDEX', 'mcp-integration-metric-test')

# Known built-in tool categories — mirrors BUILTIN_CATEGORY_TOOLS in tool_filter.py
BUILTIN_CATEGORIES = frozenset(
    {
        'core_tools',
        'memory',
        'search_relevance',
        'agentic_memory',
        'observability',
        'skills',
        'analytics',
    }
)
