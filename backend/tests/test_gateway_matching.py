"""Tests for gateway route matching -- the regex that turns a URL into params."""

from app.models import Route
from app.routers.gateway import _match_route


def route(method: str, path: str) -> Route:
    return Route(id=path, project_id="p", function_id="f", method=method, path=path)


def test_extracts_named_path_params():
    routes = [route("GET", "/users/:id")]
    matched, params = _match_route(routes, "GET", "/users/123")
    assert matched.path == "/users/:id"
    assert params == {"id": "123"}


def test_multiple_params():
    routes = [route("GET", "/users/:id/posts/:postId")]
    _, params = _match_route(routes, "GET", "/users/7/posts/9")
    assert params == {"id": "7", "postId": "9"}


def test_method_must_match():
    assert _match_route([route("GET", "/users")], "POST", "/users") is None


def test_any_method_is_the_fallback_not_the_first_choice():
    routes = [route("ANY", "/users"), route("GET", "/users")]
    matched, _ = _match_route(routes, "GET", "/users")
    assert matched.method == "GET"


def test_params_do_not_match_across_segments():
    """/users/:id must not swallow /users/1/posts."""
    assert _match_route([route("GET", "/users/:id")], "GET", "/users/1/posts") is None


def test_trailing_slash_is_ignored():
    matched, _ = _match_route([route("GET", "/health")], "GET", "/health/")
    assert matched is not None
