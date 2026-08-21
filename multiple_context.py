"""Multiple and annual valuation context builders for ui_main.render_main_page."""

from ui_common import *


def cap_float(value, default=None):
    try:
        return float(value) if value is not None else default
    except Exception:
        return default


def valuation_num(value):
    try:
        if value is None:
            return None
        value = float(value)
        if pd.isna(value) or value <= 0:
            return None
        return value
    except Exception:
        return None


def valuation_price(eps, cap):
    eps_value = valuation_num(eps)
    cap_value = valuation_num(cap)
    return eps_value * cap_value if eps_value is not None and cap_value is not None else None


def build_current_eps_valuation(
    *,
    ai_latest_month_eps=None,
    ai_latest_quarter_eps=None,
    sys_latest_quarter_eps=None,
    eff_t_eps=None,
    formula_pe_cap=None,
    raw_ai_period=None,
):
    """Build current realized EPS valuation, preferring latest-month then latest-quarter annualized EPS."""
    latest_month_eps = valuation_num(ai_latest_month_eps)
    if latest_month_eps is not None:
        current_eps_for_valuation = latest_month_eps * 12
        current_eps_raw = latest_month_eps
        source = "最新單月 EPS 年化"
        source_detail = "AI 最新單月 / 自結 EPS ×12 年化值"
        source_note = f"原始單月 EPS={current_eps_raw:.2f}；年化 EPS={current_eps_for_valuation:.2f}"
        period = raw_ai_period or "最新已抓取月份"
    else:
        latest_quarter_eps = valuation_num(ai_latest_quarter_eps)
        source = "最新單季 EPS 年化"
        source_detail = "AI 最新單季 EPS ×4 年化值"
        if latest_quarter_eps is None:
            latest_quarter_eps = valuation_num(sys_latest_quarter_eps)
            source_detail = "系統最新單季 EPS ×4 年化值"

        if latest_quarter_eps is not None:
            current_eps_for_valuation = latest_quarter_eps * 4
            current_eps_raw = latest_quarter_eps
            source_note = f"原始單季 EPS={current_eps_raw:.2f}；年化 EPS={current_eps_for_valuation:.2f}"
            period = raw_ai_period or "最新已抓取季度"
        else:
            current_eps_for_valuation = valuation_num(eff_t_eps)
            current_eps_raw = current_eps_for_valuation
            source = "TTM EPS"
            source_detail = "近四季已實現 EPS"
            source_note = "直接採 TTM EPS，未做單季年化" if current_eps_for_valuation is not None else "未取得可用 EPS"
            period = "近四季 / 系統反推" if current_eps_for_valuation is not None else "未取得"

    return {
        "current_eps_raw": current_eps_raw,
        "current_eps_for_valuation": current_eps_for_valuation,
        "current_eps_source": source,
        "current_eps_source_detail": source_detail,
        "current_eps_formula_note": source_note,
        "current_eps_period": period,
        "current_target_price_est": valuation_price(current_eps_for_valuation, formula_pe_cap),
    }


def build_run_rate_eps_context(
    *,
    latest_quarter_eps=None,
    previous_quarter_eps=None,
    last_two_quarter_eps=None,
    ttm_eps=None,
    fy1_eps=None,
    formula_pe_cap=None,
    raw_ai_period=None,
):
    """Build 1Q/2Q annualized EPS checks for fast-growth names without replacing TTM."""
    latest = valuation_num(latest_quarter_eps)
    previous = valuation_num(previous_quarter_eps)
    two_quarter_sum = valuation_num(last_two_quarter_eps)
    if two_quarter_sum is None and latest is not None and previous is not None:
        two_quarter_sum = latest + previous

    one_q_annualized = latest * 4 if latest is not None else None
    two_q_annualized = two_quarter_sum * 2 if two_quarter_sum is not None else None
    ttm = valuation_num(ttm_eps)
    fy1 = valuation_num(fy1_eps)

    reference_eps = two_q_annualized if two_q_annualized is not None else one_q_annualized
    ttm_ratio = reference_eps / ttm if reference_eps is not None and ttm is not None and ttm > 0 else None
    fy1_ratio = reference_eps / fy1 if reference_eps is not None and fy1 is not None and fy1 > 0 else None

    if one_q_annualized is not None and fy1 is not None and one_q_annualized > fy1 * 1.20:
        label = "單季過熱需確認"
        action = "最新單季年化已高於 FY1 20% 以上，需確認是否有一次性因素、認列時點或毛利率高峰。"
        severity = "orange"
    elif two_q_annualized is not None and ttm is not None and two_q_annualized > ttm * 1.30:
        label = "獲利動能加速"
        action = "近二季年化高於 TTM 30% 以上，可作 AI 高成長股動能參考，但不得取代 FY1/FY2。"
        severity = "green"
    elif two_q_annualized is not None and fy1 is not None and 0.85 <= (two_q_annualized / fy1) <= 1.15:
        label = "近二季支撐 FY1"
        action = "近二季年化與 FY1 接近，代表 FY1 預估較有落地跡象。"
        severity = "green"
    elif one_q_annualized is not None and ttm is not None and one_q_annualized > ttm * 1.30:
        label = "單季動能加速"
        action = "最新單季年化高於 TTM 30% 以上，但缺近二季確認，需等待下一季或月營收延續。"
        severity = "yellow"
    elif reference_eps is not None:
        label = "動能中性"
        action = "Run-rate EPS 未明顯高於 TTM 或 FY1，暫不提高估值口徑。"
        severity = "neutral"
    else:
        label = "資料不足"
        action = "缺少最新單季或近二季 EPS，無法建立 Run-rate EPS。"
        severity = "gray"

    return {
        "latest_quarter_eps": latest,
        "previous_quarter_eps": previous,
        "last_two_quarter_eps": two_quarter_sum,
        "one_q_annualized_eps": one_q_annualized,
        "two_q_annualized_eps": two_q_annualized,
        "one_q_target_price": valuation_price(one_q_annualized, formula_pe_cap),
        "two_q_target_price": valuation_price(two_q_annualized, formula_pe_cap),
        "reference_eps": reference_eps,
        "reference_target_price": valuation_price(reference_eps, formula_pe_cap),
        "ttm_ratio": ttm_ratio,
        "fy1_ratio": fy1_ratio,
        "label": label,
        "action": action,
        "severity": severity,
        "period": raw_ai_period or "最新兩季 / AI 財報校對",
        "rule": "Run-rate EPS 只看短期獲利動能，不取代 TTM、FY1 或 FY2。",
    }


def fmt_price(value):
    value = valuation_num(value)
    return f"{value:.1f}元" if value is not None else "N/A"


def fmt_eps(value):
    value = valuation_num(value)
    return f"{value:.2f}" if value is not None else "N/A"


def fmt_cap(value):
    value = valuation_num(value)
    return f"{value:.1f}x" if value is not None else "N/A"


def build_multiple_context(
    *,
    target_pe_cap,
    suggested_cap,
    dynamic_cap_pack,
    industry_profile,
    eff_f_eps,
    has_ai_fin_fetch,
    ai_f_eps_calc,
    ai_forward_eps_fy1,
    ai_forward_eps_fy2,
    ai_forward_eps_fy3,
    cap_adopted_forward_eps,
    sys_latest_quarter_eps=None,
    ai_latest_month_eps=None,
    ai_latest_quarter_eps=None,
    ai_previous_quarter_eps=None,
    ai_last_two_quarter_eps=None,
    eff_t_eps=None,
    raw_ai_period=None,
):
    """Build multiple caps, formula prices, manual scenario, and FY tiers."""
    dynamic_cap_pack = dynamic_cap_pack if isinstance(dynamic_cap_pack, dict) else {}
    industry_profile = industry_profile if isinstance(industry_profile, dict) else {}
    caps_disabled = dynamic_cap_pack.get("v18_2_caps_available") is False
    cap_eps_basis = str(dynamic_cap_pack.get("cap_eps_basis") or "fy1_forward")
    ttm_only = cap_eps_basis == "ttm_only"

    operable_pe_cap = None if caps_disabled else cap_float(target_pe_cap, suggested_cap)
    base_pe_cap_for_calc = cap_float(dynamic_cap_pack.get("base_multiple"), None)
    if base_pe_cap_for_calc is None and not caps_disabled:
        base_pe_cap_for_calc = cap_float(industry_profile.get("base_pe"), None)
    if base_pe_cap_for_calc is None and not caps_disabled:
        base_pe_cap_for_calc = cap_float(industry_profile.get("cap_hint"), None)

    formula_pe_cap = cap_float(dynamic_cap_pack.get("formula_cap"), None)
    if formula_pe_cap is None:
        formula_pe_cap = cap_float(dynamic_cap_pack.get("raw_cap"), base_pe_cap_for_calc if base_pe_cap_for_calc is not None else operable_pe_cap)
    if base_pe_cap_for_calc is None:
        base_pe_cap_for_calc = formula_pe_cap

    soft_pe_cap = cap_float(dynamic_cap_pack.get("optimistic_cap"), None)
    if soft_pe_cap is None:
        soft_pe_cap = cap_float(dynamic_cap_pack.get("soft_ceiling_cap"), formula_pe_cap)
    hard_pe_cap = cap_float(dynamic_cap_pack.get("hard_ceiling_cap"), cap_float(dynamic_cap_pack.get("ceiling_cap"), soft_pe_cap))

    if soft_pe_cap is not None and base_pe_cap_for_calc is not None:
        soft_pe_cap = max(soft_pe_cap, base_pe_cap_for_calc)
    if hard_pe_cap is not None and soft_pe_cap is not None:
        hard_pe_cap = max(hard_pe_cap, soft_pe_cap)

    soft_pe_cap_for_calc = soft_pe_cap
    hard_pe_cap_for_calc = hard_pe_cap
    if formula_pe_cap is not None and soft_pe_cap is not None:
        formula_pe_cap = min(formula_pe_cap, soft_pe_cap)
    extreme_pe_cap_for_calc = soft_pe_cap if soft_pe_cap is not None else operable_pe_cap

    if ttm_only:
        formula_eps_for_calc = valuation_num(eff_t_eps)
        formula_eps_source = "v18.2 TTM EPS（僅適用 TTM）"
        forward_eps_period_mismatch = {
            "has_mismatch": False,
            "recommended_eps": formula_eps_for_calc,
            "recommended_eps_source": formula_eps_source,
            "note": "v18.2 TTM 參考倍率不得乘以 FY1/FY2/FY3 EPS。",
        }
    else:
        forward_eps_period_mismatch = detect_forward_eps_period_mismatch(
            system_forward_eps=eff_f_eps,
            fy1_eps=ai_forward_eps_fy1,
            fy2_eps=ai_forward_eps_fy2,
        )
        formula_eps_for_calc = forward_eps_period_mismatch.get("recommended_eps")
        formula_eps_source = forward_eps_period_mismatch.get("recommended_eps_source")
    sys_target_price_raw = valuation_price(formula_eps_for_calc if ttm_only else eff_f_eps, formula_pe_cap)
    sys_target_price_est = valuation_price(formula_eps_for_calc, formula_pe_cap)
    is_capped = False
    extreme_target_price_raw = valuation_price(eff_f_eps, extreme_pe_cap_for_calc)
    extreme_target_price = valuation_price(formula_eps_for_calc, extreme_pe_cap_for_calc)
    current_eps_valuation = build_current_eps_valuation(
        ai_latest_month_eps=None if ttm_only else ai_latest_month_eps,
        ai_latest_quarter_eps=None if ttm_only else ai_latest_quarter_eps,
        sys_latest_quarter_eps=None if ttm_only else sys_latest_quarter_eps,
        eff_t_eps=eff_t_eps,
        formula_pe_cap=formula_pe_cap,
        raw_ai_period=raw_ai_period,
    )
    run_rate_eps_context = build_run_rate_eps_context(
        latest_quarter_eps=ai_latest_quarter_eps if ai_latest_quarter_eps is not None else sys_latest_quarter_eps,
        previous_quarter_eps=ai_previous_quarter_eps,
        last_two_quarter_eps=ai_last_two_quarter_eps,
        ttm_eps=eff_t_eps,
        fy1_eps=ai_forward_eps_fy1 if ai_forward_eps_fy1 is not None else cap_adopted_forward_eps,
        formula_pe_cap=None if ttm_only else formula_pe_cap,
        raw_ai_period=raw_ai_period,
    )

    try:
        manual_cap_user_adjusted = (
            target_pe_cap is not None
            and suggested_cap is not None
            and abs(float(target_pe_cap) - float(suggested_cap)) > 1e-6
        )
    except Exception:
        manual_cap_user_adjusted = False
    manual_cap_input = operable_pe_cap if manual_cap_user_adjusted else base_pe_cap_for_calc
    manual_cap_source_text = "使用者手動 Cap" if manual_cap_user_adjusted else ("未手動調整，採 TTM base" if ttm_only else "未手動調整，採 FY1 base")
    manual_cap_for_calc = manual_cap_input
    manual_cap_hit_hard = False
    if manual_cap_input is not None and hard_pe_cap is not None and manual_cap_input > hard_pe_cap:
        manual_cap_for_calc = hard_pe_cap
        manual_cap_hit_hard = True
    manual_eps = eff_t_eps if ttm_only else eff_f_eps
    manual_target_price = valuation_price(manual_eps, manual_cap_for_calc)

    ai_target_price_est = None if ttm_only else (ai_f_eps_calc * formula_pe_cap if has_ai_fin_fetch and ai_f_eps_calc is not None and ai_f_eps_calc > 0 and formula_pe_cap is not None else None)
    ai_is_capped = False
    ai_extreme_target_price = None if ttm_only else (ai_f_eps_calc * extreme_pe_cap_for_calc if has_ai_fin_fetch and ai_f_eps_calc is not None and ai_f_eps_calc > 0 and extreme_pe_cap_for_calc is not None else None)
    ai_manual_target_price = None if ttm_only else (ai_f_eps_calc * manual_cap_for_calc if has_ai_fin_fetch and ai_f_eps_calc is not None and ai_f_eps_calc > 0 and manual_cap_for_calc is not None else None)

    fy1_eps_for_annual = None if ttm_only else (ai_forward_eps_fy1 if ai_forward_eps_fy1 is not None else cap_adopted_forward_eps)
    annual_cap = None if ttm_only else formula_pe_cap
    annual_base = None if ttm_only else base_pe_cap_for_calc
    annual_soft = None if ttm_only else soft_pe_cap_for_calc
    annual_hard = None if ttm_only else hard_pe_cap_for_calc
    fy1_formula_target_price = valuation_price(ai_forward_eps_fy1, annual_cap)
    fy2_formula_target_price = valuation_price(ai_forward_eps_fy2, annual_cap)
    fy3_formula_target_price = valuation_price(ai_forward_eps_fy3, annual_cap)
    fy1_base_target_price = valuation_price(ai_forward_eps_fy1, annual_base)
    fy1_soft_target_price = valuation_price(ai_forward_eps_fy1, annual_soft)
    fy1_hard_target_price = valuation_price(ai_forward_eps_fy1, annual_hard)
    fy2_base_target_price = valuation_price(ai_forward_eps_fy2, annual_base)
    fy2_soft_target_price = valuation_price(ai_forward_eps_fy2, annual_soft)
    fy2_hard_target_price = valuation_price(ai_forward_eps_fy2, annual_hard)
    fy3_base_target_price = valuation_price(ai_forward_eps_fy3, annual_base)
    fy3_soft_target_price = valuation_price(ai_forward_eps_fy3, annual_soft)
    fy3_hard_target_price = valuation_price(ai_forward_eps_fy3, annual_hard)
    fy1_manual_target_price = valuation_price(fy1_eps_for_annual, manual_cap_for_calc)

    return {
        "operable_pe_cap": operable_pe_cap,
        "caps_disabled": caps_disabled,
        "cap_eps_basis": cap_eps_basis,
        "base_pe_cap_for_calc": base_pe_cap_for_calc,
        "formula_pe_cap": formula_pe_cap,
        "soft_pe_cap": soft_pe_cap,
        "hard_pe_cap": hard_pe_cap,
        "soft_pe_cap_for_calc": soft_pe_cap_for_calc,
        "hard_pe_cap_for_calc": hard_pe_cap_for_calc,
        "extreme_pe_cap_for_calc": extreme_pe_cap_for_calc,
        "sys_target_price_est": sys_target_price_est,
        "sys_target_price_raw": sys_target_price_raw,
        "formula_eps_for_calc": formula_eps_for_calc,
        "formula_eps_source": formula_eps_source,
        "forward_eps_period_mismatch": forward_eps_period_mismatch,
        "current_eps_raw": current_eps_valuation["current_eps_raw"],
        "current_eps_for_valuation": current_eps_valuation["current_eps_for_valuation"],
        "current_eps_source": current_eps_valuation["current_eps_source"],
        "current_eps_source_detail": current_eps_valuation["current_eps_source_detail"],
        "current_eps_formula_note": current_eps_valuation["current_eps_formula_note"],
        "current_eps_period": current_eps_valuation["current_eps_period"],
        "current_target_price_est": current_eps_valuation["current_target_price_est"],
        "run_rate_eps_context": run_rate_eps_context,
        "run_rate_1q_eps_annualized": run_rate_eps_context["one_q_annualized_eps"],
        "run_rate_2q_eps_annualized": run_rate_eps_context["two_q_annualized_eps"],
        "run_rate_1q_target_price": run_rate_eps_context["one_q_target_price"],
        "run_rate_2q_target_price": run_rate_eps_context["two_q_target_price"],
        "run_rate_reference_eps": run_rate_eps_context["reference_eps"],
        "run_rate_reference_target_price": run_rate_eps_context["reference_target_price"],
        "run_rate_label": run_rate_eps_context["label"],
        "run_rate_action": run_rate_eps_context["action"],
        "is_capped": is_capped,
        "extreme_target_price": extreme_target_price,
        "extreme_target_price_raw": extreme_target_price_raw,
        "manual_cap_user_adjusted": manual_cap_user_adjusted,
        "manual_cap_input": manual_cap_input,
        "manual_cap_source_text": manual_cap_source_text,
        "manual_cap_for_calc": manual_cap_for_calc,
        "manual_cap_hit_hard": manual_cap_hit_hard,
        "manual_target_price": manual_target_price,
        "ai_target_price_est": ai_target_price_est,
        "ai_is_capped": ai_is_capped,
        "ai_extreme_target_price": ai_extreme_target_price,
        "ai_manual_target_price": ai_manual_target_price,
        "fy1_eps_for_annual": fy1_eps_for_annual,
        "fy1_formula_target_price": fy1_formula_target_price,
        "fy2_formula_target_price": fy2_formula_target_price,
        "fy3_formula_target_price": fy3_formula_target_price,
        "fy1_base_target_price": fy1_base_target_price,
        "fy1_soft_target_price": fy1_soft_target_price,
        "fy1_hard_target_price": fy1_hard_target_price,
        "fy2_base_target_price": fy2_base_target_price,
        "fy2_soft_target_price": fy2_soft_target_price,
        "fy2_hard_target_price": fy2_hard_target_price,
        "fy3_base_target_price": fy3_base_target_price,
        "fy3_soft_target_price": fy3_soft_target_price,
        "fy3_hard_target_price": fy3_hard_target_price,
        "fy1_manual_target_price": fy1_manual_target_price,
    }
