# Combat Robot Database

A researched knowledge base for **1 lb antweight** and **plastic antweight** combat
robots — design archetypes, motor sizing, materials, electronics, the engineering
maths, and the rules — built to be read by people *and* queried by an LLM agent.

Three things come out of one dataset:

| | What it is | Entry point |
|---|---|---|
| **Website** | Static site with schematic diagrams, spec tables, guides and interactive calculators | `web/index.html` |
| **MCP server** | Nine tools any MCP client can call — search, lookup, compare, matchups, build guides, calculations | `agent/mcp_server.py` |
| **Discord bot** | An OpenAI-compatible LLM answers build questions in your server, using the same tools | `discord-bot/bot.py` |
| **HTTP API** | Read-only JSON endpoints for anything else | `agent/api.py` |

All three call the same query layer (`agent/kb.py`), so the site, the bot and the
MCP server never disagree with each other.

---

## Quick start

```bash
# 1. Build the database from the research files
python3 scripts/build_db.py

# 2. Generate the website
python3 scripts/build_site.py

# 3. View it (a server is needed — search uses fetch(), which browsers
#    block on file:// URLs)
cd web && python3 -m http.server 8000
```

Nothing but Python 3.8+ is required for the database, the website and the MCP
server. Only the Discord bot needs packages installed.

---

## Repository layout

```
data/
  schema/CONTRACT.md      The output contract every research agent wrote against
  research/*.json         Raw per-topic research output (the source of truth)
  combat_robots.db        Built SQLite database with FTS5 full-text search
  combat_robots.json      The whole dataset as one JSON bundle
  index.json              Trimmed index the website's search loads
  build_report.md         What was ingested, merged, and flagged on the last build
scripts/
  build_db.py             research/*.json  ->  SQLite + JSON exports
  build_site.py           SQLite  ->  static HTML site
  photos.py               Sourced real-robot photo mappings for archetypes\n  illustrations.py        Legacy schematic utility (not used by the website)
agent/
  kb.py                   Query layer + engineering calculators (shared by all)
  mcp_server.py           MCP stdio server, zero dependencies
  api.py                  Read-only HTTP JSON API, zero dependencies
discord-bot/
  bot.py                  Discord bot using OpenAI-compatible tool calling
web/                      Generated site (committed so it can be hosted directly)
tests/test_kb.py          Test suite for the query layer, builders and MCP server
```

## Data model

Two kinds of record:

- **Entities** — structured records: `archetype`, `component`, `material`, `formula`,
  `weight_class`, `ruleset`, `bot`, `event`, `supplier`, `kit`, `term`. Each carries a
  `specs` object with real numbers (`kv_rpm_per_v`, `weight_g`, `stall_current_a`,
  `density_g_cm3`, …), plus pros, cons, sources and a confidence level.
- **Chunks** — self-contained long-form explainers, 200–600 words, written to be
  quoted by an LLM.

Both are indexed with SQLite FTS5 and cross-linked, so an agent can search, then
pull the full record, then follow references.

---

## Using it from an LLM

### MCP

```bash
claude mcp add combat-robots -- python3 /absolute/path/to/agent/mcp_server.py
```

Tools exposed:

| Tool | What it does |
|---|---|
| `database_schema` | Inspect raw SQLite tables/columns and JSON fields |
| `query_database` | Run model-written, read-only SQL and return raw rows |
| `search_knowledge` | FTS5 discovery when the model does not know an id/name yet |
| `get_entity` | Fetch one stored record in full by id or name |
| `get_chunk` | Fetch one long-form stored chunk in full |
| `list_entities` | Browse stored entities by type/class/tag/category |
| `compare_entities` | Return raw records plus a side-by-side spec table |
| `calculate` | Eleven deterministic engineering calculations (below) |
| `kb_stats` | Raw database coverage metadata |

### Discord bot

The bot uses the standard OpenAI-compatible Chat Completions + function-calling
format. OpenRouter is the default endpoint, but you can point the same code at
Agent Router or another compatible gateway with environment variables.

```bash
pip install -r discord-bot/requirements.txt

export DISCORD_TOKEN=...                       # Discord developer portal
export OPENROUTER_API_KEY=...                  # or set LLM_API_KEY
export LLM_MODEL=anthropic/claude-sonnet-4.6  # any tool-capable model
python3 discord-bot/bot.py
```

Optional provider settings:

```bash
export LLM_BASE_URL=https://openrouter.ai/api/v1
export LLM_API_KEY=...          # overrides OPENROUTER_API_KEY
export LLM_MODEL=...            # provider-specific model id
export LLM_MAX_TOKENS=4000
export LLM_MAX_TOOL_TURNS=10
```

For an Agent Router or other OpenAI-compatible gateway, change only
`LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL`. The database/MCP tool layer
does not need any provider-specific changes.

The bot needs the **Message Content** intent enabled in the Discord developer
portal. Then mention it, or use the slash commands:

```
@bot what weapon motor for a plastic ant vertical spinner?
/ask      natural-language question
/search   raw knowledge base search
/part     look up one component or archetype
/calc     run a calculation
/matchup  archetype vs archetype
/stats    what's in the database
```

The **LLM is the reasoning layer; SQLite is only the evidence store.** The bot's
preferred analysis tool is `query_database`: the model writes its own read-only SQL,
joins/filter/aggregates the raw records it needs, compares candidates, and makes the
engineering judgment itself. `database_schema` lets it inspect the schema, while
`search_knowledge` is only a discovery helper for unknown names/ids. Higher-level
helpers that preassemble a build recommendation or matchup verdict are intentionally
not exposed to the LLM tool list.

The database connection used by `query_database` is opened read-only and guarded by
a SQLite authorizer, so the model cannot INSERT/UPDATE/DELETE, ATTACH another
database, or change PRAGMAs. Numeric engineering math still goes through
`calculate`. If the model uses its entire tool budget, the bot makes a final
no-tools completion from the raw evidence already gathered instead of discarding it.
Use a strong model that supports function/tool calling.

### HTTP API

For anything that speaks HTTP rather than MCP — a webhook, a bot framework in
another language, a custom tool definition:

```bash
python3 agent/api.py --port 8080
curl 'http://127.0.0.1:8080/search?q=drum+spinner&weight_class=antweight'
curl 'http://127.0.0.1:8080/calculate/tip_speed?rpm=20000&radius_mm=45'
```

Endpoints: `/health` `/stats` `/search` `/entities` `/entity/<id>`
`/chunk/<id>` `/compare` `/matchup` `/build` `/calculators` `/calculate/<name>`. Standard
library only, read-only, CORS-enabled.

### Direct Python

```python
import sys; sys.path.insert(0, "agent")
import kb

db = kb.KnowledgeBase()
db.database_schema()
db.query_database("""
    SELECT id, name, json_extract(specs, '$.weight_g') AS weight_g
    FROM entities
    WHERE type='component'
    ORDER BY weight_g
    LIMIT 20
""")
db.search("drum spinner bite", weight_class="antweight")
db.get_entity("archetype-drum-spinner")

kb.tip_speed(rpm=20000, radius_mm=45)          # -> 94.25 m/s
moi = kb.moment_of_inertia("disc", mass_g=120, dim_mm=90)
kb.kinetic_energy(moi["moi_kg_m2"], rpm=20000) # -> 266 J
```

## Calculators

`tip_speed` · `moment_of_inertia` · `kinetic_energy` · `spin_up_time` ·
`drive_speed` · `traction_force` · `motor_constants` · `bite_depth` ·
`gyro_torque` · `battery_check` · `weight_budget`

Implemented once in `agent/kb.py` and mirrored in JavaScript on the site's
calculators page, so all three surfaces give identical answers.

On motor constants: this project uses the physically exact
`Kt [N·m/A] = 9.5493 / Kv`, i.e. `60 / (2π·Kv)`. The hobby shorthand `8.27 / Kv`
that circulates in build threads bakes in roughly 87% efficiency; it appears in
some source material, and where it does the entry says so.

---

## Hosting the site

The site is plain static files, so anything can serve `web/`. A GitHub Pages
workflow is included but inert until you turn Pages on:
**Settings → Pages → Build and deployment → Source: "GitHub Actions"**. After
that, pushes to `main` rebuild the database from the research files and publish
the result, so the live site always matches the committed data.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

67 tests covering the calculators against hand-worked values, FTS input
sanitisation, the research-file normaliser and merge logic, the markdown
renderer, diagram matching, the MCP server over real stdio JSON-RPC, and
integrity of whatever database is currently built.

## Adding to the database

Write a new file into `data/research/` following `data/schema/CONTRACT.md`, then
re-run the two build scripts. The builder is deliberately forgiving — it repairs
malformed weight-class names, coerces numeric strings, resolves cross-references by
name when ids are wrong, merges records that two topics both describe, and reports
everything it had to fix in `data/build_report.md`.

## Accuracy and safety

Figures are compiled from public sources: vendor listings, community write-ups,
rulebooks and engineering references. Records whose numbers could not be verified
against a primary source are marked `confidence: "low"` and flagged as unverified on
the website.

**Check the manufacturer's own specification before you buy, and your event's
current published ruleset before you enter.** Rules change between seasons and
between organisations.

A 1 lb spinner can store a few hundred joules — enough to break bone. Use a weapon
lock whenever the robot is powered outside an arena, fit a removable link, set and
test your failsafe, and only spin a weapon inside a proper enclosure.
