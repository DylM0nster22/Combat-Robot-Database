#!/usr/bin/env python3
"""MCP server exposing the combat robot knowledge base to an LLM agent.

Speaks MCP over stdio using plain JSON-RPC 2.0 with no third-party packages,
so it runs anywhere python3 does:

    python3 agent/mcp_server.py

Register it with any MCP client, e.g. Claude Code:

    claude mcp add combat-robots -- python3 /abs/path/agent/mcp_server.py

Every tool returns JSON text so the model can quote exact numbers rather than
paraphrasing them.
"""

import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import kb  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "combat-robot-database", "version": "1.2.0"}

_KB = None


def get_kb():
    global _KB
    if _KB is None:
        _KB = kb.KnowledgeBase(os.environ.get("COMBAT_ROBOT_DB", kb.DEFAULT_DB))
    return _KB


WEIGHT_CLASS_ENUM = kb.WEIGHT_CLASSES
ENTITY_TYPE_ENUM = ["weight_class", "archetype", "component", "material",
                    "formula", "bot", "event", "supplier", "ruleset", "term", "kit"]

TOOLS = [
    {
        "name": "database_schema",
        "description": (
            "Inspect the raw SQLite schema. Use this when you need to know table or "
            "column names before writing SQL. The database stores evidence; YOU are "
            "responsible for deciding what facts matter and for reasoning from them."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "query_database",
        "description": (
            "Run one read-only SELECT/WITH query against the combat-robot SQLite "
            "database and return RAW ROWS. This is the preferred tool for serious "
            "analysis: write the SQL yourself, join/filter/aggregate the evidence you "
            "need, then make the engineering judgment yourself. JSON fields can be "
            "queried with json_extract/json_each. No tool-generated recommendation "
            "or verdict is added."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "One SQLite SELECT or WITH query."
                },
                "params": {
                    "description": "Optional SQLite bind parameters as a JSON array or object.",
                    "oneOf": [
                        {"type": "array", "items": {}},
                        {"type": "object", "additionalProperties": {}}
                    ],
                },
                "max_rows": {
                    "type": "integer", "default": 50, "minimum": 1, "maximum": 200,
                    "description": "Maximum rows returned to the model."
                },
            },
            "required": ["sql"],
        },
    },
    {
        "name": "search_knowledge",
        "description": (
            "FTS5 retrieval helper for when you do not yet know the exact entity/chunk "
            "ids or terminology. Returns search hits/previews only; it does NOT decide "
            "the answer. After discovery, fetch the record or query_database for the "
            "specific raw facts you need."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search terms, e.g. 'plastic ant weapon motor' or 'gyro dance'."},
                "kind": {"type": "string", "enum": ["all", "entities", "chunks"], "default": "all"},
                "entity_type": {"type": "string", "enum": ENTITY_TYPE_ENUM,
                                 "description": "Restrict entity results to one type."},
                "weight_class": {"type": "string", "enum": WEIGHT_CLASS_ENUM,
                                  "description": "Restrict to one weight class."},
                "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_entity",
        "description": (
            "Fetch one stored entity in full by id or exact name. Returns its raw "
            "structured specs, prose, sources, confidence, and related chunk ids."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
    {
        "name": "get_chunk",
        "description": "Fetch one stored long-form evidence/guidance chunk in full by id.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
    {
        "name": "list_entities",
        "description": (
            "Browse stored entities by type, weight class, tag or component category. "
            "Generic reference-only size classes are excluded by default so part lists "
            "prefer exact products; set include_reference=true to include them. "
            "This returns database records/previews, not a recommendation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_type": {"type": "string", "enum": ENTITY_TYPE_ENUM},
                "weight_class": {"type": "string", "enum": WEIGHT_CLASS_ENUM},
                "tag": {"type": "string"},
                "category": {"type": "string",
                             "description": "Component/material category, e.g. 'weapon-motor'."},
                "include_reference": {"type": "boolean", "default": False,
                                      "description": "Include generic size-class/reference records."},
                "limit": {"type": "integer", "default": 50, "maximum": 300},
                "offset": {"type": "integer", "default": 0},
            },
        },
    },
    {
        "name": "compare_entities",
        "description": (
            "Return raw stored records plus a side-by-side union of spec fields for "
            "2-6 entities. The model must interpret the tradeoffs itself."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "ids": {"type": "array", "items": {"type": "string"},
                        "minItems": 2, "maxItems": 6},
            },
            "required": ["ids"],
        },
    },
    {
        "name": "calculate",
        "description": (
            "Run a deterministic combat-robot engineering calculation. Available: "
            "tip_speed(rpm, radius_mm); moment_of_inertia(shape, mass_g, dim_mm, "
            "inner_dim_mm) with shape disc|ring|annulus|bar|bar_end|point|cylinder; "
            "kinetic_energy(moi_kg_m2, rpm); spin_up_time(moi_kg_m2, rpm_target, "
            "motor_kv, volts, stall_current_a, efficiency); drive_speed(motor_rpm, "
            "wheel_dia_mm, gear_ratio); traction_force(weight_g, "
            "friction_coefficient, drive_wheels_fraction); motor_constants(kv, volts, "
            "resistance_ohm); bite_depth(weapon_rpm, tooth_count, closing_speed_m_s); "
            "gyro_torque(moi_kg_m2, weapon_rpm, turn_rate_deg_s); "
            "battery_check(capacity_mah, c_rating, cells_s, average_draw_a); "
            "weight_budget(total_g, allocation)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "enum": sorted(kb.CALCULATORS.keys())},
                "params": {"type": "object",
                           "description": "Arguments for the chosen calculation."},
            },
            "required": ["name", "params"],
        },
    },
    {
        "name": "kb_stats",
        "description": (
            "Raw database coverage metadata: totals, entity counts by type/weight "
            "class, and research topics."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def call_tool(name, args):
    args = args or {}
    database = get_kb()

    if name == "database_schema":
        return database.database_schema()
    if name == "query_database":
        return database.query_database(
            sql=args.get("sql", ""),
            params=args.get("params"),
            max_rows=args.get("max_rows", 50),
        )
    if name == "search_knowledge":
        return database.search(
            query=args.get("query", ""), kind=args.get("kind", "all"),
            entity_type=args.get("entity_type"), weight_class=args.get("weight_class"),
            limit=args.get("limit", 10),
        )
    if name == "get_entity":
        result = database.get_entity(args.get("id", ""))
        return result or {"error": f"No entity with id or name {args.get('id')!r}.",
                          "hint": "Try search_knowledge or query_database first."}
    if name == "get_chunk":
        result = database.get_chunk(args.get("id", ""))
        return result or {"error": f"No chunk with id {args.get('id')!r}."}
    if name == "list_entities":
        return database.list_entities(
            entity_type=args.get("entity_type"), weight_class=args.get("weight_class"),
            tag=args.get("tag"), category=args.get("category"),
            include_reference=bool(args.get("include_reference", False)),
            limit=args.get("limit", 50), offset=args.get("offset", 0),
        )
    if name == "compare_entities":
        return database.compare(args.get("ids", []))
    if name == "calculate":
        calc_name = args.get("name", "")
        func = kb.CALCULATORS.get(calc_name)
        if not func:
            return {"error": f"Unknown calculation {calc_name!r}",
                    "available": sorted(kb.CALCULATORS)}
        try:
            return func(**(args.get("params") or {}))
        except TypeError as exc:
            return {"error": f"Bad arguments for {calc_name}: {exc}"}
    if name == "kb_stats":
        return database.stats()

    return {"error": f"Unknown tool {name!r}"}


def respond(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def handle(request):
    method = request.get("method")
    request_id = request.get("id")

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": request_id, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }}

    if method in ("notifications/initialized", "initialized"):
        return None  # notification, no reply

    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        try:
            result = call_tool(name, params.get("arguments"))
            is_error = isinstance(result, dict) and "error" in result
        except kb.KnowledgeBaseError as exc:
            result, is_error = {"error": str(exc)}, True
        except Exception:  # keep the server alive on an unexpected fault
            result = {"error": "tool raised an exception",
                      "traceback": traceback.format_exc(limit=3)}
            is_error = True
        return {"jsonrpc": "2.0", "id": request_id, "result": {
            "content": [{"type": "text",
                         "text": json.dumps(result, ensure_ascii=False, indent=1)}],
            "isError": is_error,
        }}

    if request_id is None:
        return None  # unknown notification: ignore
    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            respond({"jsonrpc": "2.0", "id": None,
                     "error": {"code": -32700, "message": "Parse error"}})
            continue
        reply = handle(request)
        if reply is not None:
            respond(reply)


if __name__ == "__main__":
    main()
