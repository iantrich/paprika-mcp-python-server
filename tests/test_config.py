"""get_config() must not choke on a subcommand's own CLI flags."""
import sys
from unittest.mock import patch

from paprika_mcp_server.config import get_config


def test_get_config_ignores_subcommand_flags(monkeypatch):
    """`paprika-mcp serve-http --host X --port N` must still resolve credentials.

    get_config() builds its own parser that knows only --username/--password.
    Using parse_args() there made every subcommand with flags of its own exit
    with "unrecognized arguments" before the server could start.
    """
    monkeypatch.setenv("PAPRIKA_USERNAME", "test@example.com")
    monkeypatch.setenv("PAPRIKA_PASSWORD", "secret")
    argv = ["paprika-mcp", "serve-http", "--host", "127.0.0.1", "--port", "8080"]
    with patch.object(sys, "argv", argv):
        cfg = get_config()
    assert cfg.paprika_username == "test@example.com"
    assert cfg.paprika_password == "secret"
