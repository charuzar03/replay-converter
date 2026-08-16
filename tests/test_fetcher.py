from __future__ import annotations

import unittest

from showdown_stats.fetcher import ReplayFetcher


class ReplayFetcherTests(unittest.TestCase):
    def test_google_redirect_url_is_unwrapped(self):
        wrapped = (
            "https://www.google.com/url?q=https://replay.pokemonshowdown.com/"
            "gen9draft-2600204129-6xr891qnbki1yoss9r5l948vsjyc4bfpw&sa=D"
        )
        normalized = ReplayFetcher._normalize_replay_url(wrapped)
        self.assertEqual(
            normalized,
            "https://replay.pokemonshowdown.com/gen9draft-2600204129-6xr891qnbki1yoss9r5l948vsjyc4bfpw",
        )

    def test_showdown_query_string_is_removed(self):
        normalized = ReplayFetcher._normalize_replay_url(
            "https://replay.pokemonshowdown.com/gen9draft-2270209672-h4ethbcxe69cw4zceiadoiulvtjbtf7pw?p2"
        )
        self.assertEqual(
            normalized,
            "https://replay.pokemonshowdown.com/gen9draft-2270209672-h4ethbcxe69cw4zceiadoiulvtjbtf7pw",
        )

    def test_html_urls_use_clean_battle_id_and_candidate_urls(self):
        url = "https://champsnatdex.dedyn.io/replays/gen9natdexchampionsdraft/26419_Charuzar_vs_caliber14.html"
        self.assertEqual(ReplayFetcher._battle_id_from_url(url), "26419_Charuzar_vs_caliber14")
        self.assertEqual(
            ReplayFetcher._candidate_urls(url),
            [
                "https://champsnatdex.dedyn.io/replays/gen9natdexchampionsdraft/26419_Charuzar_vs_caliber14.json",
                "https://champsnatdex.dedyn.io/replays/gen9natdexchampionsdraft/26419_Charuzar_vs_caliber14.log",
                url,
            ],
        )

    def test_html_detection(self):
        self.assertTrue(ReplayFetcher._looks_like_html("<html><head></head><body>Hello</body></html>"))
        self.assertFalse(ReplayFetcher._looks_like_html("|turn|1\n|win|Alice"))

    def test_protocol_detection(self):
        self.assertTrue(ReplayFetcher._looks_like_protocol_log("|player|p1|Alice|"))
        self.assertFalse(ReplayFetcher._looks_like_protocol_log("not a replay log"))

    def test_extracts_protocol_log_from_replay_html(self):
        html = """
<!DOCTYPE html>
<div class="battle"></div>
<script type="text/plain" class="battle-log-data">|player|p1|Charuzar|
|player|p2|caliber14|
|turn|1
|win|Charuzar</script>
        """
        log = ReplayFetcher._extract_protocol_log_from_html(html)
        self.assertEqual(
            log,
            "|player|p1|Charuzar|\n|player|p2|caliber14|\n|turn|1\n|win|Charuzar",
        )

    def test_parse_entries_from_text_with_multiple_links(self):
        text = """
https://replay.pokemonshowdown.com/gen9draft-2496872922
https://replay.pokemonshowdown.com/gen9draft-2505401901
https://replay.pokemonshowdown.com/gen9draft-2507590383
        """
        entries = ReplayFetcher.parse_entries_from_text(text)
        self.assertEqual(
            entries,
            [
                "https://replay.pokemonshowdown.com/gen9draft-2496872922",
                "https://replay.pokemonshowdown.com/gen9draft-2505401901",
                "https://replay.pokemonshowdown.com/gen9draft-2507590383",
            ],
        )

    def test_parse_entries_from_text_ignores_surrounding_text(self):
        text = """
can you make it parse these:
https://replay.pokemonshowdown.com/gen9draft-2506544253
https://replay.pokemonshowdown.com/gen9draft-2504780190-yxx3gbqhuhu4wp3tm34v464n166dhaypw
thanks
        """
        entries = ReplayFetcher.parse_entries_from_text(text)
        self.assertEqual(
            entries,
            [
                "https://replay.pokemonshowdown.com/gen9draft-2506544253",
                "https://replay.pokemonshowdown.com/gen9draft-2504780190-yxx3gbqhuhu4wp3tm34v464n166dhaypw",
            ],
        )


if __name__ == "__main__":
    unittest.main()
