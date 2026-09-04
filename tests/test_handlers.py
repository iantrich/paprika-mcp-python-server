"""Tests for the transport-free dispatch layer.

These cover core.handlers.dispatch, which had no direct tests before it was
extracted out of main() (previously unreachable). The tests focus on the
error-to-text contract every tool relies on: validation errors, API errors,
unexpected exceptions, and unknown tool names all become text results
rather than propagating as exceptions through the transport.

Real client call sites used below (verified by reading handlers.py):
  - "list_recipes" tool -> client.list_recipes(limit=1000)          (handlers.py:235)
  - "regenerate_recipe_image" tool -> client.regenerate_recipe_image(
        uid=..., custom_instructions=...)                            (handlers.py:523)
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from paprika_mcp_server.core.handlers import dispatch
from paprika_mcp_server.paprika_client import (
    PaprikaAPIError,
    PaprikaClient,
    ValidationError,
)


@pytest.fixture
def client():
    # spec_set=PaprikaClient (not plain spec=) matters here: plain `spec`
    # only restricts *reading* undefined attributes, but still allows
    # `client.get_recipes = AsyncMock(...)` to silently succeed even though
    # PaprikaClient has no such method. spec_set additionally restricts
    # *assignment* -- setting an attribute that doesn't exist on the spec
    # raises AttributeError immediately. That means a guessed/wrong method
    # name in a test (e.g. the brief's original `client.get_recipes`, which
    # is not real -- the actual method is `list_recipes`) fails loudly at
    # mock-setup time instead of a MagicMock silently absorbing it and the
    # dispatch code then hitting a real AttributeError that gets swallowed
    # by `except Exception` and produces plausible-looking error text.
    return MagicMock(spec_set=PaprikaClient)


@pytest.mark.asyncio
async def test_unknown_tool_returns_error_text_not_exception(client):
    """An unrecognised tool name must not raise through the transport."""
    result = await dispatch("no_such_tool", {}, client)
    assert len(result) == 1
    assert result[0].type == "text"
    assert "Unknown tool: no_such_tool" in result[0].text


@pytest.mark.asyncio
async def test_validation_error_becomes_text_result(client):
    client.list_recipes = AsyncMock(side_effect=ValidationError("bad input"))
    result = await dispatch("list_recipes", {}, client)
    assert result[0].type == "text"
    assert "Validation error" in result[0].text
    assert "bad input" in result[0].text
    client.list_recipes.assert_awaited_once_with(limit=1000)


@pytest.mark.asyncio
async def test_api_error_becomes_text_result(client):
    # PaprikaAPIError is deliberately NOT caught by its own except clause in
    # dispatch -- it falls through to the generic `except Exception`, so it
    # produces the "Error executing {name}" text rather than something more
    # specific. That is intended behavior, verified here.
    client.list_recipes = AsyncMock(side_effect=PaprikaAPIError("upstream 500"))
    result = await dispatch("list_recipes", {}, client)
    assert result[0].type == "text"
    assert "Error executing list_recipes" in result[0].text
    assert "upstream 500" in result[0].text
    client.list_recipes.assert_awaited_once_with(limit=1000)


@pytest.mark.asyncio
async def test_unexpected_error_becomes_text_result(client):
    client.list_recipes = AsyncMock(side_effect=RuntimeError("boom"))
    result = await dispatch("list_recipes", {}, client)
    assert result[0].type == "text"
    assert "Error executing list_recipes" in result[0].text
    assert "boom" in result[0].text
    client.list_recipes.assert_awaited_once_with(limit=1000)


@pytest.mark.asyncio
async def test_successful_call_returns_content(client):
    client.list_recipes = AsyncMock(
        return_value=[{"name": "Pasta Bolognese", "uid": "123"}]
    )
    result = await dispatch("list_recipes", {}, client)
    assert result[0].type == "text"
    assert "Pasta Bolognese" in result[0].text
    client.list_recipes.assert_awaited_once_with(limit=1000)


@pytest.mark.asyncio
async def test_image_tool_without_generator_is_handled(client):
    """regenerate_recipe_image with no image generator configured must not
    crash -- the client raises ValueError in that case (see
    PaprikaClient.regenerate_recipe_image), and dispatch has a dedicated
    `except ValueError` branch that turns it into user-facing guidance."""
    client.regenerate_recipe_image = AsyncMock(
        side_effect=ValueError("Image generator not configured.")
    )
    result = await dispatch(
        "regenerate_recipe_image", {"uid": "1"}, client, None
    )
    assert result[0].type == "text"
    assert "REPLICATE_API_TOKEN" in result[0].text
    client.regenerate_recipe_image.assert_awaited_once_with(
        uid="1", custom_instructions=""
    )
