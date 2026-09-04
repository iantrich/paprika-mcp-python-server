from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from paprika_mcp_server.paprika_client import (
    MealMatchAmbiguousError,
    MealNotFoundError,
    PaprikaAPIError,
    PaprikaClient,
)


class TestMealPlanningHelpers:
    @pytest.fixture
    def client(self):
        return PaprikaClient("test@example.com", "testpass")

    def test_find_recipe_by_name_exact_match(self, client):
        """Test finding recipe with exact match."""
        recipes = [
            {"name": "Pasta Bolognese", "uid": "123"},
            {"name": "Pizza Margarita", "uid": "456"},
        ]
        result = client._find_recipe_by_name("Pasta Bolognese", recipes)
        assert result["name"] == "Pasta Bolognese"
        assert result["uid"] == "123"

    def test_find_recipe_by_name_high_match(self, client):
        """Test finding recipe with high similarity match."""
        recipes = [
            {"name": "Pasta Bolognese", "uid": "123"},
            {"name": "Pizza Margarita", "uid": "456"},
        ]
        result = client._find_recipe_by_name("pasta bolognese", recipes)  # Case insensitive
        assert result["name"] == "Pasta Bolognese"

    def test_find_recipe_by_name_medium_match(self, client):
        """Test finding recipe with medium similarity raises ambiguous error."""
        recipes = [
            {"name": "Pasta Bolognese", "uid": "123"},
            {"name": "Pasta Carbonara", "uid": "456"},
        ]
        # Use a name that has medium similarity (60-85%) with multiple recipes
        # "Pasta Bol" matches "Pasta Bolognese" with ~0.75 similarity
        with pytest.raises(MealMatchAmbiguousError) as exc_info:
            client._find_recipe_by_name("Pasta Bol", recipes)
        assert len(exc_info.value.matches) > 0
        assert len(exc_info.value.matches) <= 5  # Should limit to top 5

    def test_find_recipe_by_name_poor_match(self, client):
        """Test finding recipe with poor similarity raises not found error."""
        recipes = [
            {"name": "Pasta Bolognese", "uid": "123"},
            {"name": "Pizza Margarita", "uid": "456"},
        ]
        with pytest.raises(MealNotFoundError):
            client._find_recipe_by_name("Chicken Curry", recipes)

    def test_find_recipe_by_name_empty_list(self, client):
        """Test finding recipe in empty list raises error."""
        with pytest.raises(MealNotFoundError):
            client._find_recipe_by_name("Pasta", [])

    def test_find_recipe_ambiguous_when_no_confident_match(self, client):
        """Several weak candidates must raise rather than silently pick one."""
        recipes = [
            {"name": "Pasta Bolognese", "uid": "123"},
            {"name": "Pasta Carbonara", "uid": "456"},
        ]
        with pytest.raises(MealMatchAmbiguousError):
            client._find_recipe_by_name("Pasta Bol", recipes)

    def test_find_recipe_exact_match_wins_over_ambiguity(self, client):
        """An exact name is never ambiguous, even among similar neighbours."""
        recipes = [
            {"name": "Pasta", "uid": "1"},
            {"name": "Pasta Bolognese", "uid": "2"},
            {"name": "Pasta Carbonara", "uid": "3"},
        ]
        assert client._find_recipe_by_name("Pasta", recipes)["uid"] == "1"

    def test_find_recipe_single_weak_candidate_is_returned(self, client):
        """With only one candidate there is nothing to be ambiguous between."""
        recipes = [{"name": "Pasta Bolognese", "uid": "123"}]
        assert client._find_recipe_by_name("Pasta Bol", recipes)["uid"] == "123"

    def test_find_recipe_strong_match_wins(self, client):
        """A near-exact match is confident enough to return despite neighbours."""
        recipes = [
            {"name": "Pasta Bolognese", "uid": "123"},
            {"name": "Pasta Carbonara", "uid": "456"},
        ]
        assert client._find_recipe_by_name("Pasta Bolognes", recipes)["uid"] == "123"

    def test_find_recipe_two_strong_candidates_are_ambiguous(self, client):
        """A strong best score is not enough when the runner-up is just as
        strong. "Chicken Curr" scores 0.96 against "Chicken Curry" and 0.92
        against "Chicken Currys" -- a 0.037 gap. The old guard only checked
        `best_ratio < STRONG_NAME_MATCH_RATIO`, so it silently returned
        "Chicken Curry" and this tool writes data."""
        recipes = [
            {"name": "Chicken Curry", "uid": "a"},
            {"name": "Chicken Currys", "uid": "b"},
        ]
        with pytest.raises(MealMatchAmbiguousError) as exc_info:
            client._find_recipe_by_name("Chicken Curr", recipes)
        assert {m["uid"] for m in exc_info.value.matches} == {"a", "b"}

    def test_find_recipe_no_match_raises_not_found(self, client):
        recipes = [{"name": "Pasta Bolognese", "uid": "123"}]
        with pytest.raises(MealNotFoundError):
            client._find_recipe_by_name("Beef Wellington", recipes)

    def test_parse_flexible_date_iso_format(self, client):
        """Test parsing ISO date format."""
        result = client._parse_flexible_date("2025-11-03")
        assert result == "2025-11-03"

    def test_parse_flexible_date_dd_mmm(self, client):
        """'3 Nov' resolves to 3 November in whatever year dateutil defaults to."""
        result = client._parse_flexible_date("3 Nov")
        assert result.endswith("-11-03")
        year = int(result[:4])
        assert abs(year - datetime.now().year) <= 1

    def test_parse_flexible_date_invalid(self, client):
        """Test parsing invalid date raises ValueError."""
        with pytest.raises(ValueError):
            client._parse_flexible_date("invalid date")

    def test_parse_flexible_date_iso_is_never_reordered(self, client):
        """ISO 8601 input is unambiguous and must be returned as-is."""
        assert client._parse_flexible_date("2025-11-03") == "2025-11-03"
        assert client._parse_flexible_date("2025-03-11") == "2025-03-11"

    def test_parse_flexible_date_iso_day_le_12(self, client):
        """Days <= 12 are where a month/day swap is silently plausible."""
        for iso in ["2026-01-02", "2026-09-04", "2026-12-11", "2026-06-06"]:
            assert client._parse_flexible_date(iso) == iso

    def test_parse_flexible_date_slash_is_month_first(self, client):
        """US convention: 11/03/2025 is 3 November, not 11 March."""
        assert client._parse_flexible_date("11/03/2025") == "2025-11-03"

    def test_parse_flexible_date_rejects_garbage(self, client):
        with pytest.raises(ValueError):
            client._parse_flexible_date("not a date at all")

    def test_format_date_readable(self, client):
        """Readable dates carry weekday, month, day, and year."""
        result = client._format_date_readable("2025-11-03")
        assert "Monday" in result
        assert "November" in result
        assert "03" in result
        assert "2025" in result

    def test_format_date_readable_passes_through_garbage(self, client):
        """Unparseable input is returned unchanged rather than raising."""
        assert client._format_date_readable("not a date") == "not a date"

    def test_get_next_free_day_empty_plan(self, client):
        """Test getting next free day with empty meal plan."""
        result = client._get_next_free_day([], "dinner")
        # Should return today or tomorrow
        today = datetime.now().date()
        result_date = datetime.strptime(result, "%Y-%m-%d").date()
        assert result_date >= today

    def test_get_next_free_day_with_occupied_dates(self, client):
        """Test getting next free day skipping occupied dates."""
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        day_after = today + timedelta(days=2)

        meal_plan = [
            {"date": tomorrow.strftime("%Y-%m-%d"), "type": "dinner"},
        ]

        result = client._get_next_free_day(meal_plan, "dinner")
        result_date = datetime.strptime(result, "%Y-%m-%d").date()
        assert result_date == day_after or result_date == today  # Today if no dinner today


class TestMealPlanningAPI:
    @pytest.fixture
    def client(self):
        return PaprikaClient("test@example.com", "testpass")

    @pytest.mark.asyncio
    async def test_get_meal_plan_success(self, client):
        """Test successfully getting meal plan."""
        target = (datetime.now().date() + timedelta(days=2)).strftime("%Y-%m-%d")
        mock_response = {
            "result": [
                {
                    "recipe_uid": "123",
                    "recipe_name": "Pasta Bolognese",
                    "date": target,
                    "type": "dinner",
                }
            ]
        }
        with patch.object(
            client, "_make_v1_basic_auth_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response
            result = await client.get_meal_plan(num_days=10, meal_type="dinner")
            assert len(result) == 1
            # recipe_name -> meal and recipe_uid -> meal_ID is the mapping
            # remove_meal_from_plan() matches entries on; assert it here.
            assert result[0]["meal"] == "Pasta Bolognese"
            assert result[0]["meal_ID"] == "123"
            assert result[0]["date"] == target

    @pytest.mark.asyncio
    async def test_get_meal_plan_empty(self, client):
        """Test getting empty meal plan."""
        mock_response = {"result": []}

        with patch.object(
            client, "_make_v1_basic_auth_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await client.get_meal_plan()

            assert result == []

    @pytest.mark.asyncio
    async def test_get_meal_plan_with_start_end_date(self, client):
        """Test getting meal plan with explicit start and end dates."""
        mock_response = {
            "result": [
                {
                    "recipe_uid": "123",
                    "recipe_name": "Pasta Bolognese",
                    "date": "2025-10-15",
                    "type": "dinner",
                },
                {
                    "recipe_uid": "456",
                    "recipe_name": "Pizza",
                    "date": "2025-10-20",
                    "type": "dinner",
                },
            ]
        }

        with patch.object(
            client, "_make_v1_basic_auth_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await client.get_meal_plan(
                start_date="2025-10-15",
                end_date="2025-10-25",
                meal_type="dinner"
            )

            assert len(result) == 2
            assert result[0]["meal"] == "Pasta Bolognese"
            assert result[1]["meal"] == "Pizza"

    @pytest.mark.asyncio
    async def test_get_meal_plan_historical(self, client):
        """Test getting historical meal plan (past dates)."""
        mock_response = {
            "result": [
                {
                    "recipe_uid": "123",
                    "recipe_name": "Pasta Bolognese",
                    "date": "2024-11-15",
                    "type": "dinner",
                },
            ]
        }

        with patch.object(
            client, "_make_v1_basic_auth_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            # Get meal plan from past
            result = await client.get_meal_plan(
                start_date="2024-11-01",
                end_date="2024-11-30",
                meal_type="dinner"
            )

            assert len(result) == 1
            assert result[0]["meal"] == "Pasta Bolognese"
            assert result[0]["date"] == "2024-11-15"

    @pytest.mark.asyncio
    async def test_add_meal_to_plan_with_meal_name(self, client):
        """Test adding meal to plan using meal name."""
        # Mock list_recipes
        recipes_mock = [{"name": "Pasta Bolognese", "uid": "123"}]
        with patch.object(client, "list_recipes", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = recipes_mock

            # Mock get_meal_plan (for finding next free day)
            with patch.object(
                client, "get_meal_plan", new_callable=AsyncMock
            ) as mock_plan:
                mock_plan.return_value = []

                # Mock _make_v1_basic_auth_request (for adding meal)
                with patch.object(
                    client, "_make_v1_basic_auth_request", new_callable=AsyncMock
                ) as mock_request:
                    mock_request.return_value = {"result": "success"}

                    result = await client.add_meal_to_plan(meal="Pasta Bolognese")

                    assert result["meal"] == "Pasta Bolognese"
                    assert result["meal_ID"] == "123"
                    assert "date" in result

    @pytest.mark.asyncio
    async def test_add_meal_to_plan_with_meal_id(self, client):
        """Test adding meal to plan using meal_id."""
        # Mock recipe lookup
        recipe_mock = {"result": {"name": "Pasta Bolognese"}}
        with patch.object(
            client, "_make_authenticated_request", new_callable=AsyncMock
        ) as mock_auth_request:
            mock_auth_request.return_value = recipe_mock

            # Mock get_meal_plan (for finding next free day)
            with patch.object(
                client, "get_meal_plan", new_callable=AsyncMock
            ) as mock_plan:
                mock_plan.return_value = []

                # Mock _make_v1_basic_auth_request (for adding meal)
                with patch.object(
                    client, "_make_v1_basic_auth_request", new_callable=AsyncMock
                ) as mock_v1_request:
                    mock_v1_request.return_value = {"result": "success"}

                    result = await client.add_meal_to_plan(meal_id="123")

                    assert result["meal_ID"] == "123"
                    assert "date" in result

    @pytest.mark.asyncio
    async def test_add_meal_to_plan_api_error(self, client):
        """Test adding meal when API returns error."""
        recipes_mock = [{"name": "Pasta Bolognese", "uid": "123"}]
        with patch.object(client, "list_recipes", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = recipes_mock

            with patch.object(
                client, "get_meal_plan", new_callable=AsyncMock
            ) as mock_plan:
                mock_plan.return_value = []

                with patch.object(
                    client, "_make_v1_basic_auth_request", new_callable=AsyncMock
                ) as mock_request:
                    mock_request.side_effect = Exception("API Error: 500")

                    with pytest.raises(PaprikaAPIError) as exc_info:
                        await client.add_meal_to_plan(meal="Pasta Bolognese")

                    # Per non-functional requirements: errors shown literally
                    assert "API Error: 500" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_remove_meal_from_plan_by_date(self, client):
        """Test removing meal from plan by date."""
        today = datetime.now().date().strftime("%Y-%m-%d")
        meal_plan_mock = [
            {"meal": "Pasta Bolognese", "meal_ID": "123", "date": today, "type": "dinner"}
        ]

        with patch.object(
            client, "get_meal_plan", new_callable=AsyncMock
        ) as mock_get_plan:
            mock_get_plan.return_value = meal_plan_mock

            # Mock API response for getting full meal plan (with time component)
            api_response_mock = {
                "result": [
                    {
                        "uid": "meal-plan-123",
                        "recipe_uid": "123",
                        "date": f"{today} 00:00:00",
                        "type": 2,  # dinner as integer
                    }
                ]
            }

            with patch.object(
                client, "_make_v1_basic_auth_request", new_callable=AsyncMock
            ) as mock_request:
                # First call for getting meal plan entries, second for DELETE
                mock_request.side_effect = [api_response_mock, {"result": "deleted"}]

                result = await client.remove_meal_from_plan(date=today)

                assert result["result"] == "Meal removed"
                assert result["meal"] == "Pasta Bolognese"

    @pytest.mark.asyncio
    async def test_remove_meal_from_plan_no_params(self, client):
        """Test removing last meal (no params)."""
        today = datetime.now().date().strftime("%Y-%m-%d")
        meal_plan_mock = [
            {"meal": "Pasta Bolognese", "meal_ID": "123", "date": today, "type": "dinner"}
        ]

        with patch.object(
            client, "get_meal_plan", new_callable=AsyncMock
        ) as mock_get_plan:
            mock_get_plan.return_value = meal_plan_mock

            api_response_mock = {
                "result": [
                    {
                        "uid": "meal-plan-123",
                        "recipe_uid": "123",
                        "date": f"{today} 00:00:00",
                        "type": 2,  # dinner as integer
                    }
                ]
            }

            with patch.object(
                client, "_make_v1_basic_auth_request", new_callable=AsyncMock
            ) as mock_request:
                mock_request.side_effect = [api_response_mock, {"result": "deleted"}]

                result = await client.remove_meal_from_plan()

                assert result["result"] == "Meal removed"

    @pytest.mark.asyncio
    async def test_remove_meal_from_plan_no_params_prefers_matching_type(self, client):
        """With two entries on the SAME date, the default meal_type must win.

        The tie-break sorted on `type != meal_type` with reverse=True, and
        True sorts first under reverse -- so it actively preferred the entry
        whose type did NOT match and deleted the wrong meal. A single-entry
        plan cannot catch this.
        """
        date = "2026-09-10"
        meal_plan_mock = [
            {"meal": "Lasagna", "meal_ID": "d1", "date": date, "type": "dinner"},
            {"meal": "Soup", "meal_ID": "l1", "date": date, "type": "lunch"},
        ]

        with patch.object(client, "get_meal_plan", new_callable=AsyncMock) as mock_get_plan:
            mock_get_plan.return_value = meal_plan_mock

            api_response_mock = {
                "result": [
                    {"uid": "mp-d1", "recipe_uid": "d1", "date": f"{date} 00:00:00", "type": 2},
                    {"uid": "mp-l1", "recipe_uid": "l1", "date": f"{date} 00:00:00", "type": 3},
                ]
            }

            with patch.object(
                client, "_make_v1_basic_auth_request", new_callable=AsyncMock
            ) as mock_request:
                mock_request.side_effect = [api_response_mock, {"result": "deleted"}]

                result = await client.remove_meal_from_plan()

        assert result["meal"] == "Lasagna", "removed the wrong meal type"
        assert result["type"] == "dinner"
        assert result["meal_ID"] == "d1"

    @pytest.mark.asyncio
    async def test_remove_meal_missing_entry_raises_meal_not_found(self, client):
        """MealNotFoundError must escape unwrapped.

        It is raised inside the try: block whose `except Exception` turns
        everything into PaprikaAPIError, so handlers.py's `except
        MealNotFoundError` never fired and the agent saw a generic error.
        """
        date = "2026-09-10"
        meal_plan_mock = [
            {"meal": "Lasagna", "meal_ID": "d1", "date": date, "type": "dinner"},
        ]

        with patch.object(client, "get_meal_plan", new_callable=AsyncMock) as mock_get_plan:
            mock_get_plan.return_value = meal_plan_mock

            # The sync feed has no entry matching that uid/date/type, so the
            # lookup falls through to "Meal plan entry not found for deletion".
            api_response_mock = {
                "result": [
                    {"uid": "mp-x", "recipe_uid": "other", "date": f"{date} 00:00:00", "type": 2},
                ]
            }

            with patch.object(
                client, "_make_v1_basic_auth_request", new_callable=AsyncMock
            ) as mock_request:
                mock_request.return_value = api_response_mock

                with pytest.raises(MealNotFoundError):
                    await client.remove_meal_from_plan()

