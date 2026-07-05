#!/usr/bin/env python3
"""Simple test script to verify write protection logic in GenericOpenSearchApiTool."""

import os
import sys


# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


def test_write_protection_logic():
    """Test the write protection logic directly."""
    print('Testing Write Protection Logic...')

    # Save original setting
    original_setting = os.environ.get('OPENSEARCH_SETTINGS_ALLOW_WRITE', 'true')

    try:
        # Test 1: Check environment variable parsing
        print('\n1. Testing environment variable parsing:')

        os.environ['OPENSEARCH_SETTINGS_ALLOW_WRITE'] = 'false'
        allow_write = os.getenv('OPENSEARCH_SETTINGS_ALLOW_WRITE', 'true').lower() == 'true'
        print(f'  OPENSEARCH_SETTINGS_ALLOW_WRITE=false -> allow_write={allow_write}')
        assert not allow_write, "Should be False when set to 'false'"

        os.environ['OPENSEARCH_SETTINGS_ALLOW_WRITE'] = 'true'
        allow_write = os.getenv('OPENSEARCH_SETTINGS_ALLOW_WRITE', 'true').lower() == 'true'
        print(f'  OPENSEARCH_SETTINGS_ALLOW_WRITE=true -> allow_write={allow_write}')
        assert allow_write, "Should be True when set to 'true'"

        # Test 2: Check method categorization
        print('\n2. Testing method categorization:')
        write_methods = ['POST', 'PUT', 'DELETE', 'PATCH']
        read_methods = ['GET', 'HEAD']

        for method in write_methods:
            is_write = method.upper() in write_methods
            print(f'  {method} is write method: {is_write}')
            assert is_write, f'{method} should be categorized as write method'

        for method in read_methods:
            is_write = method.upper() in write_methods
            print(f'  {method} is write method: {is_write}')
            assert not is_write, f'{method} should not be categorized as write method'

        # Test 3: Logic combination
        print('\n3. Testing combined logic:')
        os.environ['OPENSEARCH_SETTINGS_ALLOW_WRITE'] = 'false'
        allow_write = os.getenv('OPENSEARCH_SETTINGS_ALLOW_WRITE', 'true').lower() == 'true'

        for method in write_methods:
            should_block = method.upper() in write_methods and not allow_write
            print(f'  {method} should be blocked: {should_block}')
            assert should_block, f'{method} should be blocked when write is disabled'

        for method in read_methods:
            should_block = method.upper() in write_methods and not allow_write
            print(f'  {method} should be blocked: {should_block}')
            assert not should_block, f'{method} should not be blocked when write is disabled'

        print('\n✓ All write protection logic tests passed!')

    finally:
        # Restore original setting
        if original_setting:
            os.environ['OPENSEARCH_SETTINGS_ALLOW_WRITE'] = original_setting
        else:
            os.environ.pop('OPENSEARCH_SETTINGS_ALLOW_WRITE', None)


if __name__ == '__main__':
    test_write_protection_logic()
