"""Smoke test for the OAuth-protected OpenSearch MCP server (local stack).

Run from the repo root with the .env.example values loaded:
    set -a; source examples/oauth-keycloak/.env.example; set +a
    python examples/oauth-keycloak/smoke.py

With --login it instead starts the server itself over stdio with the browser login
on (public client opensearch-mcp-stdio, no secret, no token exchange) and logs alice
and bob in headlessly:
    python examples/oauth-keycloak/smoke.py --login

Credentials below are the dev-only values from the local Keycloak realm.
"""

import argparse
import asyncio
import html
import httpx2 as httpx  # streamable_http_client(http_client=) requires the httpx2 bundled with mcp
import os
import re
import sys
import tempfile
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from urllib.parse import urljoin


MCP_URL = 'http://127.0.0.1:9900/mcp/'
TOKEN_URL = 'http://localhost:8080/realms/opensearch/protocol/openid-connect/token'
AUTHORIZATION_URL = 'http://localhost:8080/realms/opensearch/protocol/openid-connect/auth'
REDIRECT_URI = 'http://127.0.0.1:9900/oauth/callback'
OPENSEARCH_URL = 'https://localhost:9200'
CA_CERT = 'examples/oauth-keycloak/root-ca.pem'
INDEX = 'smoke-idx'


def seed_index() -> None:
    """Create the smoke index with admin basic auth."""
    auth = ('admin', os.environ['OPENSEARCH_INITIAL_ADMIN_PASSWORD'])
    r = httpx.put(f'{OPENSEARCH_URL}/{INDEX}', auth=auth, verify=CA_CERT)
    if r.status_code not in (200, 400):  # 400 = already exists
        r.raise_for_status()


def get_token(user: str) -> str:
    """Password-grant access token for a dev realm user."""
    r = httpx.post(
        TOKEN_URL,
        data={
            'grant_type': 'password',
            'client_id': 'smoke-test',
            'username': user,
            'password': user,
        },
    )
    r.raise_for_status()
    return r.json()['access_token']


async def list_indices(user: str) -> tuple[bool, str]:
    """Call ListIndexTool as user over MCP; return (is_error, text)."""
    headers = {'Authorization': f'Bearer {get_token(user)}'}
    async with httpx.AsyncClient(headers=headers) as client:
        async with streamable_http_client(MCP_URL, http_client=client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool('ListIndexTool', {})
                text = ' '.join(getattr(c, 'text', '') for c in res.content)
                return bool(res.is_error), text


async def check_no_token() -> str:
    """Unauthenticated request must be rejected with discovery metadata."""
    r = httpx.post(MCP_URL, json={'jsonrpc': '2.0', 'id': 1, 'method': 'ping'})
    assert r.status_code == 401, f'status {r.status_code}'
    assert 'resource_metadata=' in r.headers.get('www-authenticate', ''), 'no resource_metadata'
    return '401 with resource_metadata'


async def check_alice() -> str:
    """Alice (opensearch_reader) must see the seeded index."""
    is_error, text = await list_indices('alice')
    assert not is_error and INDEX in text, f'is_error={is_error} text={text[:200]}'
    return f'lists {INDEX}'


async def check_bob() -> str:
    """Bob (no roles) must get a 403 security_exception from OpenSearch."""
    is_error, text = await list_indices('bob')
    assert is_error and '403' in text and 'security_exception' in text, (
        f'is_error={is_error} text={text[:200]}'
    )
    return f'isError=true: {text[:200]}'


def browser_login(url: str, user: str) -> None:
    """Do what the browser does: log in at Keycloak and follow the redirect to REDIRECT_URI."""
    # Keycloak marks its cookies Secure; browsers still send them to http://localhost, but the
    # httpx cookie jar does not, so keep the cookies in a dict and send them ourselves.
    cookies: dict[str, str] = {}

    def hop(method: str, target: str, **kwargs) -> httpx.Response:
        resp = browser.request(
            method,
            target,
            headers={'Cookie': '; '.join(f'{k}={v}' for k, v in cookies.items())},
            **kwargs,
        )
        for line in resp.headers.get_list('set-cookie'):
            pair, *attrs = [part.strip() for part in line.split(';')]
            name, _, value = pair.partition('=')
            if value and 'max-age=0' not in (a.lower() for a in attrs):
                cookies[name] = value
            else:
                cookies.pop(name, None)
        return resp

    with httpx.Client(follow_redirects=False) as browser:
        r = hop('GET', url)
        for _ in range(8):
            if r.status_code == 200:
                form = re.search(
                    r'<form\b(?=[^>]*\bid="kc-form-login")[^>]*\baction="([^"]+)"', r.text
                )
                assert form, f'no login form: status {r.status_code}, body {r.text[:200]!r}'
                r = hop(
                    'POST',
                    urljoin(str(r.url), html.unescape(form.group(1))),
                    data={'username': user, 'password': user},
                )
                continue
            loc = r.headers.get('location', '')
            assert r.status_code in (301, 302, 303, 307), f'unexpected status {r.status_code}'
            if loc.startswith(REDIRECT_URI):
                done = httpx.get(loc)  # the server's one-shot callback listener
                assert done.status_code == 200, f'callback status {done.status_code}'
                return
            r = hop('GET', urljoin(str(r.url), loc))
        raise AssertionError('redirect cap reached')


async def login_and_list(user: str, token_dir: str, log) -> tuple[str, bool, str]:
    """Start the stdio server, log user in on the first tool call, list indices again."""
    secretless = ('MCP_OAUTH_CLIENT_SECRET', 'MCP_OAUTH_OPENSEARCH_AUDIENCE')
    env = {
        **{k: v for k, v in os.environ.items() if k not in secretless},
        'MCP_OAUTH_CLIENT_ID': 'opensearch-mcp-stdio',
        'MCP_OAUTH_AUTHORIZATION_URL': AUTHORIZATION_URL,
        'MCP_OAUTH_REDIRECT_URI': REDIRECT_URI,
        'MCP_OAUTH_TOKEN_FILE': os.path.join(token_dir, f'{user}.json'),
        'BROWSER': 'true',  # webbrowser runs `true`: no window, the script logs in instead
    }
    params = StdioServerParameters(
        command=sys.executable, args=['-m', 'mcp_server_opensearch'], env=env
    )
    async with stdio_client(params, errlog=log) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            first = await session.call_tool('ListIndexTool', {})
            first_text = ' '.join(getattr(c, 'text', '') for c in first.content)
            url = re.search(r'open: (\S+)', first_text)
            assert first.is_error and url, f'no login URL in first call: {first_text[:200]}'
            await asyncio.to_thread(browser_login, url.group(1), user)
            res = await session.call_tool('ListIndexTool', {})
            text = ' '.join(getattr(c, 'text', '') for c in res.content)
            return url.group(1), bool(res.is_error), text


async def login_checks() -> list:
    """Checks for the stdio browser login, sharing one temp dir and server log."""
    token_dir = tempfile.mkdtemp(prefix='smoke-login-')
    log = open(os.path.join(token_dir, 'server.log'), 'w')
    results = {}

    async def run(user: str):
        if user not in results:
            results[user] = await login_and_list(user, token_dir, log)
        return results[user]

    async def check_login_url() -> str:
        url, _, _ = await run('alice')
        assert url.startswith(AUTHORIZATION_URL + '?'), url
        assert 'code_challenge_method=S256' in url, url
        return 'first tool call returns the Keycloak login URL'

    async def check_alice() -> str:
        _, is_error, text = await run('alice')
        assert not is_error and INDEX in text, f'is_error={is_error} text={text[:200]}'
        return f'lists {INDEX} after login'

    async def check_bob() -> str:
        _, is_error, text = await run('bob')
        assert is_error and '403' in text and 'security_exception' in text, (
            f'is_error={is_error} text={text[:200]}'
        )
        return f'isError=true: {text[:200]}'

    return [('login_url', check_login_url), ('alice', check_alice), ('bob', check_bob)]


async def main(login: bool) -> int:
    """Run all checks; return a process exit code."""
    seed_index()
    failed = False
    checks = (
        await login_checks()
        if login
        else [('no_token', check_no_token), ('alice', check_alice), ('bob', check_bob)]
    )
    for name, check in checks:
        try:
            detail = await check()
            print(f'PASS {name}: {detail}')
        except Exception as e:
            failed = True
            print(f'FAIL {name}: {type(e).__name__}: {e}')
    return 1 if failed else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        '--login',
        action='store_true',
        help='start the server over stdio with the browser login and log in headlessly',
    )
    sys.exit(asyncio.run(main(parser.parse_args().login)))
