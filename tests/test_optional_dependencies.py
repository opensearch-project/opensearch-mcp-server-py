# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the optional "aws" and "ml" extras.

The heavy dependencies must stay out of the import path taken at server startup.
Importing the ML stack eagerly costs several seconds on a warm environment and far
more on a cold one, which eats into an MCP client's initialize deadline.
"""

import builtins
import pytest
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch


SRC = str(Path(__file__).resolve().parents[1] / 'src')


def _modules_loaded_after(import_statement: str) -> set[str]:
    """Import a module in a clean interpreter and report which heavy packages it loaded."""
    script = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {SRC!r})
        {import_statement}
        heavy = [m for m in ('boto3', 'botocore', 'numpy', 'scipy', 'sklearn') if m in sys.modules]
        print(','.join(heavy))
    """)
    result = subprocess.run(
        [sys.executable, '-c', script], capture_output=True, text=True, timeout=300
    )
    assert result.returncode == 0, f'import failed: {result.stderr}'
    return {m for m in result.stdout.strip().split(',') if m}


class TestLazyImports:
    """Heavy dependencies must not be imported as a side effect of importing the server."""

    def test_client_does_not_import_boto3(self):
        assert 'boto3' not in _modules_loaded_after('import opensearch.client')

    def test_skills_tools_does_not_import_ml_stack(self):
        loaded = _modules_loaded_after('import tools.skills_tools')
        assert not loaded & {'numpy', 'scipy', 'sklearn'}

    def test_tool_registry_does_not_import_heavy_dependencies(self):
        assert not _modules_loaded_after('import tools.tools')


class TestAwsExtra:
    """AWS helpers surface an actionable message when the extra is missing."""

    def test_boto3_remains_accessible_as_module_attribute(self):
        """Kept resolvable so existing `patch('opensearch.client.boto3.Session')` still works."""
        import opensearch.client as client_module

        assert client_module.boto3 is not None

    def test_unknown_attribute_still_raises_attribute_error(self):
        import opensearch.client as client_module

        with pytest.raises(AttributeError):
            client_module.does_not_exist

    def test_import_boto3_raises_configuration_error_with_hint(self):
        from opensearch.client import AWS_EXTRA_HINT, ConfigurationError, _import_boto3

        real_import = builtins.__import__

        def fail_boto3(name, *args, **kwargs):
            if name == 'boto3':
                raise ImportError('No module named boto3')
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, '__import__', side_effect=fail_boto3):
            with pytest.raises(ConfigurationError) as excinfo:
                _import_boto3()

        assert 'opensearch-mcp-server-py[aws]' in str(excinfo.value)
        assert AWS_EXTRA_HINT in str(excinfo.value)

    def test_optional_boto3_returns_none_when_missing(self):
        """Region discovery degrades to "no region" rather than failing."""
        from opensearch.client import _optional_boto3

        real_import = builtins.__import__

        def fail_boto3(name, *args, **kwargs):
            if name == 'boto3':
                raise ImportError('No module named boto3')
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, '__import__', side_effect=fail_boto3):
            assert _optional_boto3() is None


class TestMlExtra:
    """Analysis tools are registered according to what is installed."""

    def test_ml_dependencies_available_reports_installed_state(self):
        from tools.skills_tools import _ML_MODULES, ml_dependencies_available

        expected = all(
            __import__('importlib.util', fromlist=['util']).find_spec(m) for m in _ML_MODULES
        )
        assert ml_dependencies_available() is bool(expected)

    def test_pure_python_tools_are_always_registered(self):
        from tools.skills_tools import SKILLS_TOOLS_REGISTRY

        assert 'DataDistributionTool' in SKILLS_TOOLS_REGISTRY
        assert 'MetricChangeAnalysisTool' in SKILLS_TOOLS_REGISTRY

    def test_log_pattern_tool_registration_follows_ml_availability(self):
        from tools.skills_tools import SKILLS_TOOLS_REGISTRY, ml_dependencies_available

        assert ('LogPatternAnalysisTool' in SKILLS_TOOLS_REGISTRY) is ml_dependencies_available()

    @pytest.mark.asyncio
    async def test_log_pattern_tool_reports_missing_extra(self):
        """Calling the tool without the extra explains how to install it."""
        from tools.skills_tools import LogPatternAnalysisToolArgs, log_pattern_analysis_tool

        real_import = builtins.__import__

        def fail_analysis(name, *args, **kwargs):
            if 'log_pattern_analysis' in name:
                raise ImportError('No module named sklearn')
            return real_import(name, *args, **kwargs)

        args = LogPatternAnalysisToolArgs(
            opensearch_cluster_name='test-cluster',
            index='logs',
            timeField='@timestamp',
            logFieldName='message',
            selectionTimeRangeStart='2026-01-01 00:00:00',
            selectionTimeRangeEnd='2026-01-01 01:00:00',
        )

        with patch.object(builtins, '__import__', side_effect=fail_analysis):
            result = await log_pattern_analysis_tool(args)

        assert 'opensearch-mcp-server-py[ml]' in result[0]['text']
