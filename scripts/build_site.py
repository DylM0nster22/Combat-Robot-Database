#!/usr/bin/env python3
"""Generate the static website from the built knowledge base.

    python3 scripts/build_db.py && python3 scripts/build_site.py

Writes plain HTML into web/ with no build step and no framework, so the site
can be opened from disk or served by anything (GitHub Pages included).
Search runs client-side against data/index.json.
"""

import html
import json
import os
import re
import shutil
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "agent"))

import photos  # noqa: E402
import kb  # noqa: E402

WEB = os.path.join(ROOT, "web")

NAV = [
    ("index.html", "Home"),
    ("archetypes.html", "Archetypes"),
    ("parts.html", "Parts"),
    ("materials.html", "Materials"),
    ("guides.html", "Guides"),
    ("calculators.html", "Calculators"),
    ("rules.html", "Rules"),
    ("search.html", "Search"),
]

TYPE_LABELS = {
    "archetype": "Archetype", "component": "Component", "material": "Material",
    "formula": "Formula", "bot": "Robot", "event": "Event", "supplier": "Supplier",
    "ruleset": "Ruleset", "term": "Term", "kit": "Kit", "weight_class": "Weight class",
}


def esc(text):
    return html.escape(str(text if text is not None else ""))


# ------------------------------------------------------------ markdown

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BARE_URL = re.compile(r"(?<![\"'(>=])(https?://[^\s<)\]]+)")


def _inline(text):
    """Escape first, then apply inline markdown, so content can't inject HTML."""
    out = esc(text)
    out = _INLINE_CODE.sub(lambda m: f"<code>{m.group(1)}</code>", out)
    out = _BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", out)
    out = _ITALIC.sub(lambda m: f"<em>{m.group(1)}</em>", out)
    out = _LINK.sub(lambda m: f'<a href="{m.group(2)}" rel="noopener">{m.group(1)}</a>', out)
    out = _BARE_URL.sub(lambda m: f'<a href="{m.group(1)}" rel="noopener">{m.group(1)}</a>', out)
    return out


def markdown(text):
    """A small markdown subset: headings, lists, tables, quotes, code, paragraphs.

    Written here rather than pulled from PyPI so the build has no dependencies.
    It handles what the research agents actually emit.
    """
    if not text:
        return ""
    lines = text.replace("\r\n", "\n").split("\n")
    out, i = [], 0
    list_stack = []

    def close_lists():
        while list_stack:
            out.append(f"</{list_stack.pop()}>")

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            close_lists()
            i += 1
            block = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(esc(lines[i]))
                i += 1
            i += 1
            out.append("<pre><code>" + "\n".join(block) + "</code></pre>")
            continue

        if not stripped:
            close_lists()
            i += 1
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            close_lists()
            level = min(len(heading.group(1)) + 1, 6)   # page h1 is the title
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            i += 1
            continue

        # Table: a header row followed by a |---|---| separator
        if stripped.startswith("|") and i + 1 < len(lines) and \
                re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            close_lists()
            def cells(row):
                return [c.strip() for c in row.strip().strip("|").split("|")]
            header = cells(stripped)
            i += 2
            body = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                body.append(cells(lines[i]))
                i += 1
            out.append("<table><thead><tr>"
                       + "".join(f"<th>{_inline(c)}</th>" for c in header)
                       + "</tr></thead><tbody>")
            for row in body:
                out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in row) + "</tr>")
            out.append("</tbody></table>")
            continue

        if stripped.startswith(">"):
            close_lists()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append(f"<blockquote>{_inline(' '.join(quote))}</blockquote>")
            continue

        bullet = re.match(r"^(\s*)[-*+]\s+(.*)$", line)
        number = re.match(r"^(\s*)\d+[.)]\s+(.*)$", line)
        if bullet or number:
            match = bullet or number
            tag = "ul" if bullet else "ol"
            if not list_stack:
                list_stack.append(tag)
                out.append(f"<{tag}>")
            elif list_stack[-1] != tag:
                out.append(f"</{list_stack.pop()}>")
                list_stack.append(tag)
                out.append(f"<{tag}>")
            out.append(f"<li>{_inline(match.group(2))}</li>")
            i += 1
            continue

        close_lists()
        para = [stripped]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^\s*([-*+]\s|\d+[.)]\s|#{1,6}\s|\||>|```)", lines[i]):
            para.append(lines[i].strip())
            i += 1
        out.append(f"<p>{_inline(' '.join(para))}</p>")

    close_lists()
    return "\n".join(out)


# --------------------------------------------------------------- layout

def page(title, body, active="", description="", depth=0):
    prefix = "../" * depth
    nav_parts = []
    for href, label in NAV:
        cls = ' class="active"' if href == active else ""
        nav_parts.append(f'<a href="{prefix}{href}"{cls}>{label}</a>')
    nav = "".join(nav_parts)
    desc = esc(description or
               "A researched knowledge base for 1 lb antweight and plastic "
               "antweight combat robots.")
    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{desc}">
<link rel="stylesheet" href="{prefix}assets/site.css">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><circle cx='16' cy='16' r='13' fill='none' stroke='%23ff7a1a' stroke-width='3'/><rect x='14' y='5' width='4' height='22' fill='%23ff7a1a' transform='rotate(32 16 16)'/></svg>">
<script>
// Applied before paint so a light-theme reader never sees a dark flash.
(function(){{try{{var t=localStorage.getItem('crdb-theme');if(t)document.documentElement.dataset.theme=t;}}catch(e){{}}}})();
</script>
</head>
<body>
<header class="site"><div class="wrap">
  <a class="brand" href="{prefix}index.html"><span class="mark"></span>Combat Robot Database</a>
  <nav class="main">{nav}</nav>
  <button class="theme-btn" id="theme-toggle" title="Toggle light/dark" aria-label="Toggle theme">◐</button>
</div></header>
{body}
<footer class="site"><div class="wrap">
  <p>Built from automated research into antweight and plastic antweight combat robotics.
  Figures are compiled from public sources and should be verified against your event's
  current ruleset and the manufacturer's own specifications before you cut metal or enter a competition.</p>
  <p><a href="{prefix}about.html">About &amp; data sources</a> · <a href="{prefix}search.html">Search</a></p>
</div></footer>
<script src="{prefix}assets/site.js"></script>
</body>
</html>
"""


def entity_url(entity_id, depth=0):
    return f"{'../' * depth}e/{entity_id}.html"


def chunk_url(chunk_id, depth=0):
    return f"{'../' * depth}g/{chunk_id}.html"


def pills(entity, depth=0):
    out = [f'<span class="pill type">{esc(TYPE_LABELS.get(entity["type"], entity["type"]))}</span>']
    for wc in entity.get("weight_classes", [])[:3]:
        out.append(f'<span class="pill accent">{esc(wc)}</span>')
    if entity.get("confidence") == "low":
        out.append('<span class="pill conf-low">unverified</span>')
    return "".join(out)


def photo_html(entity, detail=False):
    """Render a real-world example photo for explicitly mapped archetypes."""
    photo = photos.photo_for(entity["id"])
    if not photo:
        return ""
    img = (
        f'<img class="robot-photo" src="{esc(photo["image"])}" '
        f'alt="Real combat robot example: {esc(photo["robot"])}" '
        f'loading="lazy" decoding="async" referrerpolicy="no-referrer">'
    )
    if not detail:
        return f'<div class="card-art photo-art">{img}</div>'
    credit = (
        '<div class="photo-credit">Representative real robot: '
        f'<a href="{esc(photo["source"])}" target="_blank" rel="noopener noreferrer">'
        f'{esc(photo["robot"])} — {esc(photo["provider"])}</a></div>'
    )
    return f'<div class="card-art photo-art detail-photo">{img}</div>{credit}'


def entity_card(entity, depth=0, art=False):
    art_html = photo_html(entity) if art else ""
    summary = entity.get("summary") or ""
    if len(summary) > 155:
        summary = summary[:152].rsplit(" ", 1)[0] + "…"
    return (f'<a class="card" href="{entity_url(entity["id"], depth)}">'
            f'{art_html}<h3>{esc(entity["name"])}</h3>'
            f'<p>{esc(summary)}</p>'
            f'<div style="margin-top:10px">{pills(entity, depth)}</div></a>')


# ---------------------------------------------------------------- pages

def build_index(database, stats):
    meta = stats["meta"]
    archetypes = database.list_entities(entity_type="archetype", limit=300)["entities"]
    # Lead with archetypes that have verified real-world photo examples.
    featured = [a for a in archetypes if photos.photo_for(a["id"])][:8]

    def stat(n, label):
        return f'<div class="stat"><div class="n">{n}</div><div class="l">{label}</div></div>'

    counts = stats["entities_by_type"]
    body = f"""
<div class="hero"><div class="wrap">
  <h1>Everything that makes a <span class="hl">1&nbsp;lb combat robot</span> work.</h1>
  <p class="lead">A researched, queryable reference for antweight and plastic antweight
  builders — design archetypes, motor sizing, materials, electronics, the maths, and the
  rules. Built to be read by people and queried by an LLM agent.</p>
  <div class="statbar">
    {stat(meta.get('entity_count', '0'), 'entries')}
    {stat(meta.get('chunk_count', '0'), 'guides')}
    {stat(counts.get('archetype', 0), 'archetypes')}
    {stat(counts.get('component', 0), 'components')}
    {stat(counts.get('formula', 0), 'formulas')}
    {stat(counts.get('material', 0), 'materials')}
  </div>
</div></div>

<div class="wrap">
<section>
  <h2>Design archetypes</h2>
  <p class="sub">Every way people have found to win a 1 lb fight, and what beats each one.</p>
  <div class="grid c3">{''.join(entity_card(a, art=True) for a in featured)}</div>
  <p style="margin-top:18px"><a href="archetypes.html">All {len(archetypes)} archetypes →</a></p>
</section>

<section>
  <h2>Start here</h2>
  <div class="grid c2">
    <a class="card" href="guides.html"><h3>Build guides</h3>
      <p>Long-form explainers on drivetrain sizing, weapon selection, print settings,
      failsafes and pit repairs — {meta.get('chunk_count', '0')} of them.</p></a>
    <a class="card" href="calculators.html"><h3>Calculators</h3>
      <p>Tip speed, kinetic energy, moment of inertia, spin-up time, traction limit,
      bite depth, gyro torque, battery sizing and weight budget — all interactive.</p></a>
    <a class="card" href="parts.html"><h3>Parts catalogue</h3>
      <p>Drive motors, weapon motors, ESCs, receivers, batteries and wheels with real
      weights, KV figures, current ratings and prices.</p></a>
    <a class="card" href="rules.html"><h3>Classes &amp; rules</h3>
      <p>Weight limits, what plastic antweight actually allows, safety requirements
      and what a tech inspector checks.</p></a>
  </div>
</section>

<section>
  <h2>Ask it anything</h2>
  <p class="sub">The same data powers an MCP server and a Discord bot, so an LLM agent can
  answer build questions with real numbers instead of guesses.</p>
  <div class="card">
    <p style="color:var(--text)"><strong>Discord</strong> — <code>@bot what weapon motor for a plastic ant vertical spinner?</code></p>
    <p style="margin-top:10px"><strong>MCP</strong> — <code>claude mcp add combat-robots -- python3 agent/mcp_server.py</code></p>
    <p style="margin-top:10px">Setup lives in the repository's <code>README.md</code>.</p>
  </div>
</section>
</div>
"""
    return page("Combat Robot Database — antweight & plastic ant reference",
                body, active="index.html")


def build_archetypes(database):
    archetypes = database.list_entities(entity_type="archetype", limit=400)["entities"]
    families = defaultdict(list)
    for item in archetypes:
        full = database.get_entity(item["id"]) or {}
        families[(full.get("family") or "other").lower()].append(item)

    order = ["spinner", "control", "lifter", "flipper", "crusher", "hammer",
             "rammer", "other"]
    sections = []
    for family in sorted(families, key=lambda f: (order.index(f) if f in order else 99, f)):
        items = families[family]
        sections.append(
            f'<section><h2>{esc(family.title())}</h2>'
            f'<p class="sub">{len(items)} design{"s" if len(items) != 1 else ""}</p>'
            f'<div class="grid c3">{"".join(entity_card(a, art=True) for a in items)}</div></section>'
        )

    if not archetypes:
        sections = ['<div class="empty">No archetypes in the database yet.</div>']

    body = f"""<div class="wrap">
<h1 class="page" style="margin-top:34px">Archetypes</h1>
<p class="page-sub">Every combat robot design family, drawn and explained, with what each
one counters and what counters it. Diagrams are schematic — they show the mechanism,
not a specific robot.</p>
{''.join(sections)}
</div>"""
    return page("Archetypes — Combat Robot Database", body, active="archetypes.html",
                description="Every combat robot design archetype for antweight and "
                            "plastic antweight, with counters and build notes.")


def build_parts(database):
    components = database.list_entities(entity_type="component", limit=500)["entities"]
    by_category = defaultdict(list)
    for item in components:
        full = database.get_entity(item["id"]) or {}
        by_category[(full.get("category") or "misc")].append((item, full))

    label = {
        "drive-motor": "Drive motors", "weapon-motor": "Weapon motors",
        "esc-drive": "Drive ESCs", "esc-weapon": "Weapon ESCs",
        "receiver": "Receivers", "transmitter": "Transmitters",
        "battery": "Batteries", "wheel": "Wheels", "hub": "Hubs",
        "gearbox": "Gearboxes", "bearing": "Bearings", "fastener": "Fasteners",
        "switch": "Switches & links", "servo": "Servos",
        "belt-pulley": "Belts & pulleys", "connector": "Connectors", "misc": "Other",
    }
    priority = ["weapon-motor", "drive-motor", "esc-weapon", "esc-drive", "battery",
                "receiver", "transmitter", "wheel", "gearbox", "hub", "belt-pulley",
                "switch", "servo", "bearing", "fastener", "connector", "misc"]

    sections = []
    for category in sorted(by_category,
                           key=lambda c: (priority.index(c) if c in priority else 99, c)):
        rows = []
        # Show the spec columns that most of this category actually populates.
        spec_freq = defaultdict(int)
        for _, full in by_category[category]:
            for key in full.get("specs", {}):
                spec_freq[key] += 1
        top_specs = [k for k, n in sorted(spec_freq.items(), key=lambda kv: -kv[1])[:4]]

        for item, full in by_category[category]:
            cells = "".join(
                f'<td>{esc(full.get("specs", {}).get(k, "—"))}</td>' for k in top_specs)
            rows.append(
                f'<tr><td><a href="{entity_url(item["id"])}">{esc(item["name"])}</a><br>'
                f'<span style="color:var(--text-faint);font-size:13px">'
                f'{esc((item.get("summary") or "")[:90])}</span></td>{cells}</tr>')
        headers = "".join(f'<th>{esc(k.replace("_", " "))}</th>' for k in top_specs)
        sections.append(
            f'<section><h2>{esc(label.get(category, category.title()))}</h2>'
            f'<p class="sub">{len(by_category[category])} entries</p>'
            f'<table class="specs"><thead><tr><th style="width:40%">Part</th>{headers}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></section>')

    if not components:
        sections = ['<div class="empty">No components in the database yet.</div>']

    body = f"""<div class="wrap">
<h1 class="page" style="margin-top:34px">Parts catalogue</h1>
<p class="page-sub">Real parts people put in 1 lb robots, with the numbers that decide
whether they fit your weight budget. Prices and availability drift — check the vendor.</p>
{''.join(sections)}
</div>"""
    return page("Parts — Combat Robot Database", body, active="parts.html",
                description="Antweight drive motors, weapon motors, ESCs, batteries "
                            "and wheels with real specifications.")


def build_materials(database):
    materials = database.list_entities(entity_type="material", limit=300)["entities"]
    rows = []
    for item in materials:
        full = database.get_entity(item["id"]) or {}
        specs = full.get("specs", {})
        rows.append(
            f'<tr><td><a href="{entity_url(item["id"])}">{esc(item["name"])}</a></td>'
            f'<td>{esc(full.get("category", "—"))}</td>'
            f'<td>{esc(specs.get("density_g_cm3", "—"))}</td>'
            f'<td>{esc(specs.get("yield_strength_mpa", specs.get("tensile_strength_mpa", "—")))}</td>'
            f'<td>{esc(specs.get("cost_per_kg_usd", "—"))}</td></tr>')
    table = (
        '<table class="specs"><thead><tr><th style="width:30%">Material</th><th>Category</th>'
        '<th>Density g/cm³</th><th>Strength MPa</th><th>Cost $/kg</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    ) if rows else '<div class="empty">No materials in the database yet.</div>'

    body = f"""<div class="wrap">
<h1 class="page" style="margin-top:34px">Materials</h1>
<p class="page-sub">What to make armour, chassis and weapons from — and what the choice
costs you in grams. In a 1 lb robot, strength-to-weight beats absolute strength every time.</p>
<section>{table}</section>
<section><div class="grid c3">{''.join(entity_card(m) for m in materials[:12])}</div></section>
</div>"""
    return page("Materials — Combat Robot Database", body, active="materials.html",
                description="Armour, chassis and weapon materials for antweight combat "
                            "robots, with density, strength and cost.")


def build_guides(database):
    chunks = [dict(r) for r in database.conn.execute(
        "SELECT id, title, section, topic_id, word_count, substr(body_md,1,220) AS preview "
        "FROM chunks ORDER BY topic_id, section, title").fetchall()]
    by_topic = defaultdict(list)
    for chunk in chunks:
        by_topic[chunk["topic_id"]].append(chunk)

    topic_titles = {r["topic_id"]: r["title"] for r in
                    database.conn.execute("SELECT topic_id, title FROM topics").fetchall()}

    sections = []
    for topic in sorted(by_topic):
        card_parts = []
        for c in by_topic[topic]:
            section_pill = (f'<span class="pill">{esc(c["section"])}</span>'
                            if c["section"] else "")
            card_parts.append(
                f'<a class="card" href="{chunk_url(c["id"])}"><h3>{esc(c["title"])}</h3>'
                f'<p>{esc(c["preview"][:150])}…</p>'
                f'<div style="margin-top:10px">'
                f'<span class="pill">{c["word_count"]} words</span>'
                f'{section_pill}</div></a>')
        cards = "".join(card_parts)
        sections.append(
            f'<section><h2>{esc(topic_titles.get(topic, topic.replace("-", " ").title()))}</h2>'
            f'<p class="sub">{len(by_topic[topic])} guides</p>'
            f'<div class="grid c2">{cards}</div></section>')

    if not chunks:
        sections = ['<div class="empty">No guides in the database yet.</div>']

    body = f"""<div class="wrap">
<h1 class="page" style="margin-top:34px">Guides</h1>
<p class="page-sub">{len(chunks)} long-form explainers, grouped by the research topic
they came from.</p>
{''.join(sections)}
</div>"""
    return page("Guides — Combat Robot Database", body, active="guides.html",
                description="Long-form build guides for antweight and plastic antweight "
                            "combat robots.")


def build_rules(database):
    classes = database.list_entities(entity_type="weight_class", limit=100)["entities"]
    rulesets = database.list_entities(entity_type="ruleset", limit=100)["entities"]

    rows = []
    for item in sorted(classes, key=lambda c: (database.get_entity(c["id"]) or {}).get("limit_lb") or 0):
        full = database.get_entity(item["id"]) or {}
        rows.append(
            f'<tr><td><a href="{entity_url(item["id"])}">{esc(item["name"])}</a></td>'
            f'<td>{esc(full.get("limit_lb", "—"))}</td>'
            f'<td>{esc(full.get("limit_kg", "—"))}</td>'
            f'<td>{esc(", ".join(full.get("common_orgs", [])[:4]) or "—")}</td></tr>')
    class_table = (
        '<table class="specs"><thead><tr><th>Class</th><th>lb</th><th>kg</th>'
        f'<th>Run by</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'
    ) if rows else '<div class="empty">No weight classes recorded yet.</div>'

    body = f"""<div class="wrap">
<h1 class="page" style="margin-top:34px">Classes &amp; rules</h1>
<p class="page-sub">Weight limits, safety requirements and what changes between
organisations. Always confirm against your event's current published ruleset — these
change, and the version here is a snapshot.</p>
<section><h2>Weight classes</h2>{class_table}</section>
<section><h2>Rulesets &amp; organisations</h2>
  <div class="grid c2">{''.join(entity_card(r) for r in rulesets) or
     '<div class="empty">No rulesets recorded yet.</div>'}</div></section>
</div>"""
    return page("Rules — Combat Robot Database", body, active="rules.html",
                description="Combat robot weight classes, rulesets and safety "
                            "requirements, focused on antweight.")


def build_entity_page(database, entity):
    depth = 1
    # Do not guess artwork from names/tags. Only explicitly mapped archetypes get photos.
    art = photo_html(entity, detail=True)

    spec_rows = "".join(
        f'<tr><th>{esc(k.replace("_", " "))}</th><td>{esc(v)}</td></tr>'
        for k, v in entity.get("specs", {}).items())
    specs = (f'<h2>Specifications</h2><table class="specs"><tbody>{spec_rows}</tbody></table>'
             if spec_rows else "")

    pro_con = ""
    if entity.get("pros") or entity.get("cons"):
        pros = "".join(f"<li>{_inline(p)}</li>" for p in entity.get("pros", []))
        cons = "".join(f"<li>{_inline(c)}</li>" for c in entity.get("cons", []))
        pro_con = (
            '<div class="pro-con">'
            f'<div class="pros"><h4>Strengths</h4><ul>{pros or "<li>—</li>"}</ul></div>'
            f'<div class="cons"><h4>Weaknesses</h4><ul>{cons or "<li>—</li>"}</ul></div>'
            '</div>')

    notes = f'<h2>Notes</h2>{markdown(entity.get("notes"))}' if entity.get("notes") else ""

    formula = ""
    if entity["type"] == "formula":
        parts = []
        if entity.get("expression"):
            parts.append(f'<h2>Expression</h2><pre><code>{esc(entity["expression"])}</code></pre>')
        if isinstance(entity.get("variables"), dict) and entity["variables"]:
            rows = "".join(f'<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>'
                           for k, v in entity["variables"].items())
            parts.append(f'<h2>Variables</h2><table class="specs"><tbody>{rows}</tbody></table>')
        if entity.get("worked_example"):
            parts.append(f'<h2>Worked example</h2>{markdown(entity["worked_example"])}')
        formula = "".join(parts)

    # Archetype relationships, rendered as links where the target exists.
    def linked(values):
        out = []
        for value in values or []:
            target = database.get_entity(str(value))
            if target:
                out.append(f'<li><a href="{entity_url(target["id"], depth)}">'
                           f'{esc(target["name"])}</a></li>')
            else:
                out.append(f"<li>{esc(value)}</li>")
        return "".join(out)

    side = []
    if entity.get("counters"):
        side.append(f'<div class="side-box"><h4>Strong against</h4><ul>{linked(entity["counters"])}</ul></div>')
    if entity.get("countered_by"):
        side.append(f'<div class="side-box"><h4>Weak against</h4><ul>{linked(entity["countered_by"])}</ul></div>')
    if entity.get("weight_budget_pct") and isinstance(entity["weight_budget_pct"], dict):
        rows = "".join(f'<tr><th>{esc(k.replace("_", " "))}</th><td>{esc(v)}%</td></tr>'
                       for k, v in entity["weight_budget_pct"].items())
        side.append(f'<div class="side-box"><h4>Weight budget</h4>'
                    f'<table class="specs"><tbody>{rows}</tbody></table></div>')
    for key, heading in (("difficulty", "Build difficulty"),
                         ("typical_weapon_motor", "Typical weapon motor"),
                         ("typical_drive", "Typical drive"),
                         ("vendor", "Vendor"), ("builder", "Builder"),
                         ("organization", "Organisation"), ("country", "Country"),
                         ("website", "Website"), ("product_url", "Product page")):
        value = entity.get(key)
        if value:
            if isinstance(value, str) and value.startswith("http"):
                value = f'<a href="{esc(value)}" rel="noopener">{esc(value[:44])}…</a>'
            else:
                value = esc(value)
            side.append(f'<div class="side-box"><h4>{heading}</h4><p style="margin:0">{value}</p></div>')
    if entity.get("related_chunks"):
        links = "".join(
            f'<li><a href="{chunk_url(c["id"], depth)}">{esc(c["title"])}</a></li>'
            for c in entity["related_chunks"][:12])
        side.append(f'<div class="side-box"><h4>Related guides</h4><ul>{links}</ul></div>')
    if entity.get("sources"):
        links = "".join(
            f'<li>{_inline(s)}</li>' for s in entity["sources"][:10])
        side.append(f'<div class="side-box"><h4>Sources</h4><ul>{links}</ul></div>')
    if entity.get("aliases"):
        side.append('<div class="side-box"><h4>Also called</h4><p style="margin:0">'
                    + esc(", ".join(entity["aliases"])) + "</p></div>")

    tags = "".join(f'<span class="pill">{esc(t)}</span>' for t in entity.get("tags", [])[:12])

    confidence_note = ""
    if entity.get("confidence") == "low":
        confidence_note = ('<blockquote>Some figures on this page could not be verified '
                           'against a primary source. Treat them as indicative and check '
                           'the manufacturer before relying on them.</blockquote>')

    body = f"""<div class="wrap">
<div class="breadcrumb"><a href="{'../' * depth}index.html">Home</a> ›
  <a href="{'../' * depth}search.html">{esc(TYPE_LABELS.get(entity['type'], entity['type']))}</a> ›
  {esc(entity['name'])}</div>
<h1 class="page">{esc(entity['name'])}</h1>
<p class="page-sub">{esc(entity.get('summary'))}</p>
<div style="margin-bottom:22px">{pills(entity, depth)}{tags}</div>
<div class="two-col">
  <div class="prose">
    {art}
    {confidence_note}
    {pro_con}
    {formula}
    {specs}
    {notes}
  </div>
  <div>{''.join(side)}</div>
</div>
<p style="margin-top:34px"><code>{esc(entity['id'])}</code> — use this id with the
Discord bot or MCP tools.</p>
</div>"""
    return page(f"{entity['name']} — Combat Robot Database", body,
                description=entity.get("summary", ""), depth=depth)


def build_chunk_page(database, chunk):
    depth = 1
    refs = ""
    if chunk.get("entity_refs"):
        links = []
        for ref in chunk["entity_refs"]:
            target = database.get_entity(ref)
            if target:
                links.append(f'<li><a href="{entity_url(target["id"], depth)}">'
                             f'{esc(target["name"])}</a></li>')
        if links:
            refs = f'<div class="side-box"><h4>Related entries</h4><ul>{"".join(links)}</ul></div>'

    sources = ""
    if chunk.get("sources"):
        items = "".join(f"<li>{_inline(s)}</li>" for s in chunk["sources"][:12])
        sources = f'<div class="side-box"><h4>Sources</h4><ul>{items}</ul></div>'

    tags = "".join(f'<span class="pill">{esc(t)}</span>' for t in chunk.get("tags", [])[:10])
    wcs = "".join(f'<span class="pill accent">{esc(w)}</span>'
                  for w in chunk.get("weight_classes", []))

    body = f"""<div class="wrap">
<div class="breadcrumb"><a href="{'../' * depth}index.html">Home</a> ›
  <a href="{'../' * depth}guides.html">Guides</a> › {esc(chunk['title'])}</div>
<h1 class="page">{esc(chunk['title'])}</h1>
<p class="page-sub">{esc(chunk.get('section') or '')}</p>
<div style="margin-bottom:20px">{wcs}{tags}</div>
<div class="two-col">
  <div class="prose">{markdown(chunk['body_md'])}</div>
  <div>{refs}{sources}</div>
</div>
</div>"""
    return page(f"{chunk['title']} — Combat Robot Database", body,
                description=chunk["body_md"][:160], depth=depth)


def build_search():
    body = """<div class="wrap">
<h1 class="page" style="margin-top:34px">Search</h1>
<p class="page-sub">Search every entry and guide in the database. Runs entirely in your
browser — no server, no tracking.</p>
<input class="searchbox" id="q" type="search" placeholder="e.g. 2205 weapon motor, TPU armour, gyro dance, failsafe" autofocus>
<div class="filters">
  <select id="f-type"><option value="">All types</option></select>
  <select id="f-class"><option value="">All weight classes</option></select>
  <button id="f-clear">Clear</button>
</div>
<div class="count" id="count"></div>
<div id="results"></div>
</div>"""
    return page("Search — Combat Robot Database", body, active="search.html")


def build_calculators():
    body = """<div class="wrap">
<h1 class="page" style="margin-top:34px">Calculators</h1>
<p class="page-sub">The numbers that decide whether a design works. These run the same
formulas the Discord bot and MCP server use, so you get the same answers either way.</p>
<div id="calcs"></div>
</div>"""
    return page("Calculators — Combat Robot Database", body, active="calculators.html",
                description="Interactive combat robot calculators: tip speed, kinetic "
                            "energy, moment of inertia, spin-up, traction and more.")


def build_about(database, stats):
    meta = stats["meta"]
    topics = "".join(
        f'<tr><td>{esc(t["title"])}</td><td>{t["entity_count"]}</td>'
        f'<td>{t["chunk_count"]}</td></tr>' for t in stats["topics"])
    body = f"""<div class="wrap">
<h1 class="page" style="margin-top:34px">About this database</h1>
<div class="prose">
<p>This is a reference for people building 1&nbsp;lb combat robots — standard antweight
and the all-plastic antweight class. It was assembled by running parallel research agents
across public sources, normalising what they found into a single schema, and building a
searchable database from the result.</p>

<h2>How it was built</h2>
<p>Independent research agents each covered one domain — archetypes, weapon motors, drive
motors, electronics, batteries, materials, fabrication, the plastic ant class, design
maths, strategy, events and suppliers, and troubleshooting. Each wrote structured records
against a shared contract. A build step normalises, de-duplicates and cross-links those
records into SQLite with full-text search, then generates this site.</p>

<h2>What that means for accuracy</h2>
<p>Numbers here are compiled from public sources: vendor listings, community write-ups,
rulebooks and engineering references. Entries whose figures could not be verified against a
primary source are marked <span class="pill conf-low">unverified</span>. Prices and stock
change constantly. <strong>Before you cut material or enter an event, check the
manufacturer's own specification and your event's current published ruleset.</strong></p>

<h2>Safety</h2>
<p>Combat robots store real energy. A 1&nbsp;lb spinner can carry a few hundred joules —
enough to break bone. Use a weapon lock whenever the robot is powered outside an arena,
set and test your failsafe, fit a removable link, and never spin a weapon outside a
proper enclosure.</p>

<h2>Coverage</h2>
<table class="specs"><thead><tr><th>Research topic</th><th>Entries</th><th>Guides</th></tr></thead>
<tbody>{topics}</tbody></table>
<p>Built {esc(meta.get('built_at', '')[:19])} · {esc(meta.get('entity_count'))} entries ·
{esc(meta.get('chunk_count'))} guides · {esc(meta.get('chunk_word_count'))} words of prose.</p>

<h2>Using it from an LLM</h2>
<p>The repository ships an MCP server (<code>agent/mcp_server.py</code>) and a Discord bot
(<code>discord-bot/bot.py</code>). Both call the same query layer, so anything the site can
show, an agent can look up and compute with.</p>
</div>
</div>"""
    return page("About — Combat Robot Database", body,
                description="How the combat robot database was built and how accurate it is.")


# ----------------------------------------------------------------- main

def main():
    database = kb.KnowledgeBase()
    stats = database.stats()

    os.makedirs(os.path.join(WEB, "e"), exist_ok=True)
    os.makedirs(os.path.join(WEB, "g"), exist_ok=True)
    os.makedirs(os.path.join(WEB, "data"), exist_ok=True)

    def write(relative, content):
        path = os.path.join(WEB, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)

    write("index.html", build_index(database, stats))
    write("archetypes.html", build_archetypes(database))
    write("parts.html", build_parts(database))
    write("materials.html", build_materials(database))
    write("guides.html", build_guides(database))
    write("rules.html", build_rules(database))
    write("search.html", build_search())
    write("calculators.html", build_calculators())
    write("about.html", build_about(database, stats))

    entity_count = 0
    for row in database.conn.execute("SELECT id FROM entities").fetchall():
        entity = database.get_entity(row["id"])
        if entity:
            write(f"e/{entity['id']}.html", build_entity_page(database, entity))
            entity_count += 1

    chunk_count = 0
    for row in database.conn.execute("SELECT id FROM chunks").fetchall():
        chunk = database.get_chunk(row["id"])
        if chunk:
            write(f"g/{chunk['id']}.html", build_chunk_page(database, chunk))
            chunk_count += 1

    # The search page fetches this; keeping a copy under web/ makes the whole
    # directory self-contained for static hosting.
    shutil.copyfile(os.path.join(ROOT, "data", "index.json"),
                    os.path.join(WEB, "data", "index.json"))

    print(f"pages: {entity_count} entities, {chunk_count} guides, 9 top-level")
    print(f"site written to {WEB}")


if __name__ == "__main__":
    main()
