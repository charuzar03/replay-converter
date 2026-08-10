from __future__ import annotations

import argparse
import logging
import sys
from typing import List

from showdown_stats.exporter import write_battles_csv, write_events_csv, write_pokemon_csv
from showdown_stats.fetcher import ReplayFetcher
from showdown_stats.parser import BattleParser


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse Pokemon Showdown replay logs into battle event and per-Pokemon stats CSV files."
    )
    parser.add_argument("--url", action="append", default=[], help="Replay URL to fetch. May be passed multiple times.")
    parser.add_argument("--file", action="append", default=[], help="Local replay log or JSON file. May be passed multiple times.")
    parser.add_argument("--input", action="append", default=[], help="Text file containing replay URLs or local file paths.")
    parser.add_argument("--folder", action="append", default=[], help="Folder containing .log, .txt, or .json replay files.")
    parser.add_argument("--output", default="pokemon_stats.csv", help="Output CSV path for per-Pokemon stats.")
    parser.add_argument("--events", default="events.csv", help="Output CSV path for normalized raw event rows.")
    parser.add_argument("--battle-output", default="battle_summary.csv", help="Output CSV path for battle-level summaries.")
    parser.add_argument(
        "--paste",
        action="store_true",
        help="Paste replay URLs or file paths directly into the terminal instead of using --url/--file/--input/--folder.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging, including uncertain attribution warnings.")
    return parser


def read_pasted_block() -> str:
    print("Paste replay URLs or file paths below.")
    print("Put one per line. Blank lines are ignored.")
    print("When you are done, press Enter twice in a row.")
    lines: List[str] = []
    blank_streak = 0
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip():
            blank_streak += 1
            if blank_streak >= 2:
                break
            continue
        blank_streak = 0
        lines.append(line)
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    fetcher = ReplayFetcher()
    battle_parser = BattleParser(debug=args.debug)
    if args.paste or not any([args.url, args.file, args.input, args.folder]):
        pasted_text = read_pasted_block()
        parsed_entries = fetcher.parse_entries_from_text(pasted_text)
        if not parsed_entries:
            parser.error("No replay URLs or file paths were found in the pasted text.")
        replay_inputs = fetcher.load_pasted_text(pasted_text)
    else:
        replay_inputs = fetcher.load_many(
            urls=args.url,
            files=args.file,
            folders=args.folder,
            input_files=args.input,
        )

    all_events = []
    all_pokemon_rows = []
    battle_rows = []
    warning_count = 0

    for replay in replay_inputs:
        result = battle_parser.parse(
            replay.content,
            battle_id=replay.identifier,
            replay_url=replay.replay_url,
            metadata=replay.metadata or {},
        )
        all_events.extend(result.events)
        all_pokemon_rows.extend(result.pokemon_rows)
        battle_rows.append(result.battle_row)
        warning_count += len(result.warnings)
        for warning in result.warnings:
            logging.warning("[%s] %s", result.battle_id, warning)

    write_events_csv(args.events, all_events)
    write_pokemon_csv(args.output, all_pokemon_rows)
    write_battles_csv(args.battle_output, battle_rows)

    logging.info("Parsed %s replay(s).", len(replay_inputs))
    logging.info("Wrote %s event rows to %s", len(all_events), args.events)
    logging.info("Wrote %s Pokemon rows to %s", len(all_pokemon_rows), args.output)
    logging.info("Wrote %s battle summary rows to %s", len(battle_rows), args.battle_output)
    if warning_count:
        logging.info("Completed with %s parser warning(s).", warning_count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
