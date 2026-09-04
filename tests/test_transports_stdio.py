"""Regression tests for the stdio transport's build_runtime() helper.

Covers Finding 1 from the Task 8 review: build_runtime() must not leak the
aiohttp session created inside PaprikaClient.authenticate() when
authentication fails.
"""
from unittest.mock import patch

import pytest

from paprika_mcp_server.paprika_client import PaprikaAPIError, PaprikaClient
from paprika_mcp_server.transports import stdio as stdio_mod


class _FakeConfig:
    """Minimal stand-in for config.Config with no image generation configured."""

    paprika_username = "user@example.com"
    paprika_password = "bad-password"
    replicate_api_token = None


class _AuthFailsAfterSessionClient(PaprikaClient):
    """A PaprikaClient whose authenticate() opens a session, then fails.

    Mirrors the real PaprikaClient.authenticate(): it calls _get_session()
    (which creates and stores self.session) before ever raising, exactly
    like a bad-credentials or malformed-response failure would.
    """

    instances = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _AuthFailsAfterSessionClient.instances.append(self)

    async def authenticate(self):
        await self._get_session()
        raise PaprikaAPIError("401 bad credentials")


@pytest.mark.asyncio
async def test_build_runtime_closes_session_when_authenticate_fails():
    """build_runtime() must close the client's session if authenticate() raises.

    Without the fix, PaprikaClient() is constructed, authenticate() creates
    self.session via _get_session(), then raises. build_runtime() has no
    try/except around the await, so the exception propagates with the
    session still open and no reference to the client available to the
    caller to close it.
    """
    _AuthFailsAfterSessionClient.instances.clear()

    with patch.object(stdio_mod, "get_config", return_value=_FakeConfig()), \
         patch.object(stdio_mod, "PaprikaClient", _AuthFailsAfterSessionClient):
        with pytest.raises(PaprikaAPIError):
            await stdio_mod.build_runtime()

    assert len(_AuthFailsAfterSessionClient.instances) == 1
    client = _AuthFailsAfterSessionClient.instances[0]

    assert client.session is not None, "expected authenticate() to have created a session"
    assert client.session.closed is True, "build_runtime() leaked the aiohttp session on auth failure"
