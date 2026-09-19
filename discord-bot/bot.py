#!/usr/bin/env python3
"""Discord bot that answers combat robotics questions from the knowledge base.

Claude drives the conversation and calls into the same tool layer the MCP
server exposes (agent/kb.py), so the bot can only answer from researched data
and real calculations rather than from the model's own recollection.

Setup:
    pip install -r discord-bot/requirements.txt
    export DISCORD_TOKEN=...          # Discord bot token
    export ANTHROPIC_API_KEY=...      # or an `ant auth login` profile
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

import anthropic
import discord
from discord import app_commands

import kb
import mcp_server

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("combat-robot-bot")

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5")
# Chat Q&A does not need the default `high`; medium keeps replies quick and
# cheap. Raise it with CLAUDE_EFFORT=high for deeper design questions.
EFFORT = os.environ.get("CLAUDE_EFFORT", "medium")
MAX_TOOL_TURNS = 8
DISCORD_LIMIT = 2000

SYSTEM_PROMPT = """You are a combat robotics expert assistant for a Discord server, \
specialising in 1 lb antweight and plastic antweight (3D-printed) combat robots.

You have tools onto a researched knowledge base. Use them — do not answer from memory.
Search first, then fetch the specific entity or chunk you need. For any numeric question
(tip speed, kinetic energy, spin-up, gear ratios, traction, battery sizing, weight budget)
call the `calculate` tool rather than doing arithmetic in your head.

Style for Discord:
- Lead with the direct answer in the first sentence.
- Keep replies under about 1500 characters unless asked for detail. Use short bullets.
- Give real numbers and real part names. Cite the entity id in backticks when it helps
  someone look it up, e.g. `motor-repeat-2205`.
- If the knowledge base does not cover something, say so plainly and give your best
  general engineering answer clearly labelled as such. Never invent a part number,
  price, rule, or event.
- Safety matters: these are spinning weapons. Mention weapon locks, failsafes and
  removable links when the question touches on testing or running a bot.
"""


def anthropic_tools():
    """Convert the MCP tool definitions into Anthropic tool format."""
    return [
        {"name": t["name"], "description": t["description"],
         "input_schema": t["inputSchema"]}
        for t in mcp_server.TOOLS
    ]


TOOLS = anthropic_tools()


def run_tool(name, args):
    try:
        return mcp_server.call_tool(name, args)
    except kb.KnowledgeBaseError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # a bad tool call should not kill the reply
        log.exception("tool %s failed", name)
        return {"error": f"{type(exc).__name__}: {exc}"}


def _blocking_agent_turn(client, question, author_name):
    """One full agentic exchange. Runs in a thread; returns the reply text.

    A manual loop rather than the SDK tool runner: the runner is beta, and the
    explicit loop lets us cap tool turns so a confused model can't spend the
    channel's patience (or the API budget) in a runaway loop.
    """
    messages = [{"role": "user",
                 "content": f"[Discord user {author_name} asks] {question}"}]

    for turn in range(MAX_TOOL_TURNS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            output_config={"effort": EFFORT},
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "refusal":
            return ("I can't answer that one. Try rephrasing, or ask about a "
                    "specific part, archetype or calculation.")

        if response.stop_reason != "tool_use":
            text = "\n".join(b.text for b in response.content if b.type == "text")
            return text.strip() or "I couldn't find an answer for that."

        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            log.info("tool call: %s %s", block.name, json.dumps(block.input)[:200])
            output = run_tool(block.name, block.input)
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(output, ensure_ascii=False)[:60000],
            })
        messages.append({"role": "user", "content": results})

    return ("I looked through the database but couldn't converge on an answer "
            "in a reasonable number of steps. Try asking something narrower.")


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
        self.anthropic = anthropic.Anthropic()
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
            _blocking_agent_turn, self.anthropic, question, author_name)

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
            except anthropic.APIStatusError as exc:
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
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        log.warning("No ANTHROPIC_API_KEY set; relying on an `ant auth login` profile.")
    bot.run(token)


if __name__ == "__main__":
    main()
