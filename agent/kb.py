"""Query layer over the combat robot knowledge base.

This is the single implementation of "what can you ask the database".
The MCP server, the REST API and the Discord bot all call into here, so a
capability added in this file shows up in all three.

Everything returns plain dicts/lists so callers can hand results straight to
an LLM as JSON without another serialization step.
"""

import json
import math
import os
import re
import sqlite3
from typing import Any, Dict, Iterable, List, Optional

DEFAULT_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "combat_robots.db",
)

# FTS5 treats these as operators; a user typing "2205 motor (best?)" would
# otherwise produce a syntax error rather than results.
_FTS_TOKEN = re.compile(r"[A-Za-z0-9_]+")

# Natural-language Discord questions contain a lot of words that are useful to
# a person but actively hurt an OR-based full-text search.  Drop conversational
# filler while keeping combat-robot terms and part names intact.
_SEARCH_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "best", "better", "can", "could",
    "did", "do", "does", "for", "from", "good", "how", "i", "in", "is", "it",
    "me", "my", "of", "on", "or", "please", "should", "show", "tell", "the",
    "this", "to", "use", "using", "want", "what", "when", "where", "which",
    "with", "would", "you", "your",
}

# Builders use shorthand constantly. Expanding only a small, domain-specific
# set gives FTS a chance to match the wording used by the research files.
_QUERY_SYNONYMS = {
    "vert": ("vertical", "spinner"),
    "vertical": ("spinner",),
    "horizontal": ("spinner",),
    "ant": ("antweight",),
    "1lb": ("antweight",),
    "lipo": ("battery",),
    "esc": ("controller",),
    "rx": ("receiver",),
    "tx": ("transmitter",),
    "n20": ("gearmotor",),
}

WEIGHT_CLASSES = [
    "fairyweight", "antweight", "plastic-antweight", "beetleweight",
    "plastic-beetleweight", "hobbyweight", "featherweight", "lightweight",
    "middleweight", "heavyweight",
]


class KnowledgeBaseError(RuntimeError):
    pass


def _search_tokens(text: str) -> List[str]:
    """Extract useful search terms from a natural-language question.

    Stopwords are removed only when useful terms remain, so a literal search
    like "and" still behaves predictably. Common builder shorthand is expanded
    after de-duplication. The cap keeps generated MATCH expressions small.
    """
    raw = [token.lower() for token in _FTS_TOKEN.findall(text or "")]
    useful = [t for t in raw if len(t) >= 2 and t not in _SEARCH_STOPWORDS]
    base = useful or [t for t in raw if len(t) >= 2]

    expanded: List[str] = []
    for token in base:
        if token not in expanded:
            expanded.append(token)
        for synonym in _QUERY_SYNONYMS.get(token, ()):
            if synonym not in expanded:
                expanded.append(synonym)
    return expanded[:12]


def _fts_query(text: str, prefix: bool = True, operator: str = "OR") -> str:
    """Turn arbitrary user text into a safe FTS5 MATCH expression.

    Important terms are quoted, optionally prefix-matched, and can be joined
    with AND for a precision pass or OR for a recall pass.
    """
    tokens = _search_tokens(text)
    if not tokens:
        raw = _FTS_TOKEN.findall(text or "")
        return f'"{raw[0]}"' if raw else ""

    parts = [f'"{token}"*' if prefix else f'"{token}"' for token in tokens]
    joiner = " AND " if str(operator).upper() == "AND" else " OR "
    return joiner.join(parts)


def _loads(value: Optional[str], fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return fallback


def _entity_row(row: sqlite3.Row, include_body: bool = True) -> Dict[str, Any]:
    entity = {
        "id": row["id"],
        "type": row["type"],
        "name": row["name"],
        "aliases": _loads(row["aliases"], []),
        "summary": row["summary"],
        "weight_classes": _loads(row["weight_classes"], []),
        "tags": _loads(row["tags"], []),
        "specs": _loads(row["specs"], {}),
        "confidence": row["confidence"],
        "topic_id": row["topic_id"],
    }
    if include_body:
        entity.update({
            "pros": _loads(row["pros"], []),
            "cons": _loads(row["cons"], []),
            "notes": row["notes"],
            "sources": _loads(row["sources"], []),
        })
        # Type-specific fields (builder, counters, expression, ...) live in
        # `extra`; flatten them so callers don't need to know that.
        extra = _loads(row["extra"], {})
        if isinstance(extra, dict):
            for key, value in extra.items():
                entity.setdefault(key, value)
    return entity


def _chunk_row(row: sqlite3.Row, include_body: bool = True) -> Dict[str, Any]:
    chunk = {
        "id": row["id"],
        "title": row["title"],
        "section": row["section"],
        "topic_id": row["topic_id"],
        "tags": _loads(row["tags"], []),
        "weight_classes": _loads(row["weight_classes"], []),
        "word_count": row["word_count"],
    }
    if include_body:
        chunk["body_md"] = row["body_md"]
        chunk["entity_refs"] = _loads(row["entity_refs"], [])
        chunk["sources"] = _loads(row["sources"], [])
    else:
        chunk["preview"] = (row["body_md"] or "")[:300]
    return chunk


class KnowledgeBase:
    """Read-only access to the built knowledge base."""

    def __init__(self, db_path: str = DEFAULT_DB):
        self.db_path = db_path
        if not os.path.exists(db_path):
            raise KnowledgeBaseError(
                f"No knowledge base at {db_path}. Run: python3 scripts/build_db.py"
            )
        # Opened read-only so an agent process can never corrupt the data.
        self.conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True,
                                    check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        self.conn.close()

    # ---------------------------------------------------------------- search

    def search(self, query: str, kind: str = "all", entity_type: Optional[str] = None,
               weight_class: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        """Full-text search across entities and knowledge chunks.

        Natural-language questions get two passes: an AND query first for
        precision, then an OR query to fill the remaining slots. This avoids
        generic Discord wording drowning out the useful engineering terms.
        """
        limit = max(1, min(int(limit or 10), 50))
        precision_match = _fts_query(query, operator="AND")
        recall_match = _fts_query(query, operator="OR")
        if not recall_match:
            return {"query": query, "entities": [], "chunks": [],
                    "search_terms": [], "note": "Empty or unsearchable query."}

        matches = []
        for match in (precision_match, recall_match):
            if match and match not in matches:
                matches.append(match)

        results: Dict[str, Any] = {
            "query": query,
            "search_terms": _search_tokens(query),
            "entities": [],
            "chunks": [],
        }

        def _collect_entities() -> List[sqlite3.Row]:
            collected: List[sqlite3.Row] = []
            seen = set()
            for match in matches:
                sql = """
                    SELECT e.*, bm25(entities_fts, 10.0, 6.0, 4.0, 2.0, 3.0, 2.0, 1.0) AS rank
                    FROM entities_fts
                    JOIN entities e ON e.id = entities_fts.id
                    WHERE entities_fts MATCH ?
                """
                params: List[Any] = [match]
                if entity_type:
                    sql += " AND e.type = ?"
                    params.append(entity_type)
                if weight_class:
                    sql += (" AND EXISTS (SELECT 1 FROM entity_weight_classes w"
                            " WHERE w.entity_id = e.id AND w.weight_class = ?)")
                    params.append(weight_class)
                sql += " ORDER BY rank LIMIT ?"
                params.append(min(50, max(limit * 3, limit)))
                try:
                    rows = self.conn.execute(sql, params).fetchall()
                except sqlite3.OperationalError as exc:
                    raise KnowledgeBaseError(f"search failed: {exc}") from exc
                for row in rows:
                    if row["id"] not in seen:
                        seen.add(row["id"])
                        collected.append(row)
                        if len(collected) >= limit:
                            return collected
            return collected

        def _collect_chunks() -> List[sqlite3.Row]:
            collected: List[sqlite3.Row] = []
            seen = set()
            for match in matches:
                sql = """
                    SELECT c.*, bm25(chunks_fts, 8.0, 3.0, 1.0, 2.0) AS rank
                    FROM chunks_fts
                    JOIN chunks c ON c.id = chunks_fts.id
                    WHERE chunks_fts MATCH ?
                """
                params: List[Any] = [match]
                if weight_class:
                    sql += " AND c.weight_classes LIKE ?"
                    params.append(f'%"{weight_class}"%')
                sql += " ORDER BY rank LIMIT ?"
                params.append(min(50, max(limit * 3, limit)))
                try:
                    rows = self.conn.execute(sql, params).fetchall()
                except sqlite3.OperationalError as exc:
                    raise KnowledgeBaseError(f"search failed: {exc}") from exc
                for row in rows:
                    if row["id"] not in seen:
                        seen.add(row["id"])
                        collected.append(row)
                        if len(collected) >= limit:
                            return collected
            return collected

        if kind in ("all", "entities"):
            results["entities"] = [
                _entity_row(r, include_body=False) for r in _collect_entities()
            ]

        if kind in ("all", "chunks"):
            results["chunks"] = [
                _chunk_row(r, include_body=False) for r in _collect_chunks()
            ]

        results["total"] = len(results["entities"]) + len(results["chunks"])
        return results

    def _infer_weight_class(self, query: str) -> Optional[str]:
        """Infer only obvious class mentions; never guess from vague wording."""
        q = re.sub(r"\s+", " ", str(query or "").lower())
        if re.search(r"\bplastic[- ]?ant(weight)?s?\b", q):
            return "plastic-antweight"
        if re.search(r"\b(1\s*lb|1lb|one[- ]pound|ant[- ]?weight)s?\b", q):
            return "antweight"
        if re.search(r"\b(150\s*g|fairy[- ]?weight)s?\b", q):
            return "fairyweight"
        if re.search(r"\b(3\s*lb|3lb|beetle[- ]?weight)s?\b", q):
            return "beetleweight"
        if re.search(r"\b(12\s*lb|12lb|hobby[- ]?weight)s?\b", q):
            return "hobbyweight"
        if re.search(r"\b(30\s*lb|30lb|feather[- ]?weight)s?\b", q):
            return "featherweight"
        return None

    def answer_context(self, query: str, weight_class: Optional[str] = None,
                       entity_limit: int = 6, chunk_limit: int = 5,
                       max_chunk_chars: int = 2600) -> Dict[str, Any]:
        """Return a compact, answer-ready context pack for an LLM.

        This is deliberately higher level than raw search: it infers an obvious
        weight class, searches once, expands the strongest entity hits, follows
        their guide links, and includes full (bounded) guide text. A Discord bot
        can usually answer directly from one call instead of spending several
        tool turns searching and fetching records one by one.
        """
        entity_limit = max(1, min(int(entity_limit or 6), 12))
        chunk_limit = max(1, min(int(chunk_limit or 5), 10))
        max_chunk_chars = max(600, min(int(max_chunk_chars or 2600), 6000))
        inferred = weight_class or self._infer_weight_class(query)

        found = self.search(query, weight_class=inferred, limit=max(entity_limit, chunk_limit, 10))
        used_filter = inferred
        # Some useful generic parts/guides are intentionally class-agnostic.
        # If a class filter leaves too little context, retry without it.
        if inferred and found.get("total", 0) < 3:
            found = self.search(query, limit=max(entity_limit, chunk_limit, 10))
            used_filter = None

        entities = []
        related_chunk_ids: List[str] = []
        for hit in found.get("entities", [])[:entity_limit]:
            full = self.get_entity(hit["id"])
            if not full:
                continue
            related = full.get("related_chunks", [])[:6]
            related_chunk_ids.extend(r["id"] for r in related)
            entities.append(full)

        chunk_ids: List[str] = []
        for hit in found.get("chunks", []):
            if hit["id"] not in chunk_ids:
                chunk_ids.append(hit["id"])
        for chunk_id in related_chunk_ids:
            if chunk_id not in chunk_ids:
                chunk_ids.append(chunk_id)

        chunks = []
        for chunk_id in chunk_ids[:chunk_limit]:
            full = self.get_chunk(chunk_id)
            if not full:
                continue
            body = full.get("body_md") or ""
            if len(body) > max_chunk_chars:
                full = dict(full)
                full["body_md"] = body[:max_chunk_chars].rstrip() + "\n\n[excerpt truncated]"
            chunks.append(full)

        return {
            "query": query,
            "search_terms": found.get("search_terms", _search_tokens(query)),
            "inferred_weight_class": inferred,
            "weight_class_filter_used": used_filter,
            "entities": entities,
            "chunks": chunks,
            "coverage": {
                "entity_count": len(entities),
                "chunk_count": len(chunks),
                "raw_matches": found.get("total", 0),
            },
            "hint": (
                "Answer from this context when sufficient. Use a specialist tool "
                "(compare_entities, build_guide, archetype_matchup, calculate) only "
                "when the question actually needs it."
            ),
        }

    # ------------------------------------------------------------- retrieval

    # Entities are stored with a type prefix (`archetype-wedge`), but callers —
    # LLMs, cross-references in research text, people typing in a URL — routinely
    # use the bare slug or the display name. Try each in turn.
    _ID_PREFIXES = ("archetype-", "component-", "material-", "formula-", "term-",
                    "bot-", "event-", "supplier-", "ruleset-", "kit-", "weight-class-")

    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        if not entity_id:
            return None
        needle = str(entity_id).strip()

        row = self.conn.execute(
            "SELECT * FROM entities WHERE id = ?", (needle,)
        ).fetchone()
        if not row:
            row = self.conn.execute(
                "SELECT * FROM entities WHERE lower(name) = lower(?)", (needle,)
            ).fetchone()
        if not row:
            slug = re.sub(r"[^a-z0-9]+", "-", needle.lower()).strip("-")
            candidates = [slug] + [prefix + slug for prefix in self._ID_PREFIXES]
            placeholders = ",".join("?" * len(candidates))
            row = self.conn.execute(
                f"SELECT * FROM entities WHERE id IN ({placeholders})", candidates
            ).fetchone()
        if not row:
            # Last resort: an alias match, so "vert" finds the vertical spinner.
            row = self.conn.execute(
                "SELECT * FROM entities WHERE lower(aliases) LIKE ?",
                (f'%"{needle.lower()}"%',)
            ).fetchone()
        if not row:
            return None
        entity = _entity_row(row)
        entity["related_chunks"] = [
            {"id": r["id"], "title": r["title"], "section": r["section"]}
            for r in self.conn.execute(
                """SELECT c.id, c.title, c.section FROM chunk_entity_refs r
                   JOIN chunks c ON c.id = r.chunk_id
                   WHERE r.entity_id = ? LIMIT 20""",
                (entity["id"],),
            ).fetchall()
        ]
        return entity

    def get_chunk(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM chunks WHERE id = ?", (chunk_id,)
        ).fetchone()
        return _chunk_row(row) if row else None

    def list_entities(self, entity_type: Optional[str] = None,
                      weight_class: Optional[str] = None,
                      tag: Optional[str] = None,
                      category: Optional[str] = None,
                      limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        limit = max(1, min(int(limit or 50), 300))
        sql = "SELECT e.* FROM entities e WHERE 1=1"
        params: List[Any] = []
        if entity_type:
            sql += " AND e.type = ?"
            params.append(entity_type)
        if weight_class:
            sql += (" AND EXISTS (SELECT 1 FROM entity_weight_classes w"
                    " WHERE w.entity_id = e.id AND w.weight_class = ?)")
            params.append(weight_class)
        if tag:
            sql += (" AND EXISTS (SELECT 1 FROM entity_tags t"
                    " WHERE t.entity_id = e.id AND t.tag = ?)")
            params.append(tag.lower())
        if category:
            # `category` lives in the extra blob for components and materials.
            sql += " AND e.extra LIKE ?"
            params.append(f'%"category": "{category}"%')
        sql += " ORDER BY e.name LIMIT ? OFFSET ?"
        params.extend([limit, max(0, int(offset or 0))])
        rows = self.conn.execute(sql, params).fetchall()

        count_sql = sql.split(" ORDER BY ")[0].replace("SELECT e.*", "SELECT COUNT(*)", 1)
        total = self.conn.execute(count_sql, params[:-2]).fetchone()[0]
        return {
            "total": total,
            "returned": len(rows),
            "offset": offset,
            "entities": [_entity_row(r, include_body=False) for r in rows],
        }

    def compare(self, entity_ids: Iterable[str]) -> Dict[str, Any]:
        """Side-by-side comparison, with the union of spec keys as the row set."""
        entities = []
        missing = []
        for entity_id in entity_ids:
            entity = self.get_entity(entity_id)
            if entity:
                entities.append(entity)
            else:
                missing.append(entity_id)
        spec_keys: List[str] = []
        for entity in entities:
            for key in entity.get("specs", {}):
                if key not in spec_keys:
                    spec_keys.append(key)
        table = {
            key: {e["id"]: e.get("specs", {}).get(key) for e in entities}
            for key in sorted(spec_keys)
        }
        return {
            "entities": [
                {k: v for k, v in e.items() if k != "related_chunks"} for e in entities
            ],
            "spec_table": table,
            "missing": missing,
        }

    # ---------------------------------------------------------------- facets

    def stats(self) -> Dict[str, Any]:
        meta = {r["key"]: r["value"] for r in
                self.conn.execute("SELECT key, value FROM meta").fetchall()}
        by_type = {r["type"]: r["n"] for r in self.conn.execute(
            "SELECT type, COUNT(*) n FROM entities GROUP BY type ORDER BY n DESC"
        ).fetchall()}
        by_class = {r["weight_class"]: r["n"] for r in self.conn.execute(
            "SELECT weight_class, COUNT(*) n FROM entity_weight_classes"
            " GROUP BY weight_class ORDER BY n DESC"
        ).fetchall()}
        topics = [dict(r) for r in self.conn.execute(
            "SELECT * FROM topics ORDER BY topic_id"
        ).fetchall()]
        return {"meta": meta, "entities_by_type": by_type,
                "entities_by_weight_class": by_class, "topics": topics}

    def list_tags(self, limit: int = 100) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT tag, COUNT(*) n FROM entity_tags GROUP BY tag"
            " ORDER BY n DESC, tag LIMIT ?", (limit,)
        ).fetchall()
        return [{"tag": r["tag"], "count": r["n"]} for r in rows]

    def list_types(self) -> List[str]:
        return [r["type"] for r in self.conn.execute(
            "SELECT DISTINCT type FROM entities ORDER BY type"
        ).fetchall()]

    # -------------------------------------------------------------- matchups

    def _matchup_slugs(self, value: str) -> List[str]:
        """Candidate short slugs for an archetype, for matching matchup tags.

        Matchup records are tagged with short keys ("vertical-spinner") while
        archetype entities carry prefixed ids ("archetype-vertical-disc-spinner"),
        so a query has to be reduced to every form it might be tagged under.
        """
        candidates = set()
        raw = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
        if raw:
            candidates.add(raw)
            for prefix in self._ID_PREFIXES:
                if raw.startswith(prefix):
                    candidates.add(raw[len(prefix):])
        entity = self.get_entity(value)
        if entity:
            ent_id = entity["id"]
            candidates.add(ent_id)
            for prefix in self._ID_PREFIXES:
                if ent_id.startswith(prefix):
                    candidates.add(ent_id[len(prefix):])
            candidates.add(re.sub(r"[^a-z0-9]+", "-", entity["name"].lower()).strip("-"))
            for alias in entity.get("aliases", []):
                candidates.add(re.sub(r"[^a-z0-9]+", "-", str(alias).lower()).strip("-"))
        return [c for c in candidates if c]

    def matchup(self, archetype_a: str, archetype_b: str) -> Dict[str, Any]:
        """What the database knows about one archetype fighting another.

        Only returns matchup records that genuinely concern BOTH archetypes —
        a loose full-text match would otherwise surface an unrelated pairing
        and present it as the answer.
        """
        a = self.get_entity(archetype_a) or {}
        b = self.get_entity(archetype_b) or {}
        slugs_a = self._matchup_slugs(archetype_a)
        slugs_b = self._matchup_slugs(archetype_b)

        records = []
        seen = set()

        # An exact record for this pairing, in either order, is authoritative.
        exact_ids = [f"matchup-{x}-vs-{y}" for x in slugs_a for y in slugs_b]
        exact_ids += [f"matchup-{y}-vs-{x}" for x in slugs_a for y in slugs_b]
        if exact_ids:
            placeholders = ",".join("?" * len(exact_ids))
            for row in self.conn.execute(
                f"SELECT * FROM entities WHERE id IN ({placeholders})", exact_ids
            ).fetchall():
                if row["id"] not in seen:
                    seen.add(row["id"])
                    records.append(_entity_row(row))

        # Otherwise accept any matchup record tagged with both archetypes.
        if not records:
            rows = self.conn.execute(
                "SELECT * FROM entities WHERE type = 'term'"
                " AND (id LIKE 'matchup-%' OR tags LIKE '%matchup%')"
            ).fetchall()
            for row in rows:
                tags = set(_loads(row["tags"], []))
                blob = f"{row['id']} {row['name']}".lower()
                hit_a = any(s in tags or s in blob for s in slugs_a)
                hit_b = any(s in tags or s in blob for s in slugs_b)
                if hit_a and hit_b and row["id"] not in seen:
                    seen.add(row["id"])
                    records.append(_entity_row(row))

        def _pretty(entity, fallback):
            if entity.get("name"):
                return entity["name"]
            return str(fallback).replace("-", " ").replace("_", " ").strip().capitalize()

        def _verdict():
            a_name = _pretty(a, archetype_a)
            b_name = _pretty(b, archetype_b)
            # A stored record's own judgement beats any inference.
            for record in records:
                favoured = str(record.get("specs", {}).get("favoured", "")).lower()
                if not favoured:
                    continue
                pct = record.get("specs", {}).get("confidence_pct")
                qualifier = f" (~{pct}% confidence)" if pct else ""
                if any(s == favoured for s in slugs_a):
                    return f"{a_name} is favoured{qualifier}"
                if any(s == favoured for s in slugs_b):
                    return f"{b_name} is favoured{qualifier}"
            # Fall back to the archetypes' own counters lists.
            a_beats = {str(x).lower() for x in (a.get("counters") or [])}
            b_beats = {str(x).lower() for x in (b.get("counters") or [])}
            if any(s in a_beats for s in slugs_b):
                return f"{a_name} is favoured (inferred from its counters list)"
            if any(s in b_beats for s in slugs_a):
                return f"{b_name} is favoured (inferred from its counters list)"
            return ("No stored verdict for this pairing; see both archetype "
                    "records for the tradeoffs.")

        return {
            "a": {k: v for k, v in a.items() if k != "related_chunks"},
            "b": {k: v for k, v in b.items() if k != "related_chunks"},
            "matchup_records": records[:4],
            "heuristic_verdict": _verdict(),
        }

    # ------------------------------------------------------------ build help

    def build_guide(self, weight_class: str = "antweight",
                    archetype: Optional[str] = None) -> Dict[str, Any]:
        """Assemble the material an LLM needs to advise on a build."""
        out: Dict[str, Any] = {"weight_class": weight_class, "archetype": archetype}

        if archetype:
            out["archetype_record"] = self.get_entity(archetype)

        out["weight_class_record"] = self.get_entity(weight_class)

        for label, category in (("drive_motors", "drive-motor"),
                                ("weapon_motors", "weapon-motor"),
                                ("batteries", "battery"),
                                ("escs", "esc-weapon"),
                                ("wheels", "wheel")):
            out[label] = self.list_entities(
                entity_type="component", category=category,
                weight_class=weight_class, limit=12,
            )["entities"]
            if not out[label]:
                # Fall back to class-agnostic parts rather than returning nothing.
                out[label] = self.list_entities(
                    entity_type="component", category=category, limit=12
                )["entities"]

        terms = " ".join(filter(None, [weight_class, archetype, "build guide weight budget"]))
        out["guidance"] = self.search(terms, kind="chunks", limit=8)["chunks"]
        return out


# ---------------------------------------------------------------- calculators
#
# These are pure functions so they can be unit-tested and called by an LLM
# without touching the database. Every one returns its inputs alongside the
# result so an agent can show its working.

def _ok(**kwargs) -> Dict[str, Any]:
    return kwargs


def tip_speed(rpm: float, radius_mm: float) -> Dict[str, Any]:
    """Weapon tip speed — the headline number for any spinner."""
    omega = float(rpm) * 2 * math.pi / 60.0
    radius_m = float(radius_mm) / 1000.0
    v = omega * radius_m
    return _ok(rpm=rpm, radius_mm=radius_mm, omega_rad_s=round(omega, 2),
               tip_speed_m_s=round(v, 2), tip_speed_ft_s=round(v * 3.28084, 1),
               tip_speed_mph=round(v * 2.23694, 1))


def moment_of_inertia(shape: str, mass_g: float, dim_mm: float,
                      inner_dim_mm: float = 0.0) -> Dict[str, Any]:
    """MOI for the weapon shapes that actually show up in antweight.

    shape: disc | ring | annulus | bar | bar_end | point | cylinder
    dim_mm is the outer diameter for round shapes, or the length for a bar.
    """
    mass = float(mass_g) / 1000.0
    d = float(dim_mm) / 1000.0
    r = d / 2.0
    ri = float(inner_dim_mm) / 2000.0
    shape = (shape or "").lower().strip()

    if shape == "disc":
        inertia, formula = 0.5 * mass * r ** 2, "I = 1/2 m r^2"
    elif shape in ("ring", "cylinder", "thin_ring"):
        inertia, formula = mass * r ** 2, "I = m r^2"
    elif shape == "annulus":
        inertia, formula = 0.5 * mass * (r ** 2 + ri ** 2), "I = 1/2 m (ro^2 + ri^2)"
    elif shape == "bar":
        inertia, formula = mass * d ** 2 / 12.0, "I = 1/12 m L^2 (about centre)"
    elif shape == "bar_end":
        inertia, formula = mass * d ** 2 / 3.0, "I = 1/3 m L^2 (about one end)"
    elif shape == "point":
        inertia, formula = mass * r ** 2, "I = m r^2 (point mass at radius)"
    else:
        return {"error": f"unknown shape {shape!r}",
                "valid": ["disc", "ring", "annulus", "bar", "bar_end", "point", "cylinder"]}

    return _ok(shape=shape, formula=formula, mass_g=mass_g, dim_mm=dim_mm,
               inner_dim_mm=inner_dim_mm or None,
               moi_kg_m2=round(inertia, 8),
               moi_g_cm2=round(inertia * 1e7, 1))


def kinetic_energy(moi_kg_m2: float, rpm: float) -> Dict[str, Any]:
    """Stored rotational energy — what a spinner can in principle deliver."""
    omega = float(rpm) * 2 * math.pi / 60.0
    joules = 0.5 * float(moi_kg_m2) * omega ** 2
    return _ok(moi_kg_m2=moi_kg_m2, rpm=rpm, omega_rad_s=round(omega, 2),
               energy_j=round(joules, 2), energy_ft_lb=round(joules * 0.737562, 2))


def spin_up_time(moi_kg_m2: float, rpm_target: float, motor_kv: float,
                 volts: float, stall_current_a: float,
                 efficiency: float = 0.6) -> Dict[str, Any]:
    """Rough spin-up time from motor constants and weapon inertia.

    Treats average accelerating torque as a fraction of stall torque; real
    spin-up is slower than the ideal because torque falls off as the weapon
    approaches no-load speed. Use it to compare designs, not to certify one.
    """
    kv, volts = float(motor_kv), float(volts)
    if kv <= 0:
        return {"error": "motor_kv must be > 0"}
    kt = 9.5493 / kv                    # N*m per amp, = 60 / (2*pi*Kv)
    stall_torque = kt * float(stall_current_a)
    avg_torque = stall_torque * float(efficiency)
    omega = float(rpm_target) * 2 * math.pi / 60.0
    if avg_torque <= 0:
        return {"error": "computed zero torque; check stall_current_a"}
    seconds = float(moi_kg_m2) * omega / avg_torque
    no_load_rpm = kv * volts
    return _ok(moi_kg_m2=moi_kg_m2, rpm_target=rpm_target, motor_kv=motor_kv,
               volts=volts, stall_current_a=stall_current_a,
               kt_nm_per_a=round(kt, 6),
               stall_torque_nm=round(stall_torque, 4),
               assumed_avg_torque_nm=round(avg_torque, 4),
               no_load_rpm=round(no_load_rpm),
               spin_up_s=round(seconds, 2),
               caveat=("Assumes constant average torque at "
                       f"{efficiency:.0%} of stall. Real spin-up is longer, "
                       "especially if rpm_target is near no-load rpm."))


def drive_speed(motor_rpm: float, wheel_dia_mm: float,
                gear_ratio: float = 1.0) -> Dict[str, Any]:
    """Top speed from motor rpm, gearing and wheel size."""
    ratio = float(gear_ratio) if gear_ratio else 1.0
    wheel_rpm = float(motor_rpm) / ratio
    circumference_m = math.pi * float(wheel_dia_mm) / 1000.0
    v = wheel_rpm * circumference_m / 60.0
    return _ok(motor_rpm=motor_rpm, gear_ratio=ratio, wheel_dia_mm=wheel_dia_mm,
               wheel_rpm=round(wheel_rpm, 1), speed_m_s=round(v, 2),
               speed_mph=round(v * 2.23694, 1), speed_ft_s=round(v * 3.28084, 1))


def traction_force(weight_g: float, friction_coefficient: float = 1.0,
                   drive_wheels_fraction: float = 1.0) -> Dict[str, Any]:
    """Maximum pushing force before the wheels slip.

    Torque beyond this point does nothing, which is why a 1 lb bot with huge
    gear reduction still gets shoved around if its tyres are hard.
    """
    mass_kg = float(weight_g) / 1000.0
    normal_n = mass_kg * 9.80665 * float(drive_wheels_fraction)
    force = normal_n * float(friction_coefficient)
    return _ok(weight_g=weight_g, friction_coefficient=friction_coefficient,
               drive_wheels_fraction=drive_wheels_fraction,
               normal_force_n=round(normal_n, 2),
               max_push_force_n=round(force, 2),
               max_push_force_lbf=round(force * 0.224809, 2))


def motor_constants(kv: float, volts: float,
                    resistance_ohm: Optional[float] = None) -> Dict[str, Any]:
    """Kt, no-load rpm and (if resistance is known) stall current and torque."""
    kv = float(kv)
    if kv <= 0:
        return {"error": "kv must be > 0"}
    kt_nm_per_a = 9.5493 / kv
    out = _ok(kv=kv, volts=volts,
              kt_nm_per_a=round(kt_nm_per_a, 6),
              kt_oz_in_per_a=round(kt_nm_per_a * 141.612, 3),
              no_load_rpm=round(kv * float(volts)))
    if resistance_ohm:
        stall_a = float(volts) / float(resistance_ohm)
        stall_torque = kt_nm_per_a * stall_a
        out.update(resistance_ohm=resistance_ohm,
                   stall_current_a=round(stall_a, 1),
                   stall_torque_nm=round(stall_torque, 4),
                   peak_power_w=round(float(volts) * stall_a / 4.0, 1),
                   note="Peak mechanical power occurs near half stall current.")
    return out


def bite_depth(weapon_rpm: float, tooth_count: int,
               closing_speed_m_s: float = 1.0) -> Dict[str, Any]:
    """How deep each tooth can cut given how fast the bots close.

    Bite is why a 3-tooth weapon often does less damage than a 1-tooth weapon
    at the same energy: more teeth means less travel between impacts.
    """
    teeth = max(1, int(tooth_count))
    rpm = float(weapon_rpm)
    if rpm <= 0:
        return {"error": "weapon_rpm must be > 0"}
    hits_per_second = rpm / 60.0 * teeth
    depth_m = float(closing_speed_m_s) / hits_per_second
    return _ok(weapon_rpm=rpm, tooth_count=teeth,
               closing_speed_m_s=closing_speed_m_s,
               hits_per_second=round(hits_per_second, 1),
               bite_depth_mm=round(depth_m * 1000.0, 2),
               note=("Bite is the theoretical maximum depth per tooth. Armor "
                     "hardness, wedge angle and ground clearance all reduce it."))


def gyro_torque(moi_kg_m2: float, weapon_rpm: float,
                turn_rate_deg_s: float = 180.0) -> Dict[str, Any]:
    """Precession torque a spinning weapon fights you with when you turn."""
    omega_w = float(weapon_rpm) * 2 * math.pi / 60.0
    omega_t = float(turn_rate_deg_s) * math.pi / 180.0
    torque = float(moi_kg_m2) * omega_w * omega_t
    return _ok(moi_kg_m2=moi_kg_m2, weapon_rpm=weapon_rpm,
               turn_rate_deg_s=turn_rate_deg_s,
               precession_torque_nm=round(torque, 4),
               note=("This torque acts about the axis perpendicular to both "
                     "spin and turn — it is what lifts a wheel and causes "
                     "gyro dance in a vertical spinner."))


def battery_check(capacity_mah: float, c_rating: float, cells_s: int,
                  average_draw_a: float = 10.0) -> Dict[str, Any]:
    """Does this pack actually deliver what the bot asks of it?"""
    capacity_ah = float(capacity_mah) / 1000.0
    continuous_a = capacity_ah * float(c_rating)
    nominal_v = int(cells_s) * 3.7
    energy_wh = capacity_ah * nominal_v
    draw = float(average_draw_a)
    runtime_min = (capacity_ah / draw * 60.0) if draw > 0 else float("inf")
    return _ok(capacity_mah=capacity_mah, c_rating=c_rating, cells_s=cells_s,
               nominal_voltage_v=round(nominal_v, 1),
               energy_wh=round(energy_wh, 2),
               rated_continuous_a=round(continuous_a, 1),
               average_draw_a=draw,
               headroom_ratio=round(continuous_a / draw, 2) if draw > 0 else None,
               estimated_runtime_min=round(runtime_min, 1),
               verdict=("adequate" if continuous_a >= draw * 1.5 else
                        "marginal — expect voltage sag"),
               note=("Marketing C ratings are optimistic; treat anything under "
                     "a 1.5x headroom ratio as sag-prone in a 1 lb bot."))


def weight_budget(total_g: float = 454.0,
                  allocation: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Turn a percentage split into grams against a class weight limit."""
    allocation = allocation or {
        "weapon": 32, "drive": 20, "armor_chassis": 24,
        "electronics": 12, "battery": 8, "fasteners_misc": 4,
    }
    total_pct = sum(allocation.values())
    grams = {k: round(total_g * v / 100.0, 1) for k, v in allocation.items()}
    return _ok(total_g=total_g, total_lb=round(total_g / 453.592, 3),
               allocation_pct=allocation, allocation_g=grams,
               allocated_g=round(sum(grams.values()), 1),
               percent_allocated=total_pct,
               warning=(None if abs(total_pct - 100) < 0.01
                        else f"Allocation sums to {total_pct}%, not 100%."))


CALCULATORS = {
    "tip_speed": tip_speed,
    "moment_of_inertia": moment_of_inertia,
    "kinetic_energy": kinetic_energy,
    "spin_up_time": spin_up_time,
    "drive_speed": drive_speed,
    "traction_force": traction_force,
    "motor_constants": motor_constants,
    "bite_depth": bite_depth,
    "gyro_torque": gyro_torque,
    "battery_check": battery_check,
    "weight_budget": weight_budget,
}
