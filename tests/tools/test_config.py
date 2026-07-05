# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import copy
import os
import yaml
from tools.config import apply_custom_tool_config


MOCK_TOOL_REGISTRY = {
    'ListIndexTool': {
        'display_name': 'ListIndexTool',
        'description': 'Original description for ListIndexTool',
        'other_field': 'some_value',
        # mimic real registry structure for validation of args
        'input_schema': {
            'type': 'object',
            'properties': {
                'index': {
                    'title': 'Index',
                    'type': 'string',
                    'description': 'The name of the index to get detailed information for. If provided, returns detailed information about this specific index instead of listing all indices.',
                }
            },
        },
    },
    'SearchIndexTool': {
        'display_name': 'SearchIndexTool',
        'description': 'Original description for SearchIndexTool',
    },
}


def test_apply_config_from_yaml_file():
    """Test that tool names and descriptions are updated from a YAML file."""
    config_content = {
        'tools': {
            'ListIndexTool': {
                'display_name': 'YAML_Custom_Name',
                'description': 'YAML custom description.',
            },
            'SearchIndexTool': {'display_name': 'YAML_Searcher'},
        }
    }
    config_path = 'test_temp_config.yml'
    with open(config_path, 'w') as f:
        yaml.dump(config_content, f)

    registry = copy.deepcopy(MOCK_TOOL_REGISTRY)
    custom_registry = apply_custom_tool_config(registry, config_path, {})

    assert custom_registry['ListIndexTool']['display_name'] == 'YAML_Custom_Name'
    assert custom_registry['ListIndexTool']['description'] == 'YAML custom description.'
    assert custom_registry['SearchIndexTool']['display_name'] == 'YAML_Searcher'
    # Ensure other fields are untouched
    assert custom_registry['ListIndexTool']['other_field'] == 'some_value'
    # Ensure original is untouched
    assert registry['ListIndexTool']['display_name'] == 'ListIndexTool'

    os.remove(config_path)


def test_apply_config_from_cli_args():
    """Test that tool names and descriptions are updated from CLI arguments."""
    cli_overrides = {
        'tool.ListIndexTool.display_name': 'CLI_Custom_Name',
        'tool.SearchIndexTool.description': 'CLI custom description.',
    }
    registry = copy.deepcopy(MOCK_TOOL_REGISTRY)
    custom_registry = apply_custom_tool_config(registry, '', cli_overrides)

    assert custom_registry['ListIndexTool']['display_name'] == 'CLI_Custom_Name'
    assert custom_registry['SearchIndexTool']['description'] == 'CLI custom description.'


def test_cli_overrides_yaml():
    """Test that config file takes priority over CLI arguments when both are provided."""
    config_content = {
        'tools': {
            'ListIndexTool': {
                'display_name': 'YAML_Custom_Name',
                'description': 'YAML description.',
            }
        }
    }
    config_path = 'test_temp_config.yml'
    with open(config_path, 'w') as f:
        yaml.dump(config_content, f)

    cli_overrides = {
        'tool.ListIndexTool.name': 'CLI_Final_Name',
    }

    registry = copy.deepcopy(MOCK_TOOL_REGISTRY)
    custom_registry = apply_custom_tool_config(registry, config_path, cli_overrides)

    # Config file should take priority over CLI
    assert custom_registry['ListIndexTool']['display_name'] == 'YAML_Custom_Name'
    assert custom_registry['ListIndexTool']['description'] == 'YAML description.'

    os.remove(config_path)


def test_yaml_rejects_non_standard_keys():
    """YAML should reject non-standard top-level keys for tools."""
    config_content = {
        'tools': {
            'ListIndexTool': {
                'customKey': 'Value1',
            },
            'SearchIndexTool': {
                'customKey2': 'Value2',
            },
        }
    }
    config_path = 'test_temp_config.yml'
    with open(config_path, 'w') as f:
        yaml.dump(config_content, f)

    registry = copy.deepcopy(MOCK_TOOL_REGISTRY)
    try:
        apply_custom_tool_config(registry, config_path, {})
        assert False, 'Expected ValueError for non-standard top-level keys'
    except ValueError as e:
        assert "Invalid field 'customKey'" in str(e) or "Invalid field 'customKey2'" in str(e)

    os.remove(config_path)


def test_yaml_arbitrary_fields_rejected():
    """Non-standard top-level fields should be rejected in YAML configuration."""
    config_content = {
        'tools': {
            'ListIndexTool': {
                'display_name': 'Valid_Name',
                'unsupported_field': 'Should be rejected',
                'another_field': 123,
            },
        }
    }
    config_path = 'test_temp_config.yml'
    with open(config_path, 'w') as f:
        yaml.dump(config_content, f)

    registry = copy.deepcopy(MOCK_TOOL_REGISTRY)
    try:
        apply_custom_tool_config(registry, config_path, {})
        assert False, 'Expected ValueError for non-standard top-level fields in YAML'
    except ValueError as e:
        msg = str(e)
        assert "Invalid field 'unsupported_field'" in msg or "Invalid field 'another_field'" in msg
    os.remove(config_path)


def test_cli_arbitrary_fields_rejected():
    """Non-standard top-level fields should be ignored via CLI parser."""
    cli_overrides = {
        'tool.ListIndexTool.display_name': 'Valid_Name',
        'tool.ListIndexTool.invalid_field': 'Ignored',
        'tool.SearchIndexTool.bad_field': 'AlsoIgnored',
        'invalid.format': 'Wrong format entirely',
    }

    registry = copy.deepcopy(MOCK_TOOL_REGISTRY)
    custom_registry = apply_custom_tool_config(registry, '', cli_overrides)

    assert custom_registry['ListIndexTool']['display_name'] == 'Valid_Name'
    assert 'invalid_field' not in custom_registry['ListIndexTool']
    assert 'bad_field' not in custom_registry['SearchIndexTool']


def test_yaml_unsupported_field_now_errors():
    """YAML should error on unsupported/non-standard fields."""
    config_content = {
        'tools': {
            'ListIndexTool': {
                'name': 'Valid_Name',
                'invalid_field': 'Value',
                'another_bad_field': 'Value2',
            },
        }
    }
    config_path = 'test_temp_config.yml'
    with open(config_path, 'w') as f:
        yaml.dump(config_content, f)

    registry = copy.deepcopy(MOCK_TOOL_REGISTRY)
    try:
        apply_custom_tool_config(registry, config_path, {})
        assert False, 'Expected ValueError for non-standard fields'
    except ValueError as e:
        msg = str(e)
        assert "Invalid field 'invalid_field'" in msg or "Invalid field 'another_bad_field'" in msg
    os.remove(config_path)

    # Removed: behavior changed to ignore non-standard keys via CLI


def test_parse_cli_to_nested_config_top_level_and_args():
    from tools.config import parse_cli_to_nested_config

    cli_overrides = {
        'tool.ListIndexTool.http_methods': 'POST',  # should be ignored (non-standard)
        'tool.ListIndexTool.customTag': 'analytics',  # should be ignored (non-standard)
        'tool.ListIndexTool.args.index.required': 'true',
        'tool.ListIndexTool.args.index.default': 'my-index',
        'tool.SearchIndexTool.args.query_dsl.default': '{"match_all": {}}',
        'invalid.no_prefix': 'ignored',
        'tool.Bad': 'ignored',  # missing fieldPath
    }

    nested = parse_cli_to_nested_config(cli_overrides)

    assert 'ListIndexTool' in nested
    assert 'http_methods' not in nested['ListIndexTool']
    assert 'customTag' not in nested['ListIndexTool']
    assert nested['ListIndexTool']['args']['index']['required'] is True
    assert nested['ListIndexTool']['args']['index']['default'] == 'my-index'

    assert 'SearchIndexTool' in nested
    assert nested['SearchIndexTool']['args']['query_dsl']['default'] == {'match_all': {}}

    # invalid keys should not create entries
    assert 'Bad' not in nested


def test_parse_cli_to_nested_config_type_coercion():
    from tools.config import parse_cli_to_nested_config

    cli_overrides = {
        'tool.T.args.boolTrue': 'true',
        'tool.T.args.boolFalse': 'false',
        'tool.T.args.intVal': '10',
        'tool.T.args.floatVal': '1.5',
        'tool.T.args.jsonObj': '{"a": 1}',
        'tool.T.args.raw': 'POST',
    }

    nested = parse_cli_to_nested_config(cli_overrides)

    assert nested['T']['args']['boolTrue'] is True
    assert nested['T']['args']['boolFalse'] is False
    assert nested['T']['args']['intVal'] == 10
    assert nested['T']['args']['floatVal'] == 1.5
    assert nested['T']['args']['jsonObj'] == {'a': 1}
    assert nested['T']['args']['raw'] == 'POST'


def test_alias_artifacts_removed():
    """Alias helpers are removed; importing them should fail at runtime if attempted."""
    try:
        from tools import config as cfg  # noqa: F401

        assert not hasattr(cfg, 'FIELD_ALIASES')
        assert not hasattr(cfg, '_find_actual_field')
        assert not hasattr(cfg, '_get_all_aliases')
    except Exception:
        # Import should still succeed; attributes should not exist
        assert False, 'tools.config should be importable'


def test_load_config_from_file():
    """Test the _load_config_from_file function directly."""
    from tools.config import _load_config_from_file

    config_data = {
        'tool1': {
            'display_name': 'Tool_One',
            'description': 'First tool',
        },
        'tool2': {
            'display_name': 'Tool_Two',
        },
    }

    configs = _load_config_from_file(config_data)

    # Should return dictionary mapping tool names to their configs
    assert len(configs) == 2
    assert 'tool1' in configs
    assert 'tool2' in configs
    assert configs['tool1']['display_name'] == 'Tool_One'
    assert configs['tool1']['description'] == 'First tool'
    assert configs['tool2']['display_name'] == 'Tool_Two'


def test_parse_cli_to_nested_config_multiple_tools():
    from tools.config import parse_cli_to_nested_config

    cli_overrides = {
        'tool.tool1.display_name': 'CLI_Tool_One',
        'tool.tool2.description': 'CLI Tool Two Description',
        'invalid.format': 'Should be ignored',
        'tool.tool3.invalid_field': 'Kept',
    }

    configs = parse_cli_to_nested_config(cli_overrides)

    assert len(configs) == 2  # tool3 has non-standard top-level field and is ignored
    assert 'tool1' in configs
    assert 'tool2' in configs
    assert 'tool3' not in configs
    assert configs['tool1']['display_name'] == 'CLI_Tool_One'
    assert configs['tool2']['description'] == 'CLI Tool Two Description'
    # tool3 should not appear due to non-standard field


def test_apply_validated_configs():
    """Test the _apply_validated_configs function directly."""
    from tools.config import _apply_validated_configs

    registry = copy.deepcopy(MOCK_TOOL_REGISTRY)

    configs = {
        'ListIndexTool': {
            'display_name': 'New_Name',
            'description': 'New Description',
        },
        'NonExistentTool': {
            'display_name': 'Should be ignored',
        },
    }

    _apply_validated_configs(registry, configs)

    # Valid changes should be applied
    assert registry['ListIndexTool']['display_name'] == 'New_Name'
    assert registry['ListIndexTool']['description'] == 'New Description'

    # Non-existent tool should not be added
    assert 'NonExistentTool' not in registry


def test_config_file_priority_over_cli():
    """Test that config file completely overrides CLI arguments when both are provided."""
    config_content = {
        'tools': {
            'ListIndexTool': {
                'display_name': 'YAML_Priority_Name',
                'description': 'YAML_Priority_Description',
            }
        }
    }
    config_path = 'test_priority_config.yml'
    with open(config_path, 'w') as f:
        yaml.dump(config_content, f)

    cli_overrides = {
        'tool.ListIndexTool.name': 'CLI_Ignored_Name',
        'tool.ListIndexTool.description': 'CLI_Ignored_Description',
        'tool.SearchIndexTool.display_name': 'CLI_Also_Ignored',
    }

    registry = copy.deepcopy(MOCK_TOOL_REGISTRY)
    custom_registry = apply_custom_tool_config(registry, config_path, cli_overrides)

    # Config file should take priority
    assert custom_registry['ListIndexTool']['display_name'] == 'YAML_Priority_Name'
    assert custom_registry['ListIndexTool']['description'] == 'YAML_Priority_Description'

    # CLI arguments should be completely ignored
    assert custom_registry['SearchIndexTool']['display_name'] == 'SearchIndexTool'

    os.remove(config_path)


def test_yaml_duplicate_aliases_now_error():
    """Alias keys are non-standard and should error in YAML."""
    config_content = {
        'tools': {
            'ListIndexTool': {
                'name': 'First Alias',
                'displayName': 'Second Alias',
                'customName': 'Third Alias',
            }
        }
    }
    config_path = 'test_duplicate_aliases.yml'
    with open(config_path, 'w') as f:
        yaml.dump(config_content, f)

    registry = copy.deepcopy(MOCK_TOOL_REGISTRY)
    try:
        apply_custom_tool_config(registry, config_path, {})
        assert False, 'Expected ValueError for non-standard alias fields in YAML'
    except ValueError as e:
        msg = str(e)
        assert (
            "Invalid field 'name'" in msg
            or "Invalid field 'displayName'" in msg
            or "Invalid field 'customName'" in msg
        )

    os.remove(config_path)


def test_cli_duplicate_aliases_ignored():
    """Alias keys are non-standard and should be ignored via CLI parser."""
    cli_overrides = {
        'tool.ListIndexTool.name': 'First CLI Alias',
        'tool.ListIndexTool.displayName': 'Second CLI Alias',
        'tool.ListIndexTool.customName': 'Third CLI Alias',
    }

    registry = copy.deepcopy(MOCK_TOOL_REGISTRY)
    custom_registry = apply_custom_tool_config(registry, '', cli_overrides)

    assert 'name' not in custom_registry['ListIndexTool']
    assert 'displayName' not in custom_registry['ListIndexTool']
    assert 'customName' not in custom_registry['ListIndexTool']


def test_display_name_pattern_validation():
    """Test that display names must follow the required pattern."""
    config_content = {
        'tools': {
            'ListIndexTool': {
                'display_name': 'Valid_Name_123',
                'description': 'Valid description',
            },
            'SearchIndexTool': {
                'display_name': 'Invalid_Name!',  # Contains space and exclamation
            },
        }
    }
    config_path = 'test_pattern_validation.yml'
    with open(config_path, 'w') as f:
        yaml.dump(config_content, f)

    registry = copy.deepcopy(MOCK_TOOL_REGISTRY)

    try:
        apply_custom_tool_config(registry, config_path, {})
        assert False, 'Expected ValueError for invalid display name pattern'
    except ValueError as e:
        error_msg = str(e)
        assert 'does not follow the required pattern' in error_msg
        assert 'Invalid_Name!' in error_msg

    os.remove(config_path)


def test_duplicate_display_name_detection():
    """Test that duplicate display names across different tools raise an error."""
    config_content = {
        'tools': {
            'ListIndexTool': {
                'display_name': 'Shared_Name',
            },
            'SearchIndexTool': {
                'display_name': 'Shared_Name',  # Same as ListIndexTool
            },
        }
    }
    config_path = 'test_duplicate_display_names.yml'
    with open(config_path, 'w') as f:
        yaml.dump(config_content, f)

    registry = copy.deepcopy(MOCK_TOOL_REGISTRY)

    try:
        apply_custom_tool_config(registry, config_path, {})
        assert False, 'Expected ValueError for duplicate display names'
    except ValueError as e:
        error_msg = str(e)
        assert 'conflicts with another tool' in error_msg
        assert 'Shared_Name' in error_msg

    os.remove(config_path)


def test_empty_config_file():
    """Test that empty config files are handled gracefully."""
    config_content = {}
    config_path = 'test_empty_config.yml'
    with open(config_path, 'w') as f:
        yaml.dump(config_content, f)

    registry = copy.deepcopy(MOCK_TOOL_REGISTRY)
    custom_registry = apply_custom_tool_config(registry, config_path, {})

    # No tools should be renamed
    assert custom_registry['ListIndexTool']['display_name'] == 'ListIndexTool'
    assert custom_registry['SearchIndexTool']['display_name'] == 'SearchIndexTool'

    os.remove(config_path)


def test_non_existent_tool_validation():
    """Test that references to non-existent tools raise an error."""
    config_content = {
        'tools': {
            'NonExistentTool': {
                'display_name': 'Custom Name',
            }
        }
    }
    config_path = 'test_nonexistent_tool.yml'
    with open(config_path, 'w') as f:
        yaml.dump(config_content, f)

    registry = copy.deepcopy(MOCK_TOOL_REGISTRY)

    try:
        apply_custom_tool_config(registry, config_path, {})
        assert False, 'Expected ValueError for non-existent tool'
    except ValueError as e:
        error_msg = str(e)
        assert 'is not a valid tool name' in error_msg
        assert 'NonExistentTool' in error_msg

    os.remove(config_path)


def test_cli_non_existent_tool_validation():
    """Test that CLI references to non-existent tools raise an error."""
    cli_overrides = {
        'tool.NonExistentTool.display_name': 'Custom Name',
    }

    registry = copy.deepcopy(MOCK_TOOL_REGISTRY)

    try:
        apply_custom_tool_config(registry, '', cli_overrides)
        assert False, 'Expected ValueError for non-existent tool in CLI'
    except ValueError as e:
        error_msg = str(e)
        assert 'is not a valid tool name' in error_msg
        assert 'NonExistentTool' in error_msg


def test_mixed_valid_invalid_configurations():
    """Test that configurations with both valid and invalid fields work correctly."""
    config_content = {
        'tools': {
            'ListIndexTool': {
                'display_name': 'Valid_Name',
                'invalid_field': 'Should be ignored',
                'description': 'Valid description',
                'another_invalid': 'Also ignored',
            },
            'SearchIndexTool': {'display_name': 'Valid_Name_2'},
        }
    }
    config_path = 'test_mixed_config.yml'
    with open(config_path, 'w') as f:
        yaml.dump(config_content, f)

    registry = copy.deepcopy(MOCK_TOOL_REGISTRY)
    try:
        apply_custom_tool_config(registry, config_path, {})
        assert False, 'Expected ValueError for non-standard top-level fields in YAML'
    except ValueError as e:
        msg = str(e)
        assert "Invalid field 'invalid_field'" in msg or "Invalid field 'another_invalid'" in msg

    os.remove(config_path)


def test_yaml_args_description_update():
    """Test that argument descriptions can be updated via YAML config."""
    config_content = {
        'tools': {
            'ListIndexTool': {
                'args': {
                    'index': 'Custom description for index argument',
                }
            }
        }
    }
    config_path = 'test_args_config.yml'
    with open(config_path, 'w') as f:
        yaml.dump(config_content, f)

    registry = copy.deepcopy(MOCK_TOOL_REGISTRY)
    custom_registry = apply_custom_tool_config(registry, config_path, {})

    # Verify input_schema is updated
    index_prop = custom_registry['ListIndexTool']['input_schema']['properties']['index']
    assert index_prop['description'] == 'Custom description for index argument'

    # Verify args_model field description is also updated when available
    args_model = custom_registry['ListIndexTool'].get('args_model')
    if args_model is not None and hasattr(args_model, 'model_fields'):
        assert (
            args_model.model_fields['index'].description == 'Custom description for index argument'
        )

    os.remove(config_path)


def test_yaml_args_description_alias_desc():
    """Test that 'desc' alias works for args description inside YAML."""
    config_content = {
        'tools': {
            'ListIndexTool': {
                'args': {
                    'index': 'Alias description for index',
                }
            }
        }
    }
    config_path = 'test_args_desc_alias.yml'
    with open(config_path, 'w') as f:
        yaml.dump(config_content, f)

    registry = copy.deepcopy(MOCK_TOOL_REGISTRY)
    custom_registry = apply_custom_tool_config(registry, config_path, {})

    index_prop = custom_registry['ListIndexTool']['input_schema']['properties']['index']
    assert index_prop['description'] == 'Alias description for index'

    os.remove(config_path)


def test_yaml_args_invalid_argument_raises():
    """Test that updating a non-existent argument raises an error."""
    config_content = {
        'tools': {
            'ListIndexTool': {
                'args': {
                    'nonexistent': 'Should fail',
                }
            }
        }
    }
    config_path = 'test_args_invalid_arg.yml'
    with open(config_path, 'w') as f:
        yaml.dump(config_content, f)

    registry = copy.deepcopy(MOCK_TOOL_REGISTRY)

    try:
        apply_custom_tool_config(registry, config_path, {})
        assert False, 'Expected ValueError for invalid argument name'
    except ValueError as e:
        assert "does not exist on tool 'ListIndexTool'" in str(e)

    os.remove(config_path)


def test_yaml_args_description_must_be_string():
    """Test that args description must be a string."""
    config_content = {
        'tools': {
            'ListIndexTool': {
                'args': {
                    'index': 123,
                }
            }
        }
    }
    config_path = 'test_args_desc_type.yml'
    with open(config_path, 'w') as f:
        yaml.dump(config_content, f)

    registry = copy.deepcopy(MOCK_TOOL_REGISTRY)

    try:
        apply_custom_tool_config(registry, config_path, {})
        assert False, 'Expected ValueError for non-string description'
    except ValueError as e:
        assert 'must be a string' in str(e)

    os.remove(config_path)
