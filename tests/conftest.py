# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import os
import pytest


def pytest_addoption(parser):
    parser.addoption(
        '--run-evals',
        action='store_true',
        default=False,
        help='Run LLM eval tests that call the Anthropic API (requires ANTHROPIC_API_KEY)',
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption('--run-evals'):
        skip = pytest.mark.skip(
            reason='LLM eval tests are skipped by default; pass --run-evals to run them'
        )
        for item in items:
            if item.get_closest_marker('eval'):
                item.add_marker(skip)
    elif not os.environ.get('ANTHROPIC_API_KEY'):
        skip = pytest.mark.skip(reason='ANTHROPIC_API_KEY environment variable is not set')
        for item in items:
            if item.get_closest_marker('eval'):
                item.add_marker(skip)
