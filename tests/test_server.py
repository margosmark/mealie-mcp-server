"""Behavioural tests for mealie-mcp-server.

These run against a stubbed transport: no live Mealie instance is required.
They pin the v3.x API shapes that broke the original single-file server:
the paginated meal-plan envelope, the relocated shopping-item endpoints,
listItems vs shoppingListItems, and name->id resolution for items.
"""

import pytest

from mealie_mcp_server import server


@pytest.fixture
def mealie(monkeypatch):
    """Capture HTTP calls and serve canned responses keyed by (method, path)."""

    calls = []
    responses = {}

    def fake_request(method, path, params=None, data=None):
        calls.append({"method": method, "path": path, "params": params, "data": data})
        value = responses.get((method, path), responses.get(("*", path)))
        if isinstance(value, Exception):
            raise value
        if value is None:
            return []
        return value

    monkeypatch.setattr(server, "_request", fake_request)
    server._GROUP_SLUG = None  # don't leak the about-cache between tests
    return {"calls": calls, "responses": responses}


# --------------------------------------------------------------------------
# Meal plans — the v3.x paginated envelope
# --------------------------------------------------------------------------

def test_list_mealplans_accepts_paginated_envelope(mealie):
    """Iterating the envelope directly raised AttributeError on dict keys."""
    mealie["responses"][("GET", "/api/households/mealplans")] = {
        "page": 1,
        "per_page": 100,
        "total": 1,
        "items": [
            {"date": "2026-11-15", "entryType": "dinner", "title": "Chicken biryani", "recipe": None}
        ],
    }

    out = server.mealie_list_mealplans("2026-11-01", "2026-11-30")

    assert "Chicken biryani" in out
    assert "2026-11-15" in out
    assert "dinner" in out


def test_list_mealplans_still_accepts_bare_list(mealie):
    mealie["responses"][("GET", "/api/households/mealplans")] = [
        {"date": "2026-11-15", "entryType": "lunch", "title": "Soup", "recipe": None}
    ]

    assert "Soup" in server.mealie_list_mealplans("2026-11-01", "2026-11-30")


def test_list_mealplans_empty(mealie):
    mealie["responses"][("GET", "/api/households/mealplans")] = {"items": []}

    assert "No meal plans" in server.mealie_list_mealplans("2026-11-01", "2026-11-30")


def test_today_mealplan_shows_recipe_name(mealie):
    mealie["responses"][("GET", "/api/households/mealplans/today")] = [
        {"entryType": "dinner", "title": "", "recipe": {"name": "Tacos"}}
    ]

    out = server.mealie_get_today_mealplan()

    assert "Tacos" in out


# --------------------------------------------------------------------------
# Shopping items — endpoints moved to /shopping/items in v3.x
# --------------------------------------------------------------------------

def test_add_shopping_item_posts_to_items_endpoint(mealie):
    """The old /lists/{id}/items path answers 405 on v3.x."""
    mealie["responses"][("GET", "/api/foods")] = [{"id": "food-1", "name": "Milk"}]
    mealie["responses"][("POST", "/api/households/shopping/items")] = {"createdItems": []}

    server.mealie_add_shopping_item("list-1", "Milk", quantity=2)

    posts = [c for c in mealie["calls"] if c["method"] == "POST"]
    assert posts[-1]["path"] == "/api/households/shopping/items"
    assert posts[-1]["data"]["shoppingListId"] == "list-1"
    assert posts[-1]["data"]["foodId"] == "food-1"
    assert "food" not in posts[-1]["data"]  # nested objects are ignored by v3.x


def test_add_shopping_item_creates_unknown_food(mealie):
    mealie["responses"][("GET", "/api/foods")] = []
    mealie["responses"][("POST", "/api/foods")] = {"id": "food-new"}
    mealie["responses"][("POST", "/api/households/shopping/items")] = {"createdItems": []}

    server.mealie_add_shopping_item("list-1", "Dragonfruit")

    created = [c for c in mealie["calls"] if c["method"] == "POST" and c["path"] == "/api/foods"]
    assert created and created[0]["data"]["name"] == "Dragonfruit"
    item = [c for c in mealie["calls"] if c["path"] == "/api/households/shopping/items"][-1]
    assert item["data"]["foodId"] == "food-new"


def test_add_shopping_item_resolves_unit_id(mealie):
    mealie["responses"][("GET", "/api/foods")] = [{"id": "food-1", "name": "Flour"}]
    mealie["responses"][("GET", "/api/units")] = [{"id": "unit-1", "name": "Cup", "abbreviation": ""}]
    mealie["responses"][("POST", "/api/households/shopping/items")] = {"createdItems": []}

    server.mealie_add_shopping_item("list-1", "Flour", quantity=1, unit="Cup")

    item = [c for c in mealie["calls"] if c["path"] == "/api/households/shopping/items"][-1]
    assert item["data"]["unitId"] == "unit-1"
    assert "unit" not in item["data"]


def test_check_shopping_item_uses_bulk_put(mealie):
    mealie["responses"][("PUT", "/api/households/shopping/items")] = {}

    server.mealie_check_shopping_item("list-1", "item-1", True)

    put = [c for c in mealie["calls"] if c["method"] == "PUT"][-1]
    assert put["path"] == "/api/households/shopping/items"
    assert put["data"] == [{"id": "item-1", "shoppingListId": "list-1", "checked": True}]


def test_delete_shopping_item_uses_ids_query(mealie):
    mealie["responses"][("*", "/api/households/shopping/items?ids=item-1")] = {}

    server.mealie_delete_shopping_item("list-1", "item-1")

    delete = [c for c in mealie["calls"] if c["method"] == "DELETE"][-1]
    assert delete["path"] == "/api/households/shopping/items?ids=item-1"


def test_clear_checked_items_deletes_only_checked(mealie):
    mealie["responses"][("GET", "/api/households/shopping/lists/list-1")] = {
        "name": "Groceries",
        "listItems": [
            {"id": "a", "checked": True, "food": {"name": "Milk"}},
            {"id": "b", "checked": False, "food": {"name": "Bread"}},
            {"id": "c", "checked": True, "note": "Batteries"},
        ],
    }
    mealie["responses"][("*", "/api/households/shopping/items?ids=a,c")] = {}

    out = server.mealie_clear_checked_items("list-1")

    deletes = [c for c in mealie["calls"] if c["method"] == "DELETE"]
    assert deletes[-1]["path"] == "/api/households/shopping/items?ids=a,c"
    assert "2" in out


def test_clear_checked_items_noop_when_none_checked(mealie):
    mealie["responses"][("GET", "/api/households/shopping/lists/list-1")] = {
        "name": "Groceries",
        "listItems": [{"id": "b", "checked": False}],
    }

    out = server.mealie_clear_checked_items("list-1")

    assert "No checked items" in out
    assert not [c for c in mealie["calls"] if c["method"] == "DELETE"]


def test_get_shopping_list_reads_listitems_field(mealie):
    """v3.x renamed shoppingListItems -> listItems; the old code rendered empty."""
    mealie["responses"][("GET", "/api/households/shopping/lists/list-1")] = {
        "name": "Groceries",
        "listItems": [
            {"id": "a", "checked": False, "quantity": 2, "food": {"name": "Milk"}, "unit": {"name": "L"}}
        ],
    }

    out = server.mealie_get_shopping_list("list-1")

    assert "Groceries" in out
    assert "Milk" in out


def test_get_shopping_list_accepts_legacy_field(mealie):
    mealie["responses"][("GET", "/api/households/shopping/lists/list-1")] = {
        "name": "Legacy",
        "shoppingListItems": [{"id": "a", "checked": False, "food": {"name": "Eggs"}}],
    }

    assert "Eggs" in server.mealie_get_shopping_list("list-1")


def test_list_shopping_lists_counts_items(mealie):
    mealie["responses"][("GET", "/api/households/shopping/lists")] = {
        "items": [{"id": "l1", "name": "Groceries", "listItems": [{}, {}, {}]}]
    }

    out = server.mealie_list_shopping_lists()

    assert "Groceries" in out
    assert "3 items" in out


# --------------------------------------------------------------------------
# Formatting regressions
# --------------------------------------------------------------------------

def test_units_hide_empty_abbreviation(mealie):
    """Previously rendered "- Cup ()" and a nameless "-  ()" row."""
    mealie["responses"][("GET", "/api/units")] = {
        "items": [
            {"name": "Cup", "abbreviation": ""},
            {"name": "Tablespoons", "abbreviation": ""},
            {"name": "", "abbreviation": ""},
        ]
    }

    out = server.mealie_list_units()

    assert "()" not in out
    assert out.count("- Cup") == 1
    assert "Tablespoons" in out


def test_units_show_abbreviation_when_present(mealie):
    mealie["responses"][("GET", "/api/units")] = {
        "items": [{"name": "Gram", "abbreviation": "g"}]
    }

    assert "Gram (g)" in server.mealie_list_units()


def test_foods_skip_blank_names(mealie):
    mealie["responses"][("GET", "/api/foods")] = {
        "items": [{"name": "Rice"}, {"name": ""}, {"name": "Eggs"}]
    }

    out = server.mealie_list_foods()

    assert "Rice" in out and "Eggs" in out
    assert "- \n" not in out + "\n"


# --------------------------------------------------------------------------
# Recipe links — group slug is instance specific
# --------------------------------------------------------------------------

def test_recipe_link_uses_default_group_slug(mealie):
    mealie["responses"][("GET", "/api/app/about")] = {"defaultGroupSlug": "ourfamily"}
    mealie["responses"][("GET", "/api/recipes/cake")] = {
        "name": "Cake",
        "recipeIngredient": [],
        "recipeInstructions": [],
        "nutrition": {},
    }

    out = server.mealie_get_recipe("cake")

    assert "/g/ourfamily/r/cake" in out


def test_recipe_link_falls_back_to_home(mealie):
    mealie["responses"][("GET", "/api/app/about")] = Exception("boom")
    mealie["responses"][("GET", "/api/recipes/cake")] = {
        "name": "Cake",
        "recipeIngredient": [],
        "recipeInstructions": [],
        "nutrition": {},
    }

    assert "/g/home/r/cake" in server.mealie_get_recipe("cake")


# --------------------------------------------------------------------------
# Error handling
# --------------------------------------------------------------------------

def test_tool_error_propagates(mealie):
    from fastmcp.exceptions import ToolError

    mealie["responses"][("GET", "/api/recipes/nope")] = ToolError("Mealie API returned 404")

    with pytest.raises(ToolError):
        server.mealie_get_recipe("nope")


# --------------------------------------------------------------------------
# Tool surface contract
# --------------------------------------------------------------------------

def _tools():
    import asyncio

    return {t.name: t for t in asyncio.run(server.mcp.list_tools())}


def test_all_tools_are_prefixed():
    names = list(_tools())

    assert len(names) == 23
    assert all(n.startswith("mealie_") for n in names)


def test_read_tools_marked_read_only():
    tools = _tools()

    for name in ("mealie_list_recipes", "mealie_get_recipe", "mealie_list_units"):
        assert tools[name].annotations.read_only_hint is True
        assert tools[name].annotations.destructive_hint is False


def test_destructive_tools_marked_destructive():
    tools = _tools()

    for name in ("mealie_delete_recipe", "mealie_delete_mealplan", "mealie_clear_checked_items"):
        assert tools[name].annotations.destructive_hint is True


def test_every_tool_has_description():
    for name, tool in _tools().items():
        assert tool.description, f"{name} has no description"
