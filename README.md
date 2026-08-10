# Pokemon Showdown Replay Stats Parser

This project provides a production-oriented Python parser for Pokemon Showdown replay logs. It reads one or more replay URLs or local replay log files, interprets the pipe-delimited battle protocol, maintains battle state, and exports CSV tables that are easy to import into Google Sheets.

## Files

- [parse_showdown_stats.py](/C:/Users/charu/Documents/New%20project/parse_showdown_stats.py) is the CLI entry point.
- [showdown_stats/parser.py](/C:/Users/charu/Documents/New%20project/showdown_stats/parser.py) contains the stateful battle parser.
- [showdown_stats/fetcher.py](/C:/Users/charu/Documents/New%20project/showdown_stats/fetcher.py) loads replay data from URLs, files, folders, or batch input lists.
- [showdown_stats/exporter.py](/C:/Users/charu/Documents/New%20project/showdown_stats/exporter.py) writes the CSV outputs.
- [tests/test_parser.py](/C:/Users/charu/Documents/New%20project/tests/test_parser.py) contains regression-style parser tests with mock battle snippets.

## Installation

```bash
python -m pip install -r requirements.txt
```

## Usage

You can mix and match one or more inputs:

```bash
python parse_showdown_stats.py
python parse_showdown_stats.py --paste
python parse_showdown_stats.py --url "https://replay.pokemonshowdown.com/gen9ou-1234567890"
python parse_showdown_stats.py --file battle.log
python parse_showdown_stats.py --input replays.txt
python parse_showdown_stats.py --folder ./logs
python parse_showdown_stats.py --url "https://replay.pokemonshowdown.com/gen9ou-1234567890" --output stats.csv --events events.csv --battle-output battles.csv
```

### Simplest Way

If you want the easiest workflow, just run:

```bash
py -3 parse_showdown_stats.py
```

Then paste your replay links one per line, like this:

```text
https://replay.pokemonshowdown.com/gen9draft-2496872922
https://replay.pokemonshowdown.com/gen9draft-2505401901
https://replay.pokemonshowdown.com/gen9draft-2507590383
https://replay.pokemonshowdown.com/gen9draft-2506544253
https://replay.pokemonshowdown.com/gen9draft-2504780190-yxx3gbqhuhu4wp3tm34v464n166dhaypw
https://replay.pokemonshowdown.com/gen9draft-2503646891-7v038mt2m9jb2vm52ib5ehswbxh9jerpw
```

Blank lines in the pasted block are ignored. After the last link, press `Enter` twice in a row. The script will parse all of them.

### CLI Options

- `--paste`: Start paste mode explicitly. If you run the script with no input flags, paste mode starts automatically.
- `--url`: Replay URL to fetch. Repeatable.
- `--file`: Local replay log or replay JSON file. Repeatable.
- `--input`: Text file containing URLs or file paths, one per line.
- `--folder`: Folder containing `.log`, `.txt`, or `.json` replay files.
- `--output`: Per-Pokemon summary CSV path. Default: `pokemon_stats.csv`
- `--events`: Raw normalized event CSV path. Default: `events.csv`
- `--battle-output`: Battle-level summary CSV path. Default: `battle_summary.csv`
- `--debug`: Enables debug logging for uncertain or malformed lines.

## Output CSVs

### Raw Events CSV

One row per meaningful battle event. Columns:

- `battle_id`
- `replay_url`
- `turn`
- `event_type`
- `player`
- `source`
- `source_species`
- `target`
- `target_species`
- `move`
- `ability`
- `item`
- `amount`
- `old_hp`
- `new_hp`
- `hp_type`
- `cause`
- `cause_detail`
- `is_direct`
- `is_residual`
- `is_hazard`
- `is_recoil`
- `is_self_damage`
- `is_healing`
- `raw_line`

### Pokemon Summary CSV

One row per Pokemon per battle. Columns:

- `battle_id`
- `player`
- `pokemon_nickname`
- `species`
- `team_position`
- `result`
- `turns_active`
- `switches_in`
- `moves_used`
- `hits_landed`
- `hits_taken`
- `misses`
- `moves_dodged`
- `crits`
- `crits_taken`
- `super_effective_hits_taken`
- `resisted_hits_taken`
- `damage_dealt_pct`
- `direct_damage_dealt_pct`
- `indirect_damage_dealt_pct`
- `hazard_damage_dealt_pct`
- `residual_damage_dealt_pct`
- `damage_taken_pct`
- `direct_damage_taken_pct`
- `indirect_damage_taken_pct`
- `hazard_damage_taken_pct`
- `recoil_taken_pct`
- `healing_received_pct`
- `kos`
- `direct_kos`
- `indirect_kos`
- `deaths`
- `fainted_by`
- `status_inflicted`: total number of statuses inflicted
- `status_received`: total number of statuses received
- `hazards_set`: total number of hazard-setting events
- `hazards_removed`: total number of hazard-removal events
- `boosts_given`
- `boosts_received`
- `items_removed`
- `abilities_revealed`

### Battle Summary CSV

- `battle_id`
- `replay_url`
- `format`
- `player_1`
- `player_2`
- `winner`
- `turns`
- `date`

## Parser Design

The parser is intentionally stateful and conservative:

1. `ReplayFetcher` loads raw replay text or JSON replay payloads.
2. `BattleParser` reads each protocol line in order and updates battle state.
3. The parser emits normalized raw event rows as it goes.
4. Damage, healing, status, hazards, weather, terrain, delayed attacks, and faint attribution are tracked from state rather than from isolated regex matches.
5. At the end of each battle, the parser emits per-Pokemon and per-battle summary rows.

## Current Coverage

The parser includes dedicated logic for:

- Direct move damage and KOs
- Hazard setting, hazard damage, and hazard removal
- Poison, toxic poison, burn, and other residual sources where the log is explicit
- Leech Seed, Salt Cure, Curse, Nightmare, trapping residuals
- Recoil and self-damage
- Rocky Helmet and other item or ability punishment when the source is visible
- Wish and Future Sight style delayed effects
- Singles and doubles slot handling
- Spread moves and multi-hit moves
- Substitute, protective moves, switch/drag/replace events
- Ability and item reveals
- Terastallization and battle summary metadata
- Tera-only species edge cases such as `Ogerpon-Teal-Tera` being normalized back to the underlying mon
- Mega evolution and in-battle form changes updating the battle species identity when the replay reveals them

## Running Tests

```bash
python -m unittest discover -s tests -v
```

## Known Limitations

- Some Showdown mechanics are only partially visible in the replay log, so the parser will mark attribution as `unknown`, `self`, or `unattributed` instead of guessing.
- Zoroark Illusion, Transform, and some form changes can be tracked only when the replay explicitly reveals the real identity.
- Exact-HP battles and percent-HP battles are both supported, but mixed representations can still require manual audit in edge cases.
- `hits_landed` is best-effort and is strongest for direct damage, multi-hit, spread, and clear secondary-effect moves. Purely informational move success without an explicit follow-up event can still be undercounted.
- `hits_taken` counts direct damaging hits received. It does not include hazards, poison, burn, recoil, or other indirect damage.
- Court Change, Magic Bounce, and other hazard ownership rewrites are handled conservatively and may still need manual review for rare ordering edge cases.
