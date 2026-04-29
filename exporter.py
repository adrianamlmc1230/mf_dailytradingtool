"""Excel exporter utilities for final block-structured outputs."""

from __future__ import annotations

from io import BytesIO
import re
from typing import Any

from openpyxl import Workbook

BLANK_ROWS_AFTER_RECORD = 5
HEADER_ROW = ["開賽時間", "聯賽", "隊伍"]
BLANK_ROW = ["", "", ""]


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


def build_block_rows(records: list[dict[str, str]]) -> tuple[list[list[str]], dict[str, Any]]:
    rows: list[list[str]] = [HEADER_ROW.copy()]
    main_count = 0
    sub_count = 0
    m_insert_ok = True
    blank_rows_ok = True

    sorted_records = sorted(
        records,
        key=lambda record: (
            int(record.get("page_order", 10**9)) if str(record.get("page_order", "")).strip() != "" else 10**9,
            parse_match_time_sort_key(record.get("match_time", "")),
            record.get("league", ""),
            record.get("matched_team_name", ""),
        ),
    )

    for record in sorted_records:
        required_fields = ["match_time", "league", "matched_team_name", "matched_source", "matched_side", "team_name_display"]
        missing_fields = [field for field in required_fields if field not in record]
        if missing_fields:
            raise ValueError(f"record missing required fields {missing_fields}: {record}")

        block_rows = [
            [
                format_match_time_display(record["match_time"]),
                record["league"],
                record["team_name_display"],
            ]
        ]

        if record["matched_source"] == "sub":
            sub_count += 1
            expected_block_size = 6
        elif record["matched_source"] == "main":
            main_count += 1
            expected_block_size = 6
        else:
            raise ValueError(f"invalid matched_source: {record['matched_source']}")

        trailing_rows = [BLANK_ROW.copy() for _ in range(BLANK_ROWS_AFTER_RECORD)]
        if record["matched_source"] == "sub":
            trailing_rows[0] = ["", "", "M"]
        block_rows.extend(trailing_rows)

        if len(block_rows) != expected_block_size:
            raise ValueError(
                f"invalid block size for {record['matched_source']}: "
                f"expected {expected_block_size}, got {len(block_rows)}"
            )

        if record["matched_source"] == "sub" and block_rows[1] != ["", "", "M"]:
            m_insert_ok = False
            raise ValueError(f"sub block missing M row: {record}")

        trailing_reserved_rows = block_rows[-BLANK_ROWS_AFTER_RECORD:]
        if len(trailing_reserved_rows) != BLANK_ROWS_AFTER_RECORD:
            blank_rows_ok = False
            raise ValueError(f"invalid blank row count: {record}")
        if record["matched_source"] == "main":
            if any(any(cell for cell in row) for row in trailing_reserved_rows):
                blank_rows_ok = False
                raise ValueError(f"main block blank rows contain data: {record}")
        else:
            if trailing_reserved_rows[0] != ["", "", "M"]:
                blank_rows_ok = False
                raise ValueError(f"sub block M row invalid: {record}")
            if any(any(cell for cell in row) for row in trailing_reserved_rows[1:]):
                blank_rows_ok = False
                raise ValueError(f"sub block blank rows contain data: {record}")

        rows.extend(block_rows)

    stats = {
        "record_count": len(sorted_records),
        "main_count": main_count,
        "sub_count": sub_count,
        "total_rows_written": len(rows),
        "m_insert_ok": m_insert_ok,
        "blank_rows_ok": blank_rows_ok,
    }
    return rows, stats


def export_block_workbook(records: list[dict[str, str]], sheet_title: str) -> tuple[bytes, dict[str, Any]]:
    rows, stats = build_block_rows(records)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_title
    worksheet.column_dimensions["A"].width = 16
    worksheet.column_dimensions["B"].width = 18
    worksheet.column_dimensions["C"].width = 24

    for row_index, row_values in enumerate(rows, start=1):
        for column_index, value in enumerate(row_values, start=1):
            worksheet.cell(row=row_index, column=column_index, value=value or None)

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue(), stats
