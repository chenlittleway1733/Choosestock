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

提交完成後，在 Streamlit Cloud 重新啟動或重新部署 App。若所有檔案已完整覆蓋，首頁的「新舊模組混用」警告就不會再出現。
