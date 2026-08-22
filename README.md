# WAY投資戰情室-2.5版

WAY投資戰情室-2.5版 Streamlit 專案。

主畫面不顯示快速跳轉列；即時報價右上方提供 AI 全方位校對與補齊財報，報價下方依序呈現 TTM/FY1/FY2/FY3 計算價與法人目標價。

啟動保護：若雲端的 `ui_panels/financials.py` 或 `ui_context/prompt_context.py` 仍是舊版，`ui_main.py` 會直接使用內建 TTM/FY 計算與精簡提示詞功能，不顯示部署警告，也不再因新函式匯入失敗而中斷。交付 ZIP 採 Streamlit 專案根目錄格式，解壓後會直接看到 `app.py`、`ui_panels/` 與 `ui_context/`。

月營收查詢採 Yahoo → FinMind → MOPS 快速備援；MOPS 舊式逐月、逐市場長循環預設關閉。外部網站阻擋時會在短時間內自動跳過，不再讓整個頁面停在 `Running get_monthly_revenue(...)`。

此精簡版已移除 V3 市場推理引擎及其 AI Gateway、回測、權重最佳化、告警、自動報告、策略漏斗掃描器、籌碼集中度追蹤、AI 聯網議題選股、模型資料驗證閘門，以及國際連動與今日趨勢推估；保留個股估值、資料品質、Dynamic Cap、財報、個股籌碼、ETF 與技術分析。

## Dynamic Cap v18.2

- Base / Soft / Hard 改採 `dynamic_cap_v18_2_stock_caps.json` 逐股清冊，正式估值使用 Company Base / Soft / Hard。
- 共 277 檔：249 檔有倍率，17 檔 P/E 不適用，11 檔資料不足；不回退 v18.1 或產業預設倍率。
- 已套用 2026-08-22 新清冊：245 檔倍率更新；23 檔標記為轉型／混合型。第二產業倍率可用時顯示兩套獨立價格帶，資料不足則保留「—」，兩套禁止平均。
- 市場熱度僅用於判斷現價位置，不再上修 Company Hard。
- `v18.2 TTM 參考` 倍率僅能乘以 TTM EPS；不輸出 FY1 / FY2 / FY3 估值。`v18.2 暫行前瞻` 僅搭配同年度 FY1 EPS。

## 法人目標價與 FY EPS

- 法人目標價先由 yfinance `analyst_price_targets` 程式抓取，缺欄再用 `Ticker.info` 與 Yahoo 頁面解析備援。
- FY1 / FY2 / FY3 EPS 先由 yfinance `earnings_estimate`、`eps_trend` 程式抓取；無年份的單一 `forwardEps` 不會冒充 FY1。
- 點擊「啟動 AI 全方位校對與補齊財報」後，程式既有值會被保護，AI 只補仍為空白的欄位並交叉校對。
- AI 的 FY EPS 必須帶有可解析且連續的年度；目標價與 FY EPS 必須有可追蹤來源，否則不納入正式估值。

## 執行環境

- 建議 Python：3.11 以上
- Streamlit Cloud：`runtime.txt` 已指定 `python-3.11`
- 本機若有 pyenv/asdf，可讀取 `.python-version` 使用 Python 3.11

## 本機啟動

```bash
python -m pip install -r requirements.txt
python tools/check_runtime.py
streamlit run app.py
```

登入密碼請在 Streamlit Secrets 或本機 `.streamlit/secrets.toml` 設定：

```toml
APP_PASSWORD = "你的密碼"
```

## 測試

```bash
python -m unittest tests/test_core_models.py
```

## 打包

```bash
python tools/build_clean_package.py
```

打包規則由 `.packageignore` 控制；預設會排除舊 zip、Python cache、macOS `._*` metadata、`tmp/`、`output/` 與本機 secrets。

部署到 Streamlit Cloud 的完整步驟請見 [`DEPLOY_STREAMLIT.md`](DEPLOY_STREAMLIT.md)。
