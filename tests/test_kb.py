#!/usr/bin/env python3
"""Tests for the combat robot knowledge base.

    python3 -m unittest discover -s tests -v

The calculator tests check against values worked out by hand, because a
calculator that is confidently wrong is worse than no calculator: the Discord
bot and the website both quote these numbers as fact.
"""

import json
import math
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "agent"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import kb            # noqa: E402
import illustrations  # noqa: E402
import build_site    # noqa: E402
import build_db      # noqa: E402


class TestCalculators(unittest.TestCase):
    """Hand-checked reference values."""

    def test_tip_speed(self):
        # omega = 20000 * 2pi/60 = 2094.395 rad/s; v = omega * 0.045 = 94.25 m/s
        result = kb.tip_speed(20000, 45)
        self.assertAlmostEqual(result["tip_speed_m_s"], 94.25, places=1)
        self.assertAlmostEqual(result["tip_speed_mph"], 210.8, places=0)

    def test_moi_disc(self):
        # I = 1/2 * 0.120 kg * (0.045 m)^2 = 1.215e-4 kg m^2
        self.assertAlmostEqual(
            kb.moment_of_inertia("disc", 120, 90)["moi_kg_m2"], 1.215e-4, places=8)

    def test_moi_shapes_ordered(self):
        """For equal mass and size, a ring holds more inertia than a disc."""
        disc = kb.moment_of_inertia("disc", 100, 80)["moi_kg_m2"]
        ring = kb.moment_of_inertia("ring", 100, 80)["moi_kg_m2"]
        self.assertAlmostEqual(ring, 2 * disc, places=8)

    def test_moi_bar_about_end_is_four_times_centre(self):
        centre = kb.moment_of_inertia("bar", 100, 120)["moi_kg_m2"]
        end = kb.moment_of_inertia("bar_end", 100, 120)["moi_kg_m2"]
        self.assertAlmostEqual(end, 4 * centre, places=8)

    def test_moi_rejects_unknown_shape(self):
        self.assertIn("error", kb.moment_of_inertia("banana", 100, 80))

    def test_kinetic_energy(self):
        # KE = 0.5 * 1.215e-4 * 2094.395^2 = 266.5 J
        self.assertAlmostEqual(
            kb.kinetic_energy(1.215e-4, 20000)["energy_j"], 266.5, places=0)

    def test_kinetic_energy_scales_with_square_of_rpm(self):
        low = kb.kinetic_energy(1e-4, 10000)["energy_j"]
        high = kb.kinetic_energy(1e-4, 20000)["energy_j"]
        self.assertAlmostEqual(high / low, 4.0, places=2)

    def test_motor_constants_uses_exact_kt(self):
        """Kt must be the exact 9.5493/Kv, not the 8.27/Kv hobby shorthand."""
        result = kb.motor_constants(2000, 11.1)
        self.assertAlmostEqual(result["kt_nm_per_a"], 9.5493 / 2000, places=6)
        self.assertNotAlmostEqual(result["kt_nm_per_a"], 8.27 / 2000, places=6)
        self.assertEqual(result["no_load_rpm"], 22200)

    def test_motor_constants_stall(self):
        result = kb.motor_constants(2000, 12.0, resistance_ohm=0.1)
        self.assertAlmostEqual(result["stall_current_a"], 120.0, places=1)

    def test_motor_constants_rejects_zero_kv(self):
        self.assertIn("error", kb.motor_constants(0, 11.1))

    def test_spin_up_uses_same_kt_as_motor_constants(self):
        """The two calculators must not disagree about Kt."""
        spin = kb.spin_up_time(1e-4, 10000, 2000, 11.1, 30)
        const = kb.motor_constants(2000, 11.1)
        self.assertAlmostEqual(spin["kt_nm_per_a"], const["kt_nm_per_a"], places=6)

    def test_spin_up_plausible_magnitude(self):
        """A 1 lb-class weapon should spin up in seconds, not minutes."""
        seconds = kb.spin_up_time(1.215e-4, 20000, 2000, 11.1, 30)["spin_up_s"]
        self.assertTrue(0.1 < seconds < 30, f"implausible spin-up: {seconds}s")

    def test_spin_up_rejects_zero_kv(self):
        self.assertIn("error", kb.spin_up_time(1e-4, 10000, 0, 11.1, 30))

    def test_drive_speed(self):
        # 500 rpm on a 32 mm wheel: 500/60 * pi * 0.032 = 0.838 m/s
        self.assertAlmostEqual(kb.drive_speed(500, 32)["speed_m_s"], 0.84, places=2)

    def test_drive_speed_gear_ratio_divides(self):
        direct = kb.drive_speed(1000, 40, 1)["speed_m_s"]
        geared = kb.drive_speed(1000, 40, 2)["speed_m_s"]
        self.assertAlmostEqual(geared, direct / 2, delta=0.01)

    def test_traction_force(self):
        # 0.454 kg * 9.80665 * 1.0 = 4.45 N
        self.assertAlmostEqual(kb.traction_force(454, 1.0)["max_push_force_n"], 4.45, places=1)

    def test_bite_depth_inverse_in_tooth_count(self):
        one = kb.bite_depth(20000, 1, 1.5)["bite_depth_mm"]
        two = kb.bite_depth(20000, 2, 1.5)["bite_depth_mm"]
        self.assertAlmostEqual(two, one / 2, places=3)

    def test_bite_depth_rejects_zero_rpm(self):
        self.assertIn("error", kb.bite_depth(0, 2, 1.5))

    def test_gyro_torque(self):
        # I * omega_w * omega_t = 1.215e-4 * 2094.395 * pi = 0.799 N m
        result = kb.gyro_torque(1.215e-4, 20000, 180)
        self.assertAlmostEqual(result["precession_torque_nm"], 0.799, places=2)

    def test_battery_check_flags_marginal_pack(self):
        weak = kb.battery_check(180, 25, 2, average_draw_a=20)
        self.assertIn("marginal", weak["verdict"])
        strong = kb.battery_check(450, 75, 3, average_draw_a=10)
        self.assertEqual(strong["verdict"], "adequate")

    def test_battery_check_energy(self):
        # 0.45 Ah * 11.1 V = 5.0 Wh
        self.assertAlmostEqual(kb.battery_check(450, 75, 3)["energy_wh"], 5.0, places=1)

    def test_weight_budget_sums_to_limit(self):
        result = kb.weight_budget(454.0)
        self.assertAlmostEqual(result["allocated_g"], 454.0, delta=0.5)
        self.assertIsNone(result["warning"])

    def test_weight_budget_warns_on_bad_allocation(self):
        result = kb.weight_budget(454.0, {"weapon": 50, "drive": 30})
        self.assertIsNotNone(result["warning"])

    def test_every_calculator_is_callable_with_defaults(self):
        """CALCULATORS is the registry the MCP server and bot expose."""
        self.assertEqual(len(kb.CALCULATORS), 11)
        for name, func in kb.CALCULATORS.items():
            self.assertTrue(callable(func), name)


class TestFTSSanitisation(unittest.TestCase):
    """User input reaches FTS5 MATCH directly, so it must never be a syntax error."""

    def test_strips_operators(self):
        for text in ['2205 motor (best?)', 'AND OR NOT', 'a"b"c', '*', 'foo-bar',
                     'what about "quotes" AND (parens)?', '']:
            query = kb._fts_query(text)
            self.assertNotIn("(", query)
            self.assertFalse(query.endswith("OR"))

    def test_empty_input_yields_empty_query(self):
        self.assertEqual(kb._fts_query(""), "")
        self.assertEqual(kb._fts_query("!!!"), "")

    def test_single_character_still_searches(self):
        self.assertTrue(kb._fts_query("a"))


class TestNormalisation(unittest.TestCase):
    def test_weight_class_aliases_repaired(self):
        report = build_db.Report()
        self.assertEqual(
            build_db.normalize_weight_classes(["Plastic Antweight", "1lb", "ANTWEIGHT"],
                                              report, "t"),
            ["plastic-antweight", "antweight"])

    def test_unknown_weight_class_warns_not_crashes(self):
        report = build_db.Report()
        build_db.normalize_weight_classes(["ultraweight"], report, "t")
        self.assertTrue(report.warnings)

    def test_as_list_accepts_a_bare_string(self):
        self.assertEqual(build_db.as_list("one"), ["one"])
        self.assertEqual(build_db.as_list(["a", "b"]), ["a", "b"])
        self.assertEqual(build_db.as_list(None), [])

    def test_specs_coerce_numeric_strings(self):
        report = build_db.Report()
        specs = build_db.normalize_specs(
            {"weight_g": "42", "kv": "2300.5", "range": "1000-3000"}, report, "t")
        self.assertEqual(specs["weight_g"], 42)
        self.assertEqual(specs["kv"], 2300.5)
        self.assertEqual(specs["range"], "1000-3000")   # ranges stay text

    def test_entity_without_type_is_filed_not_dropped(self):
        report = build_db.Report()
        entity = build_db.normalize_entity(
            {"id": "x-1", "name": "Thing", "summary": "s"}, "topic", report)
        self.assertIsNotNone(entity)
        self.assertEqual(entity["type"], "term")

    def test_entity_without_id_or_name_is_dropped(self):
        report = build_db.Report()
        self.assertIsNone(build_db.normalize_entity({"summary": "s"}, "topic", report))
        self.assertTrue(report.errors)

    def test_merge_prefers_longer_prose_and_keeps_first_specs(self):
        report = build_db.Report()
        a = build_db.normalize_entity(
            {"id": "m", "type": "component", "name": "M", "summary": "short",
             "specs": {"weight_g": 10}, "tags": ["x"]}, "t1", report)
        b = build_db.normalize_entity(
            {"id": "m", "type": "component", "name": "M",
             "summary": "a considerably longer and more complete summary",
             "specs": {"weight_g": 99, "kv": 2000}, "tags": ["y"]}, "t2", report)
        build_db.merge_entities(a, b, report, "f.json")
        self.assertIn("longer", a["summary"])
        self.assertEqual(a["specs"]["weight_g"], 10)   # first file wins
        self.assertEqual(a["specs"]["kv"], 2000)       # new key adopted
        self.assertEqual(sorted(a["tags"]), ["x", "y"])


class TestMarkdown(unittest.TestCase):
    def test_escapes_html_in_content(self):
        out = build_site.markdown("A <script>alert(1)</script> tag")
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_headings_start_at_h2(self):
        self.assertIn("<h2>Title</h2>", build_site.markdown("# Title"))

    def test_lists_and_tables(self):
        self.assertIn("<li>one</li>", build_site.markdown("- one\n- two"))
        table = build_site.markdown("| a | b |\n| --- | --- |\n| 1 | 2 |")
        self.assertIn("<th>a</th>", table)
        self.assertIn("<td>1</td>", table)

    def test_inline_formatting(self):
        out = build_site.markdown("**bold** and `code`")
        self.assertIn("<strong>bold</strong>", out)
        self.assertIn("<code>code</code>", out)

    def test_empty_input(self):
        self.assertEqual(build_site.markdown(""), "")
        self.assertEqual(build_site.markdown(None), "")


class TestIllustrations(unittest.TestCase):
    def test_all_archetype_art_is_valid_svg(self):
        for name, svg in illustrations.all_art().items():
            self.assertTrue(svg.startswith("<svg"), name)
            self.assertTrue(svg.rstrip().endswith("</svg>"), name)
            self.assertIn("<title", svg, name)

    def test_specific_form_beats_orientation_modifier(self):
        """A drum labelled 'undercutter' should still get the drum drawing."""
        svg = illustrations.art_for("archetype-drum", "Drum Spinner (Undercutter)")
        self.assertIn("Drum spinner", svg)

    def test_name_beats_noisy_tags(self):
        svg = illustrations.art_for("archetype-eggbeater", "Egg-beater",
                                    ["undercutter", "horizontal"])
        self.assertIn("Eggbeater", svg)

    def test_unknown_entity_gets_no_art(self):
        self.assertIsNone(illustrations.art_for("component-xt30", "XT30 connector"))


class TestMCPServer(unittest.TestCase):
    """Drive the server over real stdio JSON-RPC, as a client would."""

    @classmethod
    def setUpClass(cls):
        cls.db_exists = os.path.exists(kb.DEFAULT_DB)

    def _rpc(self, requests):
        if not self.db_exists:
            self.skipTest("database not built")
        payload = "\n".join(json.dumps(r) for r in requests) + "\n"
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "agent", "mcp_server.py")],
            input=payload, capture_output=True, text=True, timeout=60)
        return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]

    def test_initialize_and_tools_list(self):
        replies = self._rpc([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05", "capabilities": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ])
        self.assertEqual(replies[0]["result"]["serverInfo"]["name"], "combat-robot-database")
        tools = replies[1]["result"]["tools"]
        self.assertEqual(len(tools), 9)
        for tool in tools:
            self.assertIn("name", tool)
            self.assertIn("description", tool)
            self.assertEqual(tool["inputSchema"]["type"], "object")

    def test_notification_produces_no_reply(self):
        replies = self._rpc([
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 9, "method": "tools/list"},
        ])
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0]["id"], 9)

    def test_unknown_method_returns_error(self):
        replies = self._rpc([{"jsonrpc": "2.0", "id": 5, "method": "nope/nope"}])
        self.assertIn("error", replies[0])

    def test_calculate_tool_roundtrip(self):
        replies = self._rpc([{
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "calculate",
                       "arguments": {"name": "tip_speed",
                                     "params": {"rpm": 20000, "radius_mm": 45}}}}])
        result = json.loads(replies[0]["result"]["content"][0]["text"])
        self.assertAlmostEqual(result["tip_speed_m_s"], 94.25, places=1)

    def test_bad_tool_call_is_flagged_not_fatal(self):
        replies = self._rpc([{
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "no_such_tool", "arguments": {}}}])
        self.assertTrue(replies[0]["result"]["isError"])


class TestBuiltDatabase(unittest.TestCase):
    """Sanity checks against whatever has actually been built."""

    def setUp(self):
        if not os.path.exists(kb.DEFAULT_DB):
            self.skipTest("database not built; run scripts/build_db.py")
        self.db = kb.KnowledgeBase()

    def tearDown(self):
        if hasattr(self, "db"):
            self.db.close()

    def test_has_content(self):
        stats = self.db.stats()
        self.assertGreater(int(stats["meta"]["entity_count"]), 50)
        self.assertGreater(int(stats["meta"]["chunk_count"]), 20)

    def test_focus_is_antweight(self):
        """The database is meant to be antweight-first."""
        by_class = self.db.stats()["entities_by_weight_class"]
        ant = by_class.get("antweight", 0) + by_class.get("plastic-antweight", 0)
        self.assertGreater(ant, sum(by_class.values()) * 0.5,
                           "antweight coverage should dominate")

    def test_search_returns_results(self):
        self.assertGreater(self.db.search("motor", limit=5)["total"], 0)

    def test_search_survives_hostile_input(self):
        for text in ['"', '*', 'a AND OR b', "'; DROP TABLE entities;--", "((("]:
            self.db.search(text, limit=3)   # must not raise

    def test_every_entity_has_required_fields(self):
        rows = self.db.conn.execute("SELECT id, type, name FROM entities").fetchall()
        for row in rows:
            self.assertTrue(row["id"] and row["type"] and row["name"])

    def test_entity_ids_are_unique_and_slug_shaped(self):
        rows = self.db.conn.execute("SELECT id FROM entities").fetchall()
        ids = [r["id"] for r in rows]
        self.assertEqual(len(ids), len(set(ids)))
        for entity_id in ids:
            self.assertRegex(entity_id, r"^[a-z0-9-]+$")

    def test_chunk_references_all_resolve(self):
        """Cross-links are resolved at build time; none should dangle."""
        dangling = self.db.conn.execute(
            "SELECT COUNT(*) FROM chunk_entity_refs r "
            "LEFT JOIN entities e ON e.id = r.entity_id WHERE e.id IS NULL").fetchone()[0]
        self.assertEqual(dangling, 0)

    def test_get_entity_by_name_as_well_as_id(self):
        row = self.db.conn.execute("SELECT id, name FROM entities LIMIT 1").fetchone()
        self.assertIsNotNone(self.db.get_entity(row["id"]))
        self.assertIsNotNone(self.db.get_entity(row["name"]))

    def test_get_entity_resolves_bare_slug_and_alias(self):
        """Cross-references and LLMs pass bare slugs, not prefixed ids."""
        row = self.db.conn.execute(
            "SELECT id FROM entities WHERE id LIKE 'archetype-%' LIMIT 1").fetchone()
        if not row:
            self.skipTest("no archetypes in database")
        prefixed = row["id"]
        bare = prefixed[len("archetype-"):]
        found = self.db.get_entity(bare)
        self.assertIsNotNone(found, f"bare slug {bare!r} did not resolve")
        self.assertEqual(found["id"], prefixed)

    def test_get_entity_handles_empty_and_missing(self):
        self.assertIsNone(self.db.get_entity(""))
        self.assertIsNone(self.db.get_entity(None))
        self.assertIsNone(self.db.get_entity("definitely-not-an-entity-xyz"))

    def test_archetype_counters_resolve_to_real_entities(self):
        """A counters list full of unresolvable names makes the site's
        relationship links useless, so most of them should resolve."""
        rows = self.db.conn.execute(
            "SELECT id FROM entities WHERE type = 'archetype'").fetchall()
        if not rows:
            self.skipTest("no archetypes in database")
        total = resolved = 0
        for row in rows:
            entity = self.db.get_entity(row["id"]) or {}
            for value in (entity.get("counters") or []) + (entity.get("countered_by") or []):
                total += 1
                if self.db.get_entity(str(value)):
                    resolved += 1
        if total:
            self.assertGreater(resolved / total, 0.8,
                               f"only {resolved}/{total} archetype references resolve")

    def test_build_guide_returns_all_sections(self):
        guide = self.db.build_guide("antweight")
        for key in ("drive_motors", "weapon_motors", "batteries", "guidance"):
            self.assertIn(key, guide)


if __name__ == "__main__":
    unittest.main(verbosity=2)
