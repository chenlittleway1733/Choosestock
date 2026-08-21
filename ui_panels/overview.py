"""Top-level overview panels for ui_main.render_main_page."""

from ui_common import st


def render_empty_stock_prompt():
    """Render first-load guidance when no stock is selected."""
    st.markdown(
        """
        <div style="
            margin-top: 2.5rem;
            padding: 1.4rem 1.6rem;
            border: 1px solid rgba(0,0,0,0.10);
            border-radius: 14px;
            background: rgba(127,127,127,0.07);
            max-width: 820px;
        ">
            <div style="font-size:1.35rem; font-weight:800; margin-bottom:0.55rem;">
                🔎 請先輸入股票代號或使用左側下拉選股查詢
            </div>
            <div style="font-size:1.02rem; line-height:1.8; color:rgba(120,120,120,0.95);">
                可在左側「輸入台股代號」欄位輸入，例如 <b>2330</b>、<b>3037</b>、<b>2454</b>，
                輸入後請按 <b style="color:#ff8c00;">Enter</b> 確認送出；也可以從「快速選股名單」下拉選擇股票。
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
