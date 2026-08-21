"""Stock title, watchlist, and industry-classification panel."""

from ui_common import (
    SECTOR_MAP,
    get_industry_valuation_profile,
    get_watchlist,
    st,
    toggle_watchlist,
    translate_to_zh,
)


def render_stock_header_panel(*, curr_id, stock_name, info):
    """Render stock heading and industry model summary.

    Returns:
        (sector_display, industry_profile)
    """
    info = info or {}
    col_title, col_star = st.columns([0.85, 0.15])
    with col_title:
        st.markdown(f"### 🏢 {stock_name} ({curr_id})")
    with col_star:
        in_watch = curr_id in get_watchlist()
        btn_label = "⭐ 移除自選" if in_watch else "☆ 加入自選"
        if st.button(btn_label, use_container_width=True):
            toggle_watchlist(curr_id, stock_name)
            st.rerun()

    sector_disp = SECTOR_MAP.get(info.get("sector", "未知"), info.get("sector", "未知"))
    early_ai_fin = st.session_state.ai_fetched_financials.get(curr_id, {}) if hasattr(st.session_state, "ai_fetched_financials") else {}
    if isinstance(early_ai_fin, dict) and early_ai_fin:
        if str(early_ai_fin.get("_stock_id") or curr_id) != str(curr_id):
            early_ai_fin = {}

    industry_profile = get_industry_valuation_profile(
        curr_id,
        stock_name,
        sector_disp,
        info.get("industry", "未知"),
        ai_financials=early_ai_fin,
    )
    st.markdown(
        f"**🏷️ 產業分類：** {sector_disp} / {info.get('industry', '未知')}｜"
        f"估值模型：{industry_profile.get('model_label', '一般產業')}｜"
        f"題材標籤：{industry_profile.get('themes_text', '—')}｜"
        f"分類來源：{industry_profile.get('classification_source', industry_profile.get('mapping_source', '—'))}"
    )
    if industry_profile.get("classification_needs_manual_review"):
        st.warning(
            f"⚠️ 產業分類待確認：{industry_profile.get('classification_warning', '此分類不是正式 stock_mapping.py 指定。')}"
            f"｜可信度：{industry_profile.get('classification_confidence', 'low')}"
            f"｜Dynamic Cap 分類折扣：×{float(industry_profile.get('classification_confidence_factor', 1.0) or 1.0):.2f}"
        )
    if industry_profile.get("pe_trap_warning"):
        st.warning("⚠️ 本產業具有 P/E 陷阱風險：低 P/E 不一定代表低估，請優先檢查 P/B、週期位置、報價或訂單落地。")
    if industry_profile.get("pe_model_suitable") is False:
        st.warning("⚠️ 本分類不適合使用一般 P/E 公式估值作為買進依據，應以事件、訂單、籌碼與財報落地程度評估。")

    with st.expander("📖 查看公司詳細營業項目簡介 (自動英翻中)"):
        st.write(translate_to_zh(info.get("longBusinessSummary", "暫無簡介。")))

    return sector_disp, industry_profile

