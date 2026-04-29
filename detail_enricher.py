"""Detail enrichment for template-based Daily Trading outputs."""

from __future__ import annotations

import re
import time
from functools import lru_cache
from typing import Any

import requests
from bs4 import BeautifulSoup

from crawler import REQUEST_HEADERS, clean_text
from handicap_normalizer import HandicapNormalizer

REQUEST_RETRY_COUNT = 3
REQUEST_RETRY_DELAY_SECONDS = 1.0


def build_asian_odds_url(sid: str) -> str:
    return f"https://vip.titan007.com/AsianOdds_n.aspx?id={sid}"


def build_over_under_url(sid: str) -> str:
    return f"https://vip.titan007.com/OverDown_n.aspx?id={sid}"


def fetch_text(url: str, encoding: str) -> tuple[requests.Response, str]:
    last_error: requests.RequestException | None = None
    for attempt in range(REQUEST_RETRY_COUNT):
        try:
            response = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
            response.encoding = encoding
            return response, response.text
        except requests.RequestException as exc:
            last_error = exc
            if attempt == REQUEST_RETRY_COUNT - 1:
                raise
            time.sleep(REQUEST_RETRY_DELAY_SECONDS * (attempt + 1))

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Unexpected request failure for {url}")


def format_normalized_handicap(value: float | None) -> int | float | str:
    if value is None:
        return ""
    if float(value).is_integer():
        return int(value)
    return float(f"{value:.2f}".rstrip("0").rstrip("."))


def format_odds_pair(home_rate: str, away_rate: str) -> str:
    try:
        left = int(round(float(home_rate) * 100))
        right = int(round(float(away_rate) * 100))
    except (TypeError, ValueError):
        return ""
    return f"{left}/{right}"


def compact_score(value: str) -> str:
    score = clean_text(value)
    if not score or score == "-":
        return ""
    match = re.fullmatch(r"(\d+)\s*[-:]\s*(\d+)", score)
    if not match:
        return ""
    return f"{match.group(1)}{match.group(2)}"


def parse_listing_page_score(html_text: str) -> str:
    match = re.search(
        r'<div class="row" id="headVs">.*?<div class="score">\s*([^<\s][^<]*)\s*</div>.*?'
        r'<div class="score gt">\s*([^<\s][^<]*)\s*</div>',
        html_text,
        re.S,
    )
    if not match:
        return ""
    return compact_score(f"{match.group(1)}-{match.group(2)}")


def parse_total_line(line_text: str) -> int | float | str:
    value = clean_text(line_text)
    if not value:
        return ""

    if "/" not in value:
        try:
            numeric = float(value)
        except ValueError:
            return value
        if numeric.is_integer():
            return int(numeric)
        return float(f"{numeric:.2f}".rstrip("0").rstrip("."))

    parts = value.split("/")
    if len(parts) != 2:
        return value

    try:
        left = float(parts[0])
        right = float(parts[1])
    except ValueError:
        return value

    numeric = (left + right) / 2
    if numeric.is_integer():
        return int(numeric)
    return float(f"{numeric:.2f}".rstrip("0").rstrip("."))


def parse_crow_detail_link(html_text: str, detail_path: str, listing_url: str) -> dict[str, str]:
    soup = BeautifulSoup(html_text, "html.parser")
    for row in soup.find_all("tr"):
        row_text = " ".join(row.stripped_strings)
        if "Crow" not in row_text:
            continue
        for link in row.find_all("a"):
            href = clean_text(link.get("href", ""))
            if not href or detail_path not in href:
                continue
            company_match = re.search(r"companyID=(\d+)", href)
            return {
                "company_id": company_match.group(1) if company_match else "",
                "detail_href": href,
                "detail_url": f"https://vip.titan007.com/{href.lstrip('/')}",
                "listing_url": listing_url,
            }
    return {
        "company_id": "",
        "detail_href": "",
        "detail_url": "",
        "listing_url": listing_url,
    }


def parse_change_detail_rows(html_text: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html_text, "html.parser")
    parsed_rows: list[dict[str, str]] = []
    for row in soup.find_all("tr"):
        cells = [" ".join(cell.stripped_strings) for cell in row.find_all(["th", "td"])]
        if len(cells) != 7:
            continue
        if cells[-1] not in {"早", "即", "滚"}:
            continue
        parsed_rows.append(
            {
                "runtime": clean_text(cells[0]),
                "score": clean_text(cells[1]),
                "home_rate": clean_text(cells[2]),
                "handicap_text": clean_text(cells[3]),
                "away_rate": clean_text(cells[4]),
                "changed_at": clean_text(cells[5]),
                "status": clean_text(cells[6]),
            }
        )
    return parsed_rows


def newest_detail_score(detail_rows: list[dict[str, str]], fallback_score: str) -> str:
    for row in detail_rows:
        score = compact_score(row.get("score", ""))
        if score:
            return score
    return compact_score(fallback_score)


def select_score_compact(
    detail_rows: list[dict[str, str]],
    listing_page_score: str,
    fallback_score: str,
) -> str:
    if listing_page_score:
        return listing_page_score
    return newest_detail_score(detail_rows, fallback_score)


def calculate_segment_x(detail_rows: list[dict[str, str]], rate_key: str, statuses: set[str]) -> int | str:
    filtered = [row for row in detail_rows if row["status"] in statuses]
    if not filtered:
        return ""

    chron = list(reversed(filtered))
    total = 0
    index = 0
    while index < len(chron):
        target_line = chron[index].get("handicap_text", "")
        last_index = index
        for probe in range(len(chron) - 1, index - 1, -1):
            if chron[probe].get("handicap_text", "") == target_line:
                last_index = probe
                break

        try:
            earliest_rate = float(chron[index][rate_key])
            latest_rate = float(chron[last_index][rate_key])
        except (TypeError, ValueError, KeyError):
            index = last_index + 1
            continue

        total += int(round((latest_rate - earliest_rate) * 100))
        index = last_index + 1

    return total


def pick_hdp_rate_key(match: dict[str, Any], detail_rows: list[dict[str, str]]) -> str:
    matched_side = clean_text(match.get("matched_side", "")).lower()
    if matched_side == "away":
        return "away_rate"
    if matched_side == "home":
        return "home_rate"

    for row in reversed(detail_rows):
        handicap_text = clean_text(row.get("handicap_text", ""))
        if not handicap_text:
            continue
        if "受" in handicap_text:
            return "away_rate"
        return "home_rate"

    return "home_rate"


def pick_ou_rate_key(detail_rows: list[dict[str, str]]) -> tuple[str, str]:
    filtered = [row for row in detail_rows if row["status"] in {"早", "即"}]
    if not filtered:
        return "home_rate", ""

    first_row = list(reversed(filtered))[0]
    try:
        over_rate = float(first_row["home_rate"])
        under_rate = float(first_row["away_rate"])
    except (TypeError, ValueError, KeyError):
        return "home_rate", ""

    if over_rate < under_rate:
        return "home_rate", "L"
    if under_rate < over_rate:
        return "away_rate", "S"
    return "home_rate", ""


def build_match_detail_snapshot(
    match: dict[str, Any],
    crow_row: dict[str, str],
    detail_rows: list[dict[str, str]],
    market_type: str,
    listing_page_score: str,
) -> dict[str, Any]:
    early_rows = [row for row in detail_rows if row["status"] == "早"]
    instant_rows = [row for row in detail_rows if row["status"] == "即"]

    early_first = early_rows[-1] if early_rows else None
    early_last = early_rows[0] if early_rows else None
    instant_last = instant_rows[0] if instant_rows else None

    def handicap_value(row: dict[str, str] | None) -> str:
        if not row:
            return ""
        if market_type == "totals":
            return parse_total_line(row["handicap_text"])
        return format_normalized_handicap(HandicapNormalizer.normalize(row["handicap_text"]))

    def odds_value(row: dict[str, str] | None) -> str:
        if not row:
            return ""
        return format_odds_pair(row["home_rate"], row["away_rate"])

    if market_type == "totals":
        rate_key, ex_prefix = pick_ou_rate_key(detail_rows)
        rx_value = calculate_segment_x(detail_rows, rate_key, {"早", "即"})
        ex_numeric = calculate_segment_x(detail_rows, rate_key, {"早"})
        ex_value = f"{ex_prefix}{ex_numeric}" if ex_numeric != "" and ex_prefix else ex_numeric
        league_handicap = handicap_value(early_last)
        league_odds = odds_value(early_last)
    else:
        rate_key = pick_hdp_rate_key(match, detail_rows)
        rx_value = calculate_segment_x(detail_rows, rate_key, {"早", "即"})
        ex_value = calculate_segment_x(detail_rows, rate_key, {"早"})
        league_handicap = handicap_value(early_last)
        league_odds = odds_value(early_last)

    return {
        "sid": match.get("sid", ""),
        "company_id": crow_row.get("company_id", ""),
        "detail_listing_url": crow_row.get("listing_url", ""),
        "detail_url": crow_row.get("detail_url", ""),
        "time_first_handicap": handicap_value(early_first),
        "time_first_odds": odds_value(early_first),
        "league_handicap": league_handicap,
        "league_odds": league_odds,
        "time_second_handicap": handicap_value(instant_last),
        "time_second_odds": odds_value(instant_last),
        "score_compact": select_score_compact(
            detail_rows,
            listing_page_score,
            match.get("homepage_score", ""),
        ),
        "detail_rows_count": len(detail_rows),
        "rx_value": rx_value,
        "ex_value": ex_value,
    }


@lru_cache(maxsize=512)
def fetch_match_detail_snapshot(sid: str, homepage_score: str, market_type: str, matched_side: str) -> dict[str, Any]:
    sid = clean_text(sid)
    if not sid:
        return {}

    if market_type == "totals":
        listing_url = build_over_under_url(sid)
        detail_path = "changeDetail/overunder.aspx"
    else:
        listing_url = build_asian_odds_url(sid)
        detail_path = "changeDetail/handicap.aspx"

    try:
        listing_response, listing_html = fetch_text(listing_url, encoding="utf-8")
    except requests.RequestException:
        return {}
    if listing_response.status_code != 200:
        return {}
    listing_page_score = parse_listing_page_score(listing_html)

    crow_row = parse_crow_detail_link(listing_html, detail_path, listing_url)
    detail_url = crow_row.get("detail_url", "")
    if not detail_url:
        return {
            "sid": sid,
            "company_id": "",
            "detail_listing_url": listing_url,
            "detail_url": "",
            "time_first_handicap": "",
            "time_first_odds": "",
            "league_handicap": "",
            "league_odds": "",
            "time_second_handicap": "",
            "time_second_odds": "",
            "score_compact": listing_page_score or compact_score(homepage_score),
            "detail_rows_count": 0,
            "rx_value": "",
            "ex_value": "",
        }

    try:
        detail_response, detail_html = fetch_text(detail_url, encoding="gb18030")
    except requests.RequestException:
        return {}
    if detail_response.status_code != 200:
        return {}

    detail_rows = parse_change_detail_rows(detail_html)
    return build_match_detail_snapshot(
        {"sid": sid, "homepage_score": homepage_score, "matched_side": matched_side},
        crow_row,
        detail_rows,
        market_type,
        listing_page_score,
    )


def clear_detail_cache() -> None:
    """Clear the LRU cache for fetch_match_detail_snapshot."""
    fetch_match_detail_snapshot.cache_clear()


def enrich_records_with_detail(records: list[dict[str, Any]], market_type: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    enriched_records: list[dict[str, Any]] = []
    detail_ready_count = 0

    for record in records:
        snapshot = fetch_match_detail_snapshot(
            clean_text(record.get("sid", "")),
            clean_text(record.get("homepage_score", "")),
            market_type,
            clean_text(record.get("matched_side", "")),
        )
        merged = {**record, **snapshot}
        if snapshot:
            detail_ready_count += 1
        enriched_records.append(merged)

    summary = {
        "market_type": market_type,
        "record_count": len(records),
        "detail_ready_count": detail_ready_count,
        "detail_missing_count": len(records) - detail_ready_count,
    }
    return enriched_records, summary
