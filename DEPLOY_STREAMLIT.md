# Streamlit Cloud 完整部署

此 ZIP 已採「專案根目錄」格式。解壓後，最外層應立即看到：

- `app.py`
- `requirements.txt`
- `ui_main.py`
- `ui_panels/`
- `ui_context/`

請將解壓後最外層的全部檔案與資料夾，一次複製到 GitHub 的 `choosestock` 專案根目錄並覆蓋舊檔；不要只上傳 `ui_main.py`，也不要再建立一層 `way_stock/`。

同一次提交至少要確認下列檔案已更新：

- `ui_panels/financials.py`
- `ui_context/prompt_context.py`
- `ui_main.py`
- `model_data_loader.py`
- `dynamic_cap_v18_2_stock_caps.json`（專案根目錄）

若網站仍顯示聯發科舊倍率 `31.07x / 36.51x / 38.38x`，代表雲端仍在讀舊清冊。可先只覆蓋根目錄的 `model_data_loader.py`、`dynamic_cap_v18_2_stock_caps.json` 與 `ui_main.py`，再重新啟動 App；新版聯發科主要倍率應為 `26.23x / 28.76x / 51.40x`，第二定價倍率為 `43.66x / 47.55x / 56.05x`。

提交完成後，在 Streamlit Cloud 重新啟動或重新部署 App。`ui_main.py` 已內建 TTM/FY 計算與精簡提示詞相容功能；即使這兩個子模組暫時未同步，系統也會安靜切換，不再顯示「新舊模組混用」警告。
