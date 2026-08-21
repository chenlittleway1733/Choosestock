"""Technical chart panel for ui_main.render_main_page."""

from ui_common import *


def _safe_val(series, fallback=0):
    if len(series) == 0:
        return fallback
    val = series.iloc[-1]
    return val if not pd.isna(val) else fallback


def _ma_trend(ma_series):
    if len(ma_series) < 2 or pd.isna(ma_series.iloc[-1]):
        return 0.0, "-", "#aaa"
    last_val = ma_series.iloc[-1]
    prev_val = ma_series.iloc[-2]
    if pd.isna(prev_val):
        return last_val, "-", "#aaa"
    if last_val > prev_val:
        return last_val, "▲", "#ff4d4d"
    if last_val < prev_val:
        return last_val, "▼", "#00cc66"
    return last_val, "-", "#aaa"


def render_technical_chart_panel(*, curr_id, hist):
    st.markdown("### 🤖 專業技術線圖與量化型態分析")

    chart_tf = st.radio("切換 K 線週期：", ["60分線", "日線", "週線", "月線"], index=1, horizontal=True)

    if chart_tf == "日線":
        chart_df = hist.copy()
    else:
        with st.spinner(f"載入 {chart_tf} 數據中..."):
            chart_df = get_chart_data(curr_id, chart_tf, st.session_state.fugle_key)

    if chart_df is None or chart_df.empty:
        full_df = hist.copy()
    else:
        full_df = chart_df.copy()

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col not in full_df.columns:
            full_df[col] = 0.0

    full_df["MA5"] = full_df["Close"].rolling(5).mean()
    full_df["MA10"] = full_df["Close"].rolling(10).mean()
    full_df["MA20"] = full_df["Close"].rolling(20).mean()
    full_df["MA60"] = full_df["Close"].rolling(60).mean()
    full_df["Vol_MA20"] = full_df["Volume"].rolling(20).mean()

    h9, l9 = full_df["High"].rolling(9).max(), full_df["Low"].rolling(9).min()
    h9_l9_diff = h9 - l9
    h9_l9_diff[h9_l9_diff == 0] = 1e-9
    rsv = (full_df["Close"] - l9) / h9_l9_diff * 100

    k_values, d_values = [50], [50]
    for value in rsv.fillna(50):
        k_values.append(k_values[-1] * (2 / 3) + value * (1 / 3))
        d_values.append(d_values[-1] * (2 / 3) + k_values[-1] * (1 / 3))
    full_df["K"], full_df["D"] = k_values[1:], d_values[1:]

    plot_df = full_df.tail(120).copy()
    inst_df = get_inst_data(curr_id, st.session_state.finmind_key)

    if inst_df is not None and not inst_df.empty:
        temp_dates = pd.to_datetime(plot_df.index)
        if temp_dates.tz is not None:
            temp_dates = temp_dates.tz_localize(None)
        temp_dates = temp_dates.normalize()

        inst_df_aligned = inst_df.copy()
        inst_df_aligned.index = pd.to_datetime(inst_df_aligned.index).normalize()

        plot_df["Foreign"] = temp_dates.map(inst_df_aligned["Foreign"]).fillna(0)
        plot_df["Trust"] = temp_dates.map(inst_df_aligned["Trust"]).fillna(0)
        plot_df["Dealer"] = temp_dates.map(inst_df_aligned["Dealer"]).fillna(0)
    else:
        plot_df["Foreign"] = 0
        plot_df["Trust"] = 0
        plot_df["Dealer"] = 0

    last_close = _safe_val(plot_df["Close"])
    ma5_last = _safe_val(plot_df["MA5"], last_close)
    ma20_last = _safe_val(plot_df["MA20"], last_close)
    ma60_last = _safe_val(plot_df["MA60"], ma20_last)
    k_last = _safe_val(plot_df["K"], 50)
    d_last = _safe_val(plot_df["D"], 50)

    recent_20 = plot_df.tail(20)
    recent_high = recent_20["High"].max() if not recent_20.empty else last_close
    recent_low = recent_20["Low"].min() if not recent_20.empty else last_close

    if not recent_20.empty and "Volume" in recent_20.columns and recent_20["Volume"].sum() > 0:
        max_vol_idx = recent_20["Volume"].idxmax()
        max_vol_day = recent_20.loc[max_vol_idx]
        is_high_vol = max_vol_day["Volume"] > (max_vol_day["Vol_MA20"] * 2)
        is_at_high = max_vol_day["High"] >= (recent_high * 0.95)
        is_dropping = last_close < max_vol_day["Low"]
        high_vol_warning = is_high_vol and is_at_high and is_dropping
        vol_escape_price = max_vol_day["High"]
    else:
        high_vol_warning = False
        vol_escape_price = last_close

    support_price = max(recent_low, ma60_last) if last_close > ma60_last else recent_low
    resist_price = recent_high if last_close > ma20_last else min(recent_high, ma20_last)

    if last_close < ma60_last:
        trend_status, trend_color = "⚠️ 跌破長線支撐 (趨勢轉弱)", "#00cc66"
    elif last_close > ma20_last and ma5_last > ma20_last:
        trend_status, trend_color = "📈 多頭強勢 (站上短中均線)", "#ff4d4d"
    elif last_close < ma20_last and ma5_last < ma20_last:
        trend_status, trend_color = "📉 空頭弱勢 (跌破中線)", "#00cc66"
    else:
        trend_status, trend_color = "↔️ 區間震盪 (方向未明)", "#ffd700"

    if high_vol_warning:
        adv_text, buy_rec, sell_rec = "🚨 【量價警訊】高檔爆出天量且跌破低點，切勿盲目接刀！", "強烈觀望", f"反彈至 {vol_escape_price:.2f} 逃命"
    elif last_close < ma60_last:
        adv_text, buy_rec, sell_rec = "📉 【趨勢轉弱】跌破長期均線，應耐心等待底部確立。", "等待站回均線", f"{ma60_last:.2f} (長線壓力)"
    elif k_last < 25 and k_last > d_last:
        adv_text, buy_rec, sell_rec = "📈 【技術反彈】KD 低檔黃金交叉，可嘗試逢低少量佈局。", f"現價~{support_price:.2f} 附近", f"{resist_price:.2f} (上檔壓力)"
    elif k_last > 80 and k_last < d_last:
        adv_text, buy_rec, sell_rec = "⚠️ 【動能轉弱】KD 高檔死亡交叉，建議適度獲利了結保住利潤。", "暫時觀望", f"現價~{resist_price:.2f} 附近"
    elif last_close > ma20_last:
        adv_text, buy_rec, sell_rec = "🔥 【多方格局】量價配合良好，拉回中線(20MA)有守可伺機介入。", f"{ma20_last:.2f} (中線支撐)", f"{resist_price:.2f} (近期前高)"
    else:
        adv_text, buy_rec, sell_rec = "❄️ 【空方格局】短線均線反壓，反彈至均線壓力區可考慮減碼。", "等待技術面打底", f"{ma20_last:.2f} (中線壓力)"

    st.markdown(f"""
    <div style='background:#1e1e1e; padding:15px; border-radius:8px; border:1px solid #333; margin-bottom:20px;'>
        <h4 style='margin-top:0; color:#fff;'>🎯 演算法量化交易策略</h4>
        <div style='display:flex; justify-content:space-between; flex-wrap:wrap; gap:10px;'>
            <div style='flex:1; min-width:120px;'><div style='color:#aaa; font-size:0.9rem;'>目前趨勢</div><div style='font-size:1.1rem; font-weight:bold; color:{trend_color};'>{trend_status}</div></div>
            <div style='flex:1; min-width:120px;'><div style='color:#aaa; font-size:0.9rem;'>下檔支撐</div><div style='font-size:1.1rem; font-weight:bold; color:#00bfff;'>{support_price:.2f}</div></div>
            <div style='flex:1; min-width:120px;'><div style='color:#aaa; font-size:0.9rem;'>上檔壓力</div><div style='font-size:1.1rem; font-weight:bold; color:#ab82ff;'>{resist_price:.2f}</div></div>
            <div style='flex:1; min-width:120px;'><div style='color:#aaa; font-size:0.9rem;'>建議買點</div><div style='font-size:1.1rem; font-weight:bold; color:#ff4d4d;'>{buy_rec}</div></div>
            <div style='flex:1; min-width:120px;'><div style='color:#aaa; font-size:0.9rem;'>建議賣點</div><div style='font-size:1.1rem; font-weight:bold; color:#00cc66;'>{sell_rec}</div></div>
        </div>
        <div style='margin-top:15px; padding-top:10px; border-top:1px dashed #444;'><span style='color:#aaa; font-size:0.9rem;'>💡 策略解析：</span><span style='color:#ffd700; font-weight:bold;'>{adv_text}</span></div>
    </div>
    """.replace("\n", ""), unsafe_allow_html=True)

    m5_v, m5_d, m5_c = _ma_trend(plot_df["MA5"])
    m10_v, m10_d, m10_c = _ma_trend(plot_df["MA10"])
    m20_v, m20_d, m20_c = _ma_trend(plot_df["MA20"])
    m60_v, m60_d, m60_c = _ma_trend(plot_df["MA60"])

    ma_html = f"""
    <div style='display: flex; gap: 20px; font-size: 1.05rem; padding: 10px 15px; background: #1e1e1e; border-radius: 8px; border: 1px solid #333; margin-bottom: 10px; flex-wrap: wrap; align-items: center;'>
        <div style='color: #fff;'><span style='color: #00bfff; font-size:1.2rem; vertical-align:middle;'>■</span> <b>MA5</b> {m5_v:.2f} <span style='color:{m5_c}; font-size:0.9rem;'>{m5_d}</span></div>
        <div style='color: #fff;'><span style='color: #ab82ff; font-size:1.2rem; vertical-align:middle;'>■</span> <b>MA10</b> {m10_v:.2f} <span style='color:{m10_c}; font-size:0.9rem;'>{m10_d}</span></div>
        <div style='color: #fff;'><span style='color: #ff8c00; font-size:1.2rem; vertical-align:middle;'>■</span> <b>MA20</b> {m20_v:.2f} <span style='color:{m20_c}; font-size:0.9rem;'>{m20_d}</span></div>
        <div style='color: #fff;'><span style='color: #ffd700; font-size:1.2rem; vertical-align:middle;'>■</span> <b>MA60</b> {m60_v:.2f} <span style='color:{m60_c}; font-size:0.9rem;'>{m60_d}</span></div>
    </div>
    """
    st.markdown(clean_html(ma_html), unsafe_allow_html=True)

    fig_k = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.5, 0.25, 0.25], vertical_spacing=0.05, specs=[[{"secondary_y": True}], [{"secondary_y": False}], [{"secondary_y": False}]])

    fig_k.add_trace(go.Candlestick(x=plot_df.index, open=plot_df["Open"], high=plot_df["High"], low=plot_df["Low"], close=plot_df["Close"], name="K線", increasing_line_color="#ff4d4d", decreasing_line_color="#00cc66"), row=1, col=1, secondary_y=False)
    fig_k.add_trace(go.Scatter(x=plot_df.index, y=plot_df["MA5"], mode="lines", name="5MA", line=dict(color="#00bfff", width=2.5)), row=1, col=1, secondary_y=False)
    fig_k.add_trace(go.Scatter(x=plot_df.index, y=plot_df["MA10"], mode="lines", name="10MA", line=dict(color="#ab82ff", width=1.8)), row=1, col=1, secondary_y=False)
    fig_k.add_trace(go.Scatter(x=plot_df.index, y=plot_df["MA20"], mode="lines", name="20MA", line=dict(color="#ff8c00", width=1.8)), row=1, col=1, secondary_y=False)
    fig_k.add_trace(go.Scatter(x=plot_df.index, y=plot_df["MA60"], mode="lines", name="60MA", line=dict(color="#ffd700", width=1.8)), row=1, col=1, secondary_y=False)

    vol_colors = ["#ff4d4d" if c >= o else "#00cc66" for c, o in zip(plot_df["Close"], plot_df["Open"])]
    fig_k.add_trace(go.Bar(x=plot_df.index, y=plot_df["Volume"] / 1000, marker_color=vol_colors, name="成交量(張)", opacity=0.5), row=1, col=1, secondary_y=True)

    f_colors = ["#ff4d4d" if v > 0 else "#00cc66" for v in plot_df["Foreign"]]
    t_colors = ["#ff4d4d" if v > 0 else "#00cc66" for v in plot_df["Trust"]]
    d_colors = ["#ff4d4d" if v > 0 else "#00cc66" for v in plot_df["Dealer"]]
    fig_k.add_trace(go.Bar(x=plot_df.index, y=plot_df["Foreign"], name="外資", marker_color=f_colors, opacity=0.8), row=2, col=1)
    fig_k.add_trace(go.Bar(x=plot_df.index, y=plot_df["Trust"], name="投信", marker_color=t_colors, opacity=0.8), row=2, col=1)
    fig_k.add_trace(go.Bar(x=plot_df.index, y=plot_df["Dealer"], name="自營商", marker_color=d_colors, opacity=0.8), row=2, col=1)

    fig_k.add_trace(go.Scatter(x=plot_df.index, y=plot_df["K"], mode="lines", name="K9", line=dict(color="#00bfff", width=1.5)), row=3, col=1, secondary_y=False)
    fig_k.add_trace(go.Scatter(x=plot_df.index, y=plot_df["D"], mode="lines", name="D9", line=dict(color="#ff8c00", width=1.5)), row=3, col=1, secondary_y=False)

    max_vol = plot_df["Volume"].max() / 1000 if not plot_df["Volume"].empty else 100
    fig_k.update_yaxes(side="left", showgrid=False, showticklabels=False, range=[0, max_vol * 3.5], secondary_y=True, row=1, col=1)
    fig_k.update_yaxes(side="right", mirror=True, showline=True, linecolor="#555", secondary_y=False, row=1, col=1)
    fig_k.update_yaxes(title_text="買賣超(張)", side="right", mirror=True, showline=True, linecolor="#555", row=2, col=1)
    fig_k.update_yaxes(range=[0, 100], dtick=20, side="right", mirror=True, showline=True, linecolor="#555", row=3, col=1)

    if not plot_df.empty and chart_tf == "日線":
        idx_norm = plot_df.index.normalize()
        dt_all = pd.date_range(start=idx_norm[0], end=idx_norm[-1])
        dt_obs = [d.strftime("%Y-%m-%d") for d in idx_norm]
        dt_breaks = [d.strftime("%Y-%m-%d") for d in dt_all if d.strftime("%Y-%m-%d") not in dt_obs]
    else:
        dt_breaks = []

    if chart_tf == "60分線":
        x_fmt = "%m/%d %H:%M"
        rb = [dict(bounds=["sat", "mon"]), dict(bounds=[13.5, 9], pattern="hour")]
    elif chart_tf == "月線":
        x_fmt = "%Y/%m"
        rb = []
    elif chart_tf == "週線":
        x_fmt = "%Y/%m/%d"
        rb = []
    else:
        x_fmt = "%m/%d"
        rb = [dict(bounds=["sat", "mon"])]
        if dt_breaks:
            rb.append(dict(values=dt_breaks))

    fig_k.update_xaxes(rangebreaks=rb, tickformat=x_fmt, showgrid=True, gridcolor="#333", mirror=True, showline=True, linecolor="#555")
    fig_k.update_layout(height=750, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10), template="plotly_dark", hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0))
    st.plotly_chart(fig_k, use_container_width=True)
