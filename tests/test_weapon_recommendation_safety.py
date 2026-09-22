import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WeaponRecommendationSafetyTests(unittest.TestCase):
    def _load(self, name):
        with open(ROOT / "data" / "research" / name, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_generic_6a_esc_is_not_recommendable(self):
        data = self._load("plastic-antweight.json")
        esc = next(e for e in data["entities"] if e["id"] == "component-esc-brushless-weapon-6a")
        self.assertTrue(esc.get("reference_only"))
        self.assertEqual(esc.get("confidence"), "low")
        self.assertIn("NOT generally sufficient", esc.get("summary", ""))

    def test_plastic_motor_chunk_rejects_blanket_6a_and_loaded_rpm_rules(self):
        data = self._load("plastic-antweight.json")
        chunk = next(c for c in data["chunks"] if c["id"] == "chunk-plastic-antweight-weapon-motor-selection")
        body = chunk["body_md"]
        self.assertNotIn("6A-class is usually sufficient", body)
        self.assertIn("Do not invent a fixed", body)
        self.assertIn("20A", body)
        self.assertIn("35A", body)

    def test_horizontal_motor_guidance_is_geometry_driven(self):
        data = self._load("weapon-motors.json")
        chunk = next(c for c in data["chunks"] if c["id"] == "chunk-recommend-horizontal-bar")
        body = chunk["body_md"]
        self.assertNotIn("1300-1700kv winding on 4S is a common, solid choice", body)
        self.assertIn("weapon swept diameter", body)
        self.assertIn("battery voltage", body)
        self.assertIn("reduction ratio", body)

    def test_esc_guidance_requires_exact_current_evidence(self):
        data = self._load("weapon-motors.json")
        chunk = next(c for c in data["chunks"] if c["id"] == "chunk-esc-sizing")
        body = chunk["body_md"]
        self.assertIn("current requirement unknown", body)
        self.assertIn("9.9A", body)
        self.assertIn("35A", body)

    def test_discord_prompt_has_weapon_system_guardrails(self):
        bot = (ROOT / "discord-bot" / "bot.py").read_text(encoding="utf-8")
        self.assertIn("WEAPON-SYSTEM RECOMMENDATION RULES:", bot)
        self.assertIn("Do NOT invent a fixed loaded-RPM multiplier", bot)
        self.assertIn("never use a generic ~6A weapon-ESC class", bot)


if __name__ == "__main__":
    unittest.main()
