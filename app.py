"""Streamlit app for local event data fetching and odds export."""

from __future__ import annotations

import traceback
from datetime import date

import streamlit as st

import re

from crawler import fetch_merged_matches_for_date
from detail_enricher import enrich_records_with_detail, clear_detail_cache
from excel_parser import parse_anchor_workbook
from matcher import build_handicap_matches, build_totals_matches
from template_exporter import export_template_workbook

LEAGUE_EXCLUDE_PATTERN = re.compile(r"降|升|超冠|盃|友誼|杯|公開")


def filter_excluded_leagues(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Remove rows whose league name contains excluded keywords."""
    return [row for row in rows if not LEAGUE_EXCLUDE_PATTERN.search(row.get("league", ""))]


st.set_page_config(page_title="Daily Trading 生成", layout="centered")
st.title("Daily Trading 生成")


def _empty_parse() -> dict[str, object]:
    """Return a stub parse result when MID file is not provided."""
    return {
        "source_file": "(未上傳)",
        "blocks": [],
        "team_pool_rows": [],
        "unique_values": [],
        "stats": {
            "front_anchor_count": 0,
            "tail_anchor_count": 0,
            "block_count": 0,
            "non_empty_text_count": 0,
            "unique_text_count": 0,
        },
        "warnings": [],
    }


def run_pipeline(main_file, sub_file, selected_date: date, update_status, progress_container) -> dict[str, object]:
    clear_detail_cache()

    update_status("正在解析Top&Weak表…")
    main_parse = parse_anchor_workbook(main_file, main_file.name)

    if sub_file is not None:
        update_status("正在解析MID表…")
        sub_parse = parse_anchor_workbook(sub_file, sub_file.name)
    else:
        sub_parse = _empty_parse()

    update_status("正在抓取數據…")
    merged_matches, crawl_summary = fetch_merged_matches_for_date(selected_date.strftime("%Y%m%d"))

    update_status("正在生成HDP Daily Trading 結果…")
    handicap_result = build_handicap_matches(
        merged_matches,
        main_parse["team_pool_rows"],
        sub_parse["team_pool_rows"],
    )

    update_status("正在生成OU Daily Trading 結果…")
    totals_result = build_totals_matches(
        merged_matches,
        main_parse["team_pool_rows"],
        sub_parse["team_pool_rows"],
    )

    filtered_handicap_rows = filter_excluded_leagues(handicap_result["combined_rows"])
    filtered_totals_rows = filter_excluded_leagues(totals_result["debug_rows"])

    hdp_progress = progress_container.progress(0.0, text="正在抓取HDP詳情…")
    enhanced_handicap_rows, handicap_detail_summary = enrich_records_with_detail(
        filtered_handicap_rows,
        market_type="handicap",
        progress_callback=lambda pct, label: hdp_progress.progress(pct, text=f"正在抓取HDP詳情… {label}"),
    )
    hdp_progress.empty()

    ou_progress = progress_container.progress(0.0, text="正在抓取OU詳情…")
    enhanced_totals_rows, totals_detail_summary = enrich_records_with_detail(
        filtered_totals_rows,
        market_type="totals",
        progress_callback=lambda pct, label: ou_progress.progress(pct, text=f"正在抓取OU詳情… {label}"),
    )
    ou_progress.empty()

    update_status("正在匯出 Excel…")
    handicap_bytes, handicap_export_stats = export_template_workbook(
        enhanced_handicap_rows,
        sheet_title="handicap",
    )
    totals_bytes, totals_export_stats = export_template_workbook(
        enhanced_totals_rows,
        sheet_title="totals",
    )

    export_date = selected_date.strftime("%Y-%m-%d")

    return {
        "main_parse": main_parse,
        "sub_parse": sub_parse,
        "crawl_summary": crawl_summary,
        "handicap_result": handicap_result,
        "totals_result": totals_result,
        "handicap_detail_summary": handicap_detail_summary,
        "totals_detail_summary": totals_detail_summary,
        "handicap_export_stats": handicap_export_stats,
        "totals_export_stats": totals_export_stats,
        "handicap_bytes": handicap_bytes,
        "totals_bytes": totals_bytes,
        "handicap_filename": f"{export_date}_HDP Daily Trading.xlsx",
        "totals_filename": f"{export_date}_OU Daily Trading.xlsx",
    }


main_file = st.file_uploader("上傳Top&Weak表 Excel", type=["xlsx", "xlsm", "xltx", "xltm"], key="main_excel")
sub_file = st.file_uploader("上傳MID表 Excel（可選）", type=["xlsx", "xlsm", "xltx", "xltm"], key="sub_excel")
selected_date = st.date_input("選擇日期", value=date.today(), format="YYYY-MM-DD")

status_box = st.empty()

if "generated_result" not in st.session_state:
    st.session_state.generated_result = None

if st.button("開始生成", type="primary", use_container_width=True):
    if main_file is None:
        st.error("請先上傳Top&Weak表 Excel。")
    else:
        try:
            progress_container = st.container()
            result = run_pipeline(
                main_file,
                sub_file,
                selected_date,
                update_status=lambda message: status_box.info(message),
                progress_container=progress_container,
            )
            st.session_state.generated_result = result
            status_box.success("匯出完成")
        except Exception as exc:
            st.session_state.generated_result = None
            status_box.empty()
            st.error(f"處理失敗：{exc}")
            with st.expander("錯誤詳情"):
                st.code(traceback.format_exc())


result = st.session_state.generated_result
if result:
    st.subheader("生成結果")
    col1, col2, col3 = st.columns(3)
    col1.metric("Top&Weak表球隊數", len(result["main_parse"]["team_pool_rows"]))
    col2.metric("MID表球隊數", len(result["sub_parse"]["team_pool_rows"]))
    col3.metric("當天比賽數", result["crawl_summary"]["matches_count"])

    col4, col5 = st.columns(2)
    col4.metric("HDP Matches", result["handicap_export_stats"]["record_count"])
    col5.metric("OU Matches", result["totals_export_stats"]["record_count"])

    with st.expander("Debug"):
        st.write(
            {
                "main_excel_stats": result["main_parse"]["stats"],
                "sub_excel_stats": result["sub_parse"]["stats"],
                "crawler_summary": result["crawl_summary"],
                "handicap_stats": result["handicap_result"]["stats"],
                "totals_stats": result["totals_result"]["stats"],
                "handicap_detail_summary": result["handicap_detail_summary"],
                "totals_detail_summary": result["totals_detail_summary"],
                "handicap_export_stats": result["handicap_export_stats"],
                "totals_export_stats": result["totals_export_stats"],
            }
        )

    with st.expander("錨點warnings"):
        all_warnings = result["main_parse"]["warnings"] + result["sub_parse"]["warnings"]
        if all_warnings:
            for message in all_warnings:
                st.text(message.replace("Warning:", "warnings："))
        else:
            st.caption("沒有warnings")

    st.download_button(
        "下載HDP Daily Trading",
        data=result["handicap_bytes"],
        file_name=result["handicap_filename"],
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    st.download_button(
        "下載OU Daily Trading",
        data=result["totals_bytes"],
        file_name=result["totals_filename"],
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
