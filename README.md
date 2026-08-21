# WAY投資戰情室-2.5版

WAY投資戰情室-2.5版 Streamlit 專案。

主畫面上方提供頁內快速導覽列，可直接跳至個股概覽、ETF、財報新聞、股票預估價、估值風控、法人目標價、籌碼、AI 分析、同業河流與技術分析。

此精簡版已移除 V3 市場推理引擎及其 AI Gateway、回測、權重最佳化、告警、自動報告、策略漏斗掃描器、籌碼集中度追蹤、AI 聯網議題選股、模型資料驗證閘門，以及國際連動與今日趨勢推估；保留個股估值、資料品質、Dynamic Cap、財報、個股籌碼、ETF 與技術分析。

## Dynamic Cap v18.2

- Base / Soft / Hard 改採 `dynamic_cap_v18_2_stock_caps.json` 逐股清冊，正式估值使用 Company Base / Soft / Hard。
- 共 277 檔：249 檔有倍率，17 檔 P/E 不適用，11 檔資料不足；不回退 v18.1 或產業預設倍率。
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
