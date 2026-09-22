#!/usr/bin/env python3
"""Build the combat robot knowledge base from research JSON files.

Reads every data/research/*.json produced by the research agents, normalizes it
against the contract in data/schema/CONTRACT.md, and emits:

  data/combat_robots.db    SQLite + FTS5, the queryable knowledge base
  data/combat_robots.json  single bundled JSON export
  data/index.json          lightweight index for the website's client-side search
  data/build_report.md     what came in, what was dropped, what looked wrong

The builder is deliberately forgiving: research agents produce slightly
different shapes, and dropping a whole file because one record is malformed
would lose real work. Anything questionable is repaired if possible and
recorded in the build report if not.
"""

import json
import os
import re
import sys
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESEARCH_DIR = os.path.join(ROOT, "data", "research")
DB_PATH = os.path.join(ROOT, "data", "combat_robots.db")
JSON_PATH = os.path.join(ROOT, "data", "combat_robots.json")
INDEX_PATH = os.path.join(ROOT, "data", "index.json")
REPORT_PATH = os.path.join(ROOT, "data", "build_report.md")

VALID_TYPES = {
    "weight_class", "archetype", "component", "material", "formula",
    "bot", "event", "supplier", "ruleset", "term", "kit",
}

VALID_WEIGHT_CLASSES = {
    "fairyweight", "antweight", "plastic-antweight", "beetleweight",
    "plastic-beetleweight", "hobbyweight", "featherweight", "lightweight",
    "middleweight", "heavyweight",
}

# Common spellings agents drift into, mapped back to the contract vocabulary.
WEIGHT_CLASS_ALIASES = {
    "plastic antweight": "plastic-antweight",
    "plastic ant": "plastic-antweight",
    "plasticant": "plastic-antweight",
    "pla ant": "plastic-antweight",
    "ant": "antweight",
    "1lb": "antweight",
    "1 lb": "antweight",
    "3lb": "beetleweight",
    "3 lb": "beetleweight",
    "beetle": "beetleweight",
    "fairy": "fairyweight",
    "fairyweight150g": "fairyweight",
    "150g": "fairyweight",
    "plastic beetleweight": "plastic-beetleweight",
    "plastic beetle": "plastic-beetleweight",
    "hobbyweight": "hobbyweight",
    "12lb": "hobbyweight",
    "30lb": "featherweight",
    "feather": "featherweight",
    "60lb": "lightweight",
    "120lb": "middleweight",
    "220lb": "heavyweight",
    "250lb": "heavyweight",
    "heavy": "heavyweight",
}

VALID_CONFIDENCE = {"high", "medium", "low"}

# Fields that live in the entity's `extra` blob rather than a dedicated column.
CORE_ENTITY_FIELDS = {
    "id", "type", "name", "aliases", "summary", "weight_classes", "tags",
    "specs", "pros", "cons", "notes", "sources", "confidence",
}


class Report:
    """Collects everything worth telling a human about after a build."""

    def __init__(self):
        self.lines = []
        self.warnings = []
        self.errors = []
        self.files = []

    def warn(self, msg):
        self.warnings.append(msg)

    def error(self, msg):
        self.errors.append(msg)


def slugify(value, fallback="item"):
    """kebab-case ascii slug, stable enough to use as a primary key."""
    if not value:
        return fallback
    value = unicodedata.normalize("NFKD", str(value))
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    value = re.sub(r"-{2,}", "-", value)
    return value or fallback


def as_list(value):
    """Agents sometimes hand back a string where the contract asks for a list."""
    if value is None:
        return []
    if isinstance(value, list):
        out = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, (str, int, float, bool)):
                text = str(item).strip()
                if text:
                    out.append(text)
            else:
                out.append(json.dumps(item, ensure_ascii=False))
        return out
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, dict):
        return [f"{k}: {v}" for k, v in value.items()]
    return [str(value)]


def as_text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def normalize_weight_classes(value, report, context):
    out = []
    for raw in as_list(value):
        key = raw.strip().lower()
        if key in VALID_WEIGHT_CLASSES:
            out.append(key)
            continue
        collapsed = re.sub(r"[\s_]+", " ", key).strip()
        mapped = WEIGHT_CLASS_ALIASES.get(collapsed) or WEIGHT_CLASS_ALIASES.get(
            collapsed.replace(" ", "")
        )
        if mapped:
            out.append(mapped)
        elif re.sub(r"[\s_]+", "-", collapsed) in VALID_WEIGHT_CLASSES:
            out.append(re.sub(r"[\s_]+", "-", collapsed))
        else:
            report.warn(f"{context}: unknown weight class {raw!r} (kept as tag)")
    # preserve order, drop duplicates
    seen = set()
    result = []
    for item in out:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def normalize_specs(value, report, context):
    """Flatten specs to a dict, coercing numeric-looking strings to numbers."""
    if not isinstance(value, dict):
        if value:
            report.warn(f"{context}: specs was {type(value).__name__}, not an object")
        return {}
    out = {}
    for key, raw in value.items():
        clean_key = re.sub(r"\s+", "_", str(key).strip())
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            out[clean_key] = raw
        elif isinstance(raw, str):
            text = raw.strip()
            # "1200" and "1200.5" become numbers; "1000-3000" and "~12" stay strings
            if re.fullmatch(r"-?\d+(\.\d+)?", text):
                out[clean_key] = float(text) if "." in text else int(text)
            else:
                out[clean_key] = text
        elif isinstance(raw, (list, dict, bool)) or raw is None:
            out[clean_key] = raw
        else:
            out[clean_key] = str(raw)
    return out


def specs_to_text(specs):
    """Render specs into something FTS can actually match words against."""
    parts = []
    for key, value in specs.items():
        readable = key.replace("_", " ")
        if isinstance(value, (list, dict)):
            value = json.dumps(value, ensure_ascii=False)
        parts.append(f"{readable} {value}")
    return " | ".join(parts)


def extra_to_text(extra):
    """Index useful structured metadata without stuffing image URLs into FTS."""
    parts = []
    for key, value in extra.items():
        if key.startswith("image_") or key == "also_from" or value in (None, "", [], {}):
            continue
        readable = key.replace("_", " ")
        if isinstance(value, (list, dict)):
            value = json.dumps(value, ensure_ascii=False)
        parts.append(f"{readable} {value}")
    return " | ".join(parts)


def normalize_entity(raw, topic_id, report):
    if not isinstance(raw, dict):
        report.error(f"{topic_id}: entity was {type(raw).__name__}, not an object")
        return None

    name = as_text(raw.get("name"))
    etype = as_text(raw.get("type")).strip().lower().replace("-", "_")
    ent_id = as_text(raw.get("id"))

    if not name and not ent_id:
        report.error(f"{topic_id}: entity with no id and no name, dropped")
        return None
    if not name:
        name = ent_id.replace("-", " ").title()
        report.warn(f"{topic_id}: entity {ent_id} had no name, derived one")

    if etype not in VALID_TYPES:
        guessed = "term"
        if etype:
            report.warn(
                f"{topic_id}: entity {ent_id or name!r} had type {etype!r}, "
                f"filed as {guessed!r}"
            )
        else:
            report.warn(f"{topic_id}: entity {ent_id or name!r} had no type, filed as {guessed!r}")
        etype = guessed

    if not ent_id:
        ent_id = f"{etype.replace('_', '-')}-{slugify(name)}"
        report.warn(f"{topic_id}: entity {name!r} had no id, derived {ent_id!r}")
    ent_id = slugify(ent_id, fallback=slugify(name))

    context = f"{topic_id}/{ent_id}"
    confidence = as_text(raw.get("confidence")).lower() or "medium"
    if confidence not in VALID_CONFIDENCE:
        confidence = "medium"

    extra = {k: v for k, v in raw.items() if k not in CORE_ENTITY_FIELDS}

    return {
        "id": ent_id,
        "type": etype,
        "name": name,
        "aliases": as_list(raw.get("aliases")),
        "summary": as_text(raw.get("summary")),
        "weight_classes": normalize_weight_classes(raw.get("weight_classes"), report, context),
        "tags": [t.lower() for t in as_list(raw.get("tags"))],
        "specs": normalize_specs(raw.get("specs"), report, context),
        "pros": as_list(raw.get("pros")),
        "cons": as_list(raw.get("cons")),
        "notes": as_text(raw.get("notes")),
        "sources": as_list(raw.get("sources")),
        "confidence": confidence,
        "topic_id": topic_id,
        "extra": extra,
    }


def normalize_chunk(raw, topic_id, index, report):
    if not isinstance(raw, dict):
        report.error(f"{topic_id}: chunk was {type(raw).__name__}, not an object")
        return None

    body = as_text(raw.get("body_md") or raw.get("body") or raw.get("text"))
    title = as_text(raw.get("title"))
    if not body:
        report.error(f"{topic_id}: chunk {title or index} had no body, dropped")
        return None
    if not title:
        title = f"{topic_id} note {index}"
        report.warn(f"{topic_id}: chunk {index} had no title, derived one")

    chunk_id = slugify(as_text(raw.get("id")) or f"chunk-{topic_id}-{slugify(title)}")

    return {
        "id": chunk_id,
        "title": title,
        "section": as_text(raw.get("section")),
        "body_md": body,
        "entity_refs": [slugify(r) for r in as_list(raw.get("entity_refs"))],
        "weight_classes": normalize_weight_classes(
            raw.get("weight_classes"), report, f"{topic_id}/{chunk_id}"
        ),
        "tags": [t.lower() for t in as_list(raw.get("tags"))],
        "sources": as_list(raw.get("sources")),
        "topic_id": topic_id,
        "word_count": len(body.split()),
    }



def merge_entities(existing, incoming, report, filename):
    """Fold a second research file's view of the same entity into the first.

    Two agents covering adjacent topics often both describe, say, the plastic
    antweight class. Suffixing produces two thin records that each answer half
    a question; merging produces one that answers the whole thing.
    """
    report.warn(
        f"{filename}: id {existing['id']!r} also covered by "
        f"{existing['topic_id']} — merged"
    )

    # Prefer the longer prose, which is almost always the more complete one.
    if len(incoming["summary"]) > len(existing["summary"]):
        existing["summary"] = incoming["summary"]
    if len(incoming["notes"]) > len(existing["notes"]):
        existing["notes"] = incoming["notes"]

    for field in ("aliases", "weight_classes", "tags", "pros", "cons", "sources"):
        seen = {v.lower(): v for v in existing[field]}
        for value in incoming[field]:
            if value.lower() not in seen:
                seen[value.lower()] = value
                existing[field].append(value)

    # Existing specs win: the first file to claim a key keeps it, so a merge
    # never silently overwrites a verified number with an unverified one.
    for key, value in incoming["specs"].items():
        existing["specs"].setdefault(key, value)
    for key, value in incoming["extra"].items():
        existing["extra"].setdefault(key, value)

    rank = {"low": 0, "medium": 1, "high": 2}
    if rank.get(incoming["confidence"], 1) > rank.get(existing["confidence"], 1):
        existing["confidence"] = incoming["confidence"]

    # Record provenance in `extra`, which is the part of the record that
    # actually gets persisted — a top-level key here would be dropped on write.
    also_from = existing["extra"].setdefault("also_from", [])
    if incoming["topic_id"] not in also_from:
        also_from.append(incoming["topic_id"])

def load_research(report):
    """Read every research file, normalizing and de-duplicating as we go."""
    entities = {}
    chunks = {}
    topics = []

    if not os.path.isdir(RESEARCH_DIR):
        report.error(f"No research directory at {RESEARCH_DIR}")
        return entities, chunks, topics

    for filename in sorted(os.listdir(RESEARCH_DIR)):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(RESEARCH_DIR, filename)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                # strict=False tolerates literal control characters inside
                # strings, which research agents emit often enough that
                # rejecting the file would throw away real work.
                payload = json.loads(handle.read(), strict=False)
        except json.JSONDecodeError as exc:
            report.error(f"{filename}: invalid JSON ({exc}) — FILE SKIPPED")
            continue
        except OSError as exc:
            report.error(f"{filename}: could not read ({exc}) — FILE SKIPPED")
            continue

        if not isinstance(payload, dict):
            report.error(f"{filename}: top level was not an object — FILE SKIPPED")
            continue

        topic_id = slugify(as_text(payload.get("topic_id")) or filename[:-5])
        raw_entities = payload.get("entities") or []
        raw_chunks = payload.get("chunks") or []
        if not isinstance(raw_entities, list):
            report.error(f"{filename}: entities was not a list")
            raw_entities = []
        if not isinstance(raw_chunks, list):
            report.error(f"{filename}: chunks was not a list")
            raw_chunks = []

        kept_entities = 0
        for raw in raw_entities:
            entity = normalize_entity(raw, topic_id, report)
            if not entity:
                continue
            if entity["id"] in entities:
                existing = entities[entity["id"]]
                if existing["topic_id"] == entity["topic_id"]:
                    # Two records with one id inside a single file is an agent
                    # mistake, not two views of the same thing — keep both.
                    report.warn(
                        f"{filename}: duplicate id {entity['id']!r} within file, suffixed")
                    suffix = 2
                    while f"{entity['id']}-{suffix}" in entities:
                        suffix += 1
                    entity["id"] = f"{entity['id']}-{suffix}"
                else:
                    # Two topics covering the same thing: merge into one
                    # richer record rather than shipping near-duplicates.
                    merge_entities(existing, entity, report, filename)
                    continue
            entities[entity["id"]] = entity
            kept_entities += 1

        kept_chunks = 0
        for index, raw in enumerate(raw_chunks, start=1):
            chunk = normalize_chunk(raw, topic_id, index, report)
            if not chunk:
                continue
            if chunk["id"] in chunks:
                suffix = 2
                while f"{chunk['id']}-{suffix}" in chunks:
                    suffix += 1
                chunk["id"] = f"{chunk['id']}-{suffix}"
            chunks[chunk["id"]] = chunk
            kept_chunks += 1

        topics.append({
            "topic_id": topic_id,
            "title": as_text(payload.get("title")) or topic_id.replace("-", " ").title(),
            "scope_note": as_text(payload.get("scope_note")),
            "source_file": filename,
            "entity_count": kept_entities,
            "chunk_count": kept_chunks,
        })
        report.files.append((filename, kept_entities, kept_chunks))

    return entities, chunks, topics


def resolve_cross_references(entities, chunks, report):
    """Chunks reference entities by id; agents don't always get the id exactly right.

    Matching by name and alias recovers most of them, which matters because the
    website and the agent both use these links for "related" navigation.
    """
    by_name = {}
    for entity in entities.values():
        by_name.setdefault(slugify(entity["name"]), entity["id"])
        for alias in entity["aliases"]:
            by_name.setdefault(slugify(alias), entity["id"])

    resolved_total = 0
    dropped_total = 0
    for chunk in chunks.values():
        resolved = []
        for ref in chunk["entity_refs"]:
            if ref in entities:
                resolved.append(ref)
                resolved_total += 1
            elif ref in by_name:
                resolved.append(by_name[ref])
                resolved_total += 1
            else:
                dropped_total += 1
        chunk["entity_refs"] = sorted(set(resolved))

    if dropped_total:
        report.warn(
            f"cross-references: {resolved_total} resolved, "
            f"{dropped_total} pointed at entities that do not exist (dropped)"
        )
    return resolved_total, dropped_total


def create_schema(conn):
    conn.executescript("""
        DROP TABLE IF EXISTS entities;
        DROP TABLE IF EXISTS chunks;
        DROP TABLE IF EXISTS topics;
        DROP TABLE IF EXISTS meta;
        DROP TABLE IF EXISTS entity_tags;
        DROP TABLE IF EXISTS entity_weight_classes;
        DROP TABLE IF EXISTS chunk_entity_refs;
        DROP TABLE IF EXISTS entities_fts;
        DROP TABLE IF EXISTS chunks_fts;

        CREATE TABLE entities (
            id              TEXT PRIMARY KEY,
            type            TEXT NOT NULL,
            name            TEXT NOT NULL,
            aliases         TEXT NOT NULL DEFAULT '[]',
            summary         TEXT NOT NULL DEFAULT '',
            weight_classes  TEXT NOT NULL DEFAULT '[]',
            tags            TEXT NOT NULL DEFAULT '[]',
            specs           TEXT NOT NULL DEFAULT '{}',
            pros            TEXT NOT NULL DEFAULT '[]',
            cons            TEXT NOT NULL DEFAULT '[]',
            notes           TEXT NOT NULL DEFAULT '',
            sources         TEXT NOT NULL DEFAULT '[]',
            confidence      TEXT NOT NULL DEFAULT 'medium',
            topic_id        TEXT NOT NULL,
            extra           TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX idx_entities_type ON entities(type);
        CREATE INDEX idx_entities_topic ON entities(topic_id);
        CREATE INDEX idx_entities_name ON entities(name);

        CREATE TABLE chunks (
            id              TEXT PRIMARY KEY,
            title           TEXT NOT NULL,
            section         TEXT NOT NULL DEFAULT '',
            body_md         TEXT NOT NULL,
            entity_refs     TEXT NOT NULL DEFAULT '[]',
            weight_classes  TEXT NOT NULL DEFAULT '[]',
            tags            TEXT NOT NULL DEFAULT '[]',
            sources         TEXT NOT NULL DEFAULT '[]',
            topic_id        TEXT NOT NULL,
            word_count      INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX idx_chunks_topic ON chunks(topic_id);

        CREATE TABLE topics (
            topic_id     TEXT PRIMARY KEY,
            title        TEXT NOT NULL,
            scope_note   TEXT NOT NULL DEFAULT '',
            source_file  TEXT NOT NULL,
            entity_count INTEGER NOT NULL DEFAULT 0,
            chunk_count  INTEGER NOT NULL DEFAULT 0
        );

        -- Normalized side tables make faceted filtering cheap for the website
        -- and for the agent's list/filter tools.
        CREATE TABLE entity_tags (
            entity_id TEXT NOT NULL REFERENCES entities(id),
            tag       TEXT NOT NULL,
            PRIMARY KEY (entity_id, tag)
        );
        CREATE INDEX idx_entity_tags_tag ON entity_tags(tag);

        CREATE TABLE entity_weight_classes (
            entity_id    TEXT NOT NULL REFERENCES entities(id),
            weight_class TEXT NOT NULL,
            PRIMARY KEY (entity_id, weight_class)
        );
        CREATE INDEX idx_ewc_class ON entity_weight_classes(weight_class);

        CREATE TABLE chunk_entity_refs (
            chunk_id  TEXT NOT NULL REFERENCES chunks(id),
            entity_id TEXT NOT NULL REFERENCES entities(id),
            PRIMARY KEY (chunk_id, entity_id)
        );
        CREATE INDEX idx_cer_entity ON chunk_entity_refs(entity_id);

        CREATE TABLE meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE entities_fts USING fts5(
            id UNINDEXED,
            name,
            aliases,
            summary,
            notes,
            tags,
            specs_text,
            pros_cons,
            extra_text,
            tokenize = 'porter unicode61'
        );

        CREATE VIRTUAL TABLE chunks_fts USING fts5(
            id UNINDEXED,
            title,
            section,
            body_md,
            tags,
            tokenize = 'porter unicode61'
        );
    """)


def populate(conn, entities, chunks, topics):
    cur = conn.cursor()

    for entity in entities.values():
        cur.execute(
            """INSERT INTO entities (id, type, name, aliases, summary, weight_classes,
                                     tags, specs, pros, cons, notes, sources,
                                     confidence, topic_id, extra)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                entity["id"], entity["type"], entity["name"],
                json.dumps(entity["aliases"], ensure_ascii=False),
                entity["summary"],
                json.dumps(entity["weight_classes"], ensure_ascii=False),
                json.dumps(entity["tags"], ensure_ascii=False),
                json.dumps(entity["specs"], ensure_ascii=False),
                json.dumps(entity["pros"], ensure_ascii=False),
                json.dumps(entity["cons"], ensure_ascii=False),
                entity["notes"],
                json.dumps(entity["sources"], ensure_ascii=False),
                entity["confidence"], entity["topic_id"],
                json.dumps(entity["extra"], ensure_ascii=False),
            ),
        )
        cur.executemany(
            "INSERT OR IGNORE INTO entity_tags VALUES (?,?)",
            [(entity["id"], tag) for tag in entity["tags"]],
        )
        cur.executemany(
            "INSERT OR IGNORE INTO entity_weight_classes VALUES (?,?)",
            [(entity["id"], wc) for wc in entity["weight_classes"]],
        )
        cur.execute(
            "INSERT INTO entities_fts VALUES (?,?,?,?,?,?,?,?,?)",
            (
                entity["id"], entity["name"], " ".join(entity["aliases"]),
                entity["summary"], entity["notes"], " ".join(entity["tags"]),
                specs_to_text(entity["specs"]),
                " ".join(entity["pros"] + entity["cons"]),
                extra_to_text(entity["extra"]),
            ),
        )

    for chunk in chunks.values():
        cur.execute(
            """INSERT INTO chunks (id, title, section, body_md, entity_refs,
                                   weight_classes, tags, sources, topic_id, word_count)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                chunk["id"], chunk["title"], chunk["section"], chunk["body_md"],
                json.dumps(chunk["entity_refs"], ensure_ascii=False),
                json.dumps(chunk["weight_classes"], ensure_ascii=False),
                json.dumps(chunk["tags"], ensure_ascii=False),
                json.dumps(chunk["sources"], ensure_ascii=False),
                chunk["topic_id"], chunk["word_count"],
            ),
        )
        cur.executemany(
            "INSERT OR IGNORE INTO chunk_entity_refs VALUES (?,?)",
            [(chunk["id"], ref) for ref in chunk["entity_refs"]],
        )
        cur.execute(
            "INSERT INTO chunks_fts VALUES (?,?,?,?,?)",
            (chunk["id"], chunk["title"], chunk["section"],
             chunk["body_md"], " ".join(chunk["tags"])),
        )

    cur.executemany(
        "INSERT INTO topics VALUES (?,?,?,?,?,?)",
        [(t["topic_id"], t["title"], t["scope_note"], t["source_file"],
          t["entity_count"], t["chunk_count"]) for t in topics],
    )

    total_words = sum(c["word_count"] for c in chunks.values())
    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": "1",
        "entity_count": str(len(entities)),
        "chunk_count": str(len(chunks)),
        "topic_count": str(len(topics)),
        "chunk_word_count": str(total_words),
        "focus": "antweight (1 lb) and plastic antweight",
    }
    cur.executemany("INSERT INTO meta VALUES (?,?)", list(meta.items()))
    conn.commit()
    return meta


def write_exports(entities, chunks, topics, meta):
    bundle = {
        "meta": meta,
        "topics": topics,
        "entities": list(entities.values()),
        "chunks": list(chunks.values()),
    }
    with open(JSON_PATH, "w", encoding="utf-8") as handle:
        json.dump(bundle, handle, ensure_ascii=False, indent=1)

    # The website loads this instead of the full bundle: enough to search and
    # render result cards, small enough to ship to a browser.
    index = {
        "meta": meta,
        "topics": topics,
        "entities": [
            {
                "id": e["id"],
                "type": e["type"],
                "name": e["name"],
                "summary": e["summary"],
                "weight_classes": e["weight_classes"],
                "tags": e["tags"],
                "topic_id": e["topic_id"],
                "confidence": e["confidence"],
                "spec_keys": sorted(e["specs"].keys()),
            }
            for e in entities.values()
        ],
        "chunks": [
            {
                "id": c["id"],
                "title": c["title"],
                "section": c["section"],
                "topic_id": c["topic_id"],
                "tags": c["tags"],
                "weight_classes": c["weight_classes"],
                "word_count": c["word_count"],
                "preview": c["body_md"][:280],
            }
            for c in chunks.values()
        ],
    }
    with open(INDEX_PATH, "w", encoding="utf-8") as handle:
        json.dump(index, handle, ensure_ascii=False, separators=(",", ":"))


def write_report(report, entities, chunks, topics, meta):
    type_counts = Counter(e["type"] for e in entities.values())
    wc_counts = Counter()
    for entity in entities.values():
        for wc in entity["weight_classes"]:
            wc_counts[wc] += 1
    confidence_counts = Counter(e["confidence"] for e in entities.values())
    sourced = sum(1 for e in entities.values() if e["sources"])

    lines = [
        "# Knowledge base build report",
        "",
        f"Built: {meta['built_at']}",
        "",
        "## Totals",
        "",
        f"- Entities: **{len(entities)}**",
        f"- Knowledge chunks: **{len(chunks)}** ({meta['chunk_word_count']} words)",
        f"- Research topics: **{len(topics)}**",
        f"- Entities citing at least one source: **{sourced}** "
        f"({(100 * sourced // max(len(entities), 1))}%)",
        "",
        "## Entities by type",
        "",
        "| type | count |",
        "| --- | --- |",
    ]
    lines += [f"| {t} | {n} |" for t, n in type_counts.most_common()]
    lines += [
        "",
        "## Entities by weight class",
        "",
        "| weight class | count |",
        "| --- | --- |",
    ]
    lines += [f"| {w} | {n} |" for w, n in wc_counts.most_common()]
    lines += [
        "",
        "## Confidence",
        "",
        "| level | count |",
        "| --- | --- |",
    ]
    lines += [f"| {c} | {n} |" for c, n in confidence_counts.most_common()]
    lines += [
        "",
        "## Source files",
        "",
        "| file | entities | chunks |",
        "| --- | --- | --- |",
    ]
    lines += [f"| {f} | {e} | {c} |" for f, e, c in report.files]

    if report.errors:
        lines += ["", f"## Errors ({len(report.errors)})", ""]
        lines += [f"- {e}" for e in report.errors]
    if report.warnings:
        lines += ["", f"## Warnings ({len(report.warnings)})", ""]
        lines += [f"- {w}" for w in report.warnings[:200]]
        if len(report.warnings) > 200:
            lines.append(f"- ...and {len(report.warnings) - 200} more")

    with open(REPORT_PATH, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main():
    report = Report()
    entities, chunks, topics = load_research(report)

    if not entities and not chunks:
        print("No research data found. Nothing to build.", file=sys.stderr)
        return 1

    resolve_cross_references(entities, chunks, report)

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    try:
        create_schema(conn)
        meta = populate(conn, entities, chunks, topics)
        conn.execute("VACUUM")
    finally:
        conn.close()

    write_exports(entities, chunks, topics, meta)
    write_report(report, entities, chunks, topics, meta)

    print(f"entities: {len(entities)}")
    print(f"chunks:   {len(chunks)} ({meta['chunk_word_count']} words)")
    print(f"topics:   {len(topics)}")
    print(f"warnings: {len(report.warnings)}  errors: {len(report.errors)}")
    print(f"wrote {DB_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
