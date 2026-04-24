# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""OpenSearch client initialization module.

This module provides functions to initialize OpenSearch clients with different
authentication methods and connection modes (single vs multi-cluster).
"""

import boto3
import importlib.metadata
import logging
import os
from .connection import (
    DEFAULT_MAX_RESPONSE_SIZE,
    BufferedAsyncHttpConnection,
    OpenSearchClientError,
)
from botocore.credentials import Credentials
from contextlib import asynccontextmanager
from http.client import HTTP_PORT, HTTPS_PORT
from mcp.server.lowlevel.server import request_ctx
from mcp_server_opensearch.clusters_information import ClusterInfo, get_cluster
from mcp_server_opensearch.global_state import get_mode, get_profile
from opensearchpy import AsyncOpenSearch, AWSV4SignerAsyncAuth
from starlette.requests import Request
from tools.tool_params import baseToolArgs
from typing import Any, AsyncIterator, Dict, Optional
from urllib.parse import ParseResult, urlparse, urlunparse


# Configure logging
logger = logging.getLogger(__name__)

# Constants
OPENSEARCH_SERVICE = 'es'
OPENSEARCH_SERVERLESS_SERVICE = 'aoss'
DEFAULT_TIMEOUT = 30
DEFAULT_SSL_VERIFY = True
try:
    _VERSION = importlib.metadata.version('opensearch-mcp-server-py')
except importlib.metadata.PackageNotFoundError:
    _VERSION = 'unknown'
USER_AGENT = f'opensearch-mcp-server-py/{_VERSION}'
# opensearch-py uses 9200 when the URL has no port; http/https must use RFC defaults.
_DEFAULT_PORTS_BY_SCHEME: dict[str, int] = {'http': HTTP_PORT, 'https': HTTPS_PORT}


class AuthenticationError(OpenSearchClientError):
    """Exception raised when authentication fails."""

    pass


class ConfigurationError(OpenSearchClientError):
    """Exception raised when configuration is invalid."""

    pass


# Public API Functions
def initialize_client(args: baseToolArgs) -> AsyncOpenSearch:
    """Initialize and return an OpenSearch client based on the current mode.

    Behavior depends on the global mode:
    - Single mode: Always uses environment variables, ignores cluster name
    - Multi mode: Requires cluster name to be provided, uses cluster config

    Args:
        args (baseToolArgs): Arguments containing optional opensearch_cluster_name

    Returns:
        OpenSearch: An initialized OpenSearch client instance

    Raises:
        ConfigurationError: If in multi mode but no cluster name provided or invalid mode
        AuthenticationError: If authentication fails
    """
    try:
        mode = get_mode()
        logger.info(f'Initializing OpenSearch client in {mode} mode')

        if mode == 'single':
            # In single mode, always use environment variables, ignore cluster name
            return _initialize_client_single_mode()
        elif mode == 'multi':
            # In multi mode, cluster name must be provided
            if not args or not args.opensearch_cluster_name:
                raise ConfigurationError('In multi mode, opensearch_cluster_name must be provided')
            # Get cluster information
            cluster_info = get_cluster(args.opensearch_cluster_name)
            if not cluster_info:
                raise ConfigurationError(
                    f'Cluster "{args.opensearch_cluster_name}" not found in configuration'
                )

            return _initialize_client_multi_mode(cluster_info)
        else:
            raise ConfigurationError(f'Unknown mode: {mode}. Must be "single" or "multi"')

    except (ConfigurationError, AuthenticationError):
        raise
    except Exception as e:
        logger.error(f'Unexpected error in client initialization: {e}')
        raise ConfigurationError(f'Failed to initialize OpenSearch client: {e}')


@asynccontextmanager
async def get_opensearch_client(args: baseToolArgs) -> AsyncIterator[AsyncOpenSearch]:
    """Async context manager for OpenSearch client lifecycle management.

    This context manager ensures that OpenSearch clients are properly closed after use,
    preventing connection leaks and enabling graceful server shutdown.

    Usage:
        async with get_opensearch_client(args) as client:
            # Use client for operations
            result = await client.info()

    Args:
        args (baseToolArgs): Arguments containing optional opensearch_cluster_name

    Yields:
        AsyncOpenSearch: An initialized OpenSearch client instance

    Raises:
        ConfigurationError: If in multi mode but no cluster name provided or invalid mode
        AuthenticationError: If authentication fails
    """
    client = None
    try:
        logger.debug('Creating OpenSearch client')
        client = initialize_client(args)
        yield client
    finally:
        if client is not None:
            try:
                logger.debug('Closing OpenSearch client')
                await client.close()
            except Exception as e:
                # Log but don't propagate cleanup errors to avoid masking original errors
                logger.warning(f'Error closing OpenSearch client: {e}')


# Private Implementation Functions
def _netloc_with_explicit_port(parsed: ParseResult, port: int) -> str:
    host = parsed.hostname
    if not host:
        return parsed.netloc
    host_literal = f'[{host}]' if ':' in host and not host.startswith('[') else host
    if parsed.username is not None:
        userinfo = parsed.username
        if parsed.password is not None:
            userinfo = f'{userinfo}:{parsed.password}'
        return f'{userinfo}@{host_literal}:{port}'
    return f'{host_literal}:{port}'


def _parsed_with_default_ports(parsed: ParseResult) -> tuple[str, ParseResult]:
    """Return ``(url, parsed)`` with :80/:443 in netloc when http(s) omits a port."""
    if parsed.port is not None:
        return urlunparse(parsed), parsed
    port = _DEFAULT_PORTS_BY_SCHEME.get(parsed.scheme)
    if port is None or not parsed.hostname:
        return urlunparse(parsed), parsed
    new_netloc = _netloc_with_explicit_port(parsed, port)
    new_parsed = parsed._replace(netloc=new_netloc)
    return urlunparse(new_parsed), new_parsed


def _log_connection_event(
    auth_method: str,
    datasource_type: str,
    opensearch_url: str,
    error: str,
) -> None:
    """Emit a structured error log event for failed datasource connections.

    Only logs failures because AsyncOpenSearch() construction does not
    actually connect — a "success" event would be misleading.
    """
    logger.error(
        f'Datasource connection failed: {auth_method} ({datasource_type})',
        extra={
            'event_type': 'datasource_connection',
            'auth_method': auth_method,
            'datasource_type': datasource_type,
            'status': 'error',
            'opensearch_url': opensearch_url,
            'error': error,
        },
    )


def _initialize_client_single_mode() -> AsyncOpenSearch:
    """Initialize OpenSearch client for single mode using environment variables.

    Single mode uses environment variables for connection, with optional header-based auth:
    - OPENSEARCH_URL (required, or from headers if OPENSEARCH_HEADER_AUTH=true)
    - OPENSEARCH_HEADER_AUTH: If true, prefer headers over env vars for auth
    - OPENSEARCH_USERNAME / OPENSEARCH_PASSWORD
    - AWS_PROFILE / AWS_REGION
    - AWS_IAM_ARN
    - OPENSEARCH_NO_AUTH
    - AWS_OPENSEARCH_SERVERLESS
    - OPENSEARCH_TIMEOUT
    - BEARER

    Returns:
        OpenSearch: An initialized OpenSearch client instance

    Raises:
        ConfigurationError: If required environment variables are not set
        AuthenticationError: If authentication fails
    """
    try:
        # Get connection parameters from environment variables
        opensearch_url = os.getenv('OPENSEARCH_URL', '').strip()
        opensearch_username = os.getenv('OPENSEARCH_USERNAME', '').strip()
        opensearch_password = os.getenv('OPENSEARCH_PASSWORD', '').strip()
        opensearch_no_auth = os.getenv('OPENSEARCH_NO_AUTH', '').lower() == 'true'
        iam_arn = os.getenv('AWS_IAM_ARN', '').strip()
        # Prefer command line argument, then environment variable
        profile = get_profile() or os.getenv('AWS_PROFILE', '').strip()
        is_serverless_mode = os.getenv('AWS_OPENSEARCH_SERVERLESS', '').lower() == 'true'
        opensearch_timeout_str = os.getenv('OPENSEARCH_TIMEOUT', '').strip()
        opensearch_timeout = int(opensearch_timeout_str) if opensearch_timeout_str else None
        ssl_verify = os.getenv('OPENSEARCH_SSL_VERIFY', 'true').lower() != 'false'
        opensearch_ca_cert_path = _get_env_path('OPENSEARCH_CA_CERT_PATH')
        opensearch_client_cert_path = _get_env_path('OPENSEARCH_CLIENT_CERT_PATH')
        opensearch_client_key_path = _get_env_path('OPENSEARCH_CLIENT_KEY_PATH')

        # Parse max response size from environment
        max_response_size_str = os.getenv('OPENSEARCH_MAX_RESPONSE_SIZE', '').strip()
        max_response_size = None
        if max_response_size_str:
            try:
                max_response_size = int(max_response_size_str)
                if max_response_size <= 0:
                    logger.warning(
                        f'Invalid OPENSEARCH_MAX_RESPONSE_SIZE value {max_response_size}, using default'
                    )
                    max_response_size = None
            except ValueError:
                logger.warning(
                    f'Invalid OPENSEARCH_MAX_RESPONSE_SIZE format: {max_response_size_str}, using default'
                )
        aws_access_key_id = None
        aws_secret_access_key = None
        aws_session_token = None
        bearer_auth_header = None

        # Default to region from environment
        aws_region = get_aws_region_single_mode()

        # Check if header auth is enabled and update variables accordingly
        use_header_auth = os.getenv('OPENSEARCH_HEADER_AUTH', '').lower() == 'true'
        if use_header_auth:
            header_auth = _get_auth_from_headers()
            header_url = header_auth.get('opensearch_url')
            if header_url:
                opensearch_url = header_url
            header_service = header_auth.get('aws_service_name')
            if header_service:
                is_serverless_mode = header_service.lower() == OPENSEARCH_SERVERLESS_SERVICE
            aws_access_key_id = header_auth.get('aws_access_key_id')
            aws_secret_access_key = header_auth.get('aws_secret_access_key')
            aws_session_token = header_auth.get('aws_session_token')
            # Override region if provided in headers
            header_region = header_auth.get('aws_region')
            if header_region:
                aws_region = header_region
            # Override Basic auth credentials if provided in headers
            header_username = header_auth.get('opensearch_username')
            header_password = header_auth.get('opensearch_password')
            if header_username and header_password:
                opensearch_username = header_username
                opensearch_password = header_password
            # Pass through Bearer token if provided in headers
            bearer_auth_header = header_auth.get('bearer_auth_header')

        # Validate URL after potential header override (must come from either env or headers)
        if not opensearch_url or not opensearch_url.strip():
            if use_header_auth:
                raise ConfigurationError(
                    'OPENSEARCH_URL is required. Please provide it either in request headers (opensearch-url) '
                    'or via the OPENSEARCH_URL environment variable'
                )
            else:
                raise ConfigurationError(
                    'OPENSEARCH_URL environment variable is required but not set'
                )

        logger.info(f'Initializing single mode OpenSearch client for URL: {opensearch_url}')

        # Use common client creation function
        return _create_opensearch_client(
            opensearch_url=opensearch_url,
            opensearch_username=opensearch_username,
            opensearch_password=opensearch_password,
            opensearch_no_auth=opensearch_no_auth,
            iam_arn=iam_arn,
            profile=profile,
            is_serverless_mode=is_serverless_mode,
            opensearch_timeout=opensearch_timeout,
            aws_region=aws_region,
            ssl_verify=ssl_verify,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token,
            max_response_size=max_response_size,
            bearer_auth_header=bearer_auth_header,
            opensearch_ca_cert_path=opensearch_ca_cert_path,
            opensearch_client_cert_path=opensearch_client_cert_path,
            opensearch_client_key_path=opensearch_client_key_path,
        )

    except (ConfigurationError, AuthenticationError):
        raise
    except Exception as e:
        logger.error(f'Unexpected error in single mode client initialization: {e}')
        raise ConfigurationError(f'Failed to initialize single mode client: {e}')


def _initialize_client_multi_mode(cluster_info: ClusterInfo) -> AsyncOpenSearch:
    """Initialize OpenSearch client for multi mode using cluster configuration.

    Multi mode uses cluster configuration from the provided ClusterInfo object.

    Args:
        cluster_info: Cluster information object

    Returns:
        OpenSearch: An initialized OpenSearch client instance

    Raises:
        ConfigurationError: If cluster_info is invalid
        AuthenticationError: If authentication fails
    """
    if not cluster_info:
        raise ConfigurationError('Cluster info cannot be None for multi mode')
    try:
        logger.info(
            f'Initializing multi mode OpenSearch client for cluster: {cluster_info.opensearch_url}'
        )
        # Extract parameters from cluster info
        opensearch_url = cluster_info.opensearch_url
        opensearch_username = cluster_info.opensearch_username or ''
        opensearch_password = cluster_info.opensearch_password or ''
        opensearch_no_auth = cluster_info.opensearch_no_auth or False
        iam_arn = cluster_info.iam_arn or ''
        # Prefer cluster config, then command line argument, then environment variable
        profile = cluster_info.profile or get_profile() or os.getenv('AWS_PROFILE', '').strip()
        is_serverless_mode = cluster_info.is_serverless or False
        opensearch_timeout = (
            cluster_info.timeout if cluster_info.timeout is not None else DEFAULT_TIMEOUT
        )
        ssl_verify = True  # Default to secure
        if cluster_info.ssl_verify is not None:
            ssl_verify = cluster_info.ssl_verify
        opensearch_ca_cert_path = _normalize_path_value(cluster_info.opensearch_ca_cert_path)
        opensearch_client_cert_path = _normalize_path_value(
            cluster_info.opensearch_client_cert_path
        )
        opensearch_client_key_path = _normalize_path_value(
            cluster_info.opensearch_client_key_path
        )

        # Get max response size from cluster config, fallback to environment variable
        max_response_size = cluster_info.max_response_size
        if max_response_size is None:
            max_response_size_str = os.getenv('OPENSEARCH_MAX_RESPONSE_SIZE', '').strip()
            if max_response_size_str:
                try:
                    max_response_size = int(max_response_size_str)
                    if max_response_size <= 0:
                        logger.warning(
                            f'Invalid OPENSEARCH_MAX_RESPONSE_SIZE value {max_response_size}, using default'
                        )
                        max_response_size = None
                except ValueError:
                    logger.warning(
                        f'Invalid OPENSEARCH_MAX_RESPONSE_SIZE format: {max_response_size_str}, using default'
                    )

        aws_access_key_id = None
        aws_secret_access_key = None
        aws_session_token = None
        bearer_auth_header = None

        # Default to region from cluster config
        aws_region = get_aws_region_multi_mode(cluster_info)

        # Check if header auth is enabled and update variables accordingly
        use_header_auth = cluster_info.opensearch_header_auth or False
        if use_header_auth:
            header_auth = _get_auth_from_headers()
            header_url = header_auth.get('opensearch_url')
            if header_url:
                opensearch_url = header_url
            header_service = header_auth.get('aws_service_name')
            if header_service:
                is_serverless_mode = header_service.lower() == OPENSEARCH_SERVERLESS_SERVICE
            aws_access_key_id = header_auth.get('aws_access_key_id')
            aws_secret_access_key = header_auth.get('aws_secret_access_key')
            aws_session_token = header_auth.get('aws_session_token')
            # Override region if provided in headers
            header_region = header_auth.get('aws_region')
            if header_region:
                aws_region = header_region
            # Override Basic auth credentials if provided in headers
            header_username = header_auth.get('opensearch_username')
            header_password = header_auth.get('opensearch_password')
            if header_username and header_password:
                opensearch_username = header_username
                opensearch_password = header_password
            # Pass through Bearer token if provided in headers
            bearer_auth_header = header_auth.get('bearer_auth_header')

        # Use common client creation function
        return _create_opensearch_client(
            opensearch_url=opensearch_url,
            opensearch_username=opensearch_username,
            opensearch_password=opensearch_password,
            opensearch_no_auth=opensearch_no_auth,
            iam_arn=iam_arn,
            profile=profile,
            is_serverless_mode=is_serverless_mode,
            opensearch_timeout=opensearch_timeout,
            aws_region=aws_region,
            ssl_verify=ssl_verify,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token,
            max_response_size=max_response_size,
            bearer_auth_header=bearer_auth_header,
            opensearch_ca_cert_path=opensearch_ca_cert_path,
            opensearch_client_cert_path=opensearch_client_cert_path,
            opensearch_client_key_path=opensearch_client_key_path,
        )

    except (ConfigurationError, AuthenticationError):
        raise
    except Exception as e:
        logger.error(
            f'Unexpected error in multi mode client initialization for cluster "{cluster_info.opensearch_url}": {e}'
        )
        raise ConfigurationError(
            f'Failed to initialize multi mode client for cluster "{cluster_info.opensearch_url}": {e}'
        )


def _create_opensearch_client(
    opensearch_url: str,
    opensearch_username: str = '',
    opensearch_password: str = '',
    opensearch_no_auth: bool = False,
    iam_arn: str = '',
    profile: str = '',
    is_serverless_mode: bool = False,
    opensearch_timeout: Optional[int] = None,
    aws_region: Optional[str] = None,
    ssl_verify: bool = True,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
    aws_session_token: Optional[str] = None,
    max_response_size: Optional[int] = None,
    bearer_auth_header: Optional[str] = None,
    opensearch_ca_cert_path: Optional[str] = None,
    opensearch_client_cert_path: Optional[str] = None,
    opensearch_client_key_path: Optional[str] = None,
) -> AsyncOpenSearch:
    """Common function to create OpenSearch client with authentication.

    This function handles the common authentication logic used by both
    single mode and multi mode client initialization.

    Args:
        opensearch_url: The OpenSearch cluster URL
        opensearch_username: Username for basic auth
        opensearch_password: Password for basic auth
        opensearch_no_auth: Whether to skip authentication
        iam_arn: IAM role ARN for role-based authentication
        profile: AWS profile name
        is_serverless_mode: Whether this is OpenSearch Serverless
        opensearch_timeout: Connection timeout in seconds (None uses default)
        aws_region: AWS region for authentication
        ssl_verify: Whether to verify SSL certificates (default: True)
        aws_access_key_id: AWS access key ID from headers (optional)
        aws_secret_access_key: AWS secret access key from headers (optional)
        aws_session_token: AWS session token from headers (optional)
        max_response_size: Maximum response size in bytes (None means no limit)
        bearer_auth_header: Authorization Bearer header value (optional)
        opensearch_ca_cert_path: Path to the CA certificate bundle for verifying TLS
        opensearch_client_cert_path: Path to the client certificate for mTLS
        opensearch_client_key_path: Path to the client private key for mTLS

    Returns:
        OpenSearch: An initialized OpenSearch client instance

    Raises:
        ConfigurationError: If opensearch_url is missing or invalid
        AuthenticationError: If authentication fails
        ResponseSizeExceededError: If response exceeds max_response_size
    """
    # Validate inputs
    if not opensearch_url or not opensearch_url.strip():
        raise ConfigurationError('OpenSearch URL must be provided and cannot be empty')

    opensearch_url = opensearch_url.strip()

    # Parse and validate; only when scheme is http/https and no port is given, append port.
    try:
        parsed_url = urlparse(opensearch_url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise ValueError('Invalid URL format')
        opensearch_url, parsed_url = _parsed_with_default_ports(parsed_url)
    except Exception as e:
        raise ConfigurationError(f'Invalid OpenSearch URL format: {opensearch_url}. Error: {e}')

    # Determine service name and datasource type
    service_name = OPENSEARCH_SERVERLESS_SERVICE if is_serverless_mode else OPENSEARCH_SERVICE
    datasource_type = 'aoss' if is_serverless_mode else 'aos'

    if is_serverless_mode:
        logger.info('Initializing OpenSearch Serverless client with service name: aoss')

    # Parse timeout
    timeout = opensearch_timeout if opensearch_timeout is not None else DEFAULT_TIMEOUT
    if timeout <= 0:
        logger.warning(f'Invalid timeout value {timeout}, using default {DEFAULT_TIMEOUT}')
        timeout = DEFAULT_TIMEOUT

    # Determine response size limit
    response_size_limit = (
        max_response_size if max_response_size is not None else DEFAULT_MAX_RESPONSE_SIZE
    )
    tls_config = _build_tls_kwargs(
        ssl_verify=ssl_verify,
        opensearch_ca_cert_path=opensearch_ca_cert_path,
        opensearch_client_cert_path=opensearch_client_cert_path,
        opensearch_client_key_path=opensearch_client_key_path,
    )

    # Build client configuration with buffered connection
    client_kwargs: Dict[str, Any] = {
        'hosts': [opensearch_url],
        'use_ssl': (parsed_url.scheme == 'https'),
        'verify_certs': ssl_verify,
        'connection_class': BufferedAsyncHttpConnection,
        'timeout': timeout,
        'max_response_size': response_size_limit,
        'headers': {'user-agent': USER_AGENT},
    }
    client_kwargs.update(tls_config)

    if response_size_limit is not None:
        logger.info(
            f'Configuring OpenSearch client with max_response_size={response_size_limit} bytes'
        )
    else:
        logger.info('Configuring OpenSearch client with no response size limit')

    # Create boto3 session
    try:
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    except Exception as e:
        logger.warning(f"Failed to create boto3 session with profile '{profile}': {e}")
        session = boto3.Session()

    # Authentication logic with proper error handling
    try:
        # 1. No authentication
        if opensearch_no_auth:
            logger.info('[NO AUTH] Attempting connection without authentication')
            try:
                return AsyncOpenSearch(**client_kwargs)
            except Exception as e:
                _log_connection_event('no_auth', datasource_type, opensearch_url, str(e))
                raise AuthenticationError(f'Failed to connect without authentication: {e}')

        # 2. Header-based Authorization (Bearer token)
        if bearer_auth_header:
            logger.info('[HEADER AUTH] Using Authorization Bearer header')
            try:
                client_kwargs['headers'] = {'Authorization': bearer_auth_header}
                return AsyncOpenSearch(**client_kwargs)
            except Exception as e:
                _log_connection_event(
                    'header_auth_bearer', datasource_type, opensearch_url, str(e)
                )
                raise AuthenticationError(
                    f'Failed to authenticate with Authorization Bearer header: {e}'
                )

        # 3. Header-based AWS credentials authentication (highest priority when provided)
        if aws_access_key_id and aws_secret_access_key and aws_region:
            logger.info('[HEADER AUTH] Using AWS credentials from headers')
            try:
                if not aws_region or (isinstance(aws_region, str) and not aws_region.strip()):
                    raise AuthenticationError(
                        'AWS region is required for header-based authentication'
                    )
                credentials = Credentials(
                    access_key=aws_access_key_id,
                    secret_key=aws_secret_access_key,
                    token=aws_session_token,
                )
                aws_auth = AWSV4SignerAsyncAuth(
                    credentials=credentials, region=aws_region.strip(), service=service_name
                )
                client_kwargs['http_auth'] = aws_auth
                return AsyncOpenSearch(**client_kwargs)
            except Exception as e:
                _log_connection_event('header_auth', datasource_type, opensearch_url, str(e))
                raise AuthenticationError(f'Failed to authenticate with header credentials: {e}')

        # 4. IAM role authentication
        if iam_arn and iam_arn.strip():
            logger.info(f'[IAM AUTH] Using IAM role authentication: {iam_arn}')
            try:
                if not aws_region or (isinstance(aws_region, str) and not aws_region.strip()):
                    raise AuthenticationError('AWS region is required for IAM role authentication')

                sts_client = session.client('sts', region_name=aws_region)
                assumed_role = sts_client.assume_role(
                    RoleArn=iam_arn.strip(), RoleSessionName='OpenSearchClientSession'
                )
                creds_dict = assumed_role['Credentials']
                credentials = Credentials(
                    access_key=creds_dict['AccessKeyId'],
                    secret_key=creds_dict['SecretAccessKey'],
                    token=creds_dict.get('SessionToken'),
                )

                aws_auth = AWSV4SignerAsyncAuth(
                    credentials=credentials, region=aws_region.strip(), service=service_name
                )
                client_kwargs['http_auth'] = aws_auth
                return AsyncOpenSearch(**client_kwargs)
            except Exception as e:
                _log_connection_event('iam_auth', datasource_type, opensearch_url, str(e))
                raise AuthenticationError(f'Failed to assume IAM role {iam_arn}: {e}')

        # 5. Basic authentication
        if opensearch_username and opensearch_password:
            logger.info(f'[BASIC AUTH] Using basic authentication for user: {opensearch_username}')
            try:
                client_kwargs['http_auth'] = (opensearch_username.strip(), opensearch_password)
                return AsyncOpenSearch(**client_kwargs)
            except Exception as e:
                _log_connection_event('basic_auth', datasource_type, opensearch_url, str(e))
                raise AuthenticationError(f'Failed to connect with basic authentication: {e}')

        # 6. AWS credentials authentication
        logger.info('[AWS CREDS] Attempting AWS credentials authentication')
        try:
            if not aws_region or (isinstance(aws_region, str) and not aws_region.strip()):
                raise AuthenticationError(
                    'AWS region is required for AWS credentials authentication'
                )

            credentials = session.get_credentials()
            if not credentials:
                raise AuthenticationError('No AWS credentials found in session')

            aws_auth = AWSV4SignerAsyncAuth(
                credentials=credentials, region=aws_region.strip(), service=service_name
            )
            client_kwargs['http_auth'] = aws_auth
            return AsyncOpenSearch(**client_kwargs)
        except Exception as e:
            _log_connection_event('aws_creds', datasource_type, opensearch_url, str(e))
            raise AuthenticationError(f'Failed to authenticate with AWS credentials: {e}')

    except AuthenticationError:
        raise
    except Exception as e:
        logger.error(f'Unexpected error during authentication: {e}')
        raise AuthenticationError(f'Unexpected authentication error: {e}')

    # This should never be reached, but just in case
    raise AuthenticationError('No valid authentication method provided for OpenSearch')


def _get_env_path(env_var_name: str) -> Optional[str]:
    """Return a normalized path value from the environment."""
    return _normalize_path_value(os.getenv(env_var_name, ''))


def _normalize_path_value(path_value: Optional[str]) -> Optional[str]:
    """Normalize a configured filesystem path, treating blank values as unset."""
    if path_value is None:
        return None

    normalized_path = path_value.strip()
    if not normalized_path:
        return None

    return normalized_path


def _validate_tls_file_path(path: str, description: str) -> str:
    """Validate that a configured TLS file path exists and is readable."""
    if not os.path.isfile(path):
        raise ConfigurationError(f'{description} file does not exist or is not a file: {path}')

    if not os.access(path, os.R_OK):
        raise ConfigurationError(f'{description} file is not readable: {path}')

    return path


def _build_tls_kwargs(
    ssl_verify: bool,
    opensearch_ca_cert_path: Optional[str] = None,
    opensearch_client_cert_path: Optional[str] = None,
    opensearch_client_key_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Build TLS-related OpenSearch client kwargs from configured certificate paths."""
    tls_kwargs: Dict[str, Any] = {}
    has_client_cert = opensearch_client_cert_path is not None
    has_client_key = opensearch_client_key_path is not None

    if has_client_cert != has_client_key:
        raise ConfigurationError(
            'OpenSearch mTLS requires both client certificate and client key paths to be set'
        )

    if opensearch_ca_cert_path is not None:
        tls_kwargs['ca_certs'] = _validate_tls_file_path(
            opensearch_ca_cert_path, 'OpenSearch CA certificate'
        )

    if has_client_cert and has_client_key:
        tls_kwargs['client_cert'] = _validate_tls_file_path(
            opensearch_client_cert_path, 'OpenSearch client certificate'
        )
        tls_kwargs['client_key'] = _validate_tls_file_path(
            opensearch_client_key_path, 'OpenSearch client key'
        )
        if not ssl_verify and 'ca_certs' not in tls_kwargs:
            logger.warning(
                'OpenSearch mTLS is configured with SSL verification disabled and no CA bundle'
            )

    return tls_kwargs


def get_aws_region_single_mode() -> Optional[str]:
    """Get AWS region for single mode using environment variables.

    Priority order:
    1. AWS_REGION environment variable
    2. Profile (command line argument, then environment variable)
    3. Default boto3 session region

    Returns:
        Optional[str]: AWS region, or None if not available (acceptable for basic auth/no auth)

    """
    try:
        # Try AWS_REGION first
        aws_region = os.getenv('AWS_REGION', '').strip()
        if aws_region:
            logger.debug(f'Using AWS_REGION: {aws_region}')
            return aws_region

        # Try command line argument, then environment variable
        aws_profile = get_profile() or os.getenv('AWS_PROFILE', '').strip()
        if aws_profile:
            try:
                session = boto3.Session(profile_name=aws_profile)
                region = session.region_name
                if region:
                    logger.debug(f"Using region from AWS_PROFILE '{aws_profile}': {region}")
                    return region
            except Exception as e:
                logger.warning(f"Failed to get region from AWS_PROFILE '{aws_profile}': {e}")

        # Fall back to default session
        try:
            session = boto3.Session()
            region = session.region_name
            if region:
                logger.debug(f'Using default boto3 session region: {region}')
                return region
        except Exception as e:
            logger.warning(f'Failed to get region from default boto3 session: {e}')

        # Return None if region cannot be determined
        logger.debug('No AWS region found, but this may be acceptable for basic auth or no auth')
        return None

    except Exception as e:
        logger.error(f'Unexpected error getting AWS region for single mode: {e}')
        return None


def get_aws_region_multi_mode(cluster_info: ClusterInfo) -> Optional[str]:
    """Get AWS region for multi mode using cluster configuration.

    Priority order:
    1. cluster_info.aws_region
    2. Region from cluster_info.profile
    3. AWS_REGION environment variable
    4. Profile (command line argument, then environment variable)
    5. Default boto3 session region

    Args:
        cluster_info: Cluster information

    Returns:
        Optional[str]: AWS region, or None if not available (acceptable for basic auth/no auth)

    """
    try:
        # Try cluster-specific region first
        if cluster_info.aws_region and cluster_info.aws_region.strip():
            logger.debug(f'Using cluster-specific AWS region: {cluster_info.aws_region}')
            return cluster_info.aws_region.strip()

        # Try cluster-specific profile
        if cluster_info.profile and cluster_info.profile.strip():
            try:
                session = boto3.Session(profile_name=cluster_info.profile)
                region = session.region_name
                if region:
                    logger.debug(
                        f"Using region from cluster profile '{cluster_info.profile}': {region}"
                    )
                    return region
            except Exception as e:
                logger.warning(
                    f"Failed to get region from cluster profile '{cluster_info.profile}': {e}"
                )

        # Fall back to environment variables (same as single mode)
        return get_aws_region_single_mode()

    except Exception as e:
        logger.error(f'Unexpected error getting AWS region for multi mode: {e}')
        raise ConfigurationError(f"Failed to get AWS region for cluster '{cluster_info}': {e}")


def _get_auth_from_headers() -> Dict[str, Optional[str]]:
    """Extract authentication parameters from request headers.

    Returns:
        Dict containing:
        - opensearch_url: OpenSearch cluster URL
        - aws_region: AWS region
        - aws_access_key_id: AWS access key ID
        - aws_secret_access_key: AWS secret access key
        - aws_session_token: AWS session token
        - aws_service_name: AWS service name (es or aoss)
        - opensearch_username: Username from Basic auth (Authorization header)
        - opensearch_password: Password from Basic auth (Authorization header)
        - bearer_auth_header: Authorization Bearer header value (if provided)
        All values are None if headers are not available or not set.
    """
    result: Dict[str, Optional[str]] = {
        'opensearch_url': None,
        'aws_region': None,
        'aws_access_key_id': None,
        'aws_secret_access_key': None,
        'aws_session_token': None,
        'aws_service_name': None,
        'opensearch_username': None,
        'opensearch_password': None,
        'bearer_auth_header': None,
    }

    try:
        request_context = request_ctx.get()
        if request_context and hasattr(request_context, 'request'):
            request = request_context.request
            if request and isinstance(request, Request):
                headers = dict(request.headers)
                result['opensearch_url'] = headers.get('opensearch-url', '').strip() or None
                result['aws_region'] = headers.get('aws-region', '').strip() or None
                result['aws_access_key_id'] = headers.get('aws-access-key-id', '').strip() or None
                result['aws_secret_access_key'] = (
                    headers.get('aws-secret-access-key', '').strip() or None
                )
                result['aws_session_token'] = headers.get('aws-session-token', '').strip() or None
                result['aws_service_name'] = headers.get('aws-service-name', '').strip() or None

                # Extract auth from Authorization header
                auth_header = headers.get('authorization', '').strip()
                if auth_header:
                    auth_header_lower = auth_header.lower()
                    if auth_header_lower.startswith('bearer '):
                        token = auth_header[7:].strip()
                        if token:
                            result['bearer_auth_header'] = f'Bearer {token}'
                    elif auth_header_lower.startswith('basic '):
                        import base64

                        # Extract the base64 encoded credentials
                        encoded_credentials = auth_header[6:]  # Skip 'Basic '
                        decoded_bytes = base64.b64decode(encoded_credentials)
                        decoded_credentials = decoded_bytes.decode('utf-8')

                        # Split into username and password
                        if ':' in decoded_credentials:
                            username, password = decoded_credentials.split(':', 1)
                            result['opensearch_username'] = username
                            result['opensearch_password'] = password
    except Exception as e:
        logger.debug(f'Could not read headers from request context: {e}')

    return result
