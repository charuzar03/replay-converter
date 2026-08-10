# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A Python CLI that parses Pokemon Showdown replay logs (the pipe-delimited `|event|arg1|arg2|...` protocol) into CSV files suitable for import into Google Sheets. It fetches replays by URL, local file, folder, or pasted text, replays the protocol line-by-line against an in-memory battle state machine, and exports three CSVs: raw normalized events, per-Pokemon-per-battle summaries, and per-battle summaries.

## Commands

Install dependencies:
```bash
python -m pip install -r requirements.txt
```

Run the parser (defaults to interactive paste mode if no input flags are given):
```bash
python parse_showdown_stats.py --url "https://replay.pokemonshowdown.com/gen9ou-1234567890"
python parse_showdown_stats.py --file battle.log
python parse_showdown_stats.py --folder ./logs
python parse_showdown_stats.py --input replays.txt
```
Useful flags: `--output` (Pokemon CSV, default `pokemon_stats.csv`), `--events` (default `events.csv`), `--battle-output` (default `battle_summary.csv`), `--debug` (enables debug logging including uncertain-attribution warnings).

Run all tests:
```bash
python -m unittest discover -s tests -v
```

Run a single test file or case:
```bash
python -m unittest tests.test_parser -v
python -m unittest tests.test_parser.TestClassName.test_method_name -v
```

There is no lint/type-check/build tooling configured in this repo.

## Architecture

Pipeline: `ReplayFetcher` → `BattleParser` → `showdown_stats/exporter.py`, orchestrated by `parse_showdown_stats.py` (CLI entry point).

- **`showdown_stats/fetcher.py`** (`ReplayFetcher`): turns URLs, local `.log`/`.txt`/`.json` files, folders, or pasted text blocks into a list of `ReplayInput` (raw protocol text + battle id + replay url + metadata). Handles Showdown JSON replay payloads (extracts the `log` field), Google redirect URLs, and tries `.json`/`.log`/bare URL variants when fetching. No network calls are exercised in unit tests — network paths are marked `pragma: no cover`.
- **`showdown_stats/parser.py`** (`BattleParser`): the core state machine and by far the largest module (~1500 lines). `parse()` splits replay text into lines, dispatches each `|tag|args...` line to a `_handle_<tag>` method (e.g. `_handle__damage`, `_handle_move`, `_handle__sidestart`), and mutates a `BattleState` (defined in `models.py`) containing per-side and per-Pokemon state. Key responsibilities live in private helpers rather than in the `_handle_*` methods themselves:
  - Attribution inference (`_infer_hp_change_attribution`, `_build_attribution`, `_infer_status_source`, `_infer_contact_punish_source`) decides *why* HP changed or a status was applied (direct hit, hazard, residual, recoil, self-damage, item/ability punishment, unknown) — this is the "conservative, state-driven not regex-driven" design called out in the README.
  - Entity/slot resolution (`_resolve_pokemon_for_switch`, `_resolve_active_mon_from_entity`, `_resolve_pokemon_fallback`, `_find_side_pokemon`) maps protocol tokens like `p1a: Nickname` to a stable internal `mon_id`, handling switches, doubles slots, Illusion/form-change edge cases, and Tera/Mega identity updates.
  - At the end of `parse()`, `_build_pokemon_rows()` folds accumulated per-Pokemon counters (`PokemonSummary` in `models.py`) into `PokemonSummaryRow` output rows.
  - Emits `EventRow`s incrementally via `_emit_event` during parsing (one row per meaningful event), rather than after the fact.
- **`showdown_stats/models.py`**: plain dataclasses only — no behavior. `BattleState`/`SideState`/`PokemonState`/`PokemonSummary` are the mutable parse-time state; `EventRow`/`PokemonSummaryRow`/`BattleSummaryRow` are the CSV output rows (each defines its own `columns()` and `to_csv_row()`, which is what `exporter.py` writes against).
- **`showdown_stats/exporter.py`**: thin CSV writers, one per output table, using each row dataclass's `columns()`/`to_csv_row()`. Wraps `PermissionError` (e.g. CSV open in Excel) with a clearer message.
- **`parse_showdown_stats.py`**: argparse CLI, paste-mode input loop, wires fetcher → parser → exporter, aggregates events/pokemon rows/battle rows across multiple replays into single CSV runs.

### Attribution model

Damage/healing/status/KOs are tracked as boolean flags on `EventRow`/`DamageAttribution` (`is_direct`, `is_residual`, `is_hazard`, `is_recoil`, `is_self_damage`, `is_healing`) plus a `cause`/`cause_detail` pair, rather than a single enum — an event can need multiple of these to disambiguate percent columns in the Pokemon summary CSV (e.g. `direct_damage_dealt_pct` vs `hazard_damage_dealt_pct` vs `residual_damage_dealt_pct`). When the parser can't determine a source it marks it `unknown`/`self`/`unattributed` instead of guessing — see README "Known Limitations" for the specific mechanics (Illusion, Transform, mixed exact/percent HP battles, Court Change/Magic Bounce hazard ownership) that are handled conservatively.

### Tests

`tests/test_parser.py` and `tests/test_fetcher.py` are regression-style tests built from small hand-written replay log snippets (not full replays), asserting on the resulting `EventRow`/`PokemonSummaryRow`/`BattleSummaryRow` output. When adding parser coverage for a new mechanic, follow this pattern: construct a minimal multi-line protocol snippet, run it through `BattleParser().parse(...)`, and assert on specific output row fields/flags.
