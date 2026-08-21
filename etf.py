"""ETF exposure panel for ui_main.render_main_page."""

from ui_common import *


def _render_etf_holder_table(rows, title, source_tag):
    rows = rows or []
    if not rows:
        return False
    table_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        weight = row.get("weight")
        try:
            weight_text = f"{float(weight):.2f}%" if weight is not None and str(weight).strip() != "" else "N/A"
        except Exception:
            weight_text = str(weight) if weight else "N/A"
        table_rows.append({
            "ETF名稱": row.get("etf_name") or "",
            "代號": row.get("etf_code") or "",
            "持股比例": weight_text,
            "資料日期": row.get("data_date") or "來源未揭露",
            "來源": row.get("source") or source_tag,
            "資料性質": row.get("data_type") or source_tag,
        })
    if not table_rows:
        return False
    st.markdown(title)
    st_dataframe(pd.DataFrame(table_rows), hide_index=True)
    return True


def render_etf_exposure_panel(*, curr_id, stock_name):
    """Render fast ETF exposure and optional AI ETF lookup.

    Returns fast-query ETF rows so the prompt pack can stay synchronized with
    the panel shown on screen.
    """
    st.markdown("#### 📌 主要 ETF 持有概況")
    with st.expander(f"查看含有 {stock_name} ({curr_id}) 的 ETF", expanded=False):
        st.caption("一般頁面僅做快速查詢，不使用 AI、不掃描 MoneyDJ / Pocket / CMoney 快取，避免等待過久。此區主要來自 Yahoo 個股 ETF 頁，可能只涵蓋主要 / 前十大 ETF，不代表完整 ETF 持股清單。")

        try:
            etf_holders = get_stock_etf_holders(curr_id, stock_name)
        except Exception as exc:
            etf_holders = []
            st.warning(f"⚠️ ETF 快速資料源暫時無法取得：{str(exc)[:120]}")

        has_system_etf = _render_etf_holder_table(etf_holders, "**主要 / 前十大 ETF 快速查詢**", "主要/前十大快速查詢")
        if not has_system_etf:
            st.info("目前快速資料源查無 ETF 持有資料，或網站版面暫時無法解析。")

        st.caption("⚠️ 此區不保證完整。像 00981A 這類主動式 ETF 可能因 Yahoo 個股頁只列主要/前十大而未出現；需要完整交叉檢查時，請按下方 AI 按鈕。")

        st.markdown("---")
        st.markdown("#### 🤖 AI 查完整 ETF 持有狀況")
        st.caption("此按鈕與『AI 全方位校對與補齊財報』分開執行；只有按下時才會使用 AI + 搜尋補查 ETF，不會拖慢財報校對。")

        if "ai_etf_holders" not in st.session_state:
            st.session_state.ai_etf_holders = {}

        if st.button(
            "🤖 AI 查完整 ETF 持有狀況",
            disabled=not st.session_state.api_key,
            key=f"ai_etf_lookup_{curr_id}",
            use_container_width=True,
            help="獨立查詢 ETF 持股；會特別檢查主動式 ETF，例如 00981A、00987A、00988A、00400A、00403A。",
        ):
            with st.spinner("AI 正在獨立查詢 ETF 持有狀況，請稍候...（不會執行財報校對）"):
                ai_etf_data = get_etf_holders_from_ai(curr_id, stock_name, st.session_state.api_key, get_selected_model_id())
                st.session_state.ai_etf_holders[curr_id] = ai_etf_data
            st.rerun()

        ai_etf_data = st.session_state.ai_etf_holders.get(curr_id) if isinstance(st.session_state.get("ai_etf_holders"), dict) else None
        if isinstance(ai_etf_data, dict) and ai_etf_data.get("error"):
            st.error(f"AI ETF 查詢失敗：{ai_etf_data.get('error')}")
        elif isinstance(ai_etf_data, dict):
            ai_etf_rows = ai_etf_data.get("etf_holders_ai", [])
            if ai_etf_rows:
                _render_etf_holder_table(ai_etf_rows, "**🤖 AI 完整 ETF 補查結果**", "AI完整ETF補查")
                st.caption("⚠️ AI ETF 資料為獨立聯網補查結果，只作交叉比對；正式持股仍請以投信公告、PCF 或 ETF 官方持股明細為準。")
            else:
                st.info("AI 已查詢，但沒有回傳可用的 ETF 持股清單。")
            if ai_etf_data.get("summary"):
                st.caption(f"AI 摘要：{ai_etf_data.get('summary')}")
        else:
            st.caption("尚未執行 AI ETF 補查。")

    st.markdown("---")
    return etf_holders
