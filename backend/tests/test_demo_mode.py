"""
Tests for read-only demo mode.

This is a security boundary on a public host, so the interesting cases are
the ones that must stay OPEN (or the demo is useless) and the ones that must
stay CLOSED (or a stranger gets code execution on the box).
"""

import pytest

from app.middleware.demo_mode import is_blocked


@pytest.mark.parametrize(
    "method,path",
    [
        # Running a deployed function is the whole point of the demo.
        ("POST", "/api/invoke/abc123"),
        ("POST", "/api/gateway/my-project/users"),
        ("DELETE", "/api/gateway/my-project/users/1"),
        # Reads are always fine.
        ("GET", "/api/functions"),
        ("GET", "/api/cluster"),
        ("GET", "/api/projects/abc/env"),
        # CORS preflight must not be rejected.
        ("OPTIONS", "/api/functions"),
    ],
)
def test_allowed(method, path):
    assert is_blocked(method, path) is False


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/functions"),
        ("PUT", "/api/functions/abc123"),
        ("DELETE", "/api/functions/abc123"),
        ("POST", "/api/projects"),
        ("DELETE", "/api/projects/abc123"),
        ("POST", "/api/projects/abc/env"),
        ("PUT", "/api/projects/abc/requirements"),
        ("POST", "/api/projects/abc/database/provision"),
        ("POST", "/api/projects/abc/routes"),
        # The AI assistant has create/update/delete tools. Leaving chat open
        # would hand back everything demo mode closes.
        ("POST", "/api/chat"),
    ],
)
def test_blocked(method, path):
    assert is_blocked(method, path) is True


def test_prefix_match_is_not_a_substring_match():
    """A path that merely mentions "invoke" must not slip through."""
    assert is_blocked("POST", "/api/functions/invoke-lookalike") is True
    assert is_blocked("POST", "/api/invoke") is True
