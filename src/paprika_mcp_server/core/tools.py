"""The MCP tool surface. Definitions only — no logic, no client."""
from mcp.types import Tool

TOOLS: list[Tool] = [
    Tool(
        name="create_recipe",
        description="Create a new recipe in Paprika. Auto-generates professional AI food photography (~$0.002 per image using Replicate). Set generate_image=false to disable.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The name of the recipe",
                },
                "ingredients": {
                    "type": "string",
                    "description": "Recipe ingredients, one per line",
                },
                "directions": {
                    "type": "string",
                    "description": "Cooking directions/instructions",
                },
                "description": {
                    "type": "string",
                    "description": "Optional recipe description. TIP: Add brief ingredients at the start for quick scanning (format: 'Ingredients: item1, item2, item3\\n\\n[rest of description]')",
                    "default": "",
                },
                "notes": {
                    "type": "string",
                    "description": "Optional cooking notes",
                    "default": "",
                },
                "servings": {
                    "type": "string",
                    "description": "Number of servings",
                    "default": "",
                },
                "prep_time": {
                    "type": "string",
                    "description": "Preparation time (e.g., '15 mins')",
                    "default": "",
                },
                "cook_time": {
                    "type": "string",
                    "description": "Cooking time (e.g., '30 mins')",
                    "default": "",
                },
                "difficulty": {
                    "type": "string",
                    "description": "Difficulty level (Easy, Medium, Hard)",
                    "default": "",
                },
                "generate_image": {
                    "type": "boolean",
                    "description": "Auto-generate AI food photography (default: true). Disable to skip image generation.",
                    "default": True,
                },
            },
            "required": ["name", "ingredients", "directions"],
        },
    ),
    Tool(
        name="update_recipe",
        description="Update a recipe by providing only the fields you want to change. All fields except 'uid' are optional. Omitted fields remain unchanged.",
        inputSchema={
            "type": "object",
            "properties": {
                "uid": {
                    "type": "string",
                    "description": "The UID of the recipe to update",
                },
                "name": {
                    "type": "string",
                    "description": "The name of the recipe (optional)",
                },
                "ingredients": {
                    "type": "string",
                    "description": "Recipe ingredients, one per line (optional)",
                },
                "directions": {
                    "type": "string",
                    "description": "Cooking directions/instructions (optional)",
                },
                "description": {
                    "type": "string",
                    "description": "Recipe description (optional). TIP: Add brief ingredients at the start for quick scanning (format: 'Ingredients: item1, item2, item3\\n\\n[rest of description]')",
                },
                "notes": {
                    "type": "string",
                    "description": "Cooking notes (optional)",
                },
                "servings": {
                    "type": "string",
                    "description": "Number of servings (optional)",
                },
                "prep_time": {
                    "type": "string",
                    "description": "Preparation time (optional)",
                },
                "cook_time": {
                    "type": "string",
                    "description": "Cooking time (optional)",
                },
                "difficulty": {
                    "type": "string",
                    "description": "Difficulty level (optional)",
                },
            },
            "required": ["uid"],
        },
    ),
    Tool(
        name="list_recipes",
        description="List recipes from Paprika with pagination, sorting, filtering, and field selection for large collections",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of recipes to return (default: 100, max: 500)",
                    "default": 100,
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of recipes to skip (for pagination, default: 0)",
                    "default": 0,
                },
                "sort_by": {
                    "type": "string",
                    "description": "Field to sort by: 'name', 'created', 'prep_time', 'cook_time'",
                    "enum": ["name", "created", "prep_time", "cook_time"],
                },
                "sort_order": {
                    "type": "string",
                    "description": "Sort order: 'asc' (ascending) or 'desc' (descending, default: asc)",
                    "enum": ["asc", "desc"],
                    "default": "asc",
                },
                "filter_query": {
                    "type": "string",
                    "description": "Quick text search across name, ingredients, and description",
                },
                "include_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Only return specified fields (e.g., ['name', 'uid', 'ingredients']). UID always included.",
                },
                "exclude_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Omit specified fields (e.g., ['directions', 'notes']). include_fields takes precedence.",
                },
            },
        },
    ),
    Tool(
        name="read_recipe",
        description="Read complete details of a single recipe by UID or title",
        inputSchema={
            "type": "object",
            "properties": {
                "uid": {
                    "type": "string",
                    "description": "The UID of the recipe to read (preferred if both uid and title are provided)",
                },
                "title": {
                    "type": "string",
                    "description": "The exact title of the recipe to read (case-sensitive)",
                },
            },
        },
    ),
    Tool(
        name="delete_recipe",
        description="Delete a recipe from Paprika by moving it to trash. REQUIRES CONFIRMATION. Provide either uid or title to identify the recipe, then call again with confirm=true to proceed with deletion.",
        inputSchema={
            "type": "object",
            "properties": {
                "uid": {
                    "type": "string",
                    "description": "The UID of the recipe to delete (optional if title provided)",
                },
                "title": {
                    "type": "string",
                    "description": "The title of the recipe to delete (optional if uid provided)",
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Must be set to true to confirm deletion. Without this, only shows what will be deleted.",
                },
            },
            "required": ["confirm"],
        },
    ),
    Tool(
        name="regenerate_recipe_image",
        description="Regenerate AI food photography for an existing recipe with optional custom styling instructions. Cost: ~$0.002 per generation. Requires REPLICATE_API_TOKEN to be configured.",
        inputSchema={
            "type": "object",
            "properties": {
                "uid": {
                    "type": "string",
                    "description": "The UID of the recipe to regenerate image for",
                },
                "custom_instructions": {
                    "type": "string",
                    "description": "Optional styling instructions (e.g., 'rustic style, less cream visible', 'darker lighting, wooden background')",
                    "default": "",
                },
            },
            "required": ["uid"],
        },
    ),
    Tool(
        name="search_recipes",
        description="Search for recipes by text query across multiple fields (name, ingredients, description)",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to find in recipes",
                },
                "search_fields": {
                    "type": "string",
                    "description": "Fields to search in: 'name', 'ingredients', 'description', or 'all' (default: 'all')",
                    "enum": ["name", "ingredients", "description", "all"],
                    "default": "all",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="filter_recipes_by_ingredient",
        description="Filter recipes by specific ingredients",
        inputSchema={
            "type": "object",
            "properties": {
                "ingredients": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of ingredients to search for",
                },
                "match_mode": {
                    "type": "string",
                    "description": "Match mode: 'all' (recipe must contain ALL ingredients) or 'any' (at least one ingredient)",
                    "enum": ["all", "any"],
                    "default": "all",
                },
            },
            "required": ["ingredients"],
        },
    ),
    Tool(
        name="filter_recipes_by_time",
        description="Filter recipes by time constraints (prep time, cook time, or total time)",
        inputSchema={
            "type": "object",
            "properties": {
                "max_prep_time": {
                    "type": "integer",
                    "description": "Maximum preparation time in minutes",
                },
                "max_cook_time": {
                    "type": "integer",
                    "description": "Maximum cooking time in minutes",
                },
                "max_total_time": {
                    "type": "integer",
                    "description": "Maximum total time (prep + cook) in minutes",
                },
            },
        },
    ),
    Tool(
        name="add_meal_to_plan",
        description="Add a meal to the meal plan",
        inputSchema={
            "type": "object",
            "properties": {
                "meal": {
                    "type": "string",
                    "description": "Meal name for fuzzy matching (optional if meal_id provided)",
                },
                "meal_id": {
                    "type": "string",
                    "description": "Recipe UUID (optional if meal provided)",
                },
                "date": {
                    "type": "string",
                    "description": 'Date in flexible format - accepts "YYYY-MM-DD", "dd mmm", "dd mmmm", etc. Optional, defaults to next free day.',
                },
                "type": {
                    "type": "string",
                    "description": "Meal type (default: dinner)",
                    "default": "dinner",
                },
            },
        },
    ),
    Tool(
        name="remove_meal_from_plan",
        description="Remove a meal from the meal plan. If no arguments provided, removes meal on latest date in mealplan",
        inputSchema={
            "type": "object",
            "properties": {
                "meal": {
                    "type": "string",
                    "description": "Meal name (optional)",
                },
                "meal_id": {
                    "type": "string",
                    "description": "Recipe UUID (optional)",
                },
                "date": {
                    "type": "string",
                    "description": 'Date in flexible format (optional, defaults to last day with matching meal)',
                },
                "type": {
                    "type": "string",
                    "description": "Meal type for filtering (default: dinner)",
                    "default": "dinner",
                },
            },
        },
    ),
    Tool(
        name="list_meal_plan",
        description="List meal plan entries",
        inputSchema={
            "type": "object",
            "properties": {
                "num_days": {
                    "type": "integer",
                    "description": "Number of days to show (default: 10)",
                    "default": 10,
                },
                "meal_type": {
                    "type": "string",
                    "description": "Filter by meal type (default: dinner)",
                    "default": "dinner",
                },
            },
        },
    ),
    Tool(
        name="get_grocery_lists",
        description="Get all grocery list names from Paprika",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="get_groceries",
        description="Get all groceries from a grocery list",
        inputSchema={
            "type": "object",
            "properties": {
                "grocery_list_name": {
                    "type": "string",
                    "description": "Name of the grocery list (optional, defaults to default list)",
                }
            },
        },
    ),
    Tool(
        name="get_grocery",
        description="Get a specific grocery item by name from a grocery list",
        inputSchema={
            "type": "object",
            "properties": {
                "item_name": {
                    "type": "string",
                    "description": "Name of the grocery item",
                },
                "grocery_list_name": {
                    "type": "string",
                    "description": "Name of the grocery list (optional, defaults to default list)",
                },
            },
            "required": ["item_name"],
        },
    ),
    Tool(
        name="add_grocery",
        description="Add a grocery item to a grocery list (adds to existing quantity if item already exists). Quantity can be an integer or string like '1 kilo', '4 liters', or '-2 kilos' to subtract.",
        inputSchema={
            "type": "object",
            "properties": {
                "item_name": {
                    "type": "string",
                    "description": "Name of the grocery item to add",
                },
                "quantity": {
                    "type": "string",
                    "description": "Quantity to add (default: '1'). Can be a number or string with unit like '1 kilo', '4 liters'. Use negative values like '-2 kilos' to subtract.",
                    "default": "1",
                },
                "grocery_list_name": {
                    "type": "string",
                    "description": "Name of the grocery list (optional, defaults to default list)",
                },
            },
            "required": ["item_name"],
        },
    ),
    Tool(
        name="clear_grocery_list",
        description="Clear all items from a grocery list",
        inputSchema={
            "type": "object",
            "properties": {
                "grocery_list_name": {
                    "type": "string",
                    "description": "Name of the grocery list (optional, defaults to default list)",
                }
            },
        },
    ),
]
