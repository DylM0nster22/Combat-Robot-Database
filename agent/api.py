#!/usr/bin/env python3
"""Read-only HTTP API over the combat robot knowledge base.

    python3 agent/api.py [--port 8080] [--host 127.0.0.1]

Standard library only. Useful when whatever you're integrating with speaks HTTP
rather than MCP — a webhook, a bot framework in another language, a spreadsheet,
a custom GPT/tool definition.

    GET /health
    GET /stats
    GET /context?q=what+weapon+motor+for+a+plastic+ant+vert
    GET /search?q=drum+spinner&kind=all&type=component&weight_class=antweight&limit=10
    GET /entities?type=component&category=weapon-motor&weight_class=antweight&limit=50
    GET /entity/<id>
    GET /chunk/<id>
    GET /compare?ids=a,b,c
    GET /matchup?a=vertical-spinner&b=wedge
    GET /build?weight_class=antweight&archetype=vertical-spinner
    GET /calculators
    GET /calculate/<name>?rpm=20000&radius_mm=45

Every response is JSON. Errors return a JSON body with an `error` key.
"""

import argparse
import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import kb  # noqa: E402

DB = None


def _one(params, key, default=None):
    values = params.get(key)
    return values[0] if values else default


def _int(params, key, default):
    try:
        return int(_one(params, key, default))
    except (TypeError, ValueError):
        return default


def _coerce(value):
    """Query strings are all text; calculators want numbers where numbers fit."""
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def route(path, params):
    """Return (status, payload). Raises nothing the handler can't cope with."""
    if path == "/health":
        return 200, {"ok": True, "entities": int(DB.stats()["meta"].get("entity_count", 0))}

    if path == "/stats":
        return 200, DB.stats()

    if path == "/context":
        query = _one(params, "q") or _one(params, "query") or ""
        if not query:
            return 400, {"error": "missing ?q="}
        return 200, DB.answer_context(
            query,
            weight_class=_one(params, "weight_class"),
            entity_limit=_int(params, "entity_limit", 6),
            chunk_limit=_int(params, "chunk_limit", 5))

    if path == "/search":
        query = _one(params, "q") or _one(params, "query") or ""
        if not query:
            return 400, {"error": "missing ?q="}
        return 200, DB.search(
            query, kind=_one(params, "kind", "all"),
            entity_type=_one(params, "type"),
            weight_class=_one(params, "weight_class"),
            limit=_int(params, "limit", 10))

    if path == "/entities":
        return 200, DB.list_entities(
            entity_type=_one(params, "type"),
            weight_class=_one(params, "weight_class"),
            tag=_one(params, "tag"), category=_one(params, "category"),
            limit=_int(params, "limit", 50), offset=_int(params, "offset", 0))

    if path.startswith("/entity/"):
        entity = DB.get_entity(unquote(path[len("/entity/"):]))
        return (200, entity) if entity else (404, {"error": "no such entity"})

    if path.startswith("/chunk/"):
        chunk = DB.get_chunk(unquote(path[len("/chunk/"):]))
        return (200, chunk) if chunk else (404, {"error": "no such chunk"})

    if path == "/compare":
        ids = [i for i in (_one(params, "ids", "")).split(",") if i]
        if len(ids) < 2:
            return 400, {"error": "pass ?ids=a,b (two or more)"}
        return 200, DB.compare(ids)

    if path == "/matchup":
        a, b = _one(params, "a"), _one(params, "b")
        if not a or not b:
            return 400, {"error": "pass ?a=<archetype>&b=<archetype>"}
        return 200, DB.matchup(a, b)

    if path == "/build":
        return 200, DB.build_guide(
            weight_class=_one(params, "weight_class", "antweight"),
            archetype=_one(params, "archetype"))

    if path == "/calculators":
        return 200, {"calculators": sorted(kb.CALCULATORS)}

    if path.startswith("/calculate/"):
        name = path[len("/calculate/"):]
        func = kb.CALCULATORS.get(name)
        if not func:
            return 404, {"error": f"unknown calculation {name!r}",
                         "available": sorted(kb.CALCULATORS)}
        args = {k: _coerce(v[0]) for k, v in params.items()}
        try:
            return 200, func(**args)
        except TypeError as exc:
            return 400, {"error": f"bad arguments: {exc}"}

    return 404, {"error": "no such endpoint", "see": "/health for a list in the docstring"}


class Handler(BaseHTTPRequestHandler):
    server_version = "CombatRobotDB/1.1"

    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            status, payload = route(parsed.path.rstrip("/") or "/health",
                                    parse_qs(parsed.query))
        except kb.KnowledgeBaseError as exc:
            status, payload = 503, {"error": str(exc)}
        except Exception:
            status, payload = 500, {"error": "internal error",
                                    "traceback": traceback.format_exc(limit=3)}

        body = json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # Read-only public data; allow browser clients to call it directly.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{self.address_string()} {fmt % args}\n")


def main():
    global DB
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--db", default=os.environ.get("COMBAT_ROBOT_DB", kb.DEFAULT_DB))
    args = parser.parse_args()

    DB = kb.KnowledgeBase(args.db)
    stats = DB.stats()["meta"]
    print(f"Combat Robot Database API — {stats.get('entity_count')} entities, "
          f"{stats.get('chunk_count')} guides")
    print(f"listening on http://{args.host}:{args.port}  (try /health, /stats, /search?q=drum)")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
