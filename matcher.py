"""Matching utilities for handicap and totals outputs."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value)
    cleaned_chars = []
    for char in text:
        category = unicodedata.category(char)
        if category.startswith("C") and char not in {"\t", "\n", "\r"}:
            continue
        cleaned_chars.append(char)

    return re.sub(r"\s+", " ", "".join(cleaned_chars)).strip()


def build_team_pool_index(team_pool_rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    index: dict[str, list[dict[str, str]]] = {}
    for row in team_pool_rows:
        team_name = normalize_text(row.get("team_name", ""))
        if not team_name:
            continue
        normalized_row = {
            "source_file": normalize_text(row.get("source_file", "")),
            "sheet_name": normalize_text(row.get("sheet_name", "")),
            "anchor_type": normalize_text(row.get("anchor_type", "")),
            "anchor_cell": normalize_text(row.get("anchor_cell", "")),
            "team_name": team_name,
        }
        bucket = index.setdefault(team_name, [])
        if normalized_row not in bucket:
            bucket.append(normalized_row)
    return index


def find_index_rows(index: dict[str, list[dict[str, str]]], team_name: str) -> list[dict[str, str]]:
    return list(index.get(normalize_text(team_name), []))


def parse_match_time_sort_key(match_time: str) -> tuple[int, int, int, int, str]:
    value = normalize_text(match_time)
    match = re.fullmatch(r"(\d+)-(\d+)\s+(\d+):(\d+)", value)
    if not match:
        return (999, 999, 999, 999, value)
    month, day, hour, minute = (int(part) for part in match.groups())
    return (month, day, hour, minute, value)


def is_even_handicap_display(value: str) -> bool:
    normalized = normalize_text(value).replace("*", "").strip()
    return normalized == "平手"


def build_team_name_display(team_name: str, matched_side: str) -> str:
    if matched_side == "away":
        return f"{team_name}*"
    return team_name


def infer_handicap_side(asian_handicap_display: str) -> str | None:
    value = normalize_text(asian_handicap_display)
    if not value or is_even_handicap_display(value):
        return None
    return "away" if "*" in value else "home"


def pick_preferred_candidate(candidates: list[dict[str, str]]) -> dict[str, str] | None:
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda candidate: (
            0 if candidate.get("anchor_type") == "前" else 1,
            0 if candidate.get("matched_side") == "home" else 1,
            candidate.get("sheet_name", ""),
            candidate.get("anchor_cell", ""),
            candidate.get("matched_team_name", ""),
        ),
    )[0]


def build_match_candidates(
    match: dict[str, str],
    matched_source: str,
    matched_side: str,
    team_name: str,
    pool_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    return [
        {
            **match,
            "matched_source": matched_source,
            "matched_side": matched_side,
            "matched_team_name": pool_row["team_name"],
            "team_name_display": build_team_name_display(pool_row["team_name"], matched_side),
            "source_file": pool_row["source_file"],
            "sheet_name": pool_row["sheet_name"],
            "anchor_type": pool_row["anchor_type"],
            "anchor_cell": pool_row["anchor_cell"],
            "target_side": matched_side,
            "target_team": team_name,
        }
        for pool_row in pool_rows
    ]


def build_handicap_matches(
    merged_matches: list[dict[str, Any]],
    main_team_pool_rows: list[dict[str, str]],
    sub_team_pool_rows: list[dict[str, str]],
) -> dict[str, Any]:
    main_index = build_team_pool_index(main_team_pool_rows)
    sub_index = build_team_pool_index(sub_team_pool_rows)

    eligible_matches = [
        {
            "sid": normalize_text(match.get("sid", "")),
            "league": normalize_text(match.get("league", "")),
            "match_time": normalize_text(match.get("match_time", "")),
            "home_team": normalize_text(match.get("home_team", "")),
            "away_team": normalize_text(match.get("away_team", "")),
            "asian_handicap_display": normalize_text(match.get("asian_handicap_display", "")),
            "page_order": match.get("page_order", ""),
        }
        for match in merged_matches
        if not is_even_handicap_display(normalize_text(match.get("asian_handicap_display", "")))
    ]

    main_rows: list[dict[str, str]] = []
    sub_rows: list[dict[str, str]] = []
    combined_rows: list[dict[str, str]] = []
    unmatched_matches: list[dict[str, str]] = []

    for match in eligible_matches:
        if not match["asian_handicap_display"]:
            blank_main_candidates: list[dict[str, str]] = []
            blank_sub_candidates: list[dict[str, str]] = []

            for matched_side, team_name in [("home", match["home_team"]), ("away", match["away_team"])]:
                blank_main_candidates.extend(
                    build_match_candidates(
                        match,
                        "main",
                        matched_side,
                        team_name,
                        find_index_rows(main_index, team_name),
                    )
                )
                blank_sub_candidates.extend(
                    build_match_candidates(
                        match,
                        "sub",
                        matched_side,
                        team_name,
                        find_index_rows(sub_index, team_name),
                    )
                )

            preferred_blank_main = pick_preferred_candidate(blank_main_candidates)
            preferred_blank_sub = pick_preferred_candidate(blank_sub_candidates)

            if preferred_blank_main:
                main_rows.append(preferred_blank_main)
                combined_rows.append(preferred_blank_main)
            elif preferred_blank_sub:
                sub_rows.append(preferred_blank_sub)
                combined_rows.append(preferred_blank_sub)
            else:
                unmatched_matches.append({**match, "target_side": "", "target_team": ""})
            continue

        if "*" in match["asian_handicap_display"]:
            target_side = "away"
            target_team = match["away_team"]
        else:
            target_side = "home"
            target_team = match["home_team"]

        current_main_rows = build_match_candidates(
            match, "main", target_side, target_team, find_index_rows(main_index, target_team)
        )
        current_sub_rows = build_match_candidates(
            match, "sub", target_side, target_team, find_index_rows(sub_index, target_team)
        )

        preferred_main_row = pick_preferred_candidate(current_main_rows)
        preferred_sub_row = pick_preferred_candidate(current_sub_rows)

        if preferred_main_row:
            main_rows.append(preferred_main_row)
            combined_rows.append(preferred_main_row)
        if preferred_sub_row:
            sub_rows.append(preferred_sub_row)
            combined_rows.append(preferred_sub_row)

        if not preferred_main_row and not preferred_sub_row:
            unmatched_matches.append(
                {
                    **match,
                    "target_side": target_side,
                    "target_team": target_team,
                }
            )

    main_hit_sids = {row["sid"] for row in main_rows}
    sub_hit_sids = {row["sid"] for row in sub_rows}
    all_hit_sids = main_hit_sids | sub_hit_sids

    stats = {
        "eligible_match_count": len(eligible_matches),
        "main_hit_match_count": len(main_hit_sids),
        "sub_hit_match_count": len(sub_hit_sids),
        "both_hit_match_count": len(main_hit_sids & sub_hit_sids),
        "unmatched_match_count": len(eligible_matches) - len(all_hit_sids),
        "main_match_rate": (len(main_hit_sids) / len(eligible_matches) * 100) if eligible_matches else 0.0,
        "main_output_row_count": len(main_rows),
        "sub_output_row_count": len(sub_rows),
        "combined_output_row_count": len(combined_rows),
    }
    return {
        "main_rows": main_rows,
        "sub_rows": sub_rows,
        "combined_rows": combined_rows,
        "unmatched_matches": unmatched_matches,
        "stats": stats,
    }


def build_totals_matches(
    merged_matches: list[dict[str, Any]],
    main_team_pool_rows: list[dict[str, str]],
    sub_team_pool_rows: list[dict[str, str]],
) -> dict[str, Any]:
    main_index = build_team_pool_index(main_team_pool_rows)
    sub_index = build_team_pool_index(sub_team_pool_rows)

    matches = [
        {
            "sid": normalize_text(match.get("sid", "")),
            "league": normalize_text(match.get("league", "")),
            "match_time": normalize_text(match.get("match_time", "")),
            "home_team": normalize_text(match.get("home_team", "")),
            "away_team": normalize_text(match.get("away_team", "")),
            "asian_handicap_display": normalize_text(match.get("asian_handicap_display", "")),
            "page_order": match.get("page_order", ""),
        }
        for match in merged_matches
    ]

    debug_rows: list[dict[str, str]] = []
    suppressed_sub_count = 0

    for match in matches:
        main_candidates = []
        sub_candidates = []
        main_home_rows = find_index_rows(main_index, match["home_team"])
        main_away_rows = find_index_rows(main_index, match["away_team"])
        sub_home_rows = find_index_rows(sub_index, match["home_team"])
        sub_away_rows = find_index_rows(sub_index, match["away_team"])

        for matched_side, team_name, source_rows, source_name in [
            ("home", match["home_team"], main_home_rows, "main"),
            ("away", match["away_team"], main_away_rows, "main"),
            ("home", match["home_team"], sub_home_rows, "sub"),
            ("away", match["away_team"], sub_away_rows, "sub"),
        ]:
            target_bucket = main_candidates if source_name == "main" else sub_candidates
            for pool_row in source_rows:
                target_bucket.append(
                    {
                        **match,
                        "matched_source": source_name,
                        "matched_side": matched_side,
                        "matched_team_name": pool_row["team_name"],
                        "team_name_display": build_team_name_display(pool_row["team_name"], matched_side),
                        "source_file": pool_row["source_file"],
                        "sheet_name": pool_row["sheet_name"],
                        "anchor_type": pool_row["anchor_type"],
                        "anchor_cell": pool_row["anchor_cell"],
                    }
                )

        handicap_side = infer_handicap_side(match.get("asian_handicap_display", ""))
        special_choice = None
        if handicap_side:
            both_main_front = any(r["anchor_type"] == "前" for r in main_home_rows) and any(r["anchor_type"] == "前" for r in main_away_rows)
            both_main_tail = any(r["anchor_type"] == "尾" for r in main_home_rows) and any(r["anchor_type"] == "尾" for r in main_away_rows)
            both_sub_hit = bool(sub_home_rows) and bool(sub_away_rows)

            if both_main_front:
                special_choice = pick_preferred_candidate([
                    row for row in main_candidates
                    if row["anchor_type"] == "前" and row["matched_side"] == handicap_side
                ])
            elif both_main_tail:
                special_choice = pick_preferred_candidate([
                    row for row in main_candidates
                    if row["anchor_type"] == "尾" and row["matched_side"] == handicap_side
                ])
            elif both_sub_hit:
                special_choice = pick_preferred_candidate([
                    row for row in sub_candidates
                    if row["matched_side"] == handicap_side
                ])

        if special_choice:
            debug_rows.append(special_choice)
            continue

        if main_candidates and sub_candidates:
            suppressed_sub_count += len(sub_candidates)

        preferred_main = pick_preferred_candidate(main_candidates)
        preferred_sub = pick_preferred_candidate(sub_candidates)

        if preferred_main:
            debug_rows.append(preferred_main)
        elif preferred_sub:
            debug_rows.append(preferred_sub)

    stats = {
        "match_count": len(matches),
        "main_output_row_count": sum(1 for row in debug_rows if row["matched_source"] == "main"),
        "sub_output_row_count": sum(1 for row in debug_rows if row["matched_source"] == "sub"),
        "suppressed_sub_count": suppressed_sub_count,
        "final_output_row_count": len(debug_rows),
    }
    return {
        "debug_rows": debug_rows,
        "stats": stats,
    }
