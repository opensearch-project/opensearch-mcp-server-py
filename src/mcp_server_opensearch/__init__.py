# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import argparse
import asyncio
import logging
from typing import Dict, List


def parse_unknown_args_to_dict(unknown_args: List[str]) -> Dict[str, str]:
    """Parses a list of unknown arguments into a dictionary."""
    parser = argparse.ArgumentParser()

    # Extract argument keys and track duplicates with warnings
    seen = set()
    duplicates = set()
    arg_keys = set()

    for arg in unknown_args:
        if arg.startswith('--'):
            key = arg.split('=')[0]
            arg_keys.add(key)
            if key in seen:
                duplicates.add(key)
                logging.warning(f"Duplicate argument '{key}' found. Using the latest value.")
            else:
                seen.add(key)

    for key in arg_keys:
        parser.add_argument(key)

    try:
        parsed_args, _ = parser.parse_known_args(unknown_args)
        return {k: v for k, v in vars(parsed_args).items() if v is not None}
    except Exception as e:
        logging.error(f'Error parsing unknown arguments: {e}')
        return {}


def _run_memory_install() -> None:
    """Handle the 'memory install' subcommand — interactive memory setup."""
    import sys
    import os

    from .installer import run_install

    # Parse optional --from-git and --from-local flags
    from_git = ''
    from_local = ''
    args = sys.argv[3:]  # skip 'opensearch-mcp-server-py memory install'
    for i, arg in enumerate(args):
        if arg == '--from-git' and i + 1 < len(args):
            from_git = args[i + 1]
        elif arg.startswith('--from-git='):
            from_git = arg.split('=', 1)[1]
        elif arg == '--from-local' and i + 1 < len(args):
            from_local = os.path.abspath(args[i + 1])
        elif arg.startswith('--from-local='):
            from_local = os.path.abspath(arg.split('=', 1)[1])
        elif arg == '--from-local':
            # --from-local with no value defaults to current directory
            from_local = os.getcwd()

    run_install(from_git=from_git, from_local=from_local)


def _run_install_hooks(argv: list) -> None:
    """Handle the install-hooks subcommand."""
    parser = argparse.ArgumentParser(
        prog='opensearch-mcp-server-py install-hooks',
        description='Install memory lifecycle hooks for AI coding assistants.',
    )
    parser.add_argument(
        '--client',
        required=True,
        choices=['kiro', 'claude-code', 'cursor'],
        help='AI client to install hooks for.',
    )
    parser.add_argument(
        '--scope',
        choices=['workspace', 'user'],
        default='workspace',
        help='Install scope: workspace (project-level, default) or user (global).',
    )
    args = parser.parse_args(argv)

    from .install_hooks import install_hooks

    install_hooks(client=args.client, scope=args.scope)


def main() -> None:
    """
    Main entry point for the OpenSearch MCP Server.
    Handles command line arguments and starts the appropriate server based on transport type.
    """
    # Check for subcommands before full arg parsing
    import sys

    if len(sys.argv) > 2 and sys.argv[1] == 'memory' and sys.argv[2] == 'install':
        _run_memory_install()
        return

    if len(sys.argv) > 1 and sys.argv[1] == 'install-hooks':
        _run_install_hooks(sys.argv[2:])
        return

    # Set up command line argument parser
    parser = argparse.ArgumentParser(description='OpenSearch MCP Server')
    parser.add_argument(
        '--transport',
        choices=['stdio', 'stream'],
        default='stdio',
        help='Transport type (stdio or stream)',
    )
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='Host to bind to (streaming only). Defaults to loopback; pass 0.0.0.0 to expose on all interfaces.',
    )
    parser.add_argument(
        '--port', type=int, default=9900, help='Port to listen on (streaming only)'
    )
    parser.add_argument(
        '--mode',
        choices=['single', 'multi'],
        default='single',
        help='Server mode: single (default) uses environment variables for OpenSearch connection, multi requires explicit connection parameters',
    )
    parser.add_argument(
        '--profile', default='', help='AWS profile to use for OpenSearch connection'
    )
    parser.add_argument(
        '--config',
        dest='config_file_path',
        default='',
        help='Path to a YAML configuration file',
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging',
    )
    parser.add_argument(
        '--log-format',
        choices=['text', 'json'],
        default='text',
        help='Log output format: text (default, human-readable) or json (structured)',
    )

    args, unknown = parser.parse_known_args()

    # Configure logging with appropriate level and format
    from .logging_config import configure_logging

    log_level = logging.DEBUG if args.debug else logging.INFO
    configure_logging(level=log_level, log_format=args.log_format)
    logger = logging.getLogger(__name__)

    logger.info('Starting MCP server...')
    cli_tool_overrides = parse_unknown_args_to_dict(unknown)

    # Import servers lazily to avoid circular imports at module load time
    from .stdio_server import serve as serve_stdio
    from .streaming_server import serve as serve_streaming

    # Start the appropriate server based on transport type
    if args.transport == 'stdio':
        asyncio.run(
            serve_stdio(
                mode=args.mode,
                profile=args.profile,
                config_file_path=args.config_file_path,
                cli_tool_overrides=cli_tool_overrides,
            )
        )
    else:
        asyncio.run(
            serve_streaming(
                host=args.host,
                port=args.port,
                mode=args.mode,
                profile=args.profile,
                config_file_path=args.config_file_path,
                cli_tool_overrides=cli_tool_overrides,
            )
        )


if __name__ == '__main__':
    main()
