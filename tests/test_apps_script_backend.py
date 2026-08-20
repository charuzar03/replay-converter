from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE = (ROOT / "apps-script" / "Code.js").read_text(encoding="utf-8")
MANIFEST = json.loads((ROOT / "apps-script" / "appsscript.json").read_text(encoding="utf-8"))


class AppsScriptBackendTests(unittest.TestCase):
    def test_manifest_uses_v8_runtime(self):
        self.assertEqual(MANIFEST["runtimeVersion"], "V8")
        self.assertEqual(MANIFEST["timeZone"], "America/Toronto")

    def test_backend_exposes_form_post_entrypoint(self):
        self.assertIn("function doPost(event)", CODE)
        self.assertIn("event.parameter.payload", CODE)
        self.assertIn('event.parameter.responseMode === "iframe"', CODE)
        self.assertIn("function iframeResponse(payload)", CODE)
        self.assertIn("ContentService.MimeType.JSON", CODE)
        self.assertIn('source:\\"replay-converter-apps-script\\"', CODE)
        self.assertIn("parent.postMessage", CODE)
        self.assertIn("top.postMessage", CODE)
        self.assertIn("setTimeout(send,500)", CODE)
        self.assertIn("setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)", CODE)

    def test_backend_validates_submission_contract(self):
        for required in [
            "basicBattleRow",
            "payload.basicBattleRow[4]",
            "advancedStats.battleId",
            "advancedStats.pokemonRows",
            "replaceExisting",
        ]:
            self.assertIn(required, CODE)

    def test_duplicate_contract_matches_spec(self):
        self.assertRegex(CODE, re.compile(r"findFirstValueInColumn_\(basicSheet,\s*5,\s*replayUrl\)"))
        self.assertRegex(CODE, re.compile(r"findAllValuesInColumn_\(advancedSheet,\s*1,\s*battleId\)"))
        self.assertIn('status: "duplicate"', CODE)
        self.assertIn("removeDuplicateRows_", CODE)

    def test_advanced_columns_match_parser_output(self):
        match = re.search(r"var ADVANCED_COLUMNS = \[([\s\S]*?)\];", CODE)
        self.assertIsNotNone(match)
        columns = re.findall(r'"([^"]+)"', match.group(1))
        expected = [
            "battle_id",
            "player",
            "pokemon_nickname",
            "species",
            "team_position",
            "result",
            "turns_active",
            "switches_in",
            "moves_used",
            "hits_landed",
            "hits_taken",
            "misses",
            "moves_dodged",
            "crits",
            "crits_taken",
            "super_effective_hits_taken",
            "resisted_hits_taken",
            "damage_dealt_pct",
            "direct_damage_dealt_pct",
            "indirect_damage_dealt_pct",
            "hazard_damage_dealt_pct",
            "residual_damage_dealt_pct",
            "damage_taken_pct",
            "direct_damage_taken_pct",
            "indirect_damage_taken_pct",
            "hazard_damage_taken_pct",
            "recoil_taken_pct",
            "healing_received_pct",
            "kos",
            "direct_kos",
            "indirect_kos",
            "deaths",
            "fainted_by",
            "status_inflicted",
            "status_received",
            "hazards_set",
            "hazards_removed",
            "boosts_given",
            "boosts_received",
            "items_removed",
            "abilities_revealed",
        ]
        self.assertEqual(columns, expected)


if __name__ == "__main__":
    unittest.main()
