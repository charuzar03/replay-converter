from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
AUTOMATION = (ROOT / "web" / "automation.js").read_text(encoding="utf-8")


class MainAutomationUiTests(unittest.TestCase):
    def test_main_page_has_preview_and_iframe_submit_bridge(self):
        for expected in [
            'id="preview"',
            'id="submitBattle"',
            'id="replaceBattle"',
            'id="previewBattleRow"',
            'id="submitForm"',
            'target="submitFrame"',
            'name="payload"',
            'name="responseMode"',
            'id="submitFrame"',
            'window.addEventListener(\'message\'',
            'replay-converter-apps-script',
            "ReplayAutomation.buildSingleBattleAutomationPayload",
            "ReplayAutomation.buildBattleSubmissionPayload",
            "isTrustedAppsScriptOrigin",
            "host.endsWith(\".script.googleusercontent.com\")",
            "SUBMIT_TIMEOUT_MS",
            "No Apps Script response arrived.",
        ]:
            self.assertIn(expected, INDEX)
        self.assertNotIn("submitFrame.contentDocument", INDEX)
        self.assertNotIn("submitFrame.contentWindow.document", INDEX)
        self.assertIn("setTimeout", INDEX)

    def test_main_page_reuses_advanced_parser_for_preview(self):
        for expected in [
            "loadPyodide",
            'fetch("showdown_stats/"+name)',
            'fetch("web/browser_api.py")',
            "fetchReplayFromUrl",
            "parseAdvancedStatsForReplay",
        ]:
            self.assertIn(expected, INDEX + AUTOMATION)

    def test_automation_exports_submission_contract_helpers(self):
        for expected in [
            "function buildBattleSubmissionPayload",
            "replaceExisting:Boolean(replaceExisting)",
            "function parseAppsScriptResponseText",
            "buildBattleSubmissionPayload:buildBattleSubmissionPayload",
            "parseAppsScriptResponseText:parseAppsScriptResponseText",
        ]:
            self.assertIn(expected, AUTOMATION)


if __name__ == "__main__":
    unittest.main()
