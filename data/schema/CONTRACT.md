# Combat Robot Database — Research Output Contract (v1)

Every research agent writes **exactly one file**: `data/research/<topic_id>.json`

It MUST be valid JSON (no trailing commas, no comments, no markdown fences) with this envelope:

```json
{
  "topic_id": "drive-motors",
  "title": "Drive Motors & Drivetrain Sizing",
  "scope_note": "1-3 sentences on what this file covers.",
  "entities": [ ... ],
  "chunks": [ ... ]
}
```

## entities[] — structured records

Common fields on EVERY entity:

| field | type | required | notes |
|---|---|---|---|
| `id` | string | yes | globally unique kebab-case, prefixed by type, e.g. `motor-fingertech-silver-spark` |
| `type` | string | yes | one of the types below |
| `name` | string | yes | display name |
| `aliases` | string[] | no | other names people use |
| `summary` | string | yes | 1-3 sentences, plain prose |
| `weight_classes` | string[] | no | any of: `fairyweight`, `antweight`, `plastic-antweight`, `beetleweight`, `plastic-beetleweight`, `hobbyweight`, `featherweight`, `lightweight`, `middleweight`, `heavyweight` |
| `tags` | string[] | no | free-form lowercase keywords |
| `specs` | object | no | flat key -> value. NUMERIC VALUES AS NUMBERS. Units go in the key name: `weight_g`, `voltage_nominal_v`, `kv_rpm_per_v`, `stall_current_a`, `price_usd`, `rpm_no_load`, `shaft_dia_mm`, `gear_ratio`, `torque_stall_kgcm`, `dia_mm`, `length_mm`, `resistance_ohm`, `max_current_a`, `capacity_mah`, `c_rating`, `cells_s`, `density_g_cm3`, `yield_strength_mpa`, `hardness_hrc`, `cost_per_kg_usd` |
| `pros` | string[] | no | |
| `cons` | string[] | no | |
| `notes` | string | no | longer free prose, markdown allowed |
| `sources` | string[] | no | URLs, or "domain knowledge" if uncited |
| `confidence` | string | no | `high` \| `medium` \| `low` — use `low` for numbers you could not verify |

### Entity `type` values and their extra fields

- **`weight_class`** — extra: `limit_lb`(number), `limit_kg`(number), `common_orgs`(string[]), `typical_arena`(string)
- **`archetype`** — extra: `family`(string: spinner/control/lifter/crusher/hammer/rammer/other), `counters`(string[] of archetype ids or names), `countered_by`(string[]), `difficulty`(string: beginner/intermediate/advanced), `typical_weapon_motor`(string), `typical_drive`(string), `weight_budget_pct`(object: e.g. `{"weapon":35,"drive":22,"armor":25,"electronics":12,"fasteners":6}`)
- **`component`** — extra: `category` (one of `drive-motor`, `weapon-motor`, `esc-drive`, `esc-weapon`, `receiver`, `transmitter`, `battery`, `wheel`, `hub`, `bearing`, `fastener`, `switch`, `servo`, `gearbox`, `belt-pulley`, `connector`, `misc`), `vendor`(string), `product_url`(string), `alternatives`(string[])
- **`material`** — extra: `category` (`metal`, `plastic-printed`, `plastic-stock`, `composite`, `elastomer`), `use_cases`(string[]), `machinability`(string), `printable`(boolean)
- **`formula`** — extra: `expression`(string, plain text math), `variables`(object: symbol -> description incl. units), `worked_example`(string), `applies_to`(string[])
- **`bot`** — extra: `builder`(string), `country`(string), `weapon_type`(string), `achievements`(string[]), `active_years`(string), `image_hint`(string — what a photo of it looks like; do NOT invent image URLs)
- **`event`** — extra: `organization`(string), `location`(string), `cadence`(string), `classes_run`(string[]), `website`(string)
- **`supplier`** — extra: `country`(string), `website`(string), `specialties`(string[]), `ships_internationally`(boolean)
- **`ruleset`** — extra: `organization`(string), `version`(string), `key_rules`(string[]), `banned`(string[]), `website`(string)
- **`term`** — glossary entry. extra: `category`(string)
- **`kit`** — extra: `vendor`(string), `price_usd`(number), `skill_level`(string), `includes`(string[]), `product_url`(string)

## chunks[] — long-form knowledge for retrieval

Each chunk is a self-contained explainer an LLM can quote from. Aim for 200-600 words each.

```json
{
  "id": "chunk-drive-motor-gear-ratio-selection",
  "title": "Choosing a gear ratio for antweight drive",
  "section": "Drivetrain",
  "body_md": "markdown text, may include tables, formulas, numbers",
  "entity_refs": ["motor-fingertech-silver-spark"],
  "weight_classes": ["antweight", "plastic-antweight"],
  "tags": ["drivetrain", "gear-ratio"],
  "sources": ["https://..."]
}
```

## Hard rules

1. **Bias every judgement toward 1 lb antweight and plastic antweight.** Other classes are context only.
2. **Real numbers beat prose.** If you state a motor has a KV, put the number in `specs`. If you are unsure, still give a realistic range in `notes` and set `confidence: "low"`. Never leave a spec blank just because you're unsure — say so instead.
3. **Never invent image URLs, product URLs, or prices you did not see.** Omit the field instead.
4. **Do not duplicate ids.** Prefix everything with your `topic_id` domain when in doubt.
5. Write the file with `Write`. Validate it parses: `python3 -c "import json;json.load(open('data/research/<topic_id>.json'))"`.
6. Cite sources as URLs wherever you used the web.
