"""Crawler utilities for fetching Titan007 matches and Asian handicap data."""

from __future__ import annotations

import re
import warnings
from datetime import datetime
from typing import Any

import requests
from bs4 import BeautifulSoup

warnings.filterwarnings(
    "ignore",
    message=r"urllib3 v2 only supports OpenSSL 1\.1\.1\+",
)

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://bf.titan007.com/",
}
RANKING_TAG_RE = re.compile(r"^\[[^\]]+\]\s*|\s*\[[^\]]+\]$")
GOAL_CN = [
    "平手",
    "平/半",
    "半球",
    "半/一",
    "一球",
    "一/球半",
    "球半",
    "球半/两球",
    "两球",
    "两球/两球半",
    "两球半",
    "两球半/三球",
    "三球",
    "三球/三球半",
    "三球半",
    "三球半/四球",
    "四球",
    "四球/四球半",
    "四球半",
    "四球半/五球",
    "五球",
    "五球/五球半",
    "五球半",
    "五球半/六球",
    "六球",
    "六球/六球半",
    "六球半",
    "六球半/七球",
    "七球",
    "七球/七球半",
    "七球半",
    "七球半/八球",
    "八球",
    "八球/八球半",
    "八球半",
    "八球半/九球",
    "九球",
    "九球/九球半",
    "九球半",
    "九球半/十球",
    "十球",
]


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def clean_team_name(value: str) -> str:
    cleaned = clean_text(value)
    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = RANKING_TAG_RE.sub("", cleaned).strip()
    return cleaned


def build_main_page_url(date_text: str) -> str:
    return f"https://bf.titan007.com/football/big/Next_{date_text}.htm"


def build_odds_api_url(date_text: str) -> str:
    return (
        f"https://bf.titan007.com/CommonInterface.ashx?type=3&date="
        f"{date_text[:4]}-{date_text[4:6]}-{date_text[6:8]}"
    )


def fetch_text(url: str, encoding: str) -> tuple[requests.Response, str]:
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    response.encoding = encoding
    return response, response.text


def fetch_selected_match_filter_for_date(date_text: str) -> tuple[set[str], dict[str, Any]]:
    reference_filter_page_url = build_main_page_url(date_text)
    response, html_text = fetch_text(reference_filter_page_url, encoding="gb18030")
    if response.status_code != 200:
        raise ValueError(f"Reference filter page returned HTTP {response.status_code}")

    soup = BeautifulSoup(html_text, "html.parser")
    table = soup.find("table", id="table_live")
    if table is None:
        raise ValueError("Could not find table#table_live on the reference filter page.")

    selected_match_sids: set[str] = set()
    selected_leagues: list[str] = []
    visible_match_count = 0
    for row in table.find_all("tr", recursive=False)[1:]:
        style = clean_text(row.get("style", "")).lower().replace(" ", "")
        if "display:none" in style:
            continue
        cells = row.find_all("td", recursive=False)
        if len(cells) != 10:
            continue
        sid = clean_text(row.get("sid", ""))
        league_text = clean_text(cells[0].get_text(" ", strip=True))
        if not sid or not league_text:
            continue
        visible_match_count += 1
        selected_match_sids.add(sid)
        if league_text not in selected_leagues:
            selected_leagues.append(league_text)

    return selected_match_sids, {
        "reference_filter_page_url": reference_filter_page_url,
        "selected_match_count": len(selected_match_sids),
        "selected_league_count": len(selected_leagues),
        "visible_match_count": visible_match_count,
        "selected_leagues": selected_leagues,
    }


def parse_main_page_matches(html_text: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html_text, "html.parser")
    table = soup.find("table", id="table_live")
    if table is None:
        raise ValueError("Could not find table#table_live on the main page.")

    matches: list[dict[str, Any]] = []
    for row in table.find_all("tr", recursive=False)[1:]:
        cells = row.find_all("td", recursive=False)
        if len(cells) != 10:
            continue

        sid = clean_text(row.get("sid", ""))
        league = clean_text(cells[0].get_text(" ", strip=True))
        match_time = clean_text(cells[1].get_text(" ", strip=True))
        home_team = clean_team_name(cells[3].get_text(" ", strip=True))
        away_team = clean_team_name(cells[5].get_text(" ", strip=True))

        if not any([sid, league, match_time, home_team, away_team]):
            continue

        matches.append(
            {
                "sid": sid,
                "league": league,
                "match_time": match_time,
                "home_team": home_team,
                "away_team": away_team,
                "page_order": len(matches),
            }
        )

    return matches


def parse_match_time_components(match_time: str) -> tuple[int, int, int, int] | None:
    value = clean_text(match_time)
    match = re.fullmatch(r"(\d+)-(\d+)\s+(\d+):(\d+)", value)
    if not match:
        return None
    month, day, hour, minute = (int(part) for part in match.groups())
    return month, day, hour, minute


def filter_matches_for_selected_date(matches: list[dict[str, Any]], date_text: str) -> list[dict[str, Any]]:
    selected_date = datetime.strptime(date_text, "%Y%m%d").date()
    filtered: list[dict[str, Any]] = []
    seen_sids: set[str] = set()

    for match in matches:
        components = parse_match_time_components(match.get("match_time", ""))
        if components is None:
            continue

        month, day, _, _ = components
        if month != selected_date.month or day != selected_date.day:
            continue

        sid = clean_text(match.get("sid", ""))
        if sid and sid in seen_sids:
            continue
        if sid:
            seen_sids.add(sid)
        filtered.append(match)

    return filtered


def parse_odds_api(text: str) -> dict[str, dict[str, str]]:
    odds_by_sid: dict[str, dict[str, str]] = {}
    for record in text.split("!"):
        parts = record.split("^")
        if len(parts) < 2:
            continue

        sid = clean_text(parts[0])
        letgoal = clean_text(parts[1])
        total = clean_text(parts[2]) if len(parts) > 2 else ""
        if not sid:
            continue

        odds_by_sid[sid] = {
            "sid": sid,
            "letgoal": letgoal,
            "total": total,
        }

    return odds_by_sid


def goal_to_display(raw_value: str) -> str:
    raw_value = clean_text(raw_value)
    if not raw_value:
        return ""

    try:
        goal = float(raw_value)
    except ValueError:
        return raw_value

    if goal > 10 or goal < -10:
        return f"{raw_value}球"

    index = abs(int(goal * 4))
    if index >= len(GOAL_CN):
        return raw_value

    label = GOAL_CN[index].strip()
    if goal < 0:
        return f"* {label}"
    return label


def merge_matches_with_odds(
    matches: list[dict[str, Any]],
    odds_by_sid: dict[str, dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    matched_count = 0
    homepage_without_api: list[dict[str, Any]] = []

    for match in matches:
        odds = odds_by_sid.get(match["sid"])
        asian_handicap_raw = odds["letgoal"] if odds else ""
        asian_handicap_display = goal_to_display(asian_handicap_raw)
        if odds:
            matched_count += 1
        else:
            homepage_without_api.append(match)

        merged.append(
            {
                **match,
                "asian_handicap_raw": asian_handicap_raw,
                "asian_handicap_display": asian_handicap_display,
            }
        )

    homepage_sid_set = {match["sid"] for match in matches if match["sid"]}
    api_without_homepage = [
        odds
        for sid, odds in odds_by_sid.items()
        if sid not in homepage_sid_set
    ]
    summary = {
        "matches_count": len(matches),
        "api_records_count": len(odds_by_sid),
        "matched_count": matched_count,
        "homepage_without_api_count": len(homepage_without_api),
        "api_without_homepage_count": len(api_without_homepage),
    }
    return merged, summary


def fetch_merged_matches_for_date(date_text: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    main_page_url = build_main_page_url(date_text)
    api_url = build_odds_api_url(date_text)

    main_response, main_html = fetch_text(main_page_url, encoding="gb18030")
    api_response, api_text = fetch_text(api_url, encoding="utf-8")

    if main_response.status_code != 200:
        raise ValueError(f"Main page returned HTTP {main_response.status_code}")
    if api_response.status_code != 200:
        raise ValueError(f"Odds API returned HTTP {api_response.status_code}")

    matches = parse_main_page_matches(main_html)
    odds_by_sid = parse_odds_api(api_text)
    merged_matches, summary = merge_matches_with_odds(matches, odds_by_sid)
    summary.update(
        {
            "main_page_url": main_page_url,
            "odds_api_url": api_url,
            "selected_date_matches_count": len(matches),
        }
    )
    return merged_matches, summary
