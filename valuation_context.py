"""Valuation data context builders for ui_main.render_main_page."""

from ui_common import *


def _cap_rel_gap(a, b):
    try:
        if a is None or b is None:
            return None
        aa, bb = float(a), float(b)
        denom = min(abs(aa), abs(bb))
        if denom <= 1e-9:
            return None
        return abs(aa - bb) / denom
    except Exception:
        return None


def _ai_has_trace(ai_fin, has_ai_fin_fetch, raw_ai_period, *field_keys):
    if not has_ai_fin_fetch or not isinstance(ai_fin, dict):
        return False
    if raw_ai_period:
        return True
    for field_key in field_keys:
        try:
            meta = get_ai_field_source_meta(ai_fin, field_key)
            if meta and (meta.get("source_url") or meta.get("published_date") or meta.get("source")):
                return True
        except Exception:
            pass
    return False


def _adopt_for_cap(notes, ai_fin, has_ai_fin_fetch, raw_ai_period, sys_val, ai_val, field_name, field_keys, mode="lower_better_when_diverged", gap_threshold=0.30):
    ai_trace_ok = _ai_has_trace(ai_fin, has_ai_fin_fetch, raw_ai_period, *field_keys)
    gap = _cap_rel_gap(sys_val, ai_val)
    if sys_val is None and ai_val is not None:
        notes.append(f"{field_name}：系統缺值，Dynamic Cap 採用 AI 補齊值。")
        return ai_val
    if sys_val is not None and ai_val is None:
        return sys_val
    if sys_val is None and ai_val is None:
        return None
    if gap is not None and gap > gap_threshold:
        if mode == "higher_risk_when_diverged":
            adopted = max(sys_val, ai_val)
        else:
            adopted = min(sys_val, ai_val)
        notes.append(f"{field_name}：系統與 AI 差距 {gap*100:.1f}%，Dynamic Cap 採保守值 {adopted}。")
        return adopted
    if ai_trace_ok and ai_val is not None:
        notes.append(f"{field_name}：AI 有來源/期間，Dynamic Cap 採用 AI 校對值。")
        return ai_val
    return sys_val


def build_dynamic_cap_context(
    *,
    stock_id,
    stock_name,
    has_ai_fin_fetch,
    ai_fin,
    raw_ai_period,
    gross_margin,
    ai_gm,
    eff_roe,
    ai_roe,
    sys_de,
    ai_de,
    rev_growth,
    ai_yoy,
    eff_t_eps,
    ai_t_eps,
    ai_forward_eps_consensus,
    ai_forward_eps_ai,
    ai_forward_eps_fy1,
    sys_forward_eps_system,
    ai_f_eps_calc,
    pb_ratio,
    ai_pb,
):
    """Build adopted Dynamic Cap inputs without changing valuation formulas."""
    cap_adoption_notes = []
    cap_gross_margin = _adopt_for_cap(cap_adoption_notes, ai_fin, has_ai_fin_fetch, raw_ai_period, gross_margin, ai_gm, "毛利率", ["gross_margin"], "lower_better_when_diverged", 0.20)
    cap_roe = _adopt_for_cap(cap_adoption_notes, ai_fin, has_ai_fin_fetch, raw_ai_period, eff_roe, ai_roe, "ROE", ["roe"], "lower_better_when_diverged", 0.30)
    cap_debt_to_equity = _adopt_for_cap(cap_adoption_notes, ai_fin, has_ai_fin_fetch, raw_ai_period, sys_de, ai_de, "D/E", ["debt_to_equity"], "higher_risk_when_diverged", 0.50)
    cap_revenue_yoy = _adopt_for_cap(cap_adoption_notes, ai_fin, has_ai_fin_fetch, raw_ai_period, rev_growth, ai_yoy, "營收 YoY", ["yoy", "monthly_yoy"], "lower_better_when_diverged", 0.20)
    cap_ttm_eps = _adopt_for_cap(cap_adoption_notes, ai_fin, has_ai_fin_fetch, raw_ai_period, eff_t_eps, ai_t_eps, "TTM EPS", ["ttm_eps", "trailing_eps"], "lower_better_when_diverged", 0.30)
    cap_ai_forward_eps = ai_forward_eps_consensus if ai_forward_eps_consensus is not None else ai_forward_eps_ai
    cap_system_forward_eps = sys_forward_eps_system
    cap_adopted_forward_eps = ai_forward_eps_fy1 if ai_forward_eps_fy1 is not None else (ai_forward_eps_consensus if ai_forward_eps_consensus is not None else (cap_system_forward_eps if cap_system_forward_eps is not None else cap_ai_forward_eps))
    cap_divergence_warnings = build_divergence_warnings(
        system_forward_eps=sys_forward_eps_system,
        ai_forward_eps=ai_f_eps_calc,
        system_yoy=rev_growth,
        ai_yoy=ai_yoy,
        system_peg=None,
        ai_peg=None,
        system_fair_value=None,
        ai_fair_value=None,
        system_de=sys_de,
        ai_de=ai_de,
        system_pb=pb_ratio,
        ai_pb=ai_pb,
        stock_id=stock_id,
        stock_name=stock_name,
    )
    return {
        "cap_adoption_notes": cap_adoption_notes,
        "cap_gross_margin": cap_gross_margin,
        "cap_roe": cap_roe,
        "cap_debt_to_equity": cap_debt_to_equity,
        "cap_revenue_yoy": cap_revenue_yoy,
        "cap_ttm_eps": cap_ttm_eps,
        "cap_ai_forward_eps": cap_ai_forward_eps,
        "cap_system_forward_eps": cap_system_forward_eps,
        "cap_adopted_forward_eps": cap_adopted_forward_eps,
        "cap_divergence_warnings": cap_divergence_warnings,
    }
