# Daily Trading 生成工具（mf_dailytradingtool）

## 這個專案在做什麼？

從 Titan007 網站抓取當日足球賽事和亞洲盤口數據，結合使用者上傳的球隊名單 Excel，自動比對並生成 HDP（讓球盤）和 OU（大小球）兩份 Daily Trading Excel 報表。報表基於預設的 Excel 模板匯出，包含 Crow 公司的盤口變化詳情（早盤/即時盤盤口、水位、R-X/E-X 水位變動指標）。

## 目前狀態

核心功能完整可用：
- ✅ 上傳 Top&Weak 表 + 可選 MID 表
- ✅ 抓取 Titan007 賽事列表 + 盤口 API
- ✅ HDP / OU 比對邏輯
- ✅ 抓取每場比賽的 Crow 公司盤口變化詳情
- ✅ 計算 R-X（全程水位變動）和 E-X（早盤水位變動）指標
- ✅ 基於模板的 Excel 匯出（HDP 和 OU 各自使用獨立模板）
- ✅ 聯賽過濾（排除降/升/超冠/盃/友誼/杯）
- ✅ Docker 部署（NAS runtime clone）

## 資料流程（偽代碼）

```
輸入：
  main_file = Top&Weak 表 Excel（必要）
  sub_file  = MID 表 Excel（可選，未上傳時 sub_team_pool_rows = []）
  selected_date = 使用者選擇的日期

步驟 1：解析 Excel
  for each worksheet in workbook:
    for each cell in worksheet:
      if cell.value in {"前", "尾"}:
        讀取該 cell 下方 10 格的球隊名稱
        每個非空值 → team_pool_rows[] 記錄 {source_file, sheet_name, anchor_type, anchor_cell, team_name}

步驟 2：抓取賽事
  main_page = GET titan007 主頁（gb18030 編碼）
  odds_api  = GET titan007 盤口 API（UTF-8）
  解析 HTML table#table_live → matches[]
  解析 API 文字（! 分隔記錄，^ 分隔欄位）→ odds_by_sid{}
  合併：每場比賽加上 asian_handicap_raw + asian_handicap_display

步驟 3：HDP 比對
  過濾掉平手盤（asian_handicap_display 為 "平手" 的比賽）
  for each match:
    if asian_handicap_display 為空:
      嘗試 home/away 兩邊在 main_index 和 sub_index 中找匹配
      優先取 main，main 沒有才取 sub
    else:
      if 盤口含 "*" → target = away_team
      else → target = home_team
      在 main_index 找 target → main_row
      在 sub_index 找 target → sub_row
      main 命中 → 加入 combined_rows
      sub 命中 → 加入 combined_rows
      都沒命中 → unmatched

步驟 4：OU 比對
  for each match:
    在 main/sub index 中找 home_team 和 away_team
    特殊邏輯：如果雙方都在同一個 index 的同類錨點（前/尾）中
      → 根據盤口方向選擇對應一方
    否則：main 優先，sub 備選

步驟 5：聯賽過濾
  過濾掉 league 包含「降」「升」「超冠」「盃」「友誼」「杯」的結果

步驟 6：抓取 Crow 公司盤口變化詳情（detail_enricher）
  for each matched_record:
    # 決定抓取頁面
    if market_type == "handicap":
      listing_url = vip.titan007.com/AsianOdds_n.aspx?id={sid}
      detail_path = changeDetail/handicap.aspx
    else:  # totals
      listing_url = vip.titan007.com/OverDown_n.aspx?id={sid}
      detail_path = changeDetail/overunder.aspx

    # 抓取列表頁，找 Crow 公司的詳情連結
    listing_html = GET listing_url（UTF-8，重試 3 次）
    listing_page_score = 從 #headVs 區塊解析比分
    crow_detail_url = 在 listing_html 中找包含 "Crow" 的 <tr> 的詳情 <a> 連結

    if crow_detail_url 為空:
      只回傳比分，其他欄位空白
      continue

    # 抓取變化明細頁
    detail_html = GET crow_detail_url（gb18030，重試 3 次）
    detail_rows = 解析 7 欄表格（時間、比分、主隊水位、盤口、客隊水位、變更時間、狀態）
    只保留 status in {"早", "即", "滚"} 的記錄

    # 分類
    early_rows  = status == "早" 的記錄（早盤）
    instant_rows = status == "即" 的記錄（即時盤）
    # 原始順序是「最新在前」
    early_first  = early_rows 中時間最早的（列表最後一筆）
    early_last   = early_rows 中時間最晚的（列表第一筆）
    instant_last = instant_rows 中時間最晚的（列表第一筆）

    # 盤口值轉換
    if market_type == "handicap":
      handicap_value = HandicapNormalizer.normalize(handicap_text)
      # "半球" → 0.5, "受半/一" → -0.75
    else:  # totals
      handicap_value = parse_total_line(handicap_text)
      # "2.5" → 2.5, "2/2.5" → 2.25（取平均）

    # 水位格式化
    odds_display = format_odds_pair(home_rate, away_rate)
    # 0.85, 0.95 → "85/95"

    # 決定追蹤哪邊水位（rate_key）
    if market_type == "handicap":
      if matched_side == "away" → rate_key = "away_rate"
      if matched_side == "home" → rate_key = "home_rate"
      else: 看盤口文字有無「受」字決定
    if market_type == "totals":
      看最早那筆的大小水位誰低
      over_rate < under_rate → rate_key = "home_rate", prefix = "L"
      under_rate < over_rate → rate_key = "away_rate", prefix = "S"

    # R-X 計算（早盤 + 即時盤的水位變動累計）
    # E-X 計算（僅早盤的水位變動累計）
    # 演算法（calculate_segment_x）：
    #   1. 按時間正序排列
    #   2. 按「盤口值相同」分段
    #   3. 每段：(最晚水位 - 最早水位) * 100，四捨五入為整數
    #   4. 所有段加總 = X 值
    R-X = calculate_segment_x(detail_rows, rate_key, {"早", "即"})
    if market_type == "handicap":
      E-X = calculate_segment_x(detail_rows, rate_key, {"早"})
    else:
      E-X = prefix + calculate_segment_x(detail_rows, rate_key, {"早"})

    輸出欄位：
      time_first_handicap  = 最早早盤盤口
      time_first_odds      = 最早早盤水位
      league_handicap      = 最新早盤盤口（僅 HDP）
      league_odds          = 最新早盤水位（僅 HDP）
      time_second_handicap = 最新即時盤盤口
      time_second_odds     = 最新即時盤水位
      score_compact        = 比分（如 "21"）
      rx_value             = R-X 數值
      ex_value             = E-X 數值

步驟 7：匯出模板版 Excel（template_exporter）
  載入對應模板：
    HDP → Daily Trading_HDP_Demo.xlsx
    OU  → Daily Trading_OU_Demo.xlsx
  排序規則：page_order → match_time → league → team_name
  每筆記錄佔 6 行（1 行資料 + 5 行附加資訊）
  從第 2 行開始寫入（第 1 行是模板表頭）
  寫入欄位：A/B/C 欄（基本資訊）+ F 欄（R-X/E-X 標籤和數值）
  模板的 D 欄有預設公式，根據 E-X 值和 G 欄做分級判斷
  使用者拿到報表後，手動複製 A:C 和 F 欄內容到生產環境報表
```

## 錨點解析規則

| 錨點值 | 意義 | 讀取範圍 |
|--------|------|----------|
| 前     | 前段球隊 | 錨點下方 1~10 格 |
| 尾     | 尾段球隊 | 錨點下方 1~10 格 |

- 同一個球隊可能出現在多個錨點區塊中
- 比對時優先選「前」錨點的記錄

## 盤口顯示轉換

letgoal 原始值（float）→ 中文顯示：
- 0 → 平手
- 0.25 → 平/半
- 0.5 → 半球
- 負值加 `*` 前綴（表示客隊讓球）

## 盤口標準化（HandicapNormalizer）

中文盤口文字 → 數值：
- 支援繁體和簡體（如「兩球」和「两球」都映射到 2.0）
- 「受」「受讓」前綴表示負值（如「受半球」→ -0.5）
- 支援數字型盤口和分數盤口（如 "2.5/3" → 2.75）

## 模板結構

每個 block 佔 6 行，欄位配置：

| 行偏移 | A 欄 | B 欄 | C 欄 | F 欄 |
|--------|------|------|------|------|
| +0 | 開賽時間 | 聯賽 | 隊伍 | "R-X" 標籤 |
| +1 | 最早早盤盤口 | 最新早盤盤口(HDP) | M 標記(sub) | R-X 值 |
| +2 | 最早早盤水位 | 最新早盤水位(HDP) | — | "E-X" 標籤 |
| +3 | 最新即時盤盤口 | — | 比分 | E-X 值 |
| +4 | 最新即時盤水位 | — | — | — |
| +5 | （空白行） | — | — | — |

模板的 D 欄有預設公式（引用 F 和 G 欄），用於分級判斷。
HDP 模板：D 欄公式直接比較 F 欄的 E-X 數值（純數字）。
OU 模板：D 欄公式用 RIGHT() 去掉 E-X 值的 L/S 前綴再比較。

## 關鍵決策紀錄

- 2025-07：MID 表改為可選上傳，未上傳時 sub_team_pool_rows 傳空 list
- 2025-07：新增聯賽過濾，排除「降/升/超冠/盃」關鍵字的比賽
- 2025-07：新增「友誼」「杯」到聯賽過濾關鍵字
- 2025-07：新增 Crow 公司盤口變化詳情抓取和 R-X/E-X 計算
- 2025-07：模板版匯出取代舊版基本匯出（從 4 個下載按鈕改為 2 個）
- 2025-07：HDP 和 OU 改為使用各自獨立的模板檔案
- 部署方式：NAS 使用 runtime clone（不走 GitHub Actions CI build image）
- 2025-07：刪除舊版 exporter.py 死碼，已完全由 template_exporter.py 取代
- 2025-07：詳情抓取加入進度條顯示和 0.3 秒節流

## 已知限制 / 待辦

- Titan007 網站結構變更會導致爬蟲失敗
- 球隊名稱比對是精確匹配（清除排名標記後），這是刻意的設計決策，不需要模糊匹配
- 未匹配球隊是正常的業務行為，不是所有球隊都會匹配到
- 每次容器重啟才會拉取最新程式碼
- `.github/workflows/docker.yml` 存在但目前未使用
- 詳情抓取是逐筆同步進行，記錄多時會比較慢（每筆 2 個 HTTP 請求，有重試機制）
- 模板的 D/G 欄公式由使用者在生產環境報表中維護，程式只寫入 A/B/C/F 欄
