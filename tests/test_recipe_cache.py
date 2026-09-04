"""Hash-based recipe cache.

The /sync/recipes index carries only {uid, hash}, so answering any question
about recipe names meant fetching every recipe individually -- ~356 requests
for a 354-entry library, on every list_recipes and every create_recipe. That
rate-limited the account. The index hash is the API's own change token, so an
unchanged recipe can be served from cache instead.
"""
from unittest.mock import AsyncMock, patch

import pytest

from paprika_mcp_server.paprika_client import PaprikaClient


def _index(n, hashes=None):
    return [{"uid": f"u{i}", "hash": (hashes or {}).get(f"u{i}", f"h{i}")} for i in range(n)]


def _recipe(uid):
    return {"uid": uid, "name": f"Recipe {uid}", "in_trash": False}


class _Api:
    """Stands in for the Paprika API and counts per-recipe fetches."""

    def __init__(self, index):
        self.index = index
        self.recipe_fetches = 0

    async def __call__(self, method, path, **kwargs):
        if path == "/sync/recipes":
            return {"result": self.index}
        if path.startswith("/sync/recipe/"):
            self.recipe_fetches += 1
            return {"result": _recipe(path.split("/")[3])}
        return {"result": []}


@pytest.fixture
def client():
    c = PaprikaClient("t@example.com", "pw")
    c.token = "tok"
    return c


@pytest.mark.asyncio
async def test_unchanged_library_is_not_refetched(client):
    """Second pass over an unchanged index costs zero recipe fetches."""
    api = _Api(_index(10))
    with patch.object(client, "_make_authenticated_request", api):
        first = await client._load_recipes_from_index(api.index, prune=True)
        assert api.recipe_fetches == 10
        assert len(first) == 10

        second = await client._load_recipes_from_index(api.index, prune=True)
        assert api.recipe_fetches == 10, "cache did not prevent refetching"
        assert second == first


@pytest.mark.asyncio
async def test_only_changed_hashes_are_refetched(client):
    """A recipe edited elsewhere gets a new hash and is refetched; others aren't."""
    api = _Api(_index(10))
    with patch.object(client, "_make_authenticated_request", api):
        await client._load_recipes_from_index(api.index, prune=True)
        assert api.recipe_fetches == 10

        api.index = _index(10, hashes={"u3": "CHANGED"})
        await client._load_recipes_from_index(api.index, prune=True)
        assert api.recipe_fetches == 11, "expected exactly one refetch"


@pytest.mark.asyncio
async def test_prune_drops_recipes_gone_from_the_index(client):
    api = _Api(_index(5))
    with patch.object(client, "_make_authenticated_request", api):
        await client._load_recipes_from_index(api.index, prune=True)
        assert len(client._recipe_cache) == 5

        api.index = _index(3)
        await client._load_recipes_from_index(api.index, prune=True)
        assert set(client._recipe_cache) == {"u0", "u1", "u2"}


@pytest.mark.asyncio
async def test_prune_false_keeps_entries_outside_a_truncated_index(client):
    """list_recipes passes a truncated index; pruning on it would evict live rows."""
    api = _Api(_index(5))
    with patch.object(client, "_make_authenticated_request", api):
        await client._load_recipes_from_index(api.index, prune=True)
        await client._load_recipes_from_index(api.index[:2], prune=False)
        assert set(client._recipe_cache) == {f"u{i}" for i in range(5)}


@pytest.mark.asyncio
async def test_failed_fetch_is_skipped_and_not_cached(client):
    """A 429 must not poison the cache with a missing or partial recipe."""
    calls = {"n": 0}

    async def flaky(method, path, **kwargs):
        if path == "/sync/recipes":
            return {"result": _index(3)}
        calls["n"] += 1
        if path == "/sync/recipe/u1/":
            raise RuntimeError("429 Too Many Requests")
        return {"result": _recipe(path.split("/")[3])}

    with patch.object(client, "_make_authenticated_request", flaky):
        got = await client._load_recipes_from_index(_index(3), prune=True)

    assert set(got) == {"u0", "u2"}, "failed recipe should be skipped, not fatal"
    assert "u1" not in client._recipe_cache, "failed fetch must not be cached"


@pytest.mark.asyncio
async def test_malformed_body_is_skipped_not_fatal(client):
    async def bad(method, path, **kwargs):
        if path == "/sync/recipes":
            return {"result": _index(2)}
        return {"result": ["not", "a", "dict"]}

    with patch.object(client, "_make_authenticated_request", bad):
        got = await client._load_recipes_from_index(_index(2), prune=True)
    assert got == {}


@pytest.mark.asyncio
async def test_list_recipes_second_call_hits_cache(client):
    """End to end: the tool an agent calls most stops walking the library."""
    api = _Api(_index(8))
    with patch.object(
        client, "get_meal_plan", new_callable=AsyncMock, return_value=[]
    ), patch.object(client, "_make_authenticated_request", api):
        a = await client.list_recipes(limit=1000)
        after_first = api.recipe_fetches
        b = await client.list_recipes(limit=1000)

    assert len(a) == 8 and len(b) == 8
    assert after_first == 8
    assert api.recipe_fetches == 8, "list_recipes refetched an unchanged library"
