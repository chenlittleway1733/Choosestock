"""Institutional and ownership chip panels for ui_main.render_main_page."""

from ui_common import *


def render_chip_panels(*, curr_id, info, ai_shares, eff_eg):
    """Render institutional flow and ownership panels.

    Returns the values consumed later by the prompt-pack summary so the prompt
    stays aligned with the visual panel.
    """
    result = {"has_institutional_data": False}
    shares_out = s_float(info.get("sharesOutstanding"))
    if ai_shares is not None:
        shares_out = ai_shares
    share_capital = shares_out * 10 if shares_out is not None else None

    st.markdown("#### 📡 主力籌碼追蹤雷達 (聰明錢動向與背離陷阱)", unsafe_allow_html=True)
    inst_df = get_inst_data(curr_id, st.session_state.finmind_key)

    if inst_df is not None and not inst_df.empty:
        f_streak = get_streak(inst_df["Foreign"])
        t_streak = get_streak(inst_df["Trust"])
        f_10d = inst_df["Foreign"].tail(10).sum()
        t_10d = inst_df["Trust"].tail(10).sum()

        f_status = f"連買 {f_streak} 天 🔥" if f_streak > 0 else (f"連賣 {-f_streak} 天 ⚠️" if f_streak < 0 else "無連續動向")
        t_status = f"連買 {t_streak} 天 🔥" if t_streak > 0 else (f"連賣 {-t_streak} 天 ⚠️" if t_streak < 0 else "無連續動向")

        f_color = "#ff4d4d" if f_10d > 0 else "#00cc66"
        t_color = "#ff4d4d" if t_10d > 0 else "#00cc66"

        if (eff_eg is not None and eff_eg > 0) and ((f_10d + t_10d) < -1000):
            trap_warning = "<div style='background:linear-gradient(90deg, #8b0000 0%, #ff4d4d 100%); color:white; padding:12px; border-radius:8px; margin-top:10px; font-weight:bold;'>🚨 【高危陷阱警示】基本面看似亮眼，但外資/投信近 10 日聯手倒貨超過千張！請提防主力趁利多逢高出貨！</div>"
        elif (f_streak >= 3 or t_streak >= 3) and ((f_10d + t_10d) > 1000):
            trap_warning = "<div style='background:linear-gradient(90deg, #006400 0%, #00cc66 100%); color:white; padding:12px; border-radius:8px; margin-top:10px; font-weight:bold;'>🚀 【聰明錢上車】三大法人近期連買且大幅建倉，籌碼動能強勁，極具波段上攻潛力！</div>"
        else:
            trap_warning = "<div style='background:#1e1e1e; color:#aaa; padding:12px; border-radius:8px; border:1px solid #333; margin-top:10px;'>目前三大法人買賣超動向無極端異常訊號。</div>"

        radar_html = f"""
        <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; margin-bottom:10px;'>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {f_color};'>
                <div style='color:#aaa; font-size:0.9rem;'>外資近 10 日淨買賣</div>
                <div style='font-size:1.6rem; font-weight:bold; color:{f_color};'>{f_10d:,.0f} 張</div>
                <div style='font-size:1rem; font-weight:bold; color:#fff; margin-top:5px;'>動向: {f_status}</div>
            </div>
            <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {t_color};'>
                <div style='color:#aaa; font-size:0.9rem;'>投信近 10 日淨買賣</div>
                <div style='font-size:1.6rem; font-weight:bold; color:{t_color};'>{t_10d:,.0f} 張</div>
                <div style='font-size:1rem; font-weight:bold; color:#fff; margin-top:5px;'>動向: {t_status}</div>
            </div>
        </div>
        {trap_warning}
        """
        st.markdown(clean_html(radar_html), unsafe_allow_html=True)
        result.update({
            "has_institutional_data": True,
            "f_10d": f_10d,
            "t_10d": t_10d,
            "f_status": f_status,
            "t_status": t_status,
            "trap_warning": trap_warning,
        })
    else:
        if not st.session_state.finmind_key:
            st.warning("⚠️ 系統無法獲取主力籌碼雷達。請至左側上傳 `key.txt` 匯入 FinMind 金鑰以解除限制。")
        else:
            st.warning("⚠️ 此檔股票近期無三大法人買賣超數據，無法啟動籌碼雷達。")

    st.markdown("#### 💳 信用交易風險（融資融券）", unsafe_allow_html=True)
    margin_df = get_margin_credit_data(curr_id, st.session_state.finmind_key)
    margin_credit = build_margin_credit_summary(margin_df, shares_outstanding=shares_out)
    if margin_credit.get("available"):
        def _fmt_lots(value):
            value = s_float(value)
            return "N/A" if value is None else f"{value:,.0f} 張"

        def _fmt_pct(value):
            value = s_float(value)
            return "N/A" if value is None else f"{value:.2%}"

        risk_color = margin_credit.get("risk_color", "#FFD700")
        credit_html = f"""
        <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left:5px solid {risk_color}; margin-top:8px; margin-bottom:10px;'>
            <div style='display:flex; justify-content:space-between; align-items:flex-start; gap:14px; margin-bottom:10px;'>
                <div>
                    <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>融資比例與信用風險</div>
                    <div style='color:#aaa; font-size:0.82rem;'>資料日期：{margin_credit.get("latest_date", "N/A")}｜來源：{margin_credit.get("source", "FinMind")}</div>
                </div>
                <div style='background:{risk_color}; color:#000; padding:3px 10px; border-radius:12px; font-size:0.85rem; font-weight:bold;'>{margin_credit.get("risk_label", "資料不足")}</div>
            </div>
            <div style='display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:10px;'>
                <div style='background:#111827; padding:10px; border-radius:6px;'>
                    <div style='color:#9CA3AF; font-size:0.82rem;'>融資使用率</div>
                    <div style='color:#F3F4F6; font-weight:bold; font-size:1.25rem;'>{_fmt_pct(margin_credit.get("margin_usage_ratio"))}</div>
                </div>
                <div style='background:#111827; padding:10px; border-radius:6px;'>
                    <div style='color:#9CA3AF; font-size:0.82rem;'>融資占股本</div>
                    <div style='color:#F3F4F6; font-weight:bold; font-size:1.25rem;'>{_fmt_pct(margin_credit.get("margin_to_shares_ratio"))}</div>
                </div>
                <div style='background:#111827; padding:10px; border-radius:6px;'>
                    <div style='color:#9CA3AF; font-size:0.82rem;'>融資餘額 / 1日</div>
                    <div style='color:#F3F4F6; font-weight:bold; font-size:1.25rem;'>{_fmt_lots(margin_credit.get("margin_balance"))}</div>
                    <div style='color:#CBD5E1; font-size:0.78rem;'>變化 {_fmt_lots(margin_credit.get("margin_change_1d"))}</div>
                </div>
                <div style='background:#111827; padding:10px; border-radius:6px;'>
                    <div style='color:#9CA3AF; font-size:0.82rem;'>券資比 / 融券餘額</div>
                    <div style='color:#F3F4F6; font-weight:bold; font-size:1.25rem;'>{_fmt_pct(margin_credit.get("short_margin_ratio"))}</div>
                    <div style='color:#CBD5E1; font-size:0.78rem;'>融券 {_fmt_lots(margin_credit.get("short_balance"))}</div>
                </div>
            </div>
            <div style='color:#E5E7EB; font-size:0.86rem; margin-top:10px; line-height:1.55;'>{margin_credit.get("risk_note", "")}</div>
        </div>
        """
        st.markdown(clean_html(credit_html), unsafe_allow_html=True)
        with st.expander("查看融資融券明細", expanded=False):
            st_dataframe(margin_credit.get("report"), hide_index=True)
    else:
        if not st.session_state.finmind_key:
            st.warning("⚠️ 系統無法獲取融資融券資料。請至左側上傳 `key.txt` 匯入 FinMind 金鑰。")
        else:
            st.warning(f"⚠️ 此檔股票近期無融資融券資料。{margin_credit.get('message', '')}")
    result["margin_credit"] = margin_credit
    st.markdown("---")

    st.markdown("#### 🐳 內部人與控盤主力推估", unsafe_allow_html=True)
    insider_pct = s_float(info.get("heldPercentInsiders"))
    inst_pct = s_float(info.get("heldPercentInstitutions"))

    if share_capital is not None:
        if share_capital >= 10_000_000_000:
            cap_type, driver, cap_color, driver_desc = "大型權值股", "🌍 外資主導", "#4169E1", f"股本約 {share_capital/100000000:.0f} 億。籌碼龐大，走勢受外資資金影響大。"
        elif share_capital <= 3_000_000_000:
            cap_type, driver, cap_color, driver_desc = "中小型飆股", "🔥 投信/內資主力", "#ff8c00", f"股本約 {share_capital/100000000:.0f} 億。籌碼輕薄，易受投信作帳帶動。"
        else:
            cap_type, driver, cap_color, driver_desc = "中型中堅股", "🤝 土洋共議", "#9370DB", f"股本約 {share_capital/100000000:.0f} 億。出現土洋合作易有波段行情。"
    else:
        cap_type, driver, cap_color, driver_desc = "無資料", "未知", "gray", "無法獲取股本資料"

    inst_str = to_pct(inst_pct)
    inst_color, inst_eval = ("#ff4d4d", "高度集中 (留意結帳)") if inst_pct is not None and inst_pct > 0.40 else ("#FFD700", "穩定認可") if inst_pct is not None and inst_pct > 0.15 else ("#00bfff", "內資/散戶主導") if inst_pct is not None else ("gray", "數據不足")

    insider_str = to_pct(insider_pct)
    in_color, in_eval = ("#ff4d4d", "籌碼極度安定") if insider_pct is not None and insider_pct > 0.40 else ("#FFD700", "相對穩健") if insider_pct is not None and insider_pct > 0.20 else ("#00cc66", "籌碼較渙散 (警戒)") if insider_pct is not None else ("gray", "數據不足")

    chip_html = f"""
    <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; margin-top:10px;'>
        <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {inst_color};'>
            <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>🏦 外資/機構總持股率</div>
                <div style='background:{inst_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{inst_eval}</div>
            </div>
            <div style='font-size:1.8rem; font-weight:bold; color:#fff; margin-bottom:5px;'>{inst_str}</div>
        </div>
        <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {in_color};'>
            <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>🏢 內部人與大股東持股</div>
                <div style='background:{in_color}; color:#000; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{in_eval}</div>
            </div>
            <div style='font-size:1.8rem; font-weight:bold; color:#fff; margin-bottom:5px;'>{insider_str}</div>
        </div>
        <div style='background:#1e1e1e; padding:15px; border-radius:8px; border-left: 5px solid {cap_color};'>
            <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                <div style='font-size:1.1rem; font-weight:bold; color:#fff;'>🎯 控盤主力推估</div>
                <div style='background:{cap_color}; color:#fff; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;'>{cap_type}</div>
            </div>
            <div style='font-size:1.3rem; font-weight:bold; color:{cap_color}; margin-bottom:10px;'>{driver}</div>
            <div style='color:#aaa; font-size:0.85rem; line-height:1.5;'>{driver_desc}</div>
        </div>
    </div>
    """
    st.markdown(clean_html(chip_html), unsafe_allow_html=True)
    st.markdown("---")

    result.update({
        "inst_str": inst_str,
        "inst_eval": inst_eval,
        "insider_str": insider_str,
        "in_eval": in_eval,
        "share_capital": share_capital,
        "cap_type": cap_type,
        "driver": driver,
        "driver_desc": driver_desc,
    })
    return result
