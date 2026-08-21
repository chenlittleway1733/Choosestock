"""Implied Forward P/E context builders for ui_main.render_main_page."""


def _fmt_implied(value):
    return f"{value:.1f}x" if value is not None else "N/A"


def build_implied_pe_context(
    *,
    current_price,
    adopted_forward_eps,
    broker_target_avg,
    broker_target_high,
    broker_target_low,
    hard_pe_cap,
    soft_pe_cap,
    operable_pe_cap,
    dynamic_cap_pack,
):
    """Build market/broker implied Forward P/E values and sync dynamic cap pack."""
    implied_eps = adopted_forward_eps
    market_implied_pe = current_price / implied_eps if implied_eps is not None and implied_eps > 0 and current_price is not None else None
    target_avg_implied_pe = broker_target_avg / implied_eps if implied_eps is not None and implied_eps > 0 and broker_target_avg is not None else None
    target_high_implied_pe = broker_target_high / implied_eps if implied_eps is not None and implied_eps > 0 and broker_target_high is not None else None
    target_low_implied_pe = broker_target_low / implied_eps if implied_eps is not None and implied_eps > 0 and broker_target_low is not None else None

    implied_status = "Forward EPS 缺值或 <= 0，無法反推市場 / 法人隱含 Forward P/E。"
    if market_implied_pe is not None:
        if hard_pe_cap is not None and market_implied_pe > hard_pe_cap:
            implied_status = "現價隱含倍率已高於系統 hard ceiling，屬市場重估 / 題材動能區，不代表可操作買點。"
        elif soft_pe_cap is not None and market_implied_pe > soft_pe_cap:
            implied_status = "現價隱含倍率高於 soft ceiling，屬偏樂觀估值區。"
        elif operable_pe_cap is not None and market_implied_pe > operable_pe_cap:
            implied_status = "現價隱含倍率高於可操作倍率，但仍未突破系統 hard ceiling。"
        else:
            implied_status = "現價隱含倍率未高於可操作倍率。"

    implied_html = ""
    if market_implied_pe is not None or target_avg_implied_pe is not None:
        eps_text = f"{implied_eps:.2f}" if implied_eps is not None else "N/A"
        implied_html = (
            "<div style='background:#1f2937;color:#E5E7EB;padding:7px 9px;border-radius:6px;margin-top:7px;line-height:1.55;'>"
            "<b>🧭 市場 / 法人隱含倍率對照</b><br>"
            f"採用 Forward EPS：{eps_text}｜現價隱含：{_fmt_implied(market_implied_pe)}｜"
            f"法人均價隱含：{_fmt_implied(target_avg_implied_pe)}｜"
            f"法人高標隱含：{_fmt_implied(target_high_implied_pe)}｜"
            f"法人低標隱含：{_fmt_implied(target_low_implied_pe)}<br>"
            f"<span style='color:#FBBF24;'>{implied_status}</span></div>"
        )

    if isinstance(dynamic_cap_pack, dict):
        dynamic_cap_pack["market_implied_forward_pe"] = market_implied_pe
        dynamic_cap_pack["target_avg_implied_forward_pe"] = target_avg_implied_pe
        dynamic_cap_pack["target_high_implied_forward_pe"] = target_high_implied_pe
        dynamic_cap_pack["target_low_implied_forward_pe"] = target_low_implied_pe
        dynamic_cap_pack["implied_forward_eps"] = implied_eps
        dynamic_cap_pack["implied_status"] = implied_status

    return {
        "implied_eps": implied_eps,
        "market_implied_pe": market_implied_pe,
        "target_avg_implied_pe": target_avg_implied_pe,
        "target_high_implied_pe": target_high_implied_pe,
        "target_low_implied_pe": target_low_implied_pe,
        "implied_status": implied_status,
        "implied_html": implied_html,
    }
