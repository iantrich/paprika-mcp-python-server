from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from paprika_mcp_server.paprika_client import PaprikaAPIError, PaprikaClient, ValidationError


class TestPaprikaClient:
    @pytest.fixture
    def client(self):
        return PaprikaClient("test@example.com", "testpass")

    @pytest.mark.asyncio
    async def test_authentication_success(self, client):
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.return_value = {"result": {"token": "test_token"}}
            mock_post.return_value.__aenter__.return_value = mock_response
            mock_post.return_value.__aexit__.return_value = None

            token = await client.authenticate()
            assert token == "test_token"
            assert client.token == "test_token"

    @pytest.mark.asyncio
    async def test_authentication_failure(self, client):
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 401
            mock_post.return_value.__aenter__.return_value = mock_response
            mock_post.return_value.__aexit__.return_value = None

            with pytest.raises(PaprikaAPIError):
                await client.authenticate()


class TestInputValidation:
    """Tests for input validation (add-input-validation spec)"""

    @pytest.fixture
    def client(self):
        return PaprikaClient("test@example.com", "testpass")

    # Recipe name validation tests
    def test_validate_recipe_name_empty(self, client):
        """Test that empty recipe name raises ValidationError"""
        with pytest.raises(ValidationError, match="Recipe name cannot be empty"):
            client._validate_recipe_name("")

    def test_validate_recipe_name_whitespace_only(self, client):
        """Test that whitespace-only recipe name raises ValidationError"""
        with pytest.raises(ValidationError, match="Recipe name cannot be empty"):
            client._validate_recipe_name("   ")

    def test_validate_recipe_name_none(self, client):
        """Test that None recipe name raises ValidationError"""
        with pytest.raises(ValidationError, match="Recipe name cannot be empty"):
            client._validate_recipe_name(None)

    def test_validate_recipe_name_too_long(self, client):
        """Test that recipe name over 200 chars raises ValidationError"""
        long_name = "a" * 201
        with pytest.raises(ValidationError, match="200 characters or less"):
            client._validate_recipe_name(long_name)

    def test_validate_recipe_name_valid(self, client):
        """Test that valid recipe name passes validation"""
        client._validate_recipe_name("Spaghetti Carbonara")  # Should not raise

    # Ingredients validation tests
    def test_validate_ingredients_empty_string(self, client):
        """Test that empty ingredients string raises ValidationError"""
        with pytest.raises(ValidationError, match="Ingredients"):
            client._validate_ingredients("")

    def test_validate_ingredients_empty_list(self, client):
        """Test that empty ingredients list raises ValidationError"""
        with pytest.raises(ValidationError, match="Ingredients"):
            client._validate_ingredients([])

    def test_validate_ingredients_none(self, client):
        """Test that None ingredients raises ValidationError"""
        with pytest.raises(ValidationError, match="Ingredients must be provided"):
            client._validate_ingredients(None)

    def test_validate_ingredients_list_with_empty_string(self, client):
        """Test that list with empty string raises ValidationError"""
        with pytest.raises(ValidationError, match="must be a non-empty string"):
            client._validate_ingredients(["400g pasta", "", "salt"])

    def test_validate_ingredients_valid_string(self, client):
        """Test that valid ingredients string passes validation"""
        client._validate_ingredients("400g spaghetti\n100g pancetta\nsalt")

    def test_validate_ingredients_valid_list(self, client):
        """Test that valid ingredients list passes validation"""
        client._validate_ingredients(["400g spaghetti", "100g pancetta", "salt"])

    # Directions validation tests
    def test_validate_directions_empty(self, client):
        """Test that empty directions raise ValidationError"""
        with pytest.raises(ValidationError, match="Recipe directions cannot be empty"):
            client._validate_directions("")

    def test_validate_directions_whitespace_only(self, client):
        """Test that whitespace-only directions raise ValidationError"""
        with pytest.raises(ValidationError, match="Recipe directions cannot be empty"):
            client._validate_directions("   \n  ")

    def test_validate_directions_valid(self, client):
        """Test that valid directions pass validation"""
        client._validate_directions("1. Cook pasta\n2. Fry pancetta\n3. Combine")

    # Numeric field validation tests
    def test_validate_numeric_field_negative(self, client):
        """Test that negative numeric value raises ValidationError"""
        with pytest.raises(ValidationError, match="cannot be negative"):
            client._validate_numeric_field(-1, "Servings", min_val=0)

    def test_validate_numeric_field_below_minimum(self, client):
        """Test that value below minimum raises ValidationError"""
        with pytest.raises(ValidationError, match="must be at least 1"):
            client._validate_numeric_field(0, "Servings", min_val=1)

    def test_validate_numeric_field_invalid_string(self, client):
        """Test that non-numeric string raises ValidationError"""
        with pytest.raises(ValidationError, match="must be a number"):
            client._validate_numeric_field("abc", "Servings")

    def test_validate_numeric_field_valid_int(self, client):
        """Test that valid integer passes validation"""
        client._validate_numeric_field(4, "Servings", min_val=1)

    def test_validate_numeric_field_valid_string_int(self, client):
        """Test that valid string integer passes validation"""
        client._validate_numeric_field("4", "Servings", min_val=1)

    def test_validate_numeric_field_empty_string(self, client):
        """Test that empty string is allowed for optional fields"""
        client._validate_numeric_field("", "Servings")  # Should not raise

    def test_validate_numeric_field_none(self, client):
        """Test that None is allowed for optional fields"""
        client._validate_numeric_field(None, "Servings")  # Should not raise

    # Integration tests with create_recipe
    @pytest.mark.asyncio
    async def test_create_recipe_validation_empty_name(self, client):
        """Test create_recipe with empty name fails validation"""
        with pytest.raises(ValidationError, match="Recipe name cannot be empty"):
            await client.create_recipe(
                name="",
                ingredients="400g pasta",
                directions="Cook pasta",
            )

    @pytest.mark.asyncio
    async def test_create_recipe_validation_empty_ingredients(self, client):
        """Test create_recipe with empty ingredients fails validation"""
        with pytest.raises(ValidationError, match="Ingredients"):
            await client.create_recipe(
                name="Pasta",
                ingredients="",
                directions="Cook pasta",
            )

    @pytest.mark.asyncio
    async def test_create_recipe_validation_empty_directions(self, client):
        """Test create_recipe with empty directions fails validation"""
        with pytest.raises(ValidationError, match="directions cannot be empty"):
            await client.create_recipe(
                name="Pasta",
                ingredients="400g pasta",
                directions="",
            )

    @pytest.mark.asyncio
    async def test_create_recipe_validation_invalid_servings(self, client):
        """Test create_recipe with invalid servings fails validation"""
        with pytest.raises(ValidationError, match="Servings"):
            await client.create_recipe(
                name="Pasta",
                ingredients="400g pasta",
                directions="Cook pasta",
                servings="-1",
            )

    # Integration tests with update_recipe_partial
    @pytest.mark.asyncio
    async def test_update_recipe_partial_validation_empty_uid(self, client):
        """Test update_recipe_partial with empty UID fails validation"""
        with pytest.raises(ValidationError, match="UID is required"):
            await client.update_recipe_partial(uid="", name="New Name")

    @pytest.mark.asyncio
    async def test_update_recipe_partial_validation_none_uid(self, client):
        """Test update_recipe_partial with None UID fails validation"""
        with pytest.raises(ValidationError, match="UID is required"):
            await client.update_recipe_partial(uid=None, name="New Name")

    @pytest.mark.asyncio
    async def test_update_recipe_partial_validation_invalid_name(self, client):
        """Test update_recipe_partial with invalid name fails validation"""
        with pytest.raises(ValidationError, match="Recipe name cannot be empty"):
            await client.update_recipe_partial(
                uid="TEST-UID-123",
                name="",
            )

    @pytest.mark.asyncio
    async def test_update_recipe_partial_validation_invalid_servings(self, client):
        """Test update_recipe_partial with invalid servings fails validation"""
        with pytest.raises(ValidationError, match="Servings"):
            await client.update_recipe_partial(
                uid="TEST-UID-123",
                servings="0",
            )

    @pytest.mark.asyncio
    async def test_list_recipes_with_last_planned(self, client):
        """Test list_recipes includes last_planned date when available."""
        recipe_list_response = {
            "result": [
                {"uid": "recipe-1"},
                {"uid": "recipe-2"},
            ]
        }
        recipe_1_data = {"result": {"uid": "recipe-1", "name": "Pasta Bolognese", "in_trash": False}}
        recipe_2_data = {"result": {"uid": "recipe-2", "name": "Pizza Margarita", "in_trash": False}}
        meal_plan_mock = [
            {"meal": "Pasta Bolognese", "meal_ID": "recipe-1", "date": "2025-10-15", "type": "dinner"},
            {"meal": "Pasta Bolognese", "meal_ID": "recipe-1", "date": "2025-11-01", "type": "dinner"},
            {"meal": "Pizza Margarita", "meal_ID": "recipe-2", "date": "2025-10-20", "type": "dinner"},
        ]

        with patch.object(client, "get_meal_plan", new_callable=AsyncMock) as mock_get_meal_plan:
            mock_get_meal_plan.return_value = meal_plan_mock
            with patch.object(client, "_make_authenticated_request", new_callable=AsyncMock) as mock_request:
                mock_request.side_effect = [recipe_list_response, recipe_1_data, recipe_2_data]
                recipes = await client.list_recipes(limit=50)

                assert len(recipes) == 2
                recipe_1 = next(r for r in recipes if r["uid"] == "recipe-1")
                assert recipe_1["last_planned"] == "2025-11-01"
                recipe_2 = next(r for r in recipes if r["uid"] == "recipe-2")
                assert recipe_2["last_planned"] == "2025-10-20"

    @pytest.mark.asyncio
    async def test_list_recipes_without_last_planned(self, client):
        """Test list_recipes works when no meal plan entries exist."""
        recipe_list_response = {"result": [{"uid": "recipe-1"}]}
        recipe_1_data = {"result": {"uid": "recipe-1", "name": "New Recipe", "in_trash": False}}

        with patch.object(client, "get_meal_plan", new_callable=AsyncMock) as mock_get_meal_plan:
            mock_get_meal_plan.return_value = []
            with patch.object(client, "_make_authenticated_request", new_callable=AsyncMock) as mock_request:
                mock_request.side_effect = [recipe_list_response, recipe_1_data]
                recipes = await client.list_recipes(limit=50)

                assert len(recipes) == 1
                assert "last_planned" not in recipes[0]


class TestGroceries:
    @pytest.fixture
    def client(self):
        return PaprikaClient("test@example.com", "testpass")

    @pytest.mark.asyncio
    async def test_get_grocery_lists(self, client):
        client.token = "test_token"
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.return_value = {
                "result": [
                    {"name": "supermarket", "is_default": True, "uid": "uuid1"},
                    {"name": "butcher", "is_default": False, "uid": "uuid2"},
                ]
            }

            lists = await client.get_grocery_lists()
            assert lists == [
                {"name": "supermarket", "is_default": True},
                {"name": "butcher", "is_default": False},
            ]
            mock_request.assert_called_once_with("GET", "/sync/grocerylists")

    @pytest.mark.asyncio
    async def test_get_grocery_lists_empty(self, client):
        client.token = "test_token"
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.return_value = {"result": []}
            lists = await client.get_grocery_lists()
            assert lists == []

    @pytest.mark.asyncio
    async def test_get_default_list_uuid(self, client):
        client.token = "test_token"
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.return_value = {
                "result": [
                    {"name": "supermarket", "is_default": True, "uid": "uuid1"},
                    {"name": "butcher", "is_default": False, "uid": "uuid2"},
                ]
            }
            uid = await client.get_default_list_uuid()
            assert uid == "uuid1"

    @pytest.mark.asyncio
    async def test_get_default_list_uuid_not_found(self, client):
        client.token = "test_token"
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.return_value = {
                "result": [{"name": "supermarket", "is_default": False, "uid": "uuid1"}]
            }
            with pytest.raises(PaprikaAPIError, match="No default grocery list found"):
                await client.get_default_list_uuid()

    @pytest.mark.asyncio
    async def test_get_groceries(self, client):
        client.token = "test_token"
        with patch.object(client, "_get_list_uuid_by_name") as mock_get_uuid:
            mock_get_uuid.return_value = "uuid1"
            with patch.object(client, "_make_authenticated_request") as mock_request:
                mock_request.return_value = {
                    "result": [
                        {"name": "bananas", "quantity": "3", "list_uid": "uuid1"},
                        {"name": "milk", "quantity": "4 liters", "list_uid": "uuid1"},
                        {"name": "apples", "quantity": "2", "list_uid": "uuid2"},
                    ]
                }
                groceries = await client.get_groceries()
                assert len(groceries) == 2
                assert {"name": "bananas", "quantity": "3"} in groceries
                assert {"name": "milk", "quantity": "4 liters"} in groceries

    @pytest.mark.asyncio
    async def test_get_grocery_found(self, client):
        client.token = "test_token"
        with patch.object(client, "_get_list_uuid_by_name") as mock_get_uuid:
            mock_get_uuid.return_value = "uuid1"
            with patch.object(client, "_make_authenticated_request") as mock_request:
                mock_request.return_value = {
                    "result": [{"name": "bananas", "quantity": "3", "list_uid": "uuid1", "uid": "grocery_uid"}]
                }
                grocery = await client.get_grocery("bananas")
                assert grocery is not None
                assert grocery["name"] == "bananas"
                assert grocery["quantity"] == "3"

    @pytest.mark.asyncio
    async def test_get_grocery_not_found(self, client):
        client.token = "test_token"
        with patch.object(client, "_get_list_uuid_by_name") as mock_get_uuid:
            mock_get_uuid.return_value = "uuid1"
            with patch.object(client, "_make_authenticated_request") as mock_request:
                mock_request.return_value = {"result": []}
                grocery = await client.get_grocery("bananas")
                assert grocery is None

    @pytest.mark.asyncio
    async def test_get_list_uuid_by_name_invalid_with_valid_lists(self, client):
        client.token = "test_token"
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.return_value = {
                "result": [
                    {"name": "supermarket", "is_default": True, "uid": "uuid1"},
                    {"name": "butcher", "is_default": False, "uid": "uuid2"},
                ]
            }
            with pytest.raises(PaprikaAPIError) as exc_info:
                await client._get_list_uuid_by_name("invalid_list")
            assert "Grocery list 'invalid_list' not found" in str(exc_info.value)
            assert "Valid grocery lists are" in str(exc_info.value)
            assert "'supermarket'" in str(exc_info.value)
            assert "'butcher'" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_list_uuid_by_name_invalid_no_lists(self, client):
        client.token = "test_token"
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.return_value = {"result": []}
            with pytest.raises(PaprikaAPIError) as exc_info:
                await client._get_list_uuid_by_name("invalid_list")
            assert "Grocery list 'invalid_list' not found" in str(exc_info.value)
            assert "No grocery lists are available" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_add_grocery_new_item(self, client):
        client.token = "test_token"
        with patch.object(client, "_get_list_uuid_by_name") as mock_get_uuid:
            mock_get_uuid.return_value = "uuid1"
            with patch.object(client, "_make_authenticated_request") as mock_request:
                mock_request.side_effect = [
                    {"result": []},
                    {"result": {"success": True}},
                ]
                result = await client.add_grocery("bananas", 3)
                assert result["name"] == "bananas"
                assert result["quantity"] == "3"
                assert mock_request.call_count == 2

    @pytest.mark.asyncio
    async def test_add_grocery_existing_item(self, client):
        client.token = "test_token"
        with patch.object(client, "_get_list_uuid_by_name") as mock_get_uuid:
            mock_get_uuid.return_value = "uuid1"
            with patch.object(client, "_make_authenticated_request") as mock_request:
                mock_request.side_effect = [
                    {"result": [{"name": "bananas", "quantity": "2", "list_uid": "uuid1", "uid": "grocery_uid"}]},
                    {"result": {"success": True}},
                ]
                result = await client.add_grocery("bananas", 3)
                assert result["name"] == "bananas"
                assert result["quantity"] == "5"
                assert mock_request.call_count == 2

    @pytest.mark.asyncio
    async def test_add_grocery_empty_name(self, client):
        client.token = "test_token"
        with pytest.raises(PaprikaAPIError, match="Item name cannot be empty"):
            await client.add_grocery("", 1)

    def test_parse_quantity_with_unit(self, client):
        value, unit = client._parse_quantity("4 kilos")
        assert value == 4.0
        assert unit == "kilos"
        value, unit = client._parse_quantity("5")
        assert value == 5.0
        assert unit is None
        value, unit = client._parse_quantity("-2 kilos")
        assert value == -2.0
        assert unit == "kilos"

    def test_add_quantities_with_units(self, client):
        result, _ = client._add_quantities("4 kilos", "1 kilo")
        assert result == "5 kilos"
        result, _ = client._add_quantities("3 liters", "2 liters")
        assert result == "5 liters"
        result, _ = client._add_quantities("4 kilos", "2")
        assert result == "6 kilos"

    def test_add_quantities_negative(self, client):
        result, _ = client._add_quantities("4 kilos", "-2 kilos")
        assert result == "2 kilos"
        result, _ = client._add_quantities("3", "-1")
        assert result == "2"

    def test_add_quantities_below_zero_error(self, client):
        with pytest.raises(PaprikaAPIError, match="result would be negative"):
            client._add_quantities("1 kilo", "-2 kilos")
        with pytest.raises(PaprikaAPIError, match="result would be negative"):
            client._add_quantities("2", "-5")

    @pytest.mark.asyncio
    async def test_add_grocery_with_unit_string(self, client):
        client.token = "test_token"
        with patch.object(client, "_get_list_uuid_by_name") as mock_get_uuid:
            mock_get_uuid.return_value = "uuid1"
            with patch.object(client, "_make_authenticated_request") as mock_request:
                mock_request.side_effect = [
                    {"result": []},
                    {"result": {"success": True}},
                ]
                result = await client.add_grocery("bananas", "3 kilos")
                assert result["name"] == "bananas"
                assert result["quantity"] == "3 kilos"

    @pytest.mark.asyncio
    async def test_add_grocery_existing_with_unit(self, client):
        client.token = "test_token"
        with patch.object(client, "_get_list_uuid_by_name") as mock_get_uuid:
            mock_get_uuid.return_value = "uuid1"
            with patch.object(client, "_make_authenticated_request") as mock_request:
                mock_request.side_effect = [
                    {"result": [{"name": "bananas", "quantity": "4 kilos", "list_uid": "uuid1", "uid": "grocery_uid"}]},
                    {"result": {"success": True}},
                ]
                result = await client.add_grocery("bananas", "1 kilo")
                assert result["name"] == "bananas"
                assert result["quantity"] == "5 kilos"

    @pytest.mark.asyncio
    async def test_add_grocery_subtract_with_unit(self, client):
        client.token = "test_token"
        with patch.object(client, "_get_list_uuid_by_name") as mock_get_uuid:
            mock_get_uuid.return_value = "uuid1"
            with patch.object(client, "_make_authenticated_request") as mock_request:
                mock_request.side_effect = [
                    {"result": [{"name": "bananas", "quantity": "4 kilos", "list_uid": "uuid1", "uid": "grocery_uid"}]},
                    {"result": {"success": True}},
                ]
                result = await client.add_grocery("bananas", "-2 kilos")
                assert result["name"] == "bananas"
                assert result["quantity"] == "2 kilos"

    @pytest.mark.asyncio
    async def test_add_grocery_subtract_below_zero_error(self, client):
        client.token = "test_token"
        with patch.object(client, "_get_list_uuid_by_name") as mock_get_uuid:
            mock_get_uuid.return_value = "uuid1"
            with patch.object(client, "_make_authenticated_request") as mock_request:
                mock_request.return_value = {
                    "result": [{"name": "bananas", "quantity": "1 kilo", "list_uid": "uuid1", "uid": "grocery_uid"}]
                }
                with pytest.raises(PaprikaAPIError, match="result would be negative"):
                    await client.add_grocery("bananas", "-2 kilos")

    @pytest.mark.asyncio
    async def test_clear_grocery_list(self, client):
        client.token = "test_token"
        with patch.object(client, "_get_list_uuid_by_name") as mock_get_uuid:
            mock_get_uuid.return_value = "uuid1"
            with patch.object(client, "_make_authenticated_request") as mock_request:
                mock_request.side_effect = [
                    {
                        "result": [
                            {
                                "name": "bananas", "quantity": "3", "list_uid": "uuid1",
                                "uid": "grocery_uid", "ingredient": "bananas", "recipe_uid": None,
                                "order_flag": 316, "aisle": "Produce", "recipe": None,
                                "instruction": "", "separate": False,
                                "aisle_uid": "F94467760BF4BC6B9521FFA9329D0F1DBCCA0F5AC0808BD8552FB375A565FB9E",
                            },
                        ]
                    },
                    {"result": {"success": True}},
                ]
                result = await client.clear_grocery_list()
                assert result is True
                assert mock_request.call_count == 2

    @pytest.mark.asyncio
    async def test_clear_grocery_list_empty(self, client):
        client.token = "test_token"
        with patch.object(client, "_get_list_uuid_by_name") as mock_get_uuid:
            mock_get_uuid.return_value = "uuid1"
            with patch.object(client, "_make_authenticated_request") as mock_request:
                mock_request.return_value = {"result": []}
                result = await client.clear_grocery_list()
                assert result is True
