from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from .models import BattleSummaryRow, EventRow, PokemonSummaryRow


def _open_csv_output(path: str):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        return output.open("w", newline="", encoding="utf-8")
    except PermissionError as exc:
        raise RuntimeError(
            f"Could not write to '{output}'. "
            "If the CSV is open in Excel or another spreadsheet app, close it and run the command again. "
            "You can also choose a different filename with --output, --events, or --battle-output."
        ) from exc


def write_events_csv(path: str, rows: Iterable[EventRow]) -> None:
    rows = list(rows)
    with _open_csv_output(path) as handle:
        writer = csv.DictWriter(handle, fieldnames=EventRow.columns())
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_csv_row())


def write_pokemon_csv(path: str, rows: Iterable[PokemonSummaryRow]) -> None:
    rows = list(rows)
    with _open_csv_output(path) as handle:
        writer = csv.DictWriter(handle, fieldnames=PokemonSummaryRow.columns())
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_csv_row())


def write_battles_csv(path: str, rows: Iterable[BattleSummaryRow]) -> None:
    rows = list(rows)
    with _open_csv_output(path) as handle:
        writer = csv.DictWriter(handle, fieldnames=BattleSummaryRow.columns())
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_csv_row())
