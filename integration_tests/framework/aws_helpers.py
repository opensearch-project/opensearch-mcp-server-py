# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import logging
import os
import tempfile
from pathlib import Path


logger = logging.getLogger(__name__)


class AWSProfileManager:
    """Manages a temporary AWS credentials profile for integration tests.

    Uses AWS_SHARED_CREDENTIALS_FILE to point to a temp file instead of
    modifying the user's real ~/.aws/credentials.
    """

    def __init__(self, profile_name: str = 'mcp-it-test-profile'):
        self.profile_name = profile_name
        self._temp_dir: tempfile.TemporaryDirectory | None = None
        self._creds_path: Path | None = None

    @property
    def credentials_file(self) -> str:
        """Return the path to the temporary credentials file."""
        if self._creds_path is None:
            raise RuntimeError('AWSProfileManager not set up yet. Call setup() first.')
        return str(self._creds_path)

    def setup(self) -> str:
        """Create a temporary AWS credentials file with test credentials.

        Returns:
            The profile name that was created.
        """
        access_key = os.environ.get('IT_AWS_ACCESS_KEY_ID', '')
        secret_key = os.environ.get('IT_AWS_SECRET_ACCESS_KEY', '')
        session_token = os.environ.get('IT_AWS_SESSION_TOKEN', '')

        if not access_key or not secret_key:
            raise ValueError(
                'IT_AWS_ACCESS_KEY_ID and IT_AWS_SECRET_ACCESS_KEY must be set '
                'for AWS profile tests'
            )

        self._temp_dir = tempfile.TemporaryDirectory(prefix='mcp-it-aws-')
        self._creds_path = Path(self._temp_dir.name) / 'credentials'

        profile_block = f'[{self.profile_name}]\n'
        profile_block += f'aws_access_key_id = {access_key}\n'
        profile_block += f'aws_secret_access_key = {secret_key}\n'
        if session_token:
            profile_block += f'aws_session_token = {session_token}\n'

        self._creds_path.write_text(profile_block)
        logger.info(f'Created temporary AWS profile "{self.profile_name}" at {self._creds_path}')
        return self.profile_name

    def teardown(self) -> None:
        """Clean up the temporary credentials file."""
        if self._temp_dir:
            self._temp_dir.cleanup()
            self._temp_dir = None
            self._creds_path = None
            logger.info(f'Cleaned up temporary AWS profile "{self.profile_name}"')

    def get_env_for_profile_cli(self) -> dict:
        """Return env vars for a server that uses --profile CLI arg.

        The server will read the credentials file and use the profile.
        """
        return {
            'AWS_SHARED_CREDENTIALS_FILE': self.credentials_file,
        }

    def get_env_for_profile_env(self) -> dict:
        """Return env vars for a server that uses AWS_PROFILE env var."""
        return {
            'AWS_SHARED_CREDENTIALS_FILE': self.credentials_file,
            'AWS_PROFILE': self.profile_name,
        }


def get_default_server_env() -> dict:
    """Return server env vars using the best available auth (AWS preferred, then basic).

    Raises pytest.skip if no auth credentials are available.
    """
    import pytest

    url = os.environ.get('IT_OPENSEARCH_URL')
    if not url:
        pytest.skip('IT_OPENSEARCH_URL not set')

    aws_key = os.environ.get('IT_AWS_ACCESS_KEY_ID')
    aws_secret = os.environ.get('IT_AWS_SECRET_ACCESS_KEY')
    aws_region = os.environ.get('IT_AWS_REGION', 'us-west-2')

    if aws_key and aws_secret:
        return {
            'OPENSEARCH_URL': url,
            'AWS_REGION': aws_region,
            'AWS_ACCESS_KEY_ID': aws_key,
            'AWS_SECRET_ACCESS_KEY': aws_secret,
            'AWS_SESSION_TOKEN': os.environ.get('IT_AWS_SESSION_TOKEN', ''),
        }

    basic_user = os.environ.get('IT_BASIC_AUTH_USERNAME')
    basic_pass = os.environ.get('IT_BASIC_AUTH_PASSWORD')
    if basic_user and basic_pass:
        return {
            'OPENSEARCH_URL': url,
            'OPENSEARCH_USERNAME': basic_user,
            'OPENSEARCH_PASSWORD': basic_pass,
        }

    pytest.skip('No auth credentials available')


def build_header_auth_headers() -> dict:
    """Build HTTP headers for header-based authentication from env vars.

    Prefers AWS credentials when available; falls back to basic auth.
    Calls pytest.skip if no auth credentials are available.
    """
    import base64
    import pytest

    url = os.environ.get('IT_OPENSEARCH_URL', '')
    headers = {}
    if url:
        headers['opensearch-url'] = url

    # Prefer AWS header auth
    access_key = os.environ.get('IT_AWS_ACCESS_KEY_ID', '')
    secret_key = os.environ.get('IT_AWS_SECRET_ACCESS_KEY', '')
    if access_key and secret_key:
        region = os.environ.get('IT_AWS_REGION', '')
        session_token = os.environ.get('IT_AWS_SESSION_TOKEN', '')
        if region:
            headers['aws-region'] = region
        headers['aws-access-key-id'] = access_key
        headers['aws-secret-access-key'] = secret_key
        if session_token:
            headers['aws-session-token'] = session_token
        headers['aws-service-name'] = 'es'
        return headers

    # Fall back to basic auth via Authorization header
    basic_user = os.environ.get('IT_BASIC_AUTH_USERNAME', '')
    basic_pass = os.environ.get('IT_BASIC_AUTH_PASSWORD', '')
    if basic_user and basic_pass:
        credentials = base64.b64encode(f'{basic_user}:{basic_pass}'.encode()).decode()
        headers['Authorization'] = f'Basic {credentials}'
        return headers

    pytest.skip('No auth credentials available for header auth')
