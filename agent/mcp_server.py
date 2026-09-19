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
SERVER_INFO = {"name": "combat-robot-database", "version": "1.0.0"}

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
        "name": "search_knowledge",
        "description": (
            "Full-text search the combat robot knowledge base. Returns matching "
            "entities (parts, archetypes, materials, formulas, bots, events, rules) "
            "and knowledge chunks (long-form explainers). Start here for almost any "
            "question, then call get_entity or get_chunk for the full text."
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
            "Fetch one entity in full by id (or exact name): all specs, pros, cons, "
            "notes, sources and the knowledge chunks that reference it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
    {
        "name": "get_chunk",
        "description": "Fetch the full markdown body of one knowledge chunk by id.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
    {
        "name": "list_entities",
        "description": (
            "Browse entities by type, weight class, tag or component category "
            "(drive-motor, weapon-motor, esc-weapon, battery, wheel, ...). Use this "
            "to answer 'what options are there for X' questions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_type": {"type": "string", "enum": ENTITY_TYPE_ENUM},
                "weight_class": {"type": "string", "enum": WEIGHT_CLASS_ENUM},
                "tag": {"type": "string"},
                "category": {"type": "string",
                             "description": "Component/material category, e.g. 'weapon-motor'."},
                "limit": {"type": "integer", "default": 50, "maximum": 300},
                "offset": {"type": "integer", "default": 0},
            },
        },
    },
    {
        "name": "compare_entities",
        "description": (
            "Compare 2-6 entities side by side, returning a spec table keyed by the "
            "union of their spec fields. Ideal for 'X vs Y' part questions."
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
        "name": "archetype_matchup",
        "description": (
            "How two archetypes fare against each other: stored matchup records "
            "where researched, plus both archetypes' counters/countered_by and a "
            "heuristic verdict."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "archetype_a": {"type": "string"},
                "archetype_b": {"type": "string"},
            },
            "required": ["archetype_a", "archetype_b"],
        },
    },
    {
        "name": "build_guide",
        "description": (
            "Assemble everything needed to advise on a build for a weight class and "
            "optional archetype: the class rules, the archetype record, candidate "
            "drive motors, weapon motors, ESCs, batteries and wheels, plus relevant "
            "guidance chunks."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "weight_class": {"type": "string", "enum": WEIGHT_CLASS_ENUM,
                                  "default": "antweight"},
                "archetype": {"type": "string",
                              "description": "Archetype id or name, e.g. 'vertical-spinner'."},
            },
        },
    },
    {
        "name": "calculate",
        "description": (
            "Run a combat robotics engineering calculation. Available: "
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
            "What is in the knowledge base: totals, entity counts by type and weight "
            "class, and the research topics it was built from. Use it to tell a user "
            "what you can and cannot answer."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def call_tool(name, args):
    args = args or {}
    database = get_kb()

    if name == "search_knowledge":
        return database.search(
            query=args.get("query", ""), kind=args.get("kind", "all"),
            entity_type=args.get("entity_type"), weight_class=args.get("weight_class"),
            limit=args.get("limit", 10),
        )
    if name == "get_entity":
        result = database.get_entity(args.get("id", ""))
        return result or {"error": f"No entity with id or name {args.get('id')!r}.",
                          "hint": "Try search_knowledge first."}
    if name == "get_chunk":
        result = database.get_chunk(args.get("id", ""))
        return result or {"error": f"No chunk with id {args.get('id')!r}."}
    if name == "list_entities":
        return database.list_entities(
            entity_type=args.get("entity_type"), weight_class=args.get("weight_class"),
            tag=args.get("tag"), category=args.get("category"),
            limit=args.get("limit", 50), offset=args.get("offset", 0),
        )
    if name == "compare_entities":
        return database.compare(args.get("ids", []))
    if name == "archetype_matchup":
        return database.matchup(args.get("archetype_a", ""), args.get("archetype_b", ""))
    if name == "build_guide":
        return database.build_guide(
            weight_class=args.get("weight_class", "antweight"),
            archetype=args.get("archetype"),
        )
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
