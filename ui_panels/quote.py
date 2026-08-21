"""Quote panel for ui_main.render_main_page."""

from ui_common import *


def _quote_color(value, base):
    if value > base:
        return "#ff4d4d"
    if value < base:
        return "#00cc66"
    return "#ffffff"


def render_quote_panel(*, hist, info):
    """Render latest quote data and return values reused by valuation logic."""
    st.markdown("#### ⚡ 即時報價與交易資訊")
    info = info or {}
    today_data = hist.iloc[-1]
    prev_data = hist.iloc[-2] if len(hist) > 1 else today_data

    curr_p = s_float(today_data.get("Close"), 0)
    open_p = s_float(today_data.get("Open"), 0)
    high_p = s_float(today_data.get("High"), 0)
    low_p = s_float(today_data.get("Low"), 0)
    vol_shares = s_float(today_data.get("Volume"), 0)

    vol_lots = int(vol_shares // 1000) if vol_shares else 0
    prev_vol_lots = int(s_float(prev_data.get("Volume"), 0) // 1000) if len(hist) > 1 else 0

    prev_close = s_float(info.get("previousClose"), s_float(prev_data.get("Close"), 0))
    change = curr_p - prev_close if prev_close else 0
    change_pct = (change / prev_close) * 100 if prev_close else 0
    amp = ((high_p - low_p) / prev_close) * 100 if prev_close and prev_close > 0 else 0
    avg_price = (high_p + low_p + curr_p) / 3 if curr_p else 0
    turnover_100m = (vol_shares * avg_price) / 100000000

    c_curr = _quote_color(curr_p, prev_close)
    c_open = _quote_color(open_p, prev_close)
    c_high = _quote_color(high_p, prev_close)
    c_low = _quote_color(low_p, prev_close)
    c_change = _quote_color(change, 0)
    arrow = "▲" if change > 0 else ("▼" if change < 0 else "")

    quote_html = f"""
    <style>
    .q-container {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px 30px; background: #1e1e1e; padding: 15px 20px; border-radius: 8px; font-family: sans-serif; margin-bottom: 20px; border: 1px solid #333; }}
    .q-item {{ display: flex; justify-content: space-between; border-bottom: 1px solid #333; padding-bottom: 4px; }}
    .q-label {{ color: #aaa; font-size: 1rem; }}
    .q-val {{ font-weight: bold; font-size: 1.1rem; }}
    </style>
    <div class="q-container">
        <div class="q-item"><span class="q-label">成交</span><span class="q-val" style="color: {c_curr};">{curr_p:,.2f}</span></div>
        <div class="q-item"><span class="q-label">昨收</span><span class="q-val" style="color: #fff;">{prev_close:,.2f}</span></div>
        <div class="q-item"><span class="q-label">開盤</span><span class="q-val" style="color: {c_open};">{open_p:,.2f}</span></div>
        <div class="q-item"><span class="q-label">漲跌幅</span><span class="q-val" style="color: {c_change};">{arrow} {abs(change_pct):.2f}%</span></div>
        <div class="q-item"><span class="q-label">最高</span><span class="q-val" style="color: {c_high};">{high_p:,.2f}</span></div>
        <div class="q-item"><span class="q-label">漲跌</span><span class="q-val" style="color: {c_change};">{arrow} {abs(change):.2f}</span></div>
        <div class="q-item"><span class="q-label">最低</span><span class="q-val" style="color: {c_low};">{low_p:,.2f}</span></div>
        <div class="q-item"><span class="q-label">總量 (張)</span><span class="q-val" style="color: #ffd700;">{vol_lots:,}</span></div>
        <div class="q-item"><span class="q-label">均價</span><span class="q-val" style="color: #fff;">{avg_price:,.2f}</span></div>
        <div class="q-item"><span class="q-label">昨量 (張)</span><span class="q-val" style="color: #fff;">{prev_vol_lots:,}</span></div>
        <div class="q-item"><span class="q-label">成交金額(億)</span><span class="q-val" style="color: #fff;">{turnover_100m:,.2f}</span></div>
        <div class="q-item"><span class="q-label">振幅</span><span class="q-val" style="color: #fff;">{amp:.2f}%</span></div>
    </div>
    """
    st.markdown(clean_html(quote_html), unsafe_allow_html=True)

    return {
        "curr_p": curr_p,
        "open_p": open_p,
        "high_p": high_p,
        "low_p": low_p,
        "vol_shares": vol_shares,
        "vol_lots": vol_lots,
        "prev_vol_lots": prev_vol_lots,
        "prev_close": prev_close,
        "change": change,
        "change_pct": change_pct,
        "amp": amp,
        "avg_price": avg_price,
        "turnover_100m": turnover_100m,
    }
