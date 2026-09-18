"""
Mealie MCP Server — Minimal, self-built MCP server for Mealie recipe management.
Covers: recipes, meal plans, shopping lists, categories, tags, foods, units.
"""

import os
import json
from typing import Optional
from fastmcp import FastMCP
import httpx

# --- Config ---
MEALIE_URL = os.environ["MEALIE_URL"].rstrip("/")
MEALIE_API_KEY = os.environ["MEALIE_API_KEY"]
HOUSEHOLD_ID = os.environ.get("MEALIE_HOUSEHOLD_ID", "5bc04442-abbd-4aab-b88f-a7105809bc18")

HEADERS = {
    "Authorization": f"Bearer {MEALIE_API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

mcp = FastMCP("mealie")


# --- Helpers ---
def _get(path: str, params: dict = None) -> dict:
    r = httpx.get(f"{MEALIE_URL}{path}", headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json() if r.text else {}


def _post(path: str, data: dict = None) -> dict:
    r = httpx.post(f"{MEALIE_URL}{path}", headers=HEADERS, json=data or {}, timeout=30)
    r.raise_for_status()
    return r.json() if r.text else {}


def _put(path: str, data: dict = None) -> dict:
    r = httpx.put(f"{MEALIE_URL}{path}", headers=HEADERS, json=data or {}, timeout=30)
    r.raise_for_status()
    return r.json() if r.text else {}


def _delete(path: str) -> dict:
    r = httpx.delete(f"{MEALIE_URL}{path}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json() if r.text else {}


# ============================================================
# RECIPES
# ============================================================

@mcp.tool()
def search_recipes(query: str, per_page: int = 20) -> str:
    """Search recipes by name, ingredient, or keyword. Returns list of matching recipes."""
    data = _get("/api/recipes", {"search": query, "perPage": per_page})
    items = data.get("items", [])
    if not items:
        return "No recipes found."
    lines = []
    for r in items:
        cats = ", ".join(c.get("name", "") for c in r.get("recipeCategory", []))
        lines.append(f"- **{r['name']}** (slug: {r['slug']}) — {cats}")
    return "\n".join(lines)


@mcp.tool()
def get_recipe(slug: str) -> str:
    """Get full recipe details by slug. Includes ingredients, instructions, nutrition, times."""
    r = _get(f"/api/recipes/{slug}")
    lines = [f"# {r['name']}", ""]
    if r.get("description"):
        lines.append(r["description"])
        lines.append("")
    if r.get("prepTime") or r.get("cookTime") or r.get("totalTime"):
        lines.append(f"**Prep:** {r.get('prepTime', 'N/A')} | **Cook:** {r.get('cookTime', 'N/A')} | **Total:** {r.get('totalTime', 'N/A')}")
        lines.append(f"**Servings:** {r.get('servings', 'N/A')}")
        lines.append("")
    cats = [c.get("name", "") for c in r.get("recipeCategory", [])]
    tags = [t.get("name", "") for t in r.get("tags", [])]
    if cats:
        lines.append(f"**Categories:** {', '.join(cats)}")
    if tags:
        lines.append(f"**Tags:** {', '.join(tags)}")
    lines.append("")
    lines.append("## Ingredients")
    for ing in r.get("recipeIngredient", []):
        note = ing.get("note", "")
        qty = ing.get("quantity", "")
        unit = ing.get("unit", {})
        unit_name = unit.get("name", "") if unit else ""
        food = ing.get("food", {})
        food_name = food.get("name", "") if food else ""
        parts = [str(qty) if qty else "", unit_name, food_name, note]
        lines.append(f"- {' '.join(p for p in parts if p)}")
    lines.append("")
    lines.append("## Instructions")
    for i, step in enumerate(r.get("recipeInstructions", []), 1):
        lines.append(f"{i}. {step.get('text', '')}")
    nut = r.get("nutrition", {})
    if nut and any(v for v in nut.values() if v):
        lines.append("")
        lines.append("## Nutrition")
        for k, v in nut.items():
            if v:
                lines.append(f"- {k}: {v}")
    link = f"{MEALIE_URL}/g/home/r/{slug}"
    lines.append(f"\n🔗 {link}")
    return "\n".join(lines)


@mcp.tool()
def list_recipes(per_page: int = 50, page: int = 1) -> str:
    """List recipes with pagination. Returns recipe names and slugs."""
    data = _get("/api/recipes", {"perPage": per_page, "page": page})
    items = data.get("items", [])
    total = data.get("total", 0)
    if not items:
        return "No recipes found."
    lines = [f"**{total} total recipes** (showing page {page})", ""]
    for r in items:
        lines.append(f"- {r['name']} (slug: {r['slug']})")
    return "\n".join(lines)


@mcp.tool()
def create_recipe(
    name: str,
    description: str = "",
    servings: int = 4,
    prep_time: str = "",
    cook_time: str = "",
    ingredients: str = "",
    instructions: str = "",
    category: str = "",
) -> str:
    """Create a new recipe. Ingredients and instructions are newline-separated strings.
    Times format: 'HH:MM:SS' (e.g. '00:15:00')."""
    recipe = {
        "name": name,
        "description": description,
        "servings": servings,
    }
    if prep_time:
        recipe["prepTime"] = prep_time
    if cook_time:
        recipe["cookTime"] = cook_time
    if category:
        recipe["recipeCategory"] = [{"name": category}]
    if ingredients:
        recipe["recipeIngredient"] = [{"note": line.strip()} for line in ingredients.strip().split("\n") if line.strip()]
    if instructions:
        recipe["recipeInstructions"] = [{"text": line.strip()} for line in instructions.strip().split("\n") if line.strip()]

    r = _post("/api/recipes", recipe)
    slug = r.get("slug", "unknown")
    link = f"{MEALIE_URL}/g/home/r/{slug}"
    return f"Created recipe: **{name}**\n🔗 {link}"


@mcp.tool()
def create_recipe_from_url(url: str) -> str:
    """Import a recipe by scraping a URL. Returns the created recipe slug."""
    r = _post("/api/recipes/create/url", {"url": url})
    slug = r.get("slug", "unknown")
    link = f"{MEALIE_URL}/g/home/r/{slug}"
    return f"Imported recipe (slug: {slug})\n🔗 {link}"


@mcp.tool()
def update_recipe(slug: str, name: str = "", description: str = "") -> str:
    """Update a recipe's name and/or description."""
    data = {}
    if name:
        data["name"] = name
    if description:
        data["description"] = description
    if not data:
        return "Nothing to update."
    _put(f"/api/recipes/{slug}", data)
    return f"Updated recipe: {slug}"


@mcp.tool()
def delete_recipe(slug: str) -> str:
    """Delete a recipe by slug."""
    _delete(f"/api/recipes/{slug}")
    return f"Deleted recipe: {slug}"


# ============================================================
# MEAL PLANS
# ============================================================

@mcp.tool()
def get_today_mealplan() -> str:
    """Get today's meal plan."""
    items = _get("/api/households/mealplans/today")
    if not items:
        return "No meals planned for today."
    lines = ["## Today's Meals", ""]
    for entry in items:
        meal_type = entry.get("entryType", "unknown")
        title = entry.get("title", "No title")
        recipe = entry.get("recipe")
        recipe_name = recipe.get("name", "") if recipe else ""
        display = recipe_name or title
        lines.append(f"- **{meal_type}**: {display}")
    return "\n".join(lines)


@mcp.tool()
def list_mealplans(start_date: str, end_date: str) -> str:
    """List meal plans for a date range. Dates in YYYY-MM-DD format."""
    items = _get("/api/households/mealplans", {"start_date": start_date, "end_date": end_date})
    if not items:
        return "No meal plans found for this range."
    lines = [f"## Meal Plans ({start_date} to {end_date})", ""]
    for entry in items:
        date = entry.get("date", "?")
        meal_type = entry.get("entryType", "?")
        title = entry.get("title", "No title")
        recipe = entry.get("recipe")
        recipe_name = recipe.get("name", "") if recipe else ""
        display = recipe_name or title
        lines.append(f"- **{date}** {meal_type}: {display}")
    return "\n".join(lines)


@mcp.tool()
def create_mealplan(date: str, entry_type: str, title: str = "", recipe_slug: str = "") -> str:
    """Create a meal plan entry. entry_type: breakfast/lunch/dinner/snack.
    Provide either title (free text) or recipe_slug (link to a recipe)."""
    entry = {"date": date, "entryType": entry_type}
    if title:
        entry["title"] = title
    if recipe_slug:
        entry["recipe"] = {"slug": recipe_slug}
    r = _post("/api/households/mealplans", entry)
    return f"Created meal plan: {date} {entry_type}"


@mcp.tool()
def delete_mealplan(mealplan_id: str) -> str:
    """Delete a meal plan entry by ID."""
    _delete(f"/api/households/mealplans/{mealplan_id}")
    return f"Deleted meal plan entry: {mealplan_id}"


# ============================================================
# SHOPPING LISTS
# ============================================================

@mcp.tool()
def list_shopping_lists() -> str:
    """List all shopping lists."""
    data = _get("/api/households/shopping/lists")
    items = data.get("items", []) if isinstance(data, dict) else data
    if not items:
        return "No shopping lists found."
    lines = []
    for sl in items:
        name = sl.get("name", "Unnamed")
        sid = sl.get("id", "?")
        count = len(sl.get("shoppingListItems", []))
        lines.append(f"- **{name}** (id: {sid}, {count} items)")
    return "\n".join(lines)


@mcp.tool()
def get_shopping_list(list_id: str) -> str:
    """Get a shopping list with all its items."""
    sl = _get(f"/api/households/shopping/lists/{list_id}")
    name = sl.get("name", "Unnamed")
    items = sl.get("shoppingListItems", [])
    if not items:
        return f"**{name}** — empty"
    lines = [f"## {name}", ""]
    for item in items:
        checked = "✅" if item.get("checked", False) else "⬜"
        food = item.get("food", {})
        food_name = food.get("name", "Unknown") if food else "Unknown"
        qty = item.get("quantity", "")
        unit = item.get("unit", {})
        unit_name = unit.get("name", "") if unit else ""
        parts = [str(qty) if qty else "", unit_name, food_name]
        lines.append(f"{checked} {' '.join(p for p in parts if p)}")
    return "\n".join(lines)


@mcp.tool()
def create_shopping_list(name: str) -> str:
    """Create a new shopping list."""
    r = _post("/api/households/shopping/lists", {"name": name})
    sid = r.get("id", "unknown")
    return f"Created shopping list: **{name}** (id: {sid})"


@mcp.tool()
def add_shopping_item(list_id: str, food_name: str, quantity: float = 1, unit: str = "") -> str:
    """Add an item to a shopping list."""
    item = {"shoppingListId": list_id, "quantity": quantity, "checked": False}
    if food_name:
        item["food"] = {"name": food_name}
    if unit:
        item["unit"] = {"name": unit}
    _post(f"/api/households/shopping/lists/{list_id}/items", item)
    return f"Added {quantity} {unit} {food_name} to list"


@mcp.tool()
def add_recipe_to_shopping_list(list_id: str, recipe_slug: str) -> str:
    """Add all ingredients from a recipe to a shopping list."""
    # Get recipe to find its ID
    recipe = _get(f"/api/recipes/{recipe_slug}")
    recipe_id = recipe.get("id")
    if not recipe_id:
        return f"Recipe not found: {recipe_slug}"
    _post(f"/api/households/shopping/lists/{list_id}/recipe/{recipe_id}")
    return f"Added ingredients from **{recipe.get('name', recipe_slug)}** to shopping list"


@mcp.tool()
def check_shopping_item(list_id: str, item_id: str, checked: bool = True) -> str:
    """Mark a shopping list item as checked or unchecked."""
    _put(f"/api/households/shopping/lists/{list_id}/items/{item_id}", {"checked": checked})
    status = "checked" if checked else "unchecked"
    return f"Item {status}"


@mcp.tool()
def delete_shopping_item(list_id: str, item_id: str) -> str:
    """Remove an item from a shopping list."""
    _delete(f"/api/households/shopping/lists/{list_id}/items/{item_id}")
    return "Item removed"


@mcp.tool()
def clear_checked_items(list_id: str) -> str:
    """Remove all checked items from a shopping list."""
    _delete(f"/api/households/shopping/lists/{list_id}/clear")
    return "Checked items cleared"


# ============================================================
# ORGANIZATION
# ============================================================

@mcp.tool()
def list_categories() -> str:
    """List all recipe categories."""
    data = _get("/api/organizers/categories")
    items = data.get("items", []) if isinstance(data, dict) else data
    if not items:
        return "No categories found."
    lines = []
    for cat in items:
        lines.append(f"- {cat.get('name', '?')} (id: {cat.get('id', '?')})")
    return "\n".join(lines)


@mcp.tool()
def list_tags() -> str:
    """List all recipe tags."""
    data = _get("/api/organizers/tags")
    items = data.get("items", []) if isinstance(data, dict) else data
    if not items:
        return "No tags found."
    lines = []
    for tag in items:
        lines.append(f"- {tag.get('name', '?')} (id: {tag.get('id', '?')})")
    return "\n".join(lines)


@mcp.tool()
def list_foods(per_page: int = 50) -> str:
    """List known food items/ingredients."""
    data = _get("/api/foods", {"perPage": per_page})
    items = data.get("items", []) if isinstance(data, dict) else data
    if not items:
        return "No foods found."
    lines = [f"- {f.get('name', '?')}" for f in items]
    return "\n".join(lines)


@mcp.tool()
def list_units() -> str:
    """List measurement units."""
    data = _get("/api/units")
    items = data.get("items", []) if isinstance(data, dict) else data
    if not items:
        return "No units found."
    lines = [f"- {u.get('name', '?')} ({u.get('abbreviation', '')})" for u in items]
    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    mcp.run(transport="stdio")
