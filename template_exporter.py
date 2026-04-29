"""Template-based Excel exporter for enhanced Daily Trading outputs."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
from typing import Any

from openpyxl import load_workbook

BLOCK_HEIGHT = 6
ROW_OFFSETS = {
    "match_time": 0,
    "league": 0,
    "team_name": 0,
    "m_marker": 1,
    "rx_label": 0,
    "time_first_handicap": 1,
    "league_handicap": 1,
    "rx_value": 1,
    "time_first_odds": 2,
    "league_odds": 2,
    "ex_label": 2,
    "time_second_handicap": 3,
    "score_compact": 3,
    "ex_value": 3,
    "time_second_odds": 4,
}
COLS = {
    "match_time": "A",
    "league": "B",
    "team_name": "C",
    "m_marker": "C",
    "rx_label": "F",
    "time_first_handicap": "A",
    "league_handicap": "B",
    "rx_value": "F",
    "time_first_odds": "A",
    "league_odds": "B",
    "ex_label": "F",
    "time_second_handicap": "A",
    "score_compact": "C",
    "ex_value": "F",
    "time_second_odds": "A",
}
TEMPLATE_BY_SHEET = {
    "handicap": "Daily Trading_HDP_Demo.xlsx",
    "totals": "Daily Trading_OU_Demo.xlsx",
}


def parse_match_time_sort_key(match_time: str) -> tuple[int, int, int, int, str]:
    match = re.fullmatch(r"(\d+)-(\d+)\s+(\d+):(\d+)", str(match_time or "").strip())
    if not match:
        return (999, 999, 999, 999, str(match_time or "").strip())
    month, day, hour, minute = (int(part) for part in match.groups())
    return (month, day, hour, minute, str(match_time or "").strip())


def format_match_time_display(match_time: str) -> str:
    value = str(match_time or "").strip()
    match = re.search(r"(\d{1,2}:\d{2})$", value)
    if match:
        return match.group(1)
    return value


def resolve_template_path(sheet_title: str) -> Path:
    template_name = TEMPLATE_BY_SHEET.get(sheet_title)
    if not template_name:
        raise ValueError(f"Unsupported sheet_title for template export: {sheet_title}")
    return Path(__file__).resolve().parent / template_name


def sorted_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda record: (
            int(record.get("page_order", 10**9))
            if str(record.get("page_order", "")).strip() != ""
            else 10**9,
            parse_match_time_sort_key(record.get("match_time", "")),
            record.get("league", ""),
            record.get("matched_team_name", ""),
        ),
    )


def clear_block(worksheet, row_start: int) -> None:
    for row in range(row_start, row_start + BLOCK_HEIGHT):
        for col in ("A", "B", "C", "F"):
            worksheet[f"{col}{row}"] = None


def write_cell(worksheet, row_start: int, field: str, value: Any) -> None:
    cell_ref = f"{COLS[field]}{row_start + ROW_OFFSETS[field]}"
    worksheet[cell_ref] = value if value not in {"", None} else None


def write_record_block(worksheet, row_start: int, record: dict[str, Any], sheet_title: str) -> None:
    clear_block(worksheet, row_start)

    write_cell(worksheet, row_start, "match_time", format_match_time_display(record.get("match_time", "")))
    write_cell(worksheet, row_start, "league", record.get("league", ""))
    write_cell(worksheet, row_start, "team_name", record.get("team_name_display", ""))
    if record.get("matched_source") == "sub":
        write_cell(worksheet, row_start, "m_marker", "M")
    write_cell(worksheet, row_start, "rx_label", "R-X")
    write_cell(worksheet, row_start, "time_first_handicap", record.get("time_first_handicap", ""))
    write_cell(worksheet, row_start, "league_handicap", record.get("league_handicap", ""))
    write_cell(worksheet, row_start, "rx_value", record.get("rx_value", ""))
    write_cell(worksheet, row_start, "time_first_odds", record.get("time_first_odds", ""))
    write_cell(worksheet, row_start, "league_odds", record.get("league_odds", ""))
    write_cell(worksheet, row_start, "ex_label", "E-X")
    write_cell(worksheet, row_start, "time_second_handicap", record.get("time_second_handicap", ""))
    write_cell(worksheet, row_start, "score_compact", record.get("score_compact", ""))
    write_cell(worksheet, row_start, "ex_value", record.get("ex_value", ""))
    write_cell(worksheet, row_start, "time_second_odds", record.get("time_second_odds", ""))


def export_template_workbook(records: list[dict[str, Any]], sheet_title: str) -> tuple[bytes, dict[str, Any]]:
    template_path = resolve_template_path(sheet_title)
    workbook = load_workbook(template_path)
    worksheet = workbook.active

    ordered_records = sorted_records(records)
    row_start = 2
    for record in ordered_records:
        write_record_block(worksheet, row_start, record, sheet_title)
        row_start += BLOCK_HEIGHT

    stats = {
        "record_count": len(ordered_records),
        "template_path": str(template_path),
        "last_row_used": row_start - 1 if ordered_records else 1,
        "detail_ready_count": sum(
            1
            for record in ordered_records
            if any(
                record.get(field, "")
                for field in (
                    "time_first_handicap",
                    "league_handicap",
                    "time_second_handicap",
                    "time_first_odds",
                    "league_odds",
                    "time_second_odds",
                    "score_compact",
                )
            )
        ),
    }

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue(), stats
