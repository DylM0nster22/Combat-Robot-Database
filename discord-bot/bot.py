#!/usr/bin/env python3
"""Discord bot that answers combat robotics questions from the knowledge base.

An OpenAI-compatible LLM drives the conversation and calls into the same tool
layer the MCP server exposes (agent/kb.py), so the bot can use OpenRouter,
Agent Router, or another compatible gateway without changing the knowledge
base or tool code.

Setup:
    pip install -r discord-bot/requirements.txt
    export DISCORD_TOKEN=...                    # Discord bot token
    export OPENROUTER_API_KEY=...               # easiest default
    export LLM_MODEL=anthropic/claude-sonnet-4.6
    python3 discord-bot/bot.py

Usage in Discord:
    @BotName what weapon motor for a plastic ant vertical spinner?
    /ask       natural-language question (same agent, as a slash command)
    /search    raw knowledge base search
    /part      look up one component or archetype by name
    /calc      run an engineering calculation
    /matchup   archetype vs archetype
    /stats     what's in the database
"""

import asyncio
import json
import logging
import os
import sys
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent"))

import discord
import openai
from openai import OpenAI
from discord import app_commands

import kb
import mcp_server

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("combat-robot-bot")

BASE_URL = os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
API_KEY = (os.environ.get("LLM_API_KEY")
           or os.environ.get("OPENROUTER_API_KEY")
           or "not-needed")
MODEL = os.environ.get("LLM_MODEL", "anthropic/claude-sonnet-4.6")
MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "4000"))
MAX_TOOL_TURNS = int(os.environ.get("LLM_MAX_TOOL_TURNS", "10"))
DISCORD_LIMIT = 2000

SYSTEM_PROMPT = """You are the reasoning layer for a combat robotics database assistant.
You specialise in 1 lb antweight and plastic antweight combat robots.

IMPORTANT ARCHITECTURE:
- The SQLite database is an evidence store, NOT an expert system.
- Do not ask a retrieval tool to choose the answer for you.
- You decide what evidence is relevant, compare tradeoffs, perform the engineering
  reasoning, and write the final recommendation.
- Prefer `query_database` for substantive questions. Write your own read-only SQL,
  inspect the raw rows, and make the judgment yourself.
- Use `database_schema` if you need table/column details.
- Use `search_knowledge` only to discover unknown names/ids/terminology, then query
  or fetch the specific records you actually need.
- `get_entity` and `get_chunk` return stored evidence; they do not decide what is best.
- Use `calculate` for numeric engineering calculations rather than mental arithmetic.

CORE DATABASE MAP:
- entities: id, type, name, aliases(JSON), summary, weight_classes(JSON), tags(JSON),
  specs(JSON), pros(JSON), cons(JSON), notes, sources(JSON), confidence, topic_id,
  extra(JSON)
- chunks: id, title, section, body_md, entity_refs(JSON), weight_classes(JSON),
  tags(JSON), sources(JSON), topic_id, word_count
- entity_weight_classes(entity_id, weight_class): exact class filtering
- entity_tags(entity_id, tag)
- chunk_entity_refs(chunk_id, entity_id)
- topics and meta: coverage/build metadata
- entities_fts / chunks_fts: FTS5 search tables
SQLite JSON1 is available: use json_extract() and json_each() for specs/extra/arrays.

HOW TO REASON:
1. Translate the user's question into the actual engineering criteria.
2. Query enough candidate rows to compare those criteria directly. Do not just take
   the first search hit.
3. Prefer verified/high-confidence specs and primary-source-backed records when the
   evidence conflicts. For part recommendations, prefer exact product records where
   json_extract(extra,'$.reference_only') is not 1; reference-only records describe
   generic size classes/standards and are context, not candidate SKUs. A record with
   json_extract(extra,'$.catalog_entry_only')=1 is a real exact product but has only
   partially verified specs: use it for discovery, and never fill missing numbers from
   a similar model.
4. Separate stored facts from your engineering inference.
5. For "best" questions, define why one option fits the user's stated constraints;
   there is rarely a universal best part.
6. If an important spec is missing, say it is missing. Do not invent it. You may use
   general engineering knowledge only when clearly labeled and when the database
   cannot answer that part.
7. Avoid looping on nearly identical searches. Change the SQL/query when evidence is
   insufficient.

Useful SQL patterns:
- Exact class:
  SELECT e.* FROM entities e
  JOIN entity_weight_classes w ON w.entity_id=e.id
  WHERE w.weight_class='antweight' AND e.type='component';
- Numeric JSON spec:
  SELECT id,name,json_extract(specs,'$.weight_g') AS weight_g
  FROM entities WHERE type='component';
- Component category, exact products only:
  WHERE json_extract(extra,'$.category')='weapon-motor'
    AND COALESCE(json_extract(extra,'$.reference_only'),0) != 1
- Search discovery can be done with search_knowledge, then follow ids with SQL or
  get_entity/get_chunk.

Style for Discord:
- Lead with the actual conclusion, then give the evidence that produced it.
- Keep replies concise by default, but do not sacrifice necessary reasoning.
- Give real numbers and part names when the database contains them.
- Cite useful entity ids in backticks so users can inspect them.
- Mention uncertainty/confidence when it materially affects the recommendation.
- Safety matters for spinning weapons: mention weapon locks/failsafes/removable links
  when the question concerns powered testing or operation.
"""


def openai_tools():
    """Convert MCP tool definitions into OpenAI-compatible function tools."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["inputSchema"],
            },
        }
        for t in mcp_server.TOOLS
    ]


TOOLS = openai_tools()


def run_tool(name, args):
    try:
        return mcp_server.call_tool(name, args)
    except kb.KnowledgeBaseError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # a bad tool call should not kill the reply
        log.exception("tool %s failed", name)
        return {"error": f"{type(exc).__name__}: {exc}"}


def _blocking_agent_turn(client, question, author_name):
    """Run one complete OpenAI-compatible tool-calling exchange."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",
         "content": f"[Discord user {author_name} asks] {question}"},
    ]

    for _turn in range(MAX_TOOL_TURNS):
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            tools=TOOLS,
            tool_choice="auto",
            messages=messages,
        )

        message = response.choices[0].message
        refusal = getattr(message, "refusal", None)
        if refusal and not message.tool_calls:
            return ("I can't answer that one. Try rephrasing, or ask about a "
                    "specific part, archetype or calculation.")

        assistant_message = {
            "role": "assistant",
            "content": message.content or "",
        }

        if message.tool_calls:
            assistant_message["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in message.tool_calls
            ]

        messages.append(assistant_message)

        if not message.tool_calls:
            return (message.content or "").strip() or "I couldn't find an answer for that."

        for tool_call in message.tool_calls:
            name = tool_call.function.name
            raw_args = tool_call.function.arguments or "{}"
            try:
                args = json.loads(raw_args)
            except (json.JSONDecodeError, TypeError) as exc:
                output = {"error": f"Invalid tool arguments returned by model: {exc}"}
            else:
                log.info("tool call: %s %s", name, json.dumps(args)[:200])
                output = run_tool(name, args)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(output, ensure_ascii=False)[:60000],
            })

    # The model used the whole tool budget. Do not throw away the evidence it
    # already gathered: make one final completion with tools disabled and force
    # a best-effort answer from the retrieved context.
    messages.append({
        "role": "system",
        "content": (
            "Tool budget reached. Answer the user's original question NOW using the "
            "evidence already present in this conversation. Do not ask for another "
            "tool call. If evidence is incomplete, state the uncertainty briefly and "
            "give the best supported answer you can."
        ),
    })
    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=messages,
        )
        final_message = response.choices[0].message
        return (final_message.content or "").strip() or (
            "I found relevant database material, but the model returned an empty final answer."
        )
    except Exception:
        log.exception("final no-tools completion failed")
        return (
            "I found relevant database material but couldn't format the final reply. "
            "Try /search with the main part or design term from your question."
        )

def chunk_message(text, limit=DISCORD_LIMIT):
    """Split a reply into Discord-sized pieces without cutting mid-line."""
    text = text or ""
    if len(text) <= limit:
        return [text] if text else ["(no response)"]
    parts, current = [], ""
    for line in text.split("\n"):
        while len(line) > limit:      # a single very long line
            parts.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) + 1 > limit:
            parts.append(current.rstrip())
            current = ""
        current += line + "\n"
    if current.strip():
        parts.append(current.rstrip())
    return parts


class CombatRobotBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.llm = OpenAI(api_key=API_KEY, base_url=BASE_URL)
        self.kb = kb.KnowledgeBase(os.environ.get("COMBAT_ROBOT_DB", kb.DEFAULT_DB))

    async def setup_hook(self):
        await self.tree.sync()
        log.info("slash commands synced")

    async def on_ready(self):
        stats = self.kb.stats()["meta"]
        log.info("logged in as %s — %s entities, %s chunks loaded",
                 self.user, stats.get("entity_count"), stats.get("chunk_count"))
        await self.change_presence(activity=discord.Game(
            name=f"{stats.get('entity_count', '?')} robot parts | @me to ask"))

    async def ask(self, question, author_name):
        return await asyncio.to_thread(
            _blocking_agent_turn, self.llm, question, author_name)

    async def on_message(self, message):
        if message.author.bot:
            return
        is_dm = isinstance(message.channel, discord.DMChannel)
        if not is_dm and self.user not in message.mentions:
            return

        question = message.content.replace(f"<@{self.user.id}>", "").strip()
        if not question:
            await message.reply("Ask me about antweight or plastic ant design — "
                                "parts, archetypes, rules, or the maths.")
            return

        async with message.channel.typing():
            try:
                answer = await self.ask(question, message.author.display_name)
            except openai.APIStatusError as exc:
                log.exception("API error")
                answer = f"The model API returned an error ({exc.status_code}). Try again shortly."
            except Exception as exc:
                log.exception("unhandled error")
                answer = f"Something broke handling that: {type(exc).__name__}."

        for i, part in enumerate(chunk_message(answer)):
            if i == 0:
                await message.reply(part)
            else:
                await message.channel.send(part)


bot = CombatRobotBot()


@bot.tree.command(name="ask", description="Ask anything about combat robot design")
@app_commands.describe(question="e.g. what weapon motor for a plastic ant vertical spinner?")
async def slash_ask(interaction: discord.Interaction, question: str):
    await interaction.response.defer(thinking=True)
    try:
        answer = await bot.ask(question, interaction.user.display_name)
    except Exception as exc:
        log.exception("slash ask failed")
        answer = f"Error: {type(exc).__name__}"
    parts = chunk_message(answer)
    await interaction.followup.send(parts[0])
    for part in parts[1:]:
        await interaction.followup.send(part)


@bot.tree.command(name="search", description="Search the knowledge base directly")
@app_commands.describe(query="Search terms", weight_class="Optional weight class filter")
async def slash_search(interaction: discord.Interaction, query: str,
                       weight_class: str = None):
    await interaction.response.defer()
    results = bot.kb.search(query, weight_class=weight_class, limit=8)
    lines = [f"**Search:** {query}"]
    if results["entities"]:
        lines.append("\n**Entities**")
        for e in results["entities"]:
            lines.append(f"• `{e['id']}` — **{e['name']}** ({e['type']}) — {e['summary'][:120]}")
    if results["chunks"]:
        lines.append("\n**Guides**")
        for c in results["chunks"]:
            lines.append(f"• `{c['id']}` — {c['title']}")
    if not results["entities"] and not results["chunks"]:
        lines.append("_No matches._")
    await interaction.followup.send(chunk_message("\n".join(lines))[0])


@bot.tree.command(name="part", description="Look up one part, archetype or term by id or name")
@app_commands.describe(name="Entity id or exact name")
async def slash_part(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    entity = bot.kb.get_entity(name)
    if not entity:
        hits = bot.kb.search(name, kind="entities", limit=5)["entities"]
        suggestion = ("\nDid you mean: " + ", ".join(f"`{h['id']}`" for h in hits)) if hits else ""
        await interaction.followup.send(f"No entity called `{name}`.{suggestion}")
        return

    lines = [f"**{entity['name']}** — _{entity['type']}_", entity["summary"]]
    if entity.get("specs"):
        lines.append("\n**Specs**")
        lines += [f"• {k.replace('_', ' ')}: **{v}**"
                  for k, v in list(entity["specs"].items())[:14]]
    if entity.get("pros"):
        lines.append("\n**Pros:** " + "; ".join(entity["pros"][:4]))
    if entity.get("cons"):
        lines.append("**Cons:** " + "; ".join(entity["cons"][:4]))
    if entity.get("weight_classes"):
        lines.append("\n_Classes: " + ", ".join(entity["weight_classes"]) + "_")
    await interaction.followup.send(chunk_message("\n".join(lines))[0])


@bot.tree.command(name="calc", description="Run a combat robotics calculation")
@app_commands.describe(
    name="Calculation name",
    params='JSON params, e.g. {"rpm": 20000, "radius_mm": 45}')
async def slash_calc(interaction: discord.Interaction, name: str, params: str):
    await interaction.response.defer()
    func = kb.CALCULATORS.get(name)
    if not func:
        await interaction.followup.send(
            "Unknown calculation. Available:\n"
            + "\n".join(f"• `{n}`" for n in sorted(kb.CALCULATORS)))
        return
    try:
        parsed = json.loads(params)
    except json.JSONDecodeError as exc:
        await interaction.followup.send(f"Params must be JSON: {exc}")
        return
    try:
        result = func(**parsed)
    except TypeError as exc:
        await interaction.followup.send(f"Bad arguments: {exc}")
        return
    body = "\n".join(f"• {k.replace('_', ' ')}: **{v}**" for k, v in result.items())
    await interaction.followup.send(
        chunk_message(f"**{name}**\n{body}")[0])


@slash_calc.autocomplete("name")
async def calc_autocomplete(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=n, value=n)
            for n in sorted(kb.CALCULATORS) if current.lower() in n][:25]


@bot.tree.command(name="matchup", description="How two archetypes fare against each other")
@app_commands.describe(a="First archetype", b="Second archetype")
async def slash_matchup(interaction: discord.Interaction, a: str, b: str):
    await interaction.response.defer()
    result = bot.kb.matchup(a, b)
    lines = [f"**{a}** vs **{b}**", f"_{result['heuristic_verdict']}_"]
    for record in result["matchup_records"][:2]:
        lines.append(f"\n**{record['name']}**\n{record['summary']}")
        if record.get("notes"):
            lines.append(textwrap.shorten(record["notes"], 600, placeholder=" …"))
    if not result["matchup_records"]:
        for side, label in ((result["a"], a), (result["b"], b)):
            if side.get("countered_by"):
                lines.append(f"\n{label} is countered by: " + ", ".join(
                    str(x) for x in side["countered_by"][:5]))
    await interaction.followup.send(chunk_message("\n".join(lines))[0])


@bot.tree.command(name="stats", description="What's in the knowledge base")
async def slash_stats(interaction: discord.Interaction):
    await interaction.response.defer()
    stats = bot.kb.stats()
    meta = stats["meta"]
    lines = [
        "**Combat Robot Database**",
        f"{meta.get('entity_count')} entities · {meta.get('chunk_count')} guides "
        f"· {meta.get('chunk_word_count')} words",
        f"Built {meta.get('built_at', '?')[:10]}",
        "\n**By type**",
    ]
    lines += [f"• {t}: {n}" for t, n in list(stats["entities_by_type"].items())[:12]]
    lines.append("\n**By weight class**")
    lines += [f"• {c}: {n}" for c, n in list(stats["entities_by_weight_class"].items())[:8]]
    await interaction.followup.send(chunk_message("\n".join(lines))[0])


def main():
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        sys.exit("DISCORD_TOKEN is not set. See discord-bot/README.md")
    if BASE_URL == "https://openrouter.ai/api/v1" and API_KEY == "not-needed":
        sys.exit("OPENROUTER_API_KEY or LLM_API_KEY is not set.")
    log.info("LLM endpoint: %s", BASE_URL)
    log.info("LLM model: %s", MODEL)
    bot.run(token)


if __name__ == "__main__":
    main()
