# mealie-mcp-server

A [Model Context Protocol](https://modelcontextprotocol.io) server that connects any MCP client — Claude Desktop, Cursor, or anything else — to a self-hosted [Mealie](https://mealie.io) instance.

**23 tools**, all prefixed `mealie_`, covering:

- **Recipes** — search, read (formatted ingredients/instructions/nutrition), create from scratch or by URL, update, delete
- **Meal plans** — today's meals, date-range views, create/delete entries
- **Shopping lists** — list, read, create, add items or a whole recipe's ingredients, check off, clear
- **Organization** — categories, tags, foods, measurement units

Every tool carries [MCP tool annotations](https://modelcontextprotocol.io/specification/2025-06-18/server/tools#tool-annotations) (`readOnly` / `write` / `destructive`) so clients can warn you before anything destructive runs.

## Requirements

- Python **3.10+** (or Docker)
- A running Mealie instance and an API token
  (Mealie → your profile → **User Settings → API Tokens**)

## Environment variables

| Variable | Required | Example value |
|---|---|---|
| `MEALIE_URL` | ✅ | `https://mealie.example.com` |
| `MEALIE_API_KEY` | ✅ | `<your-mealie-api-key>` |

Placeholders only — never commit real values. The server reads them from its environment at startup.

## Install

### pip

The PyPI distribution is `mcp-server-mealie`; the command it installs is
`mealie-mcp-server`.

```bash
pip install mcp-server-mealie
MEALIE_URL=https://mealie.example.com MEALIE_API_KEY=<token> mealie-mcp-server
```

### uvx (no install)

```bash
uvx --from mcp-server-mealie mealie-mcp-server
```

### From source

```bash
git clone https://github.com/margosmark/mealie-mcp-server.git
cd mealie-mcp-server
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

### Docker

```bash
git clone https://github.com/margosmark/mealie-mcp-server.git
cd mealie-mcp-server
docker build -t mealie-mcp .
```

> The server speaks MCP over **stdio** — you don't run it by hand; your MCP client starts it (locally or via `docker run -i --rm`, see below).

## Client configuration

### Claude Desktop

Add to `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`,
Windows: `%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "mealie": {
      "command": "mealie-mcp-server",
      "env": {
        "MEALIE_URL": "https://mealie.example.com",
        "MEALIE_API_KEY": "<your-mealie-api-key>"
      }
    }
  }
}
```

Using Docker instead of a local Python environment:

```json
{
  "mcpServers": {
    "mealie": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "MEALIE_URL",
        "-e", "MEALIE_API_KEY",
        "mealie-mcp"
      ],
      "env": {
        "MEALIE_URL": "https://mealie.example.com",
        "MEALIE_API_KEY": "<your-mealie-api-key>"
      }
    }
  }
}
```

(`-e NAME` with no value forwards the entry from the client's `env` block into the container.)

### Cursor

Create `.cursor/mcp.json` in your project (or `~/.cursor/mcp.json` for global) with the **same JSON as above**:

```json
{
  "mcpServers": {
    "mealie": {
      "command": "mealie-mcp-server",
      "env": {
        "MEALIE_URL": "https://mealie.example.com",
        "MEALIE_API_KEY": "<your-mealie-api-key>"
      }
    }
  }
}
```

Restart the client after editing; the `mealie_*` tools appear in the tool picker.

## Sample session

Captured live from this server (mock Mealie backend, real MCP round-trip):

```text
# connected — tools/list
(23 tools) mealie_search_recipes, mealie_get_recipe, mealie_list_recipes, mealie_create_recipe, mealie_create_recipe_from_url, mealie_update_recipe, mealie_delete_recipe, mealie_get_today_mealplan, mealie_list_mealplans, mealie_create_mealplan, mealie_delete_mealplan, mealie_list_shopping_lists, mealie_get_shopping_list, mealie_create_shopping_list, mealie_add_shopping_item, mealie_add_recipe_to_shopping_list, mealie_check_shopping_item, mealie_delete_shopping_item, mealie_clear_checked_items, mealie_list_categories, mealie_list_tags, mealie_list_foods, mealie_list_units

> mealie_search_recipes(query='pasta')
- **Creamy Tuscan Pasta** (slug: creamy-tuscan-pasta) — Dinner
- **Lemon Herb Chicken** (slug: lemon-herb-chicken) — Dinner

> mealie_get_recipe(slug='creamy-tuscan-pasta')
# Creamy Tuscan Pasta

Weeknight pasta with sun-dried tomatoes and spinach.

**Prep:** 00:10:00 | **Cook:** 00:20:00 | **Total:** 00:30:00
**Servings:** 4

**Categories:** Dinner
**Tags:** quick

## Ingredients
- 340 gram penne
- 2 cup spinach fresh

## Instructions
1. Boil pasta until al dente.
2. Simmer sauce, add spinach, toss and serve.

## Nutrition
- calories: 520
- proteinContent: 18

🔗 https://mealie.example.com/g/home/r/creamy-tuscan-pasta

> mealie_get_today_mealplan()
## Today's Meals

- **dinner**: Creamy Tuscan Pasta

> mealie_add_shopping_item(list_id='list-1', food_name='parmesan', quantity=1, unit='block')
Added 1.0 block parmesan to list

```

## Tools (23)

| Tool | Description | Type |
|---|---|---|
| `mealie_search_recipes` | Search recipes by name, ingredient, or keyword. The query is required; use mealie_list_recipes to browse all. | 🟢 read |
| `mealie_get_recipe` | Get full recipe details by slug. Includes ingredients, instructions, nutrition, times. | 🟢 read |
| `mealie_list_recipes` | List recipes with pagination. Returns recipe names and slugs. | 🟢 read |
| `mealie_create_recipe` | Create a new recipe. Ingredients and instructions are newline-separated strings. | 🟡 write |
| `mealie_create_recipe_from_url` | Import a recipe by scraping a URL. Returns the created recipe slug. | 🟡 write |
| `mealie_update_recipe` | Update a recipe's name and/or description. | 🟡 write |
| `mealie_delete_recipe` | Delete a recipe by slug. This cannot be undone. | 🔴 destructive |
| `mealie_get_today_mealplan` | Get today's meal plan. | 🟢 read |
| `mealie_list_mealplans` | List meal plans for a date range. Dates in YYYY-MM-DD format. | 🟢 read |
| `mealie_create_mealplan` | Create a meal plan entry. entry_type: breakfast/lunch/dinner/snack. | 🟡 write |
| `mealie_delete_mealplan` | Delete a meal plan entry by ID. | 🔴 destructive |
| `mealie_list_shopping_lists` | List all shopping lists. | 🟢 read |
| `mealie_get_shopping_list` | Get a shopping list with all its items. | 🟢 read |
| `mealie_create_shopping_list` | Create a new shopping list. | 🟡 write |
| `mealie_add_shopping_item` | Add an item to a shopping list. | 🟡 write |
| `mealie_add_recipe_to_shopping_list` | Add all ingredients from a recipe to a shopping list. | 🟡 write |
| `mealie_check_shopping_item` | Mark a shopping list item as checked or unchecked. | 🟡 write |
| `mealie_delete_shopping_item` | Remove an item from a shopping list. | 🔴 destructive |
| `mealie_clear_checked_items` | Remove all checked items from a shopping list. | 🔴 destructive |
| `mealie_list_categories` | List all recipe categories. | 🟢 read |
| `mealie_list_tags` | List all recipe tags. | 🟢 read |
| `mealie_list_foods` | List known food items/ingredients. | 🟢 read |
| `mealie_list_units` | List measurement units. | 🟢 read |

## License

[MIT](LICENSE) © Mark Arslan
