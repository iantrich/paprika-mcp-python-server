"""Tool dispatch. Transport-free: no HTTP, no stdio, no OAuth."""
import logging
import re
from typing import Any, Optional

from mcp.types import TextContent

from paprika_mcp_server.image_generator import ImageGenerator
from paprika_mcp_server.paprika_client import (
    MealMatchAmbiguousError,
    MealNotFoundError,
    PaprikaClient,
    ValidationError,
)

logger = logging.getLogger(__name__)


# Helper functions for search and filtering
def _search_text(text: str, query: str) -> bool:
    """
    Case-insensitive text search helper.

    Args:
        text: Text to search in
        query: Search query

    Returns:
        True if query is found in text (case-insensitive)
    """
    if not text or not query:
        return False
    return query.lower() in text.lower()


def _format_time_info(recipe: dict[str, Any]) -> str | None:
    """
    Format prep and cook time information.

    Args:
        recipe: Recipe dictionary

    Returns:
        Formatted time string or None if no times available
    """
    times = []
    if recipe.get("prep_time"):
        times.append(f"Prep: {recipe['prep_time']}")
    if recipe.get("cook_time"):
        times.append(f"Cook: {recipe['cook_time']}")
    return ", ".join(times) if times else None


def _ingredient_matches(
    recipe_ingredients: str, search_ingredients: list[str], match_mode: str
) -> bool:
    """
    Check if recipe ingredients match search criteria.

    Args:
        recipe_ingredients: Recipe's ingredient string
        search_ingredients: List of ingredients to search for
        match_mode: "all" (recipe must contain ALL ingredients) or "any" (at least one)

    Returns:
        True if ingredients match according to mode
    """
    if not recipe_ingredients or not search_ingredients:
        return False

    ingredients_lower = recipe_ingredients.lower()

    if match_mode == "all":
        # Recipe must contain ALL specified ingredients
        return all(
            ingredient.lower() in ingredients_lower for ingredient in search_ingredients
        )
    else:  # "any" mode
        # Recipe must contain AT LEAST ONE specified ingredient
        return any(
            ingredient.lower() in ingredients_lower for ingredient in search_ingredients
        )


def _format_recipe_summary(recipe: dict[str, Any]) -> str:
    """
    Format a recipe as a summary string.

    Args:
        recipe: Recipe dictionary

    Returns:
        Formatted recipe summary
    """
    summary = f"• **{recipe['name']}**\n"
    summary += f"  UID: {recipe['uid']}\n"

    if recipe.get("description"):
        summary += f"  Description: {recipe['description']}\n"

    if recipe.get("servings"):
        summary += f"  Servings: {recipe['servings']}\n"

    time_info = _format_time_info(recipe)
    if time_info:
        summary += f"  Time: {time_info}\n"

    if recipe.get("ingredients"):
        # Show first 3 ingredients as preview
        ingredients_lines = recipe["ingredients"].split("\n")
        preview_count = min(3, len(ingredients_lines))
        ingredients_preview = "\n    ".join(ingredients_lines[:preview_count])
        summary += f"  Ingredients:\n    {ingredients_preview}"
        if len(ingredients_lines) > 3:
            summary += f"\n    ... and {len(ingredients_lines) - 3} more"
        summary += "\n"

    return summary


def _parse_time(time_str: str) -> int | None:
    """
    Parse time string to minutes (e.g., '15 mins', '1 hour', '30 minutes').

    Args:
        time_str: Time string to parse

    Returns:
        Time in minutes, or None if parsing fails
    """
    if not time_str:
        return None

    time_str = time_str.lower().strip()
    total_minutes = 0

    # Parse hours
    if "hour" in time_str:
        try:
            parts = time_str.split("hour")[0].strip().split()
            hours = int(parts[-1])
            total_minutes += hours * 60
            # Remove hour part for further parsing
            time_str = time_str.split("hour", 1)[1] if len(time_str.split("hour")) > 1 else ""
        except (ValueError, IndexError):
            pass

    # Parse minutes
    if "min" in time_str:
        try:
            parts = time_str.split("min")[0].strip().split()
            minutes = int(parts[-1])
            total_minutes += minutes
        except (ValueError, IndexError):
            pass

    # If we only have digits, assume minutes
    if total_minutes == 0:
        try:
            # Extract first number found
            numbers = re.findall(r"\d+", time_str)
            if numbers:
                total_minutes = int(numbers[0])
        except (ValueError, IndexError):
            pass

    return total_minutes if total_minutes > 0 else None


async def dispatch(
    name: str,
    arguments: dict[str, Any],
    client: PaprikaClient,
    image_generator: Optional[ImageGenerator] = None,
) -> list[TextContent]:
    """Execute one tool call and return its content.

    Mirrors the error handling the stdio server used: validation and API
    errors become text results rather than exceptions, so the agent sees a
    message instead of a transport failure.
    """
    try:
        if name == "create_recipe":
            result = await client.create_recipe(
                name=arguments["name"],
                ingredients=arguments["ingredients"],
                directions=arguments["directions"],
                description=arguments.get("description", ""),
                notes=arguments.get("notes", ""),
                servings=arguments.get("servings", ""),
                prep_time=arguments.get("prep_time", ""),
                cook_time=arguments.get("cook_time", ""),
                difficulty=arguments.get("difficulty", ""),
                generate_image=arguments.get("generate_image", True),
            )

            # Add image info to response if generated
            response_text = f"Successfully created recipe '{result['name']}' with UID: {result['uid']}"
            if result.get("photo_url"):
                response_text += "\nAI-generated food photography added."

            return [
                TextContent(
                    type="text",
                    text=response_text,
                )
            ]

        elif name == "update_recipe":
            result = await client.update_recipe_partial(
                uid=arguments["uid"],
                **{
                    k: v
                    for k, v in arguments.items()
                    if k != "uid" and v is not None
                },
            )
            return [
                TextContent(
                    type="text",
                    text=f"Successfully updated recipe '{result['name']}'",
                )
            ]

        elif name == "list_recipes":
            limit = arguments.get("limit", 100)
            offset = arguments.get("offset", 0)
            sort_by = arguments.get("sort_by")
            sort_order = arguments.get("sort_order", "asc")
            filter_query = arguments.get("filter_query")
            include_fields = arguments.get("include_fields")
            exclude_fields = arguments.get("exclude_fields")

            # Fetch all recipes (high limit to get complete collection)
            recipes = await client.list_recipes(limit=1000)

            if not recipes:
                return [
                    TextContent(
                        type="text",
                        text="No recipes found in your Paprika account.",
                    )
                ]

            total_count = len(recipes)

            # Apply filtering if query provided
            if filter_query:
                filtered_recipes = []
                for recipe in recipes:
                    if (
                        _search_text(recipe.get("name", ""), filter_query)
                        or _search_text(recipe.get("ingredients", ""), filter_query)
                        or _search_text(recipe.get("description", ""), filter_query)
                    ):
                        filtered_recipes.append(recipe)
                recipes = filtered_recipes

            match_count = len(recipes)

            # Apply sorting if sort_by provided
            if sort_by:
                reverse = sort_order == "desc"

                if sort_by == "name":
                    recipes.sort(key=lambda r: r.get("name", "").lower(), reverse=reverse)
                elif sort_by == "created":
                    recipes.sort(
                        key=lambda r: r.get("created", ""), reverse=reverse
                    )
                elif sort_by == "prep_time":
                    recipes.sort(
                        key=lambda r: _parse_time(r.get("prep_time", "")) or 0,
                        reverse=reverse,
                    )
                elif sort_by == "cook_time":
                    recipes.sort(
                        key=lambda r: _parse_time(r.get("cook_time", "")) or 0,
                        reverse=reverse,
                    )

            # Apply pagination
            paginated_recipes = recipes[offset : offset + limit]
            returned_count = len(paginated_recipes)
            has_more = (offset + limit) < len(recipes)

            # Apply field selection
            if include_fields:
                # Always include UID for recipe identification
                if "uid" not in include_fields:
                    include_fields = include_fields + ["uid"]

                selected_recipes = []
                for recipe in paginated_recipes:
                    selected_recipe = {
                        field: recipe.get(field)
                        for field in include_fields
                        if field in recipe
                    }
                    selected_recipes.append(selected_recipe)
                paginated_recipes = selected_recipes
            elif exclude_fields:
                selected_recipes = []
                for recipe in paginated_recipes:
                    selected_recipe = {
                        k: v
                        for k, v in recipe.items()
                        if k not in exclude_fields or k == "uid"  # Always keep UID
                    }
                    selected_recipes.append(selected_recipe)
                paginated_recipes = selected_recipes

            # Build response with metadata
            recipe_text = ""

            # Add pagination metadata
            if filter_query:
                recipe_text += f"Found {match_count} matching recipes (filtered from {total_count} total)\n"

            recipe_text += f"Showing {returned_count} recipes"
            if offset > 0:
                recipe_text += f" (offset: {offset})"
            if has_more:
                recipe_text += f" - {len(recipes) - offset - limit} more available"
            recipe_text += "\n\n"

            # Format recipe list
            for recipe in paginated_recipes:
                recipe_text += f"• **{recipe.get('name', 'Untitled')}**\n"
                recipe_text += f"  UID: {recipe.get('uid', 'N/A')}\n"

                if recipe.get("description"):
                    recipe_text += f"  Description: {recipe['description']}\n"
                if recipe.get("servings"):
                    recipe_text += f"  Servings: {recipe['servings']}\n"

                time_info = _format_time_info(recipe)
                if time_info:
                    recipe_text += f"  Time: {time_info}\n"

                if recipe.get("last_planned"):
                    recipe_text += f"  Last planned: {recipe['last_planned']}\n"

                if recipe.get("ingredients"):
                    ingredients_lines = recipe["ingredients"].split("\n")
                    ingredients_preview = "\n    ".join(ingredients_lines)
                    recipe_text += (
                        f"  Ingredients:\n    {ingredients_preview}\n"
                    )
                recipe_text += "\n"

            return [TextContent(type="text", text=recipe_text)]

        elif name == "read_recipe":
            uid = arguments.get("uid")
            title = arguments.get("title")

            # Validate that at least one identifier is provided
            if not uid and not title:
                return [
                    TextContent(
                        type="text",
                        text="Error: Either 'uid' or 'title' parameter is required",
                    )
                ]

            # Prefer UID lookup if both are provided
            recipe = None
            if uid:
                recipe = await client.get_recipe_by_uid(str(uid))
                if not recipe:
                    return [
                        TextContent(
                            type="text",
                            text=f"Recipe with UID '{uid}' not found",
                        )
                    ]
            elif title:
                recipe = await client.get_recipe_by_title(str(title))
                if not recipe:
                    return [
                        TextContent(
                            type="text",
                            text=f"Recipe with title '{title}' not found",
                        )
                    ]

            # Format complete recipe details
            recipe_text = f"**{recipe['name']}**\n\n"

            if recipe.get("description"):
                recipe_text += f"**Description:** {recipe['description']}\n\n"

            if recipe.get("servings"):
                recipe_text += f"**Servings:** {recipe['servings']}\n"

            if recipe.get("prep_time"):
                recipe_text += f"**Prep Time:** {recipe['prep_time']}\n"

            if recipe.get("cook_time"):
                recipe_text += f"**Cook Time:** {recipe['cook_time']}\n"

            if recipe.get("difficulty"):
                recipe_text += f"**Difficulty:** {recipe['difficulty']}\n"

            recipe_text += f"\n**Ingredients:**\n{recipe.get('ingredients', 'None')}\n\n"
            recipe_text += f"**Directions:**\n{recipe.get('directions', 'None')}\n\n"

            if recipe.get("notes"):
                recipe_text += f"**Notes:** {recipe['notes']}\n\n"

            recipe_text += f"**UID:** {recipe['uid']}\n"
            recipe_text += f"**Created:** {recipe.get('created', 'Unknown')}\n"

            # Add photo/image fields if present
            if recipe.get("photo_url"):
                recipe_text += f"**Photo URL:** {recipe['photo_url']}\n"
            if recipe.get("image_url"):
                recipe_text += f"**Image URL:** {recipe['image_url']}\n"
            if recipe.get("photo"):
                recipe_text += f"**Photo Data:** [Present - {len(recipe['photo'])} chars]\n"

            return [TextContent(type="text", text=recipe_text)]

        elif name == "regenerate_recipe_image":
            uid = arguments["uid"]
            custom_instructions = arguments.get("custom_instructions", "")

            try:
                result = await client.regenerate_recipe_image(
                    uid=str(uid),
                    custom_instructions=str(custom_instructions) if custom_instructions else ""
                )

                response_text = f"Successfully regenerated AI image for recipe '{result['name']}' (UID: {result['uid']})"
                if custom_instructions:
                    response_text += f"\nApplied custom styling: {custom_instructions}"

                return [
                    TextContent(
                        type="text",
                        text=response_text,
                    )
                ]

            except ValueError as e:
                # Image generator not configured
                return [
                    TextContent(
                        type="text",
                        text=f"Error: {str(e)}\nTo enable AI image generation, set the REPLICATE_API_TOKEN environment variable.",
                    )
                ]
            except Exception as e:
                logger.error(f"Error regenerating image: {str(e)}")
                return [
                    TextContent(
                        type="text",
                        text=f"Error regenerating image: {str(e)}",
                    )
                ]

        elif name == "search_recipes":
            query = arguments["query"]
            search_fields = arguments.get("search_fields", "all")

            # Get all recipes
            recipes = await client.list_recipes(limit=1000)

            if not recipes:
                return [
                    TextContent(
                        type="text",
                        text="No recipes found in your Paprika account.",
                    )
                ]

            # Filter recipes based on search query
            matching_recipes = []
            for recipe in recipes:
                match = False

                if search_fields in ["name", "all"]:
                    if _search_text(recipe.get("name", ""), query):
                        match = True

                if search_fields in ["ingredients", "all"]:
                    if _search_text(recipe.get("ingredients", ""), query):
                        match = True

                if search_fields in ["description", "all"]:
                    if _search_text(recipe.get("description", ""), query):
                        match = True

                if match:
                    matching_recipes.append(recipe)

            if not matching_recipes:
                return [
                    TextContent(
                        type="text",
                        text=f"No recipes found matching '{query}'",
                    )
                ]

            # Sort by relevance (exact name match first)
            def sort_key(recipe):
                name = recipe.get("name", "").lower()
                query_lower = query.lower()
                if name == query_lower:
                    return 0  # Exact match
                elif name.startswith(query_lower):
                    return 1  # Starts with query
                else:
                    return 2  # Contains query

            matching_recipes.sort(key=sort_key)

            # Format results
            result_text = f"Found {len(matching_recipes)} recipes matching '{query}':\n\n"
            for recipe in matching_recipes:
                result_text += _format_recipe_summary(recipe) + "\n"

            return [TextContent(type="text", text=result_text)]

        elif name == "filter_recipes_by_ingredient":
            ingredients = arguments["ingredients"]
            match_mode = arguments.get("match_mode", "all")

            # Get all recipes
            recipes = await client.list_recipes(limit=1000)

            if not recipes:
                return [
                    TextContent(
                        type="text",
                        text="No recipes found in your Paprika account.",
                    )
                ]

            # Filter recipes by ingredients
            matching_recipes = []
            for recipe in recipes:
                recipe_ingredients = recipe.get("ingredients", "")
                if _ingredient_matches(
                    recipe_ingredients, ingredients, match_mode
                ):
                    matching_recipes.append(recipe)

            if not matching_recipes:
                return [
                    TextContent(
                        type="text",
                        text="No recipes found with specified ingredients",
                    )
                ]

            # Format results
            ingredient_list = ", ".join(ingredients)
            mode_text = "ALL" if match_mode == "all" else "ANY"
            result_text = f"Found {len(matching_recipes)} recipes containing {mode_text} of [{ingredient_list}]:\n\n"
            for recipe in matching_recipes:
                result_text += _format_recipe_summary(recipe) + "\n"

            return [TextContent(type="text", text=result_text)]

        elif name == "filter_recipes_by_time":
            max_prep_time = arguments.get("max_prep_time")
            max_cook_time = arguments.get("max_cook_time")
            max_total_time = arguments.get("max_total_time")

            # Validate that at least one time parameter is provided
            if (
                max_prep_time is None
                and max_cook_time is None
                and max_total_time is None
            ):
                return [
                    TextContent(
                        type="text",
                        text="Error: At least one time parameter (max_prep_time, max_cook_time, or max_total_time) is required",
                    )
                ]

            # Get all recipes
            recipes = await client.list_recipes(limit=1000)

            if not recipes:
                return [
                    TextContent(
                        type="text",
                        text="No recipes found in your Paprika account.",
                    )
                ]

            # Filter recipes by time constraints
            matching_recipes = []
            for recipe in recipes:
                prep_mins = _parse_time(recipe.get("prep_time", ""))
                cook_mins = _parse_time(recipe.get("cook_time", ""))

                # Skip recipes with missing time fields
                if max_prep_time is not None and prep_mins is None:
                    continue
                if max_cook_time is not None and cook_mins is None:
                    continue
                if max_total_time is not None and (
                    prep_mins is None or cook_mins is None
                ):
                    continue

                # Apply filters
                matches = True

                if max_prep_time is not None and prep_mins is not None:
                    if prep_mins > max_prep_time:
                        matches = False

                if max_cook_time is not None and cook_mins is not None:
                    if cook_mins > max_cook_time:
                        matches = False

                if max_total_time is not None and prep_mins is not None and cook_mins is not None:
                    if (prep_mins + cook_mins) > max_total_time:
                        matches = False

                if matches:
                    matching_recipes.append(recipe)

            if not matching_recipes:
                return [
                    TextContent(
                        type="text",
                        text="No recipes found matching the specified time constraints",
                    )
                ]

            # Format results
            constraints = []
            if max_prep_time is not None:
                constraints.append(f"prep ≤ {max_prep_time} min")
            if max_cook_time is not None:
                constraints.append(f"cook ≤ {max_cook_time} min")
            if max_total_time is not None:
                constraints.append(f"total ≤ {max_total_time} min")

            constraint_text = ", ".join(constraints)
            result_text = f"Found {len(matching_recipes)} recipes with {constraint_text}:\n\n"
            for recipe in matching_recipes:
                result_text += _format_recipe_summary(recipe) + "\n"

            return [TextContent(type="text", text=result_text)]

        elif name == "add_meal_to_plan":
            meal = arguments.get("meal")
            meal_id = arguments.get("meal_id")
            date = arguments.get("date")
            meal_type = arguments.get("type", "dinner")

            try:
                result = await client.add_meal_to_plan(
                    meal=meal, meal_id=meal_id, date=date, meal_type=meal_type
                )
                all_meals = await client.get_meal_plan(num_days=365, meal_type=None)
                lunch_count = sum(1 for m in all_meals if m.get("type", "").lower() == "lunch")
                dinner_count = sum(1 for m in all_meals if m.get("type", "").lower() == "dinner")
                formatted_date = client._format_date_readable(result["date"])
                response_text = (
                    f"Meal '{result['meal']}' added to the meal plan on {formatted_date}. "
                    f"Now {lunch_count} lunches and {dinner_count} dinners are planned."
                )
                return [TextContent(type="text", text=response_text)]
            except MealNotFoundError as e:
                return [TextContent(type="text", text=f"Meal not found: {str(e)}")]
            except MealMatchAmbiguousError as e:
                match_names = ", ".join(m.get("name", "") for m in e.matches[:5])
                return [TextContent(type="text", text=f"Ambiguous meal name. Matches: {match_names}")]

        elif name == "remove_meal_from_plan":
            meal = arguments.get("meal")
            meal_id = arguments.get("meal_id")
            date = arguments.get("date")
            meal_type = arguments.get("type", "dinner")

            try:
                result = await client.remove_meal_from_plan(
                    meal=meal, meal_id=meal_id, date=date, meal_type=meal_type
                )
                formatted_date = client._format_date_readable(result["date"])
                response_text = (
                    f"Meal '{result['meal']}' removed from meal plan on {formatted_date}"
                )
                return [TextContent(type="text", text=response_text)]
            except MealNotFoundError as e:
                return [TextContent(type="text", text=f"Meal not found: {str(e)}")]

        elif name == "list_meal_plan":
            num_days = arguments.get("num_days", 10)
            meal_type = arguments.get("meal_type", "dinner")

            meals = await client.get_meal_plan(
                num_days=num_days, meal_type=meal_type
            )
            if not meals:
                return [TextContent(type="text", text="No meals planned.")]

            meal_text = f"Meal plan ({meal_type or 'all'}, next {num_days} days):\n\n"
            for entry in meals:
                formatted_date = client._format_date_readable(entry["date"])
                meal_text += f"- {formatted_date}: {entry['meal']}\n"
            return [TextContent(type="text", text=meal_text)]

        elif name == "get_grocery_lists":
            lists = await client.get_grocery_lists()
            if not lists:
                return [
                    TextContent(
                        type="text",
                        text="No grocery lists found in your Paprika account.",
                    )
                ]
            list_text = "Grocery lists:\n"
            for grocery_list in lists:
                list_name = grocery_list.get("name", "")
                is_default = grocery_list.get("is_default", False)
                default_marker = " (default)" if is_default else ""
                list_text += f"- {list_name}{default_marker}\n"
            return [TextContent(type="text", text=list_text)]

        elif name == "get_groceries":
            grocery_list_name = arguments.get("grocery_list_name")
            groceries = await client.get_groceries(grocery_list_name)
            if not groceries:
                list_name = grocery_list_name or "default"
                return [
                    TextContent(
                        type="text",
                        text=f"No groceries found in '{list_name}' list.",
                    )
                ]
            grocery_text = (
                f"Groceries on {grocery_list_name or 'default'} list:\n"
            )
            for grocery in groceries:
                quantity = grocery.get("quantity", "")
                name = grocery.get("name", "")
                grocery_text += f"- {quantity}, {name}\n"
            return [TextContent(type="text", text=grocery_text)]

        elif name == "get_grocery":
            item_name = arguments["item_name"]
            grocery_list_name = arguments.get("grocery_list_name")
            grocery = await client.get_grocery(
                item_name, grocery_list_name
            )
            if not grocery:
                list_name = grocery_list_name or "default"
                return [
                    TextContent(
                        type="text",
                        text=f"Grocery item '{item_name}' not found in '{list_name}' list.",
                    )
                ]
            quantity = grocery.get("quantity", "")
            name = grocery.get("name", "")
            return [
                TextContent(
                    type="text",
                    text=f"Grocery item: {name}\nQuantity: {quantity}",
                )
            ]

        elif name == "add_grocery":
            item_name = arguments["item_name"]
            quantity = arguments.get("quantity", "1")
            if isinstance(quantity, int):
                quantity = str(quantity)
            grocery_list_name = arguments.get("grocery_list_name")
            result = await client.add_grocery(
                item_name, quantity, grocery_list_name
            )
            return [
                TextContent(
                    type="text",
                    text=f"Added {quantity} '{item_name}' to grocery list. Total quantity: {result['quantity']}",
                )
            ]

        elif name == "clear_grocery_list":
            grocery_list_name = arguments.get("grocery_list_name")
            await client.clear_grocery_list(grocery_list_name)
            list_name = grocery_list_name or "default"
            return [
                TextContent(
                    type="text",
                    text=f"Successfully cleared '{list_name}' grocery list.",
                )
            ]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except ValidationError as e:
        # Validation errors are user-facing, return them directly
        logger.warning(f"Validation error in tool {name}: {str(e)}")
        return [
            TextContent(type="text", text=f"Validation error: {str(e)}")
        ]
    except Exception as e:
        logger.error(f"Error in tool {name}: {str(e)}")
        return [
            TextContent(type="text", text=f"Error executing {name}: {str(e)}")
        ]
