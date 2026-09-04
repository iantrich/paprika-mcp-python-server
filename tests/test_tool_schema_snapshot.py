"""The MCP tool surface is a public contract. This test fails if it drifts.

Regenerate deliberately with:
    python scripts/capture_tool_schemas.py
and commit the diff only when the change to the tool surface is intended.
"""
import json
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "tool_schemas.json"

EXPECTED_TOOL_NAMES = [
    "add_grocery",
    "add_meal_to_plan",
    "clear_grocery_list",
    "create_recipe",
    "delete_recipe",
    "filter_recipes_by_ingredient",
    "filter_recipes_by_time",
    "get_groceries",
    "get_grocery",
    "get_grocery_lists",
    "list_meal_plan",
    "list_recipes",
    "read_recipe",
    "regenerate_recipe_image",
    "remove_meal_from_plan",
    "search_recipes",
    "update_recipe",
]


def test_snapshot_has_all_seventeen_tools():
    schemas = json.loads(FIXTURE.read_text())
    assert [t["name"] for t in schemas] == EXPECTED_TOOL_NAMES


def test_every_tool_has_a_description_and_object_schema():
    schemas = json.loads(FIXTURE.read_text())
    for tool in schemas:
        assert tool.get("description"), f"{tool['name']} has no description"
        assert tool["inputSchema"]["type"] == "object", tool["name"]
