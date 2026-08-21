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

提交完成後，在 Streamlit Cloud 重新啟動或重新部署 App。`ui_main.py` 已內建 TTM/FY 計算與精簡提示詞相容功能；即使這兩個子模組暫時未同步，系統也會安靜切換，不再顯示「新舊模組混用」警告。
