"""Peer comparison panel for ui_main.render_main_page."""

from ui_common import *


def render_peer_compare_panel(*, curr_id, stock_name):
    if not st.session_state.show_pk:
        return

    st.markdown("#### ⚔️ 產業橫向對比 (同業估值與利潤率 PK)")
    st.markdown("<small style='color:gray;'>*註：透過 AI 動態檢索業務相近的競爭對手，並抓取最新財報數據進行橫向比較。*</small>", unsafe_allow_html=True)
    with st.spinner("AI 正在深度檢索產業鏈與競爭對手，並同步抓取最新財報數據..."):
        peers = get_peers_from_ai(stock_name, curr_id, st.session_state.api_key)
        if not peers:
            st.error("AI 暫時找不到明確的同業數據，或請檢查您的 API Key 額度。")
            st.markdown("---")
            return

        compare_list = [curr_id] + [p for p in peers if p != curr_id]
        compare_data = []
        for code in compare_list:
            _, p_info = get_stock_data(code, st.session_state.fugle_key, st.session_state.finmind_key)
            p_name = get_chinese_name(code) or code
            if not p_info:
                continue

            pe_val = s_float(p_info.get("trailingPE"))
            pe_fmt = f"{pe_val:.2f}x" if pe_val is not None else "N/A"
            gm_fmt = to_pct(s_float(p_info.get("grossMargins")))
            om_fmt = to_pct(s_float(p_info.get("operatingMargins")))
            roe_fmt = to_pct(s_float(p_info.get("returnOnEquity")))
            prev_close_val = s_float(p_info.get("previousClose"))
            prev_close_fmt = f"{prev_close_val:.2f}" if prev_close_val is not None else "N/A"
            t_eps_p = s_float(p_info.get("trailingEps"))
            f_eps_p = s_float(p_info.get("forwardEps"))
            t_eps_p_str = f"{t_eps_p:.2f}" if t_eps_p is not None else "N/A"
            f_eps_p_str = f"{f_eps_p:.2f}" if f_eps_p is not None else "N/A"
            eps_display = f"{t_eps_p_str} / <span style='color:#00bfff;'>{f_eps_p_str}</span>"
            if prev_close_val is not None and f_eps_p is not None and f_eps_p > 0:
                fpe_fmt = f"<b style='color:#FFD700;'>{prev_close_val / f_eps_p:.1f}x</b>"
            else:
                fpe_fmt = "<span style='color:gray;'>N/A</span>"
            target_mean_p = s_float(p_info.get("targetMeanPrice"))
            if target_mean_p is not None and prev_close_val is not None and prev_close_val > 0:
                upside = ((target_mean_p - prev_close_val) / prev_close_val) * 100
                if upside >= 25:
                    upside_fmt = f"<span style='color:#ff4d4d; font-weight:bold;'>+{upside:.1f}%</span>"
                elif upside > 0:
                    upside_fmt = f"<span style='color:#00cc66;'>+{upside:.1f}%</span>"
                else:
                    upside_fmt = f"<span style='color:#aaa;'>{upside:.1f}%</span>"
                target_display = f"{target_mean_p:.1f} ({upside_fmt})"
            else:
                target_display = "<span style='color:gray;'>無資料</span>"
            compare_data.append({
                "代號": f"{p_name} ({code})",
                "股價": prev_close_fmt,
                "前瞻 P/E": fpe_fmt,
                "預估 EPS": eps_display,
                "目標價": target_display,
                "毛利率": gm_fmt,
                "營益率": om_fmt,
                "ROE": roe_fmt,
            })

        if compare_data:
            table_html = "<table style='width:100%; text-align:center; border-collapse: collapse; margin-top: 10px; font-size: 1.05rem; color: #e0e0e0;'><tr style='background-color:#333; color:#fff; border-bottom: 2px solid #555;'><th style='padding:12px;'>公司名稱</th><th>最新收盤價</th><th>前瞻 P/E</th><th>預估 EPS (今/明)</th><th>目標價 (潛在空間)</th><th>毛利率</th><th>營益率</th><th>ROE</th></tr>"
            for row in compare_data:
                row_bg = "#2c3e50" if str(curr_id) in row["代號"] else "#1e1e1e"
                table_html += f"<tr style='background-color:{row_bg}; border-bottom:1px solid #444;'><td style='padding:12px; color:#ffffff;'><b>{row['代號']}</b></td><td>{row['股價']}</td><td>{row['前瞻 P/E']}</td><td>{row['預估 EPS']}</td><td>{row['目標價']}</td><td>{row['毛利率']}</td><td>{row['營益率']}</td><td style='color:#00bfff;'><b>{row['ROE']}</b></td></tr>"
            table_html += "</table>"
            st.markdown(table_html, unsafe_allow_html=True)
    st.markdown("---")
