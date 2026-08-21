"""Valuation river charts for ui_main.render_main_page."""

from ui_common import *


def render_valuation_river_charts(*, hist, df_per_bk):
    if df_per_bk is None or df_per_bk.empty:
        return

    st.markdown("### 🌊 估值位階雙河流圖 (P/E & P/B River)")
    st.markdown("<small style='color:gray;'>*實戰密技：『成長股』看本益比判斷潛力；『景氣循環股』(航運/鋼鐵/面板) 獲利不穩定，必須看淨值比(P/B)河流圖抄底！*</small>", unsafe_allow_html=True)

    h_reset = hist.copy()
    h_reset.index.name = "Date"
    h_reset = h_reset.reset_index()

    if h_reset["Date"].dt.tz is not None:
        h_reset["Date"] = h_reset["Date"].dt.tz_localize(None)
    h_reset["Date_only"] = h_reset["Date"].dt.date

    d_per = df_per_bk.drop_duplicates(subset=["date"], keep="last").copy()
    d_per["date_only"] = d_per["date"].dt.date
    h_reset = h_reset.drop_duplicates(subset=["Date_only"], keep="last")

    merged = pd.merge(h_reset, d_per, left_on="Date_only", right_on="date_only", how="inner").sort_values("Date_only")
    if merged.empty:
        st.markdown("---")
        return

    tab_pe, tab_pb = st.tabs(["🌊 本益比河流圖 (P/E River)", "⚓ 股價淨值比河流圖 (P/B River - 循環股剋星)"])

    with tab_pe:
        merged_pe = merged[merged["PER"] > 0].copy()
        if len(merged_pe) > 60:
            merged_pe["EPS_calc"] = merged_pe["Close"] / merged_pe["PER"]
            pe_quantiles = merged_pe["PER"].quantile([0.1, 0.25, 0.5, 0.75, 0.9]).values

            fig_river = go.Figure()
            b1 = merged_pe["EPS_calc"] * pe_quantiles[0]
            b2 = merged_pe["EPS_calc"] * pe_quantiles[1]
            b3 = merged_pe["EPS_calc"] * pe_quantiles[2]
            b4 = merged_pe["EPS_calc"] * pe_quantiles[3]
            b5 = merged_pe["EPS_calc"] * pe_quantiles[4]

            fig_river.add_trace(go.Scatter(x=merged_pe["Date"], y=b1, mode="lines", line=dict(color="#00cc66", width=1), name=f"悲觀區 ({pe_quantiles[0]:.1f}x)"))
            fig_river.add_trace(go.Scatter(x=merged_pe["Date"], y=b2, mode="lines", fill="tonexty", fillcolor="rgba(0, 204, 102, 0.2)", line=dict(color="#00cc66", width=1), name=f"低估區 ({pe_quantiles[1]:.1f}x)"))
            fig_river.add_trace(go.Scatter(x=merged_pe["Date"], y=b3, mode="lines", fill="tonexty", fillcolor="rgba(255, 215, 0, 0.2)", line=dict(color="#FFD700", width=1), name=f"合理區 ({pe_quantiles[2]:.1f}x)"))
            fig_river.add_trace(go.Scatter(x=merged_pe["Date"], y=b4, mode="lines", fill="tonexty", fillcolor="rgba(255, 140, 0, 0.2)", line=dict(color="#ff8c00", width=1), name=f"高估區 ({pe_quantiles[3]:.1f}x)"))
            fig_river.add_trace(go.Scatter(x=merged_pe["Date"], y=b5, mode="lines", fill="tonexty", fillcolor="rgba(255, 77, 77, 0.2)", line=dict(color="#ff4d4d", width=1), name=f"瘋狂區 ({pe_quantiles[4]:.1f}x)"))
            fig_river.add_trace(go.Scatter(x=merged_pe["Date"], y=merged_pe["Close"], mode="lines", line=dict(color="#0033cc", width=3), name="實際股價"))

            current_pe = merged_pe["PER"].iloc[-1]
            current_price = merged_pe["Close"].iloc[-1]
            if current_price <= b2.iloc[-1]:
                pe_status, status_color = "🔥 處於歷史低估區間！(潛在買點)", "#00cc66"
            elif current_price >= b5.iloc[-1]:
                pe_status, status_color = "🚨 突破歷史瘋狂區間！(極度高估)", "#ff4d4d"
            elif current_price >= b4.iloc[-1]:
                pe_status, status_color = "⚠️ 處於歷史高估區間！(留意風險)", "#ff8c00"
            else:
                pe_status, status_color = "⚖️ 處於歷史合理區間", "#FFD700"

            fig_river.update_layout(height=450, margin=dict(l=10, r=10, t=50, b=10), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0), hovermode="x unified")
            fig_river.update_yaxes(title_text="股價 (元)", showgrid=True, gridcolor="#e0e0e0")
            st.markdown(f"<div style='background:#f8f9fa; border-left:4px solid {status_color}; padding:10px; border-radius:5px; margin-bottom:10px; color:#333;'>目前位階推估：<b><span style='color:{status_color};'>{pe_status}</span></b> (最新本益比約 {current_pe:.1f}x)</div>", unsafe_allow_html=True)
            st.plotly_chart(fig_river, use_container_width=True)
        else:
            st.info("⚠️ 缺乏足夠的有效本益比數據 (通常因為過去常處於虧損狀態)，建議切換查看「股價淨值比河流圖」。")

    with tab_pb:
        merged_pb = merged[merged["PBR"] > 0].copy()
        if len(merged_pb) > 60:
            merged_pb["BVPS_calc"] = merged_pb["Close"] / merged_pb["PBR"]
            pb_quantiles = merged_pb["PBR"].quantile([0.1, 0.25, 0.5, 0.75, 0.9]).values

            fig_pb = go.Figure()
            pb1 = merged_pb["BVPS_calc"] * pb_quantiles[0]
            pb2 = merged_pb["BVPS_calc"] * pb_quantiles[1]
            pb3 = merged_pb["BVPS_calc"] * pb_quantiles[2]
            pb4 = merged_pb["BVPS_calc"] * pb_quantiles[3]
            pb5 = merged_pb["BVPS_calc"] * pb_quantiles[4]

            fig_pb.add_trace(go.Scatter(x=merged_pb["Date"], y=pb1, mode="lines", line=dict(color="#00cc66", width=1), name=f"悲觀區 ({pb_quantiles[0]:.2f}x)"))
            fig_pb.add_trace(go.Scatter(x=merged_pb["Date"], y=pb2, mode="lines", fill="tonexty", fillcolor="rgba(0, 204, 102, 0.2)", line=dict(color="#00cc66", width=1), name=f"低估區 ({pb_quantiles[1]:.2f}x)"))
            fig_pb.add_trace(go.Scatter(x=merged_pb["Date"], y=pb3, mode="lines", fill="tonexty", fillcolor="rgba(255, 215, 0, 0.2)", line=dict(color="#FFD700", width=1), name=f"合理區 ({pb_quantiles[2]:.2f}x)"))
            fig_pb.add_trace(go.Scatter(x=merged_pb["Date"], y=pb4, mode="lines", fill="tonexty", fillcolor="rgba(255, 140, 0, 0.2)", line=dict(color="#ff8c00", width=1), name=f"高估區 ({pb_quantiles[3]:.2f}x)"))
            fig_pb.add_trace(go.Scatter(x=merged_pb["Date"], y=pb5, mode="lines", fill="tonexty", fillcolor="rgba(255, 77, 77, 0.2)", line=dict(color="#ff4d4d", width=1), name=f"瘋狂區 ({pb_quantiles[4]:.2f}x)"))
            fig_pb.add_trace(go.Scatter(x=merged_pb["Date"], y=merged_pb["Close"], mode="lines", line=dict(color="#0033cc", width=3), name="實際股價"))

            current_pb = merged_pb["PBR"].iloc[-1]
            current_price_pb = merged_pb["Close"].iloc[-1]
            if current_price_pb <= pb2.iloc[-1]:
                pb_status, status_color_pb = "⚓ 跌入歷史低估淨值區！(循環股潛買點)", "#00cc66"
            elif current_price_pb >= pb5.iloc[-1]:
                pb_status, status_color_pb = "🚨 突破歷史瘋狂淨值區！(極度高估)", "#ff4d4d"
            elif current_price_pb >= pb4.iloc[-1]:
                pb_status, status_color_pb = "⚠️ 處於歷史高估淨值區！(留意風險)", "#ff8c00"
            else:
                pb_status, status_color_pb = "⚖️ 處於歷史合理淨值區", "#FFD700"

            fig_pb.update_layout(height=450, margin=dict(l=10, r=10, t=50, b=10), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0), hovermode="x unified")
            fig_pb.update_yaxes(title_text="股價 (元)", showgrid=True, gridcolor="#e0e0e0")
            st.markdown(f"<div style='background:#f8f9fa; border-left:4px solid {status_color_pb}; padding:10px; border-radius:5px; margin-bottom:10px; color:#333;'>目前位階推估：<b><span style='color:{status_color_pb};'>{pb_status}</span></b> (最新淨值比約 {current_pb:.2f}x)</div>", unsafe_allow_html=True)
            st.plotly_chart(fig_pb, use_container_width=True)
        else:
            st.info("缺乏足夠的淨值比數據。")
    st.markdown("---")
