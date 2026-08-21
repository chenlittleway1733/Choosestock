"""
Dynamic Cap 2.0 係數校準模型（目前版本 18.2）。

設計原則：
- 不再採用「產業基準 + 各項絕對倍數」加總，避免倍率連續堆高。
- 改為「產業基準 × 成長係數 × 品質係數 × 題材係數 × 規模係數 × 風險折扣」。
- 正式倍率改採 v18.2 逐股清冊的 Company Base / Soft / Hard。
- v18.2 已納入個股品質與成長校準，不再重複套用動態係數或市場熱度上修。
- 毛利率改採相對產業基準；M10 margin benchmark 已納入品質係數守門與 UI / prompt 摘要。
- 台灣關鍵半導體供應鏈加入地緣政治折價，特別避免台積電類超大型晶圓代工龍頭被推到過高 P/E。
- P/B 週期股與題材 / 事件股仍不輸出 P/E 買進倍率。
- 版本階段表見 DYNAMIC_CAP_MODEL_VERSION_TABLE。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import pandas as pd

DYNAMIC_CAP_MODEL_VERSION = "18.2"
DYNAMIC_CAP_MODEL_BUILD_DATE = "2026-08-20"
DYNAMIC_CAP_MODEL_ENGINE_VERSION = f"Dynamic Cap 2.0 calibration {DYNAMIC_CAP_MODEL_VERSION}"
DYNAMIC_CAP_MODEL_VERSION_TABLE = [
    {
        "stage": "17-C-4",
        "order": 1704,
        "title": "Dynamic Cap 校準覆寫",
        "scope": "重整產業預設倍率、係數上限、風險折扣與 hard ceiling。",
        "kind": "calibration",
    },
    {
        "stage": "17-C-5",
        "order": 1705,
        "title": "品質係數細緻化",
        "scope": "將絕對毛利率、相對產業毛利率、ROE 與營益率納入漸進式品質係數。",
        "kind": "calibration",
    },
    {
        "stage": "17-C-6",
        "order": 1706,
        "title": "IC 設計 / ASIC / IP 分層預設校準",
        "scope": "補強 IC_DESIGN_ASIC、IP/EDA、成熟 IC 與消費型 MCU 的 Dynamic Cap 預設。",
        "kind": "calibration",
    },
    {
        "stage": "17-C-7A",
        "order": 1707,
        "title": "混合產業權重估值引擎",
        "scope": "支援 stock_mapping.py 的 hybrid_taxons，混合 base/soft/hard 與係數上限。",
        "kind": "engine",
    },
    {
        "stage": "17-C-9",
        "order": 1709,
        "title": "第一批 AI 混合股補充預設校準",
        "scope": "補上 AI 伺服器、散熱、測試、先進封裝與光通訊等混合股需要的校準值。",
        "kind": "extension",
    },
    {
        "stage": "17-C-10",
        "order": 1710,
        "title": "新增產業 Dynamic Cap 校準補齊",
        "scope": "為新增分類補齊 base/floor/soft/hard、品質與題材係數。",
        "kind": "extension",
    },
    {
        "stage": "17-C-11",
        "order": 1711,
        "title": "第二批上市半導體缺漏股校準",
        "scope": "補齊半導體缺漏分類的預設倍率與週期風險邊界。",
        "kind": "extension",
    },
    {
        "stage": "17-C-11B",
        "order": 1711.5,
        "title": "既有 P/B 週期與特殊分類兜底",
        "scope": "為既有 P/B 週期股與特殊分類補上 Dynamic Cap 兜底設定。",
        "kind": "safety",
    },
    {
        "stage": "17-C-12",
        "order": 1712,
        "title": "高倍率分類拆分校準",
        "scope": "細分高倍率科技分類，避免題材股共用過寬的估值天花板。",
        "kind": "calibration",
    },
    {
        "stage": "17-C-13",
        "order": 1713,
        "title": "半導體中游 / 週期分類校準",
        "scope": "補強中游封測、材料、耗材與週期型半導體的 Dynamic Cap 預設。",
        "kind": "extension",
    },
    {
        "stage": "17-C-14",
        "order": 1714,
        "title": "第三批 AI 伺服器 / 電子零組件主鏈校準",
        "scope": "擴充 AI 伺服器、連接器、散熱、PCB、光通訊與電源鏈的係數邊界。",
        "kind": "extension",
    },
    {
        "stage": "17-C-15",
        "order": 1715,
        "title": "第四批非 AI 主鏈與防禦 / 循環分類校準",
        "scope": "補強非 AI 電子、傳產、防禦、金融、通路與週期分類的預設倍率。",
        "kind": "extension",
    },
    {
        "stage": "17-C-16",
        "order": 1716,
        "title": "第五批尾端總稽核校準",
        "scope": "補齊消費 IC、記憶體、舊科技資料審核與尾端缺漏分類，作為目前 Dynamic Cap 版本。",
        "kind": "extension",
    },
    {
        "stage": "17-C-17",
        "order": 1717,
        "title": "base / soft / hard 倍率寬鬆度收斂",
        "scope": "依 2026-06-09 倍率寬鬆度查核，收斂高 hard ceiling 類別並同步 taxonomy 顯示口徑。",
        "kind": "calibration",
    },
    {
        "stage": "17-C-18",
        "order": 1718,
        "title": "ABF 載板與公式 cap 風控收斂",
        "scope": "收斂 ABF_SUBSTRATE base/soft/hard，並讓公式合理價採用資料可信度折扣後的 cap。",
        "kind": "calibration",
    },
    {
        "stage": "17-C-19",
        "order": 1719,
        "title": "ABF 法人目標價情境校準",
        "scope": "ABF_SUBSTRATE 維持 base 保守，但 soft/hard 回補至可解釋法人平均與最高目標價的 FY2 先行定價區間。",
        "kind": "calibration",
    },
    {
        "stage": "17-C-20",
        "order": 1720,
        "title": "使用者收集 FY2026E / 目標價倍率校準",
        "scope": "依 tw_stock_90_category_tasks_T86_T90_done.xlsx 已完成樣本，校準 base/soft/hard；base 不追現價，soft/hard 反映法人目標與市場先行定價。",
        "kind": "calibration",
    },
    {
        "stage": "17-C-21",
        "order": 1721,
        "title": "市場狀況 hard ceiling overlay",
        "scope": "保留產業結構 hard，實算時依現價隱含 Forward P/E、成長、資料品質與流動性產生市場調整 hard。",
        "kind": "engine",
    },
    {
        "stage": "17-C-22",
        "order": 1722,
        "title": "M10 margin benchmark 品質係數守門",
        "scope": "導入 M10 毛利率 / 營益率 benchmark，區分可納入、只追蹤與不適用狀態；同步 Dynamic Cap 拆解、UI 與提示詞。",
        "kind": "engine",
    },
    {
        "stage": "17-C-23",
        "order": 1723,
        "title": "欄位級混合權重與 FY2 soft 風控",
        "scope": "支援 hybrid_taxons 對 base/soft/hard 使用不同權重；聯發科 Cloud AI ASIC 重評價提高成長權重但不推高 hard ceiling。",
        "kind": "engine",
    },
    {
        "stage": "18.2",
        "order": 1802,
        "title": "逐股 Company Base / Soft / Hard 正式接管",
        "scope": "採用 Dynamic Cap v18.2 逐股倍率清冊；不回退 v18.1，不以市場熱度上修倍率，並強制區分 FY1 forward、TTM only、P/E 不適用與資料不足。",
        "kind": "governed_registry",
    },
]


def get_dynamic_cap_version_table():
    return [dict(row) for row in DYNAMIC_CAP_MODEL_VERSION_TABLE]


def get_dynamic_cap_version_info():
    return {
        "version": DYNAMIC_CAP_MODEL_VERSION,
        "build_date": DYNAMIC_CAP_MODEL_BUILD_DATE,
        "engine_version": DYNAMIC_CAP_MODEL_ENGINE_VERSION,
        "latest_stage": DYNAMIC_CAP_MODEL_VERSION_TABLE[-1]["stage"],
        "stage_count": len(DYNAMIC_CAP_MODEL_VERSION_TABLE),
        "version_table": get_dynamic_cap_version_table(),
    }


def _sf(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None:
            return default
        if isinstance(x, str):
            x = x.replace(",", "").replace("%", "").strip()
            if x in {"", "None", "nan", "NULL", "N/A", "—"}:
                return default
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def _pct01(x: Any) -> Optional[float]:
    """接受 0.25 或 25 兩種百分比口徑，統一轉成 0.25。"""
    v = _sf(x)
    if v is None:
        return None
    if abs(v) > 3:
        return v / 100.0
    return v


def _fmt_x(x: Any, digits: int = 1) -> str:
    v = _sf(x)
    return "NULL" if v is None else f"{v:.{digits}f}x"


def _fmt_pct(x: Any, digits: int = 1) -> str:
    v = _pct01(x)
    return "NULL" if v is None else f"{v*100:.{digits}f}%"


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _add_row(rows: List[Dict[str, Any]], kind: str, name: str, value: Any, reason: str) -> None:
    rows.append({"類型": kind, "項目": name, "倍率/係數": value, "說明": reason})


def _add_factor(rows: List[Dict[str, Any]], name: str, factor: float, reason: str) -> None:
    _add_row(rows, "係數項", name, f"×{factor:.3f}", reason)


def _add_discount(rows: List[Dict[str, Any]], name: str, factor: float, reason: str) -> None:
    _add_row(rows, "折扣項", name, f"×{factor:.3f}", reason)


M10_MARGIN_STATUS_LABELS = {
    "usable": "可納入品質係數",
    "tracking_only": "只作追蹤 / 不給正向加分",
    "stock_not_valuation_ready": "背景參考 / 樣本未達估值就緒",
    "not_applicable": "不適用 margin 模型",
    "missing_stock_model_data": "未建立 M10 margin benchmark",
}

M10_MARGIN_RULE_LABELS = {
    "standard_margin_benchmark": "一般 margin benchmark",
    "high_operating_margin_cap": "高營益率 cap",
    "high_gross_margin_profile": "高毛利 profile",
    "low_operating_margin_cap": "低營益率 cap",
    "cycle_margin_sensitive": "循環敏感 margin",
    "event_or_cycle_tracking_only": "事件 / 循環追蹤用",
    "margin_not_applicable": "不適用 margin 模型",
}


def _first_defined(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return bool(value)


def _pct_value_for_summary(*values: Any) -> Optional[float]:
    raw = _first_defined(*values)
    ratio = _pct01(raw)
    return None if ratio is None else round(ratio * 100.0, 4)


def build_m10_margin_benchmark_summary(
    industry_profile: Dict[str, Any] = None,
    calibration: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Return structured M10 margin benchmark metadata for UI and prompt packs."""
    profile = industry_profile if isinstance(industry_profile, dict) else {}
    c = calibration if isinstance(calibration, dict) else {}

    def get_value(key: str, default: Any = None) -> Any:
        return _first_defined(profile.get(key), c.get(key), default)

    quality = str(get_value("margin_quality", "") or "").strip().upper()
    rule = str(get_value("margin_rule", "") or "").strip()
    status = str(get_value("m10_margin_status", "") or "").strip()
    available = _as_bool(get_value("m10_margin_available"), False) or bool(quality or rule or status)

    model_applicable = get_value("margin_model_applicable")
    if model_applicable is None:
        model_applicable = not (available and (quality == "N/A" or rule == "margin_not_applicable"))
    else:
        model_applicable = _as_bool(model_applicable, False)

    can_affect = get_value("margin_can_affect_valuation")
    if can_affect is None:
        can_affect = bool(model_applicable) and not (
            available and (quality == "C" or rule == "event_or_cycle_tracking_only")
        )
    else:
        can_affect = _as_bool(can_affect, False)

    if not available:
        status = status or "missing_stock_model_data"
    elif not status:
        if not model_applicable:
            status = "not_applicable"
        elif not can_affect:
            status = "tracking_only"
        else:
            status = "usable"

    if not model_applicable:
        usage_label = "不適用製造業毛利率 / 營益率模型；品質係數只採 ROE 與財務風險"
    elif not can_affect:
        usage_label = "只作追蹤或風險背景；正向 margin 加分歸零，只保留負向折扣"
    else:
        usage_label = "可納入 Dynamic Cap 品質係數，但仍受產業 max_quality_factor 與 hard ceiling 限制"

    gross_base = _pct_value_for_summary(get_value("base_gross_margin_pct"), get_value("base_gross_margin_ratio"))
    gross_low = _pct_value_for_summary(get_value("gross_margin_low_pct"), get_value("gross_margin_low_ratio"))
    gross_high = _pct_value_for_summary(get_value("gross_margin_high_pct"), get_value("gross_margin_high_ratio"))
    op_base = _pct_value_for_summary(get_value("base_operating_margin_pct"), get_value("base_operating_margin_ratio"))
    op_low = _pct_value_for_summary(get_value("operating_margin_low_pct"), get_value("operating_margin_low_ratio"))
    op_high = _pct_value_for_summary(get_value("operating_margin_high_pct"), get_value("operating_margin_high_ratio"))

    return {
        "available": bool(available),
        "source": "M10 model_data",
        "task_id": get_value("m10_task_id"),
        "category_name": get_value("m10_category_name"),
        "taxonomy_key": get_value("m10_taxonomy_key"),
        "status": status,
        "status_label": M10_MARGIN_STATUS_LABELS.get(status, status or "未分類"),
        "margin_quality": quality or "N/A",
        "margin_rule": rule or "N/A",
        "margin_rule_label": M10_MARGIN_RULE_LABELS.get(rule, rule or "N/A"),
        "model_applicable": bool(model_applicable),
        "can_affect_valuation": bool(can_affect),
        "usage_label": usage_label,
        "base_gross_margin_pct": gross_base,
        "gross_margin_low_pct": gross_low,
        "gross_margin_high_pct": gross_high,
        "base_operating_margin_pct": op_base,
        "operating_margin_low_pct": op_low,
        "operating_margin_high_pct": op_high,
        "margin_profile": get_value("margin_profile"),
        "margin_model_usage": get_value("margin_model_usage"),
        "margin_reference_stocks": get_value("margin_reference_stocks"),
        "margin_notes": get_value("margin_notes"),
        "warning": get_value("m10_margin_warning"),
        "data_quality_grade": get_value("m10_data_quality_grade"),
        "valuation_ready_flag": get_value("m10_valuation_ready_flag"),
        "discount_factor": get_value("m10_discount_factor"),
    }


# 未在 taxonomy.py 明確設定時，由此表提供保守校準。
# base_pe 以「可解釋公式倍率」為主，不是追價倍數；hard_ceiling 為強制截斷上限。
CALIBRATION_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "FOUNDRY": {
        "base_pe": 24.0, "floor_pe": 16.0, "soft_ceiling_pe": 30.0, "hard_ceiling_pe": 35.0,
        "max_growth_factor": 1.16, "max_quality_factor": 1.10, "max_theme_factor": 1.06, "max_scale_factor": 1.00,
        "gross_margin_baseline": 0.54, "gross_margin_good": 0.58, "gross_margin_excellent": 0.62,
        "baked_in_themes": ["ai", "hpc", "cowos", "先進製程"],
        "geopolitical_factor": 0.92,
        "geopolitical_note": "台灣關鍵半導體供應鏈地緣政治折價；超大型晶圓代工龍頭不宜用 40x 以上作操作倍率。",
    },
    "IC_DESIGN_ASIC": {
        "base_pe": 35.0, "floor_pe": 22.0, "soft_ceiling_pe": 55.0, "hard_ceiling_pe": 70.0,
        "max_growth_factor": 1.25, "max_quality_factor": 1.22, "max_theme_factor": 1.18, "max_scale_factor": 1.08,
        "gross_margin_baseline": 0.42, "gross_margin_good": 0.48, "gross_margin_excellent": 0.55,
        "baked_in_themes": ["asic", "ai晶片", "ai asic"],
        "geopolitical_factor": 0.97,
    },
    "IP_EDA_DESIGN_SERVICE": {
        "base_pe": 42.0, "floor_pe": 25.0, "soft_ceiling_pe": 65.0, "hard_ceiling_pe": 80.0,
        "max_growth_factor": 1.25, "max_quality_factor": 1.25, "max_theme_factor": 1.15, "max_scale_factor": 1.08,
        "gross_margin_baseline": 0.55, "gross_margin_good": 0.65, "gross_margin_excellent": 0.75,
        "baked_in_themes": ["ip", "eda", "矽智財"],
        "geopolitical_factor": 0.97,
    },
    "OSAT_TESTING": {
        "base_pe": 24.0, "floor_pe": 15.0, "soft_ceiling_pe": 35.0, "hard_ceiling_pe": 42.0,
        "max_growth_factor": 1.18, "max_quality_factor": 1.12, "max_theme_factor": 1.10, "max_scale_factor": 1.04,
        "gross_margin_baseline": 0.22, "gross_margin_good": 0.28, "gross_margin_excellent": 0.35,
        "baked_in_themes": ["先進封裝", "cowos"], "geopolitical_factor": 0.96,
        "recovery_sensitive": True,
    },
    "PROBE_TEST_INTERFACE": {
        "base_pe": 34.0, "floor_pe": 22.0, "soft_ceiling_pe": 50.0, "hard_ceiling_pe": 60.0,
        "max_growth_factor": 1.22, "max_quality_factor": 1.20, "max_theme_factor": 1.12, "max_scale_factor": 1.08,
        "gross_margin_baseline": 0.38, "gross_margin_good": 0.45, "gross_margin_excellent": 0.52,
        "baked_in_themes": ["測試", "探針"], "geopolitical_factor": 0.97,
        "recovery_sensitive": True,
    },
    "SEMICAP_COWOS_EQUIPMENT": {
        "base_pe": 32.0, "floor_pe": 20.0, "soft_ceiling_pe": 48.0, "hard_ceiling_pe": 58.0,
        "max_growth_factor": 1.22, "max_quality_factor": 1.18, "max_theme_factor": 1.12, "max_scale_factor": 1.08,
        "gross_margin_baseline": 0.30, "gross_margin_good": 0.38, "gross_margin_excellent": 0.45,
        "baked_in_themes": ["cowos", "先進封裝", "設備"], "geopolitical_factor": 0.96,
        "recovery_sensitive": True,
    },
    "FAB_FACILITY_MATERIALS": {
        "base_pe": 26.0, "floor_pe": 16.0, "soft_ceiling_pe": 38.0, "hard_ceiling_pe": 45.0,
        "max_growth_factor": 1.16, "max_quality_factor": 1.12, "max_theme_factor": 1.08, "max_scale_factor": 1.05,
        "gross_margin_baseline": 0.24, "gross_margin_good": 0.30, "gross_margin_excellent": 0.36,
        "baked_in_themes": ["廠務", "材料"], "geopolitical_factor": 0.96,
        "recovery_sensitive": True,
    },
    "ABF_SUBSTRATE": {
        "base_pe": 30.0, "floor_pe": 18.0, "soft_ceiling_pe": 45.0, "hard_ceiling_pe": 55.0,
        "max_growth_factor": 1.20, "max_quality_factor": 1.16, "max_theme_factor": 1.10, "max_scale_factor": 1.06,
        "gross_margin_baseline": 0.23, "gross_margin_good": 0.30, "gross_margin_excellent": 0.38,
        "baked_in_themes": ["abf", "ai載板", "hpc", "載板"],
        "cyclical_low_base_cap": True,
        "recovery_sensitive": True,
    },
    "SERVER_PCB_BOARD": {
        "base_pe": 28.0, "floor_pe": 16.0, "soft_ceiling_pe": 42.0, "hard_ceiling_pe": 52.0,
        "max_growth_factor": 1.18, "max_quality_factor": 1.14, "max_theme_factor": 1.10, "max_scale_factor": 1.06,
        "gross_margin_baseline": 0.18, "gross_margin_good": 0.24, "gross_margin_excellent": 0.30,
        "baked_in_themes": ["ai伺服器", "高階pcb"],
        "recovery_sensitive": True,
    },
    "AI_SERVER_ODM": {
        "base_pe": 24.0, "floor_pe": 14.0, "soft_ceiling_pe": 34.0, "hard_ceiling_pe": 42.0,
        "max_growth_factor": 1.16, "max_quality_factor": 1.15, "max_theme_factor": 1.08, "max_scale_factor": 1.03,
        "gross_margin_baseline": 0.06, "gross_margin_good": 0.09, "gross_margin_excellent": 0.12,
        "baked_in_themes": ["ai", "ai伺服器", "資料中心"],
    },
    "CONNECTOR_CABLE": {
        "base_pe": 30.0, "floor_pe": 18.0, "soft_ceiling_pe": 45.0, "hard_ceiling_pe": 55.0,
        "max_growth_factor": 1.18, "max_quality_factor": 1.16, "max_theme_factor": 1.10, "max_scale_factor": 1.06,
        "gross_margin_baseline": 0.25, "gross_margin_good": 0.32, "gross_margin_excellent": 0.40,
        "baked_in_themes": ["高速傳輸", "連接器"],
    },
    "SERVER_CHASSIS_RAIL": {
        "base_pe": 26.0, "floor_pe": 16.0, "soft_ceiling_pe": 38.0, "hard_ceiling_pe": 45.0,
        "max_growth_factor": 1.15, "max_quality_factor": 1.12, "max_theme_factor": 1.08, "max_scale_factor": 1.05,
        "gross_margin_baseline": 0.20, "gross_margin_good": 0.26, "gross_margin_excellent": 0.32,
        "baked_in_themes": ["機構件", "滑軌", "機殼"],
    },
    "POWER_BBU": {
        "base_pe": 26.0, "floor_pe": 16.0, "soft_ceiling_pe": 38.0, "hard_ceiling_pe": 46.0,
        "max_growth_factor": 1.16, "max_quality_factor": 1.12, "max_theme_factor": 1.08, "max_scale_factor": 1.05,
        "gross_margin_baseline": 0.18, "gross_margin_good": 0.24, "gross_margin_excellent": 0.30,
        "baked_in_themes": ["電源", "bbu"],
    },
    "THERMAL_LIQUID_COOLING": {
        "base_pe": 34.0, "floor_pe": 20.0, "soft_ceiling_pe": 50.0, "hard_ceiling_pe": 62.0,
        "max_growth_factor": 1.20, "max_quality_factor": 1.18, "max_theme_factor": 1.12, "max_scale_factor": 1.08,
        "gross_margin_baseline": 0.26, "gross_margin_good": 0.32, "gross_margin_excellent": 0.40,
        "baked_in_themes": ["水冷", "液冷", "散熱"],
        "recovery_sensitive": "partial",
    },
    "OPTICAL_COMM_SILICON_PHOTONICS": {
        "base_pe": 36.0, "floor_pe": 22.0, "soft_ceiling_pe": 55.0, "hard_ceiling_pe": 68.0,
        "max_growth_factor": 1.22, "max_quality_factor": 1.18, "max_theme_factor": 1.12, "max_scale_factor": 1.08,
        "gross_margin_baseline": 0.32, "gross_margin_good": 0.40, "gross_margin_excellent": 0.48,
        "baked_in_themes": ["矽光子", "cpo", "800g", "1.6t"],
    },
    "NETWORK_SWITCH": {
        "base_pe": 28.0, "floor_pe": 16.0, "soft_ceiling_pe": 42.0, "hard_ceiling_pe": 52.0,
        "max_growth_factor": 1.18, "max_quality_factor": 1.14, "max_theme_factor": 1.08, "max_scale_factor": 1.05,
        "gross_margin_baseline": 0.24, "gross_margin_good": 0.32, "gross_margin_excellent": 0.40,
        "baked_in_themes": ["交換器", "網通"],
    },
    "OPTICS_LENS_MODULE": {
        "base_pe": 28.0, "floor_pe": 16.0, "soft_ceiling_pe": 42.0, "hard_ceiling_pe": 52.0,
        "max_growth_factor": 1.18, "max_quality_factor": 1.20, "max_theme_factor": 1.08, "max_scale_factor": 1.05,
        "gross_margin_baseline": 0.38, "gross_margin_good": 0.48, "gross_margin_excellent": 0.58,
        "baked_in_themes": ["光學", "鏡頭"],
    },
    "ROBOTICS_AUTOMATION": {
        "base_pe": 28.0, "floor_pe": 16.0, "soft_ceiling_pe": 42.0, "hard_ceiling_pe": 52.0,
        "max_growth_factor": 1.18, "max_quality_factor": 1.14, "max_theme_factor": 1.10, "max_scale_factor": 1.06,
        "gross_margin_baseline": 0.28, "gross_margin_good": 0.36, "gross_margin_excellent": 0.45,
        "baked_in_themes": ["機器人", "自動化"],
        "recovery_sensitive": True,
    },
    "SPACE_LEO_SATELLITE": {
        "base_pe": 30.0, "floor_pe": 16.0, "soft_ceiling_pe": 45.0, "hard_ceiling_pe": 55.0,
        "max_growth_factor": 1.16, "max_quality_factor": 1.14, "max_theme_factor": 1.10, "max_scale_factor": 1.06,
        "gross_margin_baseline": 0.25, "gross_margin_good": 0.33, "gross_margin_excellent": 0.42,
        "baked_in_themes": ["低軌", "衛星", "太空"],
    },
    "EV_AUTO_ELECTRONICS": {
        "base_pe": 28.0, "floor_pe": 16.0, "soft_ceiling_pe": 42.0, "hard_ceiling_pe": 50.0,
        "max_growth_factor": 1.16, "max_quality_factor": 1.14, "max_theme_factor": 1.08, "max_scale_factor": 1.05,
        "gross_margin_baseline": 0.22, "gross_margin_good": 0.30, "gross_margin_excellent": 0.38,
        "baked_in_themes": ["車用", "電動車"],
        "recovery_sensitive": "partial",
    },
    "GRID_POWER_STORAGE": {
        "base_pe": 28.0, "floor_pe": 16.0, "soft_ceiling_pe": 38.0, "hard_ceiling_pe": 46.0,
        "max_growth_factor": 1.16, "max_quality_factor": 1.15, "max_theme_factor": 1.08, "max_scale_factor": 1.05,
        "gross_margin_baseline": 0.18, "gross_margin_good": 0.24, "gross_margin_excellent": 0.30,
        "baked_in_themes": ["重電", "電網", "儲能"],
    },
    "SOFTWARE_SECURITY_CLOUD": {
        "base_pe": 32.0, "floor_pe": 18.0, "soft_ceiling_pe": 50.0, "hard_ceiling_pe": 60.0,
        "max_growth_factor": 1.20, "max_quality_factor": 1.20, "max_theme_factor": 1.08, "max_scale_factor": 1.06,
        "gross_margin_baseline": 0.45, "gross_margin_good": 0.55, "gross_margin_excellent": 0.65,
        "baked_in_themes": ["資安", "雲端", "軟體"],
    },
    "SPECIALTY_CHEM_ELECTRONIC_MATERIALS": {'base_pe': 17.0,
     'floor_pe': 10.0,
     'soft_ceiling_pe': 24.0,
     'hard_ceiling_pe': 30.0,
     'max_growth_factor': 1.1,
     'max_quality_factor': 1.12,
     'max_theme_factor': 1.05,
     'max_scale_factor': 1.03,
     'gross_margin_baseline': 0.22,
     'gross_margin_good': 0.28,
     'gross_margin_excellent': 0.35,
     'baked_in_themes': ['電子材料', 'PCB材料', '特用化學'],
     'recovery_sensitive': True},
    "CCL_HIGH_SPEED_MATERIALS": {'base_pe': 24.0,
     'floor_pe': 14.0,
     'soft_ceiling_pe': 35.0,
     'hard_ceiling_pe': 42.0,
     'max_growth_factor': 1.15,
     'max_quality_factor': 1.15,
     'max_theme_factor': 1.08,
     'max_scale_factor': 1.05,
     'gross_margin_baseline': 0.25,
     'gross_margin_good': 0.32,
     'gross_margin_excellent': 0.4,
     'baked_in_themes': ['ccl', '高速材料', 'ai伺服器材料'],
     'recovery_sensitive': True},
    "SEMICONDUCTOR_MATERIALS_CONSUMABLES": {'base_pe': 26.0,
     'floor_pe': 15.0,
     'soft_ceiling_pe': 38.0,
     'hard_ceiling_pe': 45.0,
     'max_growth_factor': 1.15,
     'max_quality_factor': 1.15,
     'max_theme_factor': 1.08,
     'max_scale_factor': 1.05,
     'gross_margin_baseline': 0.3,
     'gross_margin_good': 0.38,
     'gross_margin_excellent': 0.45,
     'baked_in_themes': ['半導體材料', '耗材', 'euv', '再生晶圓'],
     'recovery_sensitive': True},
    "CIS_SEMICONDUCTOR_OPTICS": {'base_pe': 28.0,
     'floor_pe': 15.0,
     'soft_ceiling_pe': 40.0,
     'hard_ceiling_pe': 50.0,
     'max_growth_factor': 1.18,
     'max_quality_factor': 1.18,
     'max_theme_factor': 1.1,
     'max_scale_factor': 1.05,
     'gross_margin_baseline': 0.32,
     'gross_margin_good': 0.42,
     'gross_margin_excellent': 0.5,
     'baked_in_themes': ['cis', '影像感測', '半導體光學'],
     'recovery_sensitive': True},
    "TEST_AUTOMATION_EQUIPMENT": {'base_pe': 30.0,
     'floor_pe': 18.0,
     'soft_ceiling_pe': 42.0,
     'hard_ceiling_pe': 50.0,
     'max_growth_factor': 1.18,
     'max_quality_factor': 1.16,
     'max_theme_factor': 1.1,
     'max_scale_factor': 1.06,
     'gross_margin_baseline': 0.28,
     'gross_margin_good': 0.36,
     'gross_margin_excellent': 0.45,
     'baked_in_themes': ['aoi', '檢測設備', '自動化設備'],
     'recovery_sensitive': True},
    "GREEN_ENERGY_INFRA": {'base_pe': 22.0,
     'floor_pe': 10.0,
     'soft_ceiling_pe': 30.0,
     'hard_ceiling_pe': 38.0,
     'max_growth_factor': 1.12,
     'max_quality_factor': 1.1,
     'max_theme_factor': 1.03,
     'max_scale_factor': 1.03,
     'gross_margin_baseline': 0.15,
     'gross_margin_good': 0.22,
     'gross_margin_excellent': 0.28,
     'baked_in_themes': ['綠能', '風電', '儲能'],
     'recovery_sensitive': True},
    "AUTO_PARTS_AM": {'base_pe': 16.0,
     'floor_pe': 8.0,
     'soft_ceiling_pe': 24.0,
     'hard_ceiling_pe': 30.0,
     'max_growth_factor': 1.1,
     'max_quality_factor': 1.1,
     'max_theme_factor': 1.02,
     'max_scale_factor': 1.03,
     'gross_margin_baseline': 0.22,
     'gross_margin_good': 0.3,
     'gross_margin_excellent': 0.38,
     'baked_in_themes': ['am汽車零件'],
     'recovery_sensitive': True},
    "AUTO_PARTS_EV": {'base_pe': 22.0,
     'floor_pe': 12.0,
     'soft_ceiling_pe': 32.0,
     'hard_ceiling_pe': 40.0,
     'max_growth_factor': 1.14,
     'max_quality_factor': 1.12,
     'max_theme_factor': 1.06,
     'max_scale_factor': 1.04,
     'gross_margin_baseline': 0.2,
     'gross_margin_good': 0.28,
     'gross_margin_excellent': 0.35,
     'baked_in_themes': ['ev零組件', '車用零件'],
     'recovery_sensitive': True},
    "AUTO_OEM_CYCLE": {'base_pe': 12.0,
     'floor_pe': 6.0,
     'soft_ceiling_pe': 18.0,
     'hard_ceiling_pe': 24.0,
     'max_growth_factor': 1.08,
     'max_quality_factor': 1.05,
     'max_theme_factor': 1.0,
     'max_scale_factor': 1.02,
     'gross_margin_baseline': 0.12,
     'gross_margin_good': 0.18,
     'gross_margin_excellent': 0.25,
     'baked_in_themes': ['整車', '汽車集團'],
     'recovery_sensitive': True},
    "AI_SERVER_BOARD_SYSTEM": {'base_pe': 26.0,
     'floor_pe': 14.0,
     'soft_ceiling_pe': 36.0,
     'hard_ceiling_pe': 45.0,
     'max_growth_factor': 1.16,
     'max_quality_factor': 1.14,
     'max_theme_factor': 1.08,
     'max_scale_factor': 1.04,
     'gross_margin_baseline': 0.12,
     'gross_margin_good': 0.18,
     'gross_margin_excellent': 0.25,
     'baked_in_themes': ['主板', '板卡', 'ai伺服器系統'],
     'recovery_sensitive': True},
    "PC_BRAND_AI_PC": {'base_pe': 18.0,
     'floor_pe': 10.0,
     'soft_ceiling_pe': 28.0,
     'hard_ceiling_pe': 35.0,
     'max_growth_factor': 1.12,
     'max_quality_factor': 1.12,
     'max_theme_factor': 1.05,
     'max_scale_factor': 1.03,
     'gross_margin_baseline': 0.1,
     'gross_margin_good': 0.16,
     'gross_margin_excellent': 0.24,
     'baked_in_themes': ['ai pc', 'pc品牌'],
     'recovery_sensitive': True},
    "PC_NB_ODM": {'base_pe': 16.0,
     'floor_pe': 8.0,
     'soft_ceiling_pe': 24.0,
     'hard_ceiling_pe': 32.0,
     'max_growth_factor': 1.1,
     'max_quality_factor': 1.08,
     'max_theme_factor': 1.03,
     'max_scale_factor': 1.02,
     'gross_margin_baseline': 0.04,
     'gross_margin_good': 0.07,
     'gross_margin_excellent': 0.1,
     'baked_in_themes': ['nb odm', 'ems'],
     'recovery_sensitive': True},
    "MACHINE_TOOL_CYCLE": {'base_pe': 14.0,
     'floor_pe': 8.0,
     'soft_ceiling_pe': 22.0,
     'hard_ceiling_pe': 30.0,
     'max_growth_factor': 1.1,
     'max_quality_factor': 1.08,
     'max_theme_factor': 1.02,
     'max_scale_factor': 1.02,
     'gross_margin_baseline': 0.18,
     'gross_margin_good': 0.25,
     'gross_margin_excellent': 0.32,
     'baked_in_themes': ['工具機', '工業機械'],
     'recovery_sensitive': True},
    "MEMORY_CONTROLLER_CYCLE": {'base_pe': 24.0,
     'floor_pe': 12.0,
     'soft_ceiling_pe': 35.0,
     'hard_ceiling_pe': 45.0,
     'max_growth_factor': 1.15,
     'max_quality_factor': 1.14,
     'max_theme_factor': 1.06,
     'max_scale_factor': 1.04,
     'gross_margin_baseline': 0.25,
     'gross_margin_good': 0.35,
     'gross_margin_excellent': 0.45,
     'baked_in_themes': ['nand控制ic', '記憶體'],
     'recovery_sensitive': True},
    "RF_MODULE_PACKAGING": {'base_pe': 24.0,
     'floor_pe': 12.0,
     'soft_ceiling_pe': 34.0,
     'hard_ceiling_pe': 42.0,
     'max_growth_factor': 1.14,
     'max_quality_factor': 1.12,
     'max_theme_factor': 1.06,
     'max_scale_factor': 1.03,
     'gross_margin_baseline': 0.22,
     'gross_margin_good': 0.3,
     'gross_margin_excellent': 0.38,
     'baked_in_themes': ['rf', '高頻', '特殊封裝'],
     'recovery_sensitive': True},
    "GENERAL": {
        "base_pe": 20.0, "floor_pe": 10.0, "soft_ceiling_pe": 28.0, "hard_ceiling_pe": 35.0,
        "max_growth_factor": 1.12, "max_quality_factor": 1.10, "max_theme_factor": 1.05, "max_scale_factor": 1.03,
        "gross_margin_baseline": None,
    },
}



# ===== 第 17-C-6：IC 設計 / ASIC / IP 分層預設校準 =====
CALIBRATION_DEFAULTS.update({
    "IC_DESIGN_ASIC_SERVICE": {
        "base_pe": 35.0, "floor_pe": 22.0, "soft_ceiling_pe": 55.0, "hard_ceiling_pe": 70.0,
        "max_growth_factor": 1.25, "max_quality_factor": 1.20, "max_theme_factor": 1.12, "max_scale_factor": 1.08,
        "gross_margin_baseline": 0.42, "gross_margin_good": 0.50, "gross_margin_excellent": 0.60,
        "baked_in_themes": ["asic", "設計服務", "nre"],
        "geopolitical_factor": 0.97,
    },
    "IC_DESIGN_ASIC_HIGH_VISIBILITY": {
        "base_pe": 45.0, "floor_pe": 28.0, "soft_ceiling_pe": 70.0, "hard_ceiling_pe": 85.0,
        "max_growth_factor": 1.30, "max_quality_factor": 1.22, "max_theme_factor": 1.12, "max_scale_factor": 1.08,
        "gross_margin_baseline": 0.45, "gross_margin_good": 0.55, "gross_margin_excellent": 0.65,
        "baked_in_themes": ["ai asic", "custom silicon", "hyperscaler", "hpc"],
        "geopolitical_factor": 0.97,
    },
    "IC_DESIGN_IP_ROYALTY": {
        "base_pe": 45.0, "floor_pe": 28.0, "soft_ceiling_pe": 75.0, "hard_ceiling_pe": 90.0,
        "max_growth_factor": 1.28, "max_quality_factor": 1.25, "max_theme_factor": 1.10, "max_scale_factor": 1.08,
        "gross_margin_baseline": 0.55, "gross_margin_good": 0.65, "gross_margin_excellent": 0.75,
        "baked_in_themes": ["ip", "矽智財", "royalty", "eda"],
        "geopolitical_factor": 0.98,
    },
    "IC_DESIGN_PLATFORM_AI_EDGE": {
        "base_pe": 24.0, "floor_pe": 14.0, "soft_ceiling_pe": 38.0, "hard_ceiling_pe": 50.0,
        "max_growth_factor": 1.18, "max_quality_factor": 1.14, "max_theme_factor": 1.08, "max_scale_factor": 1.03,
        "gross_margin_baseline": 0.42, "gross_margin_good": 0.48, "gross_margin_excellent": 0.55,
        "baked_in_themes": ["ai edge", "手機晶片", "平台型 ic"],
        "geopolitical_factor": 0.97,
    },
})

# ===== 第 17-C-9：第一批 AI 混合股補充預設校準 =====
CALIBRATION_DEFAULTS.update({
    "EMS_PLATFORM_CONTRACT_MANUFACTURING": {
        "base_pe": 14.0, "floor_pe": 8.0, "soft_ceiling_pe": 24.0, "hard_ceiling_pe": 32.0,
        "max_growth_factor": 1.10, "max_quality_factor": 1.08, "max_theme_factor": 1.05, "max_scale_factor": 1.02,
        "gross_margin_baseline": 0.06, "gross_margin_good": 0.09, "gross_margin_excellent": 0.12,
        "baked_in_themes": ["ems", "電子製造服務", "平台型製造"],
        "geopolitical_factor": 0.97,
        "recovery_sensitive": True,
    },
})

# ===== 第 17-C-7A：混合產業權重估值引擎 =====
def _safe_weight(x: Any) -> float:
    v = _sf(x, 0.0) or 0.0
    return max(0.0, min(float(v), 0.50))


def _hybrid_weight_for_key(hybrid: Dict[str, Any], key: str) -> float:
    base_weight = float(hybrid.get("effective_weight", hybrid.get("weight", 0)) or 0)
    aliases = {
        "base_pe": ("base_weight", "base_pe_weight"),
        "floor_pe": ("floor_weight", "floor_pe_weight"),
        "soft_ceiling_pe": ("soft_weight", "soft_ceiling_weight", "soft_ceiling_pe_weight"),
        "hard_ceiling_pe": ("hard_weight", "hard_ceiling_weight", "hard_ceiling_pe_weight"),
    }.get(key, (f"{key}_weight",))
    for alias in aliases:
        if hybrid.get(alias) is not None:
            return _safe_weight(hybrid.get(alias))
    return _safe_weight(base_weight)


def _hybrid_key_weights(hybrids: List[Dict[str, Any]], key: str) -> tuple[List[float], float]:
    weights: List[float] = []
    total_weight = 0.0
    for h in hybrids:
        weight = _hybrid_weight_for_key(h, key)
        if total_weight + weight > 0.50:
            weight = max(0.0, 0.50 - total_weight)
        weights.append(weight)
        total_weight += weight
        if total_weight >= 0.50:
            weights.extend([0.0] * (len(hybrids) - len(weights)))
            break
    return weights, total_weight


def _weighted_value(primary: Any, hybrids: List[Dict[str, Any]], key: str) -> Optional[float]:
    base = _sf(primary)
    if base is None:
        return None
    key_weights, total_hybrid_weight = _hybrid_key_weights(hybrids, key)
    primary_weight = 1.0 - total_hybrid_weight
    total = base * primary_weight
    for h, weight in zip(hybrids, key_weights):
        hv = _sf(h.get(key))
        if hv is not None:
            total += hv * weight
    return total


def _build_hybrid_calibration(industry_profile: Dict[str, Any], primary_calibration: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """建立混合產業權重後的校準參數。

    原則：
    - hybrid_taxons 必須由 stock_mapping.py 人工指定，不由 AI 自動亂加。
    - total_weight 硬上限 0.50。
    - 若 classification 非 confirmed 或 Forward EPS 缺值/有嚴重分歧，後續可在此擴充折半；17-C-7A 先建立引擎。
    - 若 hybrid taxon 與 primary 相同，或已明顯內含 baked_in_themes，跳過避免重複加分。
    """
    p = industry_profile or {}
    hybrids_raw = p.get("hybrid_taxons") or []
    if not isinstance(hybrids_raw, list) or not hybrids_raw:
        return dict(primary_calibration), {"enabled": False, "reason": "未設定混合產業權重", "hybrids": []}

    primary_key = str(p.get("model_key") or p.get("taxon_key") or "").strip().upper()
    primary_baked = {str(x).lower() for x in (primary_calibration.get("baked_in_themes") or [])}
    valid = []
    total_weight = 0.0
    reasons = []

    for h in hybrids_raw:
        if not isinstance(h, dict):
            continue
        taxon = str(h.get("taxon") or "").strip().upper()
        weight = _safe_weight(h.get("weight"))
        if not taxon or weight <= 0:
            continue
        if taxon == primary_key:
            reasons.append(f"{taxon} 與主分類相同，跳過避免重複加分")
            continue
        hc = dict(CALIBRATION_DEFAULTS.get(taxon, {}))
        # 若 DEFAULTS 沒有，仍可用 taxonomy 參數；避免 import 循環，使用 dynamic defaults 為主。
        if not hc:
            reasons.append(f"{taxon} 找不到校準參數，跳過")
            continue
        # 內含題材防重複：若 hybrid taxon baked themes 已全部包含在 primary baked，降低至 0。
        hybrid_baked = {str(x).lower() for x in (hc.get("baked_in_themes") or [])}
        if hybrid_baked and primary_baked and hybrid_baked.issubset(primary_baked):
            reasons.append(f"{taxon} 題材已內含於主分類，跳過")
            continue
        if total_weight + weight > 0.50:
            weight = max(0.0, 0.50 - total_weight)
        if weight <= 0:
            continue
        hc["taxon"] = taxon
        hc["weight"] = weight
        hc["effective_weight"] = weight
        hc["reason"] = str(h.get("reason") or "")
        for weight_key in [
            "base_weight", "base_pe_weight",
            "floor_weight", "floor_pe_weight",
            "soft_weight", "soft_ceiling_weight", "soft_ceiling_pe_weight",
            "hard_weight", "hard_ceiling_weight", "hard_ceiling_pe_weight",
        ]:
            if h.get(weight_key) is not None:
                hc[weight_key] = h.get(weight_key)
        valid.append(hc)
        total_weight += weight
        if total_weight >= 0.50:
            break

    if not valid:
        return dict(primary_calibration), {"enabled": False, "reason": "混合產業權重全部被跳過；" + "；".join(reasons), "hybrids": []}

    primary_weight = max(0.50, 1.0 - total_weight)
    c = dict(primary_calibration)

    for key in ["base_pe", "floor_pe", "soft_ceiling_pe", "hard_ceiling_pe",
                "gross_margin_baseline", "gross_margin_good", "gross_margin_excellent",
                "max_growth_factor", "max_quality_factor", "max_theme_factor", "max_scale_factor"]:
        v = _weighted_value(primary_calibration.get(key), valid, key)
        if v is not None:
            c[key] = round(v, 4)

    # 風險與 baked theme 合併，避免題材係數再次過度加分。
    baked = list(primary_calibration.get("baked_in_themes") or [])
    for h in valid:
        baked.extend(h.get("baked_in_themes") or [])
    if baked:
        c["baked_in_themes"] = sorted(set(str(x) for x in baked if str(x).strip()))

    note_parts = [
        f"主分類權重 {primary_weight:.0%}",
        *[
            f"{h.get('taxon')} {float(h.get('effective_weight', 0)):.0%}"
            + (
                f"（hard {_hybrid_weight_for_key(h, 'hard_ceiling_pe'):.0%}）"
                if abs(_hybrid_weight_for_key(h, "hard_ceiling_pe") - float(h.get("effective_weight", 0) or 0)) > 1e-9
                else ""
            )
            + (f"（{h.get('reason')}）" if h.get("reason") else "")
            for h in valid
        ],
    ]
    summary = {
        "enabled": True,
        "primary_weight": primary_weight,
        "total_hybrid_weight": total_weight,
        "hybrids": [
            {
                "taxon": h.get("taxon"),
                "weight": h.get("effective_weight"),
                "hard_weight": _hybrid_weight_for_key(h, "hard_ceiling_pe"),
                "reason": h.get("reason", ""),
            }
            for h in valid
        ],
        "reason": "；".join(note_parts + reasons),
        "mixed_base_pe": c.get("base_pe"),
        "mixed_soft_ceiling_pe": c.get("soft_ceiling_pe"),
        "mixed_hard_ceiling_pe": c.get("hard_ceiling_pe"),
    }
    return c, summary

def _calibration(industry_profile: Dict[str, Any]) -> Dict[str, Any]:
    key = str(industry_profile.get("model_key") or industry_profile.get("taxon_key") or "GENERAL")
    c = dict(CALIBRATION_DEFAULTS.get(key, CALIBRATION_DEFAULTS.get("GENERAL", {})))
    # 若 taxonomy 已明確設新欄位，允許覆寫；舊 base_pe/pe_range 不直接覆寫保守校準，避免舊表過度樂觀。
    for k in [
        "floor_pe", "soft_ceiling_pe", "hard_ceiling_pe",
        "max_growth_factor", "max_quality_factor", "max_theme_factor", "max_scale_factor",
        "gross_margin_baseline", "gross_margin_good", "gross_margin_excellent",
        "baked_in_themes", "geopolitical_factor", "geopolitical_note",
        "m10_margin_available", "m10_margin_status", "m10_task_id", "m10_category_name",
        "base_gross_margin_ratio", "gross_margin_low_ratio", "gross_margin_high_ratio",
        "base_operating_margin_ratio", "operating_margin_low_ratio", "operating_margin_high_ratio",
        "margin_quality", "margin_rule", "margin_model_applicable", "margin_can_affect_valuation",
    ]:
        if industry_profile.get(k) is not None:
            c[k] = industry_profile.get(k)
    if c.get("base_pe") is None:
        c["base_pe"] = _sf(industry_profile.get("base_pe"), 20.0) or 20.0

    # 17-C-7A：若 stock_mapping.py 有人工指定 hybrid_taxons，混合 base/soft/hard 與係數上限。
    mixed, summary = _build_hybrid_calibration(industry_profile, c)
    mixed["hybrid_summary"] = summary
    return mixed


def _growth_to_factor(growth: Optional[float]) -> float:
    if growth is None:
        return 1.00
    if growth < -0.20:
        return 0.85
    if growth < 0:
        return 0.92
    if growth < 0.10:
        return 1.00
    if growth < 0.20:
        return 1.05
    if growth < 0.35:
        return 1.10
    if growth < 0.60:
        return 1.15
    if growth < 1.00:
        return 1.20
    return 1.25


def growth_factor_hierarchical(
    *,
    system_forward_eps: Any = None,
    ai_forward_eps: Any = None,
    consensus_forward_eps: Any = None,
    ttm_eps: Any = None,
    ai_ttm_eps: Any = None,
    revenue_yoy: Any = None,
    revenue_yoy_3m: Any = None,
    industry_profile: Dict[str, Any] = None,
    calibration: Dict[str, Any] = None,
    roe: Any = None,
    gross_margin: Any = None,
) -> Dict[str, Any]:
    """成長係數只採一個最高優先資料源，避免重複加分。"""
    industry_profile = industry_profile or {}
    calibration = calibration or {}
    base_eps = _sf(ttm_eps) or _sf(ai_ttm_eps)
    consensus = _sf(consensus_forward_eps)
    system_f = _sf(system_forward_eps)
    ai_f = _sf(ai_forward_eps)

    src = None
    growth = None
    if base_eps and base_eps > 0 and consensus and consensus > 0:
        growth = (consensus - base_eps) / base_eps
        src = "法人共識 Forward EPS 成長"
    elif base_eps and base_eps > 0 and system_f and system_f > 0:
        growth = (system_f - base_eps) / base_eps
        src = "系統 Forward EPS 成長"
    elif base_eps and base_eps > 0 and ai_f and ai_f > 0:
        growth = (ai_f - base_eps) / base_eps
        src = "AI Forward EPS 成長"
    elif _pct01(revenue_yoy_3m) is not None:
        growth = _pct01(revenue_yoy_3m)
        src = "近三個月營收 YoY 平均"
    elif _pct01(revenue_yoy) is not None:
        growth = _pct01(revenue_yoy)
        src = "最新單月 / 最新可得營收 YoY"

    if growth is None:
        return {"factor": 1.00, "reason": "缺少 Forward EPS 或營收 YoY，成長係數 ×1.00", "source": "none", "growth": None}

    factor = _growth_to_factor(growth)
    reason = f"採用{src}：{_fmt_pct(growth)}；低優先級成長項不重複加分"

    # 循環股低基期修復：EPS 成長很高，但 ROE / 毛利未改善時不可視為長期結構成長。
    cyc = bool(industry_profile.get("cyclical"))
    r = _pct01(roe)
    gm = _pct01(gross_margin)
    gm_base = calibration.get("gross_margin_baseline")
    gm_base = _sf(gm_base)
    if cyc and growth is not None and growth > 1.0:
        cap = 1.18
        if (r is not None and r < 0.10) or (gm is not None and gm_base is not None and gm < gm_base):
            cap = 1.12
            reason += "；循環股高成長疑似低基期修復，且 ROE/毛利未同步改善，成長係數保守上限 ×1.12"
        else:
            reason += "；循環股高成長採低基期折扣，成長係數上限 ×1.18"
        factor = min(factor, cap)

    max_f = _sf(calibration.get("max_growth_factor"), 1.20) or 1.20
    clipped = min(factor, max_f)
    if clipped < factor:
        reason += f"；套用產業成長係數上限 ×{max_f:.2f}"
    return {"factor": round(clipped, 4), "reason": reason, "source": src, "growth": growth}


def _linear_score(value: float, left: float, right: float, out_left: float, out_right: float) -> float:
    """線性插值工具：value 在 left~right 間，輸出 out_left~out_right。"""
    if right == left:
        return out_right
    ratio = (value - left) / (right - left)
    ratio = max(0.0, min(1.0, ratio))
    return out_left + (out_right - out_left) * ratio


def _absolute_margin_adjustment(gm: Optional[float]) -> tuple[float, str]:
    """第 17-C-5：絕對毛利率水準調整，不同毛利率區間給漸進式加減分。"""
    if gm is None:
        return 0.0, "絕對毛利率缺值"
    if gm < 0.10:
        return -0.06, f"絕對毛利率 {_fmt_pct(gm)} 低於 10%，品質扣分 -0.06"
    if gm < 0.20:
        return _linear_score(gm, 0.10, 0.20, -0.02, 0.00), f"絕對毛利率 {_fmt_pct(gm)} 位於 10%～20%，偏低至中性"
    if gm < 0.30:
        return _linear_score(gm, 0.20, 0.30, 0.00, 0.02), f"絕對毛利率 {_fmt_pct(gm)} 位於 20%～30%，中性略佳"
    if gm < 0.40:
        return _linear_score(gm, 0.30, 0.40, 0.02, 0.04), f"絕對毛利率 {_fmt_pct(gm)} 位於 30%～40%，品質加分"
    if gm < 0.50:
        return _linear_score(gm, 0.40, 0.50, 0.04, 0.06), f"絕對毛利率 {_fmt_pct(gm)} 位於 40%～50%，高毛利加分"
    if gm < 0.60:
        return _linear_score(gm, 0.50, 0.60, 0.06, 0.08), f"絕對毛利率 {_fmt_pct(gm)} 位於 50%～60%，高毛利加分"
    return 0.10, f"絕對毛利率 {_fmt_pct(gm)} 高於 60%，絕對毛利加分上限 +0.10"


def _relative_margin_adjustment(
    gm: Optional[float],
    gm_base: Optional[float],
    gm_good: Optional[float],
    gm_excellent: Optional[float],
) -> tuple[float, str]:
    """第 17-C-5：相對產業毛利門檻調整，包含低於同業的扣分。"""
    if gm is None:
        return 0.0, "相對產業毛利無法判斷"
    if gm_base is None:
        if gm < 0.10:
            return -0.04, f"缺少產業毛利基準；毛利率 {_fmt_pct(gm)} 偏低，保守扣分"
        if gm >= 0.45:
            return 0.02, f"缺少產業毛利基準；毛利率 {_fmt_pct(gm)} 偏高，但僅小幅加分"
        return 0.0, f"缺少產業毛利基準；毛利率 {_fmt_pct(gm)} 不做相對加分"

    # 低於同業：分層扣分，不再只粗略扣 0.96/0.90。
    if gm < gm_base:
        gap = gm_base - gm
        if gap >= 0.10:
            return -0.10, f"毛利率 {_fmt_pct(gm)} 較產業基準 {_fmt_pct(gm_base)} 低超過 10 個百分點，明顯低於同業"
        if gap >= 0.05:
            return -0.07, f"毛利率 {_fmt_pct(gm)} 較產業基準 {_fmt_pct(gm_base)} 低 5～10 個百分點，低於同業"
        return -0.03, f"毛利率 {_fmt_pct(gm)} 略低於產業基準 {_fmt_pct(gm_base)}"

    # 高於同業：採漸進式，不再只要高於 good 就碰上限。
    if gm_good is None or gm_excellent is None or gm_excellent <= gm_good:
        if gm >= gm_base + 0.10:
            return 0.05, f"毛利率 {_fmt_pct(gm)} 明顯高於產業基準 {_fmt_pct(gm_base)}"
        if gm >= gm_base + 0.05:
            return 0.03, f"毛利率 {_fmt_pct(gm)} 高於產業基準 {_fmt_pct(gm_base)}"
        return 0.01, f"毛利率 {_fmt_pct(gm)} 略高於產業基準 {_fmt_pct(gm_base)}"

    if gm < gm_good:
        adj = _linear_score(gm, gm_base, gm_good, 0.01, 0.03)
        return adj, f"毛利率 {_fmt_pct(gm)} 位於產業基準～good 區間，僅小幅加分"
    if gm < gm_excellent:
        adj = _linear_score(gm, gm_good, gm_excellent, 0.04, 0.08)
        return adj, f"毛利率 {_fmt_pct(gm)} 位於 good～excellent 區間，漸進式加分"
    # 超過 excellent 才給較高相對加分，但仍交由產業 max_quality_factor 截斷。
    extra = min(0.04, max(0.0, gm - gm_excellent) * 0.5)
    return 0.09 + extra, f"毛利率 {_fmt_pct(gm)} 高於產業 excellent 門檻 {_fmt_pct(gm_excellent)}，相對同業優勢明確"


def _roe_adjustment(roev: Optional[float]) -> tuple[float, str]:
    """第 17-C-5：ROE 漸進式調整，不直接把品質推到上限。"""
    if roev is None:
        return 0.0, "ROE 缺值"
    if roev < 0:
        return -0.08, f"ROE {_fmt_pct(roev)} 為負"
    if roev < 0.08:
        return -0.04, f"ROE {_fmt_pct(roev)} 偏低"
    if roev < 0.15:
        return 0.0, f"ROE {_fmt_pct(roev)} 中性"
    if roev < 0.25:
        return _linear_score(roev, 0.15, 0.25, 0.02, 0.04), f"ROE {_fmt_pct(roev)} 正常偏佳，小幅加分"
    if roev < 0.35:
        return _linear_score(roev, 0.25, 0.35, 0.05, 0.07), f"ROE {_fmt_pct(roev)} 優良"
    return 0.09, f"ROE {_fmt_pct(roev)} 極佳"


def _operating_margin_adjustment(opm: Optional[float]) -> tuple[float, str]:
    """第 17-C-16：營益率納入品質係數，而不只是高毛利低轉換率防呆。"""
    if opm is None:
        return 0.0, "營益率缺值"
    if opm < 0:
        return -0.08, f"營益率 {_fmt_pct(opm)} 為負"
    if opm < 0.05:
        return -0.04, f"營益率 {_fmt_pct(opm)} 偏低，獲利轉換率不足"
    if opm < 0.10:
        return -0.02, f"營益率 {_fmt_pct(opm)} 略低"
    if opm < 0.15:
        return 0.0, f"營益率 {_fmt_pct(opm)} 中性"
    if opm < 0.25:
        return _linear_score(opm, 0.15, 0.25, 0.01, 0.03), f"營益率 {_fmt_pct(opm)} 正常偏佳，小幅加分"
    if opm < 0.35:
        return _linear_score(opm, 0.25, 0.35, 0.04, 0.06), f"營益率 {_fmt_pct(opm)} 優良"
    return 0.07, f"營益率 {_fmt_pct(opm)} 極佳，獲利轉換率明確"


def _relative_operating_margin_adjustment(
    opm: Optional[float],
    op_base: Optional[float],
    op_low: Optional[float] = None,
    op_high: Optional[float] = None,
) -> tuple[float, str]:
    """M10：營益率相對分類 benchmark 的小幅調整。"""
    if opm is None:
        return 0.0, "M10 營益率相對 benchmark 缺公司營益率"
    if op_base is None:
        return 0.0, "M10 營益率 benchmark 缺值"

    gap = opm - op_base
    if op_low is not None and opm < op_low:
        return -0.05, f"營益率 {_fmt_pct(opm)} 低於 M10 分類下緣 {_fmt_pct(op_low)}"
    if gap <= -0.10:
        return -0.05, f"營益率 {_fmt_pct(opm)} 較 M10 分類基準 {_fmt_pct(op_base)} 低超過 10 個百分點"
    if gap <= -0.05:
        return -0.03, f"營益率 {_fmt_pct(opm)} 較 M10 分類基準 {_fmt_pct(op_base)} 低 5～10 個百分點"
    if gap < -0.02:
        return -0.01, f"營益率 {_fmt_pct(opm)} 略低於 M10 分類基準 {_fmt_pct(op_base)}"
    if op_high is not None and opm > op_high:
        return 0.04, f"營益率 {_fmt_pct(opm)} 高於 M10 分類上緣 {_fmt_pct(op_high)}，小幅品質加分"
    if gap >= 0.10:
        return 0.04, f"營益率 {_fmt_pct(opm)} 較 M10 分類基準 {_fmt_pct(op_base)} 高超過 10 個百分點"
    if gap >= 0.05:
        return 0.025, f"營益率 {_fmt_pct(opm)} 較 M10 分類基準 {_fmt_pct(op_base)} 高 5～10 個百分點"
    if gap > 0.02:
        return 0.01, f"營益率 {_fmt_pct(opm)} 略高於 M10 分類基準 {_fmt_pct(op_base)}"
    return 0.0, f"營益率 {_fmt_pct(opm)} 接近 M10 分類基準 {_fmt_pct(op_base)}"


def _operating_margin_guard(
    opm: Optional[float],
    gm: Optional[float],
    factor: float,
    notes: List[str],
) -> float:
    """第 17-C-5：營益率輔助判斷，避免高毛利但費用率吃掉獲利仍拿高品質分。"""
    if opm is None:
        return factor
    if opm < 0:
        notes.append(f"營益率 {_fmt_pct(opm)} 為負，品質折價")
        return min(factor, 0.94)
    if gm is not None and gm >= 0.30 and opm < 0.05 and factor > 1.0:
        notes.append(f"毛利率 {_fmt_pct(gm)} 不低，但營益率僅 {_fmt_pct(opm)}，費用率/營運槓桿壓力，品質溢價減半")
        return 1.0 + (factor - 1.0) * 0.5
    if opm < 0.03 and factor > 1.0:
        notes.append(f"營益率 {_fmt_pct(opm)} 偏低，品質溢價折半")
        return 1.0 + (factor - 1.0) * 0.5
    return factor


def quality_factor_relative(
    gross_margin: Any,
    roe: Any = None,
    revenue_yoy: Any = None,
    eps_positive: bool = True,
    debt_to_equity: Any = None,
    warning_count: int = 0,
    calibration: Dict[str, Any] = None,
    operating_margin: Any = None,
    free_cash_flow: Any = None,
) -> Dict[str, Any]:
    """第 17-C-5：品質係數細緻化。

    不再採用「高於 good 門檻就直接套 max_quality_factor」。
    改為：
    1) 絕對毛利率水準
    2) 相對產業毛利位置，含低於同業分層扣分
    3) ROE 漸進式加減分
    4) 營益率獲利轉換率加減分
    5) 高毛利低營益率、D/E、FCF 與資料分歧防呆
    6) 最後才套產業 max_quality_factor
    """
    calibration = calibration or {}
    gm = _pct01(gross_margin)
    roev = _pct01(roe)
    opm = _pct01(operating_margin)
    de = _sf(debt_to_equity)
    fcf = _sf(free_cash_flow)
    max_q = _sf(calibration.get("max_quality_factor"), 1.12) or 1.12
    min_q = _sf(calibration.get("min_quality_factor"), 0.86) or 0.86
    gm_base = _sf(calibration.get("gross_margin_baseline"))
    gm_good = _sf(calibration.get("gross_margin_good"))
    gm_excellent = _sf(calibration.get("gross_margin_excellent"))
    margin_quality = str(calibration.get("margin_quality") or "").strip().upper()
    margin_rule = str(calibration.get("margin_rule") or "").strip()
    margin_status = str(calibration.get("m10_margin_status") or "").strip()
    has_m10_margin = bool(calibration.get("m10_margin_available")) or bool(margin_quality) or bool(margin_rule)
    margin_model_applicable = calibration.get("margin_model_applicable")
    if margin_model_applicable is None:
        margin_model_applicable = not (has_m10_margin and (margin_quality == "N/A" or margin_rule == "margin_not_applicable"))
    margin_can_affect = calibration.get("margin_can_affect_valuation")
    if margin_can_affect is None:
        margin_can_affect = bool(margin_model_applicable) and not (
            has_m10_margin and (margin_quality == "C" or margin_rule == "event_or_cycle_tracking_only")
        )
    op_base = _sf(calibration.get("base_operating_margin_ratio"))
    op_low = _sf(calibration.get("operating_margin_low_ratio"))
    op_high = _sf(calibration.get("operating_margin_high_ratio"))

    if not eps_positive:
        return {"factor": 1.00, "reason": "EPS 不穩或為負，不給品質係數溢價"}

    notes: List[str] = []
    adjustment = 0.0

    abs_adj, abs_note = _absolute_margin_adjustment(gm)
    rel_adj, rel_note = _relative_margin_adjustment(gm, gm_base, gm_good, gm_excellent)
    roe_adj, roe_note = _roe_adjustment(roev)
    op_adj, op_note = _operating_margin_adjustment(opm)
    if has_m10_margin and op_base is not None:
        op_rel_adj, op_rel_note = _relative_operating_margin_adjustment(opm, op_base, op_low, op_high)
    else:
        op_rel_adj, op_rel_note = 0.0, ""

    margin_adj = abs_adj + rel_adj + op_adj + op_rel_adj
    margin_notes = [x for x in [abs_note, rel_note, op_note, op_rel_note] if x]

    if not margin_model_applicable:
        margin_adj = 0.0
        notes.append(
            f"M10 margin_rule={margin_rule or 'N/A'} / margin_quality={margin_quality or 'N/A'}，"
            "不適用製造業毛利率 / 營益率模型，品質係數只採 ROE 與財務風險"
        )
    elif not margin_can_affect:
        raw_margin_adj = margin_adj
        margin_adj = min(0.0, margin_adj)
        notes.extend(margin_notes)
        if raw_margin_adj > 0:
            notes.append(
                f"M10 margin_status={margin_status or 'tracking_only'} / margin_quality={margin_quality or 'N/A'}，"
                "正向 margin 加分歸零，只保留風險折扣"
            )
    else:
        notes.extend(margin_notes)

    adjustment += margin_adj + roe_adj
    notes.append(roe_note)

    factor = 1.0 + adjustment

    # 營益率輔助判斷；M10 標示不適用 margin 模型者不可再用營益率防呆扣分。
    if margin_model_applicable:
        before_op = factor
        factor = _operating_margin_guard(opm, gm, factor, notes)
        if opm is not None and before_op == factor:
            notes.append(f"營益率 {_fmt_pct(opm)} 已納入品質係數，未觸發額外折扣")
    else:
        notes.append("M10 margin 不適用，跳過營益率防呆")

    # 營收、負債、FCF、防呆。
    rev = _pct01(revenue_yoy)
    if rev is not None and rev < 0 and factor > 1.0:
        factor = 1 + (factor - 1) * 0.5
        notes.append("營收 YoY 為負，品質溢價減半")
    if de is not None:
        if de > 4 and factor > 1.0:
            factor = 1.0
            notes.append(f"D/E {de:.2f} 過高，品質溢價歸零")
        elif de > 2 and factor > 1.0:
            factor = 1 + (factor - 1) * 0.5
            notes.append(f"D/E {de:.2f} 偏高，品質溢價減半")
    if fcf is not None and fcf < 0 and factor > 1.08:
        factor = min(factor, 1.08)
        notes.append("FCF 為負，品質係數上限 ×1.08")
    if warning_count > 0 and factor > 1.10:
        factor = min(factor, 1.10)
        notes.append("資料分歧存在，品質係數上限 ×1.10")

    # 套上下限；max_quality_factor 只是硬上限，不是一般加分。
    if factor > max_q:
        factor = max_q
        notes.append(f"套用產業品質係數硬上限 ×{max_q:.2f}")
    if factor < min_q:
        factor = min_q
        notes.append(f"套用產業品質係數下限 ×{min_q:.2f}")

    return {"factor": round(factor, 4), "reason": "；".join(notes) or "品質資料中性，係數 ×1.00"}


def theme_order_factor(themes: List[str], industry_profile: Dict[str, Any], eps_positive: bool = True, data_warning_count: int = 0, calibration: Dict[str, Any] = None) -> Dict[str, Any]:
    calibration = calibration or {}
    if not industry_profile.get("theme_premium_allowed", False):
        return {"factor": 1.00, "reason": "此產業模型不建議額外給題材高倍率"}
    text = " ".join(str(x) for x in (themes or [])).lower()
    if not text.strip():
        return {"factor": 1.00, "reason": "未偵測到題材標籤，題材係數 ×1.00"}

    baked = [str(x).lower() for x in (calibration.get("baked_in_themes") or [])]
    baked_hits = [k for k in baked if k and k in text]

    rules = [
        (1.18, ["ai asic", "asic", "cpo", "矽光子"]),
        (1.15, ["hpc", "cowos", "ai載板", "abf", "水冷", "液冷", "資料中心"]),
        (1.10, ["ai", "低軌", "衛星", "電網", "重電", "儲能"]),
        (1.06, ["車用", "高速傳輸", "機器人", "自動化"]),
    ]
    factor = 1.00
    hit = []
    for score, keys in rules:
        matched = [k for k in keys if k.lower() in text]
        if matched:
            factor = max(factor, score)
            hit.extend(matched)

    if factor <= 1.00:
        return {"factor": 1.00, "reason": "題材標籤未命中可量化溢價，僅列為備註"}

    reason = f"題材標籤命中：{'、'.join(sorted(set(hit)))}"
    if baked_hits:
        factor = min(factor, 1.05)
        reason += f"；{'、'.join(sorted(set(baked_hits)))} 已包含在產業基準中，避免重複加分，題材係數上限 ×1.05"
    if not eps_positive:
        factor = 1 + (factor - 1) * 0.5
        reason += "；EPS 未落地，題材係數減半"
    if data_warning_count >= 2:
        factor = 1 + (factor - 1) * 0.5
        reason += "；資料分歧較多，題材係數減半"
    max_f = _sf(calibration.get("max_theme_factor"), 1.10) or 1.10
    if factor > max_f:
        factor = max_f
        reason += f"；套用產業題材係數上限 ×{max_f:.2f}"
    return {"factor": round(factor, 4), "reason": reason}


def scale_growth_flex_factor(market_cap: Any, eps_positive: bool = True, liquidity_ok: bool = True, calibration: Dict[str, Any] = None) -> Dict[str, Any]:
    calibration = calibration or {}
    mc = _sf(market_cap)
    max_scale = _sf(calibration.get("max_scale_factor"), 1.05) or 1.05
    if mc is None or mc <= 0:
        return {"factor": 1.00, "reason": "市值缺值，不做規模與成長彈性修正"}
    billion = mc / 100_000_000  # 億元
    if billion >= 50_000:
        f, msg = 0.94, "超大型權值股，成長彈性與本益比擴張受限制"
    elif billion >= 10_000:
        f, msg = 0.97, "大型龍頭，穩定性高但夢想倍率有限"
    elif billion >= 3_000:
        f, msg = 1.00, "大型成長股，規模修正中性"
    elif billion >= 500:
        f, msg = 1.04, "中型成長股，成長彈性較佳"
    elif billion >= 100 and eps_positive and liquidity_ok:
        f, msg = 1.06, "小型高成長且流動性尚可，給小幅彈性溢價"
    else:
        f, msg = 0.92, "市值小、EPS 或流動性條件不足，套用規模風險折扣"
    if f > max_scale:
        f = max_scale
        msg += f"；套用產業規模係數上限 ×{max_scale:.2f}"
    return {"factor": round(f, 4), "reason": f"市值約 {billion:,.0f} 億；{msg}"}


def geopolitical_factor(industry_profile: Dict[str, Any], calibration: Dict[str, Any]) -> Dict[str, Any]:
    f = _sf(calibration.get("geopolitical_factor"), 1.00) or 1.00
    if f >= 0.999:
        return {"factor": 1.00, "reason": "未套用特別地緣政治折價"}
    note = calibration.get("geopolitical_note") or "台灣供應鏈地緣政治與出口管制 / 客戶集中風險折價"
    return {"factor": round(f, 4), "reason": note}


def data_confidence_factor(warnings: List[Dict[str, Any]] = None, dq_warnings: List[str] = None) -> Dict[str, Any]:
    warnings = warnings or []
    dq_warnings = dq_warnings or []
    danger = sum(1 for w in warnings if str(w.get("嚴重度", "")).lower() == "danger")
    count = len(warnings) + len(dq_warnings)
    # 17-B-4：一項重大分歧不再直接打到 ×0.80，避免從過度樂觀修成過度保守。
    if danger >= 2 or count >= 5:
        f, label = 0.70, "低 / 資料異常"
    elif count >= 3:
        f, label = 0.82, "偏低"
    elif danger >= 1:
        f, label = 0.90, "中 / 重大分歧"
    elif count == 2:
        f, label = 0.90, "中"
    elif count == 1:
        f, label = 0.95, "中高"
    else:
        f, label = 1.00, "高"
    return {"factor": f, "label": label, "reason": f"分歧警告 {len(warnings)} 項、資料校驗提醒 {len(dq_warnings)} 項"}


def detect_cycle_recovery_state(
    industry_profile: Dict[str, Any],
    calibration: Dict[str, Any],
    growth_pack: Dict[str, Any],
    gross_margin: Any = None,
    roe: Any = None,
    revenue_yoy: Any = None,
) -> Dict[str, Any]:
    """判斷是否屬於循環復甦 / 訂單週期復甦。避免低基期股被成長與品質雙重誤判。"""
    p = industry_profile or {}
    key = str(p.get("model_key") or p.get("taxon_key") or "")
    recovery_keys = {
        "ABF_SUBSTRATE", "SERVER_PCB_BOARD", "OSAT_TESTING", "PROBE_TEST_INTERFACE",
        "SEMICAP_COWOS_EQUIPMENT", "FAB_FACILITY_MATERIALS", "THERMAL_LIQUID_COOLING",
        "EV_AUTO_ELECTRONICS", "ROBOTICS_AUTOMATION",
    }
    sensitive = p.get("recovery_sensitive") or calibration.get("recovery_sensitive") or bool(p.get("cyclical")) or key in recovery_keys
    if not sensitive:
        return {"state": "normal_growth", "label": "一般成長", "quality_floor": None, "growth_cap": None, "reason": "非循環復甦敏感產業"}

    growth = growth_pack.get("growth") if isinstance(growth_pack, dict) else None
    gm = _pct01(gross_margin)
    roev = _pct01(roe)
    rev = _pct01(revenue_yoy)
    gm_base = _sf(calibration.get("gross_margin_baseline"))

    weak_quality = False
    weak_notes = []
    if gm is not None and gm_base is not None and gm < gm_base:
        weak_quality = True
        weak_notes.append(f"毛利率 {_fmt_pct(gm)} 低於產業基準 {_fmt_pct(gm_base)}")
    if roev is not None and roev < 0.10:
        weak_quality = True
        weak_notes.append(f"ROE {_fmt_pct(roev)} 尚未恢復")

    rev_ok = rev is None or rev >= -0.05
    if growth is not None and growth >= 0.50 and weak_quality and rev_ok:
        return {
            "state": "cycle_recovery",
            "label": "循環復甦",
            "quality_floor": 0.93,
            "growth_cap": 1.15,
            "reason": "Forward EPS / 營收顯示復甦，但當期品質指標尚未完全恢復；" + "、".join(weak_notes),
        }
    if growth is not None and growth >= 1.00 and bool(p.get("cyclical")):
        return {
            "state": "low_base_recovery",
            "label": "低基期修復",
            "quality_floor": 0.92,
            "growth_cap": 1.12,
            "reason": "循環產業 Forward EPS 高成長，疑似低基期修復，成長係數與品質扣分同時保守化。",
        }
    if bool(p.get("cyclical")):
        return {"state": "cyclical_normal", "label": "循環一般", "quality_floor": None, "growth_cap": 1.12, "reason": "循環產業，避免把單期 EPS 當長期結構性成長。"}
    return {"state": "normal_growth", "label": "一般成長", "quality_floor": None, "growth_cap": None, "reason": "未偵測到明確復甦狀態"}

def valuation_risk_factor(current_price: Any = None, operable_low: Any = None, operable_high: Any = None) -> Dict[str, Any]:
    cp = _sf(current_price)
    lo = _sf(operable_low)
    hi = _sf(operable_high)
    if cp is None or lo is None or hi is None or hi <= 0:
        return {"factor": 0.95, "label": "保守預設", "reason": "可操作區間尚未建立，先套用保守估值折扣 ×0.95"}
    if cp <= lo:
        return {"factor": 1.00, "label": "低於區間", "reason": "現價低於或接近可操作區間下緣"}
    if cp <= hi:
        return {"factor": 0.95, "label": "區間內", "reason": "現價位於可操作區間內"}
    over = (cp / hi) - 1
    if over <= 0.10:
        f = 0.90
    elif over <= 0.30:
        f = 0.80
    else:
        f = 0.70
    return {"factor": f, "label": "高於區間", "reason": f"現價高於可操作區間上緣 {over*100:.1f}%"}


def liquidity_factor(hist_data: Any = None, info: Dict[str, Any] = None) -> Dict[str, Any]:
    avg_shares = None
    try:
        if hist_data is not None and hasattr(hist_data, "empty") and not hist_data.empty and "Volume" in hist_data.columns:
            avg_shares = float(hist_data["Volume"].tail(20).mean())
    except Exception:
        avg_shares = None
    if avg_shares is None and isinstance(info, dict):
        avg_shares = _sf(info.get("averageVolume") or info.get("averageVolume10days") or info.get("averageDailyVolume10Day"))
    if avg_shares is None or avg_shares <= 0:
        return {"factor": 1.00, "label": "未套用", "avg_lots": None, "reason": "近 20 日均量缺值，暫不套流動性折扣"}
    lots = avg_shares / 1000.0
    if lots >= 5000:
        f, label = 1.00, "佳"
    elif lots >= 2000:
        f, label = 0.95, "正常"
    elif lots >= 1000:
        f, label = 0.90, "稍低"
    elif lots >= 500:
        f, label = 0.85, "偏低"
    else:
        f, label = 0.78, "低"
    return {"factor": f, "label": label, "avg_lots": lots, "reason": f"近 20 日均量約 {lots:,.0f} 張"}


def pe_floor_ceiling(industry_profile: Dict[str, Any], calibration: Dict[str, Any]) -> Dict[str, Any]:
    floor = _sf(calibration.get("floor_pe"), 12.0) or 12.0
    soft = _sf(calibration.get("soft_ceiling_pe"), None)
    hard = _sf(calibration.get("hard_ceiling_pe"), None)
    if soft is None or hard is None:
        rng = industry_profile.get("pe_range")
        if isinstance(rng, (tuple, list)) and len(rng) == 2 and _sf(rng[0]) and _sf(rng[1]):
            floor = float(rng[0])
            soft = float(rng[1]) * 0.90
            hard = float(rng[1])
        else:
            soft, hard = 35.0, 45.0
    return {"floor": float(floor), "soft_ceiling": float(soft), "hard_ceiling": float(hard), "ceiling": float(hard)}


def market_condition_hard_overlay(
    floor_ceiling: Dict[str, Any],
    *,
    current_price: Any = None,
    adopted_forward_eps: Any = None,
    growth_pack: Dict[str, Any] = None,
    revenue_yoy: Any = None,
    industry_profile: Dict[str, Any] = None,
    data_confidence_pack: Dict[str, Any] = None,
    liquidity_pack: Dict[str, Any] = None,
    warning_count: int = 0,
) -> Dict[str, Any]:
    """17-C-21：依市場狀況調整 hard ceiling，但不直接推高 base/soft。"""
    fc = dict(floor_ceiling or {})
    hard = _sf(fc.get("hard_ceiling"))
    soft = _sf(fc.get("soft_ceiling"))
    cp = _sf(current_price)
    eps = _sf(adopted_forward_eps)
    p = industry_profile or {}
    growth_pack = growth_pack or {}
    dc = data_confidence_pack or {}
    liq = liquidity_pack or {}
    fc["structural_hard_ceiling"] = hard
    fc["market_condition_adjusted"] = False
    fc["market_condition_hard_factor"] = 1.0
    fc["market_condition_reason"] = "市場 hard overlay 未啟用"
    fc["market_implied_forward_pe_for_hard"] = None

    if hard is None or soft is None:
        fc["market_condition_reason"] = "hard / soft ceiling 缺值，無法做市場 overlay"
        return fc
    if p.get("disable_market_hard_overlay"):
        fc["market_condition_reason"] = "本股設定關閉市場 hard overlay，避免因股價先漲而反向調高 hard ceiling"
        return fc
    if cp is None or cp <= 0 or eps is None or eps <= 0:
        fc["market_condition_reason"] = "現價或 Forward EPS 缺值，維持產業結構 hard"
        return fc

    implied = cp / eps
    fc["market_implied_forward_pe_for_hard"] = implied
    if implied <= hard:
        fc["market_condition_reason"] = f"現價隱含 Forward P/E {implied:.1f}x 未高於產業結構 hard {hard:.1f}x"
        return fc

    data_factor = float(dc.get("factor", 1.0) or 1.0)
    liquidity_factor_value = float(liq.get("factor", 1.0) or 1.0)
    if data_factor < 0.90 or warning_count >= 3:
        fc["market_condition_reason"] = f"現價隱含 {implied:.1f}x 高於結構 hard，但資料分歧/可信度不足，維持 {hard:.1f}x"
        return fc
    if liquidity_factor_value < 0.85:
        fc["market_condition_reason"] = f"現價隱含 {implied:.1f}x 高於結構 hard，但流動性偏低，維持 {hard:.1f}x"
        return fc

    growth = growth_pack.get("growth") if isinstance(growth_pack, dict) else None
    growth = _pct01(growth)
    if growth is None:
        growth = _pct01(revenue_yoy)
    theme_or_momentum = bool(p.get("market_momentum_zone_if_above_hard") or p.get("theme_premium_allowed"))

    if growth is not None and growth >= 0.60 and theme_or_momentum:
        expansion_limit = 1.30
        regime = "強成長 + 市場動能"
    elif growth is not None and growth >= 0.35 and theme_or_momentum:
        expansion_limit = 1.22
        regime = "中高成長 + 市場動能"
    elif growth is not None and growth >= 0.20:
        expansion_limit = 1.12
        regime = "成長支撐"
    elif theme_or_momentum:
        expansion_limit = 1.08
        regime = "市場動能但基本面成長證據不足"
    else:
        fc["market_condition_reason"] = f"現價隱含 {implied:.1f}x 高於結構 hard，但缺少成長或市場動能條件，維持 {hard:.1f}x"
        return fc

    adjusted_hard = min(implied * 1.03, hard * expansion_limit)
    adjusted_hard = max(hard, adjusted_hard)
    if adjusted_hard <= hard + 1e-9:
        fc["market_condition_reason"] = f"市場 overlay 後仍未高於結構 hard {hard:.1f}x"
        return fc

    fc["hard_ceiling"] = round(adjusted_hard, 1)
    fc["ceiling"] = round(adjusted_hard, 1)
    fc["market_condition_adjusted"] = True
    fc["market_condition_hard_factor"] = round(fc["hard_ceiling"] / hard, 4)
    growth_text = "成長缺值" if growth is None else f"成長 {_fmt_pct(growth)}"
    fc["market_condition_reason"] = (
        f"{regime}：現價隱含 Forward P/E {implied:.1f}x 高於產業結構 hard {hard:.1f}x；"
        f"{growth_text}、資料可信度 {data_factor:.2f}、流動性係數 {liquidity_factor_value:.2f}，"
        f"市場調整 hard 至 {fc['hard_ceiling']:.1f}x"
    )
    return fc


def build_pb_cycle_pack(current_price: Any, pb_ratio: Any, industry_profile: Dict[str, Any]) -> Dict[str, Any]:
    pb = _sf(pb_ratio)
    cp = _sf(current_price)
    pb_range = industry_profile.get("pb_range")
    rows = []
    if not (isinstance(pb_range, (tuple, list)) and len(pb_range) == 2):
        pb_range = (None, None)
    low_pb, high_pb = _sf(pb_range[0]), _sf(pb_range[1])
    bvps = cp / pb if cp is not None and pb and pb > 0 else None
    low_val = bvps * low_pb if bvps and low_pb else None
    high_val = bvps * high_pb if bvps and high_pb else None
    rows.append({"類型": "P/B 週期模型", "項目": "目前 P/B", "倍率/係數": _fmt_x(pb), "說明": "週期股優先看 P/B 與報價/運價/庫存週期"})
    rows.append({"類型": "P/B 週期模型", "項目": "參考 P/B 區間", "倍率/係數": f"{_fmt_x(low_pb)}～{_fmt_x(high_pb)}", "說明": industry_profile.get("warning_note", "低 P/E 不一定代表低估")})
    rows.append({"類型": "P/B 週期模型", "項目": "BVPS 推估", "倍率/係數": "NULL" if bvps is None else f"{bvps:.2f}", "說明": "以現價 ÷ P/B 反推；後續可改接 Yahoo BVPS"})
    warnings = ["本產業優先使用 P/B 週期模型，P/E 僅作輔助"]
    high_warn = _sf(industry_profile.get("pb_high_warning_threshold"))
    low_warn = _sf(industry_profile.get("pb_low_warning_threshold"))
    if pb is not None and high_warn is not None and pb > high_warn:
        warnings.append(f"目前 P/B {pb:.2f}x 高於週期警戒 {high_warn:.1f}x，需避免用低 P/E 誤判便宜")
        rows.append({"類型": "P/B 週期模型", "項目": "P/B 高檔警示", "倍率/係數": f"{pb:.2f}x", "說明": f"高於週期警戒 {high_warn:.1f}x；需確認報價/庫存/稼動率是否仍在上行段。"})
    if pb is not None and low_warn is not None and pb < low_warn:
        warnings.append(f"目前 P/B {pb:.2f}x 低於週期低檔 {low_warn:.1f}x，需查獲利與資產減損風險")
        rows.append({"類型": "P/B 週期模型", "項目": "P/B 低檔觀察", "倍率/係數": f"{pb:.2f}x", "說明": f"低於週期低檔 {low_warn:.1f}x；可能是低估，也可能反映獲利/資產疑慮。"})
    return {
        "available": False,
        "valuation_mode": "pb_cycle",
        "final_cap": None,
        "raw_cap": None,
        "pb_ratio": pb,
        "bvps": bvps,
        "pb_low_price": low_val,
        "pb_high_price": high_val,
        "warnings": warnings,
        "report": pd.DataFrame(rows),
    }


def build_event_theme_pack(industry_profile: Dict[str, Any]) -> Dict[str, Any]:
    rows = [
        {"類型": "題材 / 事件模型", "項目": "P/E Cap", "倍率/係數": "不輸出", "說明": "本分類 EPS 或訂單落地程度不足，不適合一般 P/E 買進倍率。"},
        {"類型": "題材 / 事件模型", "項目": "主要觀察", "倍率/係數": "—", "說明": "事件催化、訂單真實性、籌碼、成交量與財報落地程度。"},
        {"類型": "題材 / 事件模型", "項目": "風險提醒", "倍率/係數": "高", "說明": industry_profile.get("warning_note", industry_profile.get("note", "題材股不輸出公式買進倍率。"))},
    ]
    return {
        "available": False,
        "valuation_mode": "event_chip",
        "final_cap": None,
        "raw_cap": None,
        "warnings": ["題材 / 事件驅動股不輸出 P/E 買進倍率"],
        "report": pd.DataFrame(rows),
    }



def build_turnaround_event_pack(industry_profile: Dict[str, Any], reason: str = "") -> Dict[str, Any]:
    """17-C-4：EPS 尚未穩定轉正時停用 P/E 估值，改用轉機 / 事件模型。"""
    rows = [
        {"類型": "轉機 / 事件模型", "項目": "P/E 公式估值", "倍率/係數": "停用", "說明": "Forward EPS、TTM EPS 或年度 EPS 尚未穩定轉正，不適合使用 P/E 公式合理價。"},
        {"類型": "轉機 / 事件模型", "項目": "主要觀察", "倍率/係數": "—", "說明": "連續單季 EPS 轉正、營益率改善、月營收連續成長、訂單落地、法人開始提供明確 Forward EPS。"},
        {"類型": "轉機 / 事件模型", "項目": "替代估值", "倍率/係數": "P/B / 事件", "說明": "可輔助觀察 P/B、淨值、現金流與籌碼；不可輸出負的公式合理價或負的極限價。"},
    ]
    warnings = ["Forward EPS / TTM EPS 未穩定轉正，已停用 P/E Dynamic Cap 買進估值", "此類標的應改用轉機事件模型，不輸出公式合理價 / 公式極限價"]
    if reason:
        warnings.append(reason)
    return {
        "available": False,
        "valuation_mode": "turnaround_event",
        "final_cap": None,
        "raw_cap": None,
        "formula_cap": None,
        "optimistic_cap": None,
        "hard_cap": None,
        "operable_cap_low": None,
        "operable_cap_high": None,
        "warnings": warnings,
        "industry_profile": industry_profile,
        "report": pd.DataFrame(rows),
        "explanation": "17-C-4：負 EPS / 轉機股防呆；停用 P/E 估值，避免出現負目標價。",
    }


def _v18_2_neutral_factor(reason: str) -> Dict[str, Any]:
    return {"factor": 1.0, "label": "v18.2 已校準", "reason": reason}


def build_v18_2_unavailable_pack(
    industry_profile: Dict[str, Any],
    stock_id: str,
    stock_name: str,
    cap_row: Dict[str, Any],
    m10_margin_benchmark: Dict[str, Any],
) -> Dict[str, Any]:
    """Return an explicit no-cap result; v18.2 coverage never falls back to an older engine."""
    cap_row = dict(cap_row or {})
    status = str(cap_row.get("status") or "v18.2 倍率未建立")
    engine = str(cap_row.get("engine") or "v18.2 資料不足")
    eps_basis = str(cap_row.get("eps_basis") or "insufficient")
    explanation = f"{engine}｜{status}；依 v18.2 規則不回退 v18.1 或產業預設倍率。"
    rows = [
        {"類型": "v18.2 狀態", "項目": "倍率引擎", "倍率/係數": engine, "說明": status},
        {"類型": "v18.2 狀態", "項目": "EPS 適用口徑", "倍率/係數": eps_basis, "說明": "倍率不適用或尚未建立，不輸出 P/E 公式價。"},
        {"類型": "風控", "項目": "舊版回退", "倍率/係數": "禁止", "說明": "v18.2 是唯一正式倍率來源；不使用 v18.1、taxonomy 或默認 30x 補值。"},
    ]
    return {
        "available": False,
        "valuation_mode": "pe_not_applicable" if eps_basis == "not_applicable" else "insufficient_data",
        "model_version": DYNAMIC_CAP_MODEL_ENGINE_VERSION,
        "stock_id": stock_id,
        "stock_name": stock_name,
        "v18_2_caps_available": False,
        "v18_2_engine": engine,
        "v18_2_status": status,
        "v18_2_confidence": cap_row.get("confidence"),
        "v18_2_special_case_review": bool(cap_row.get("special_case_review")),
        "cap_eps_basis": eps_basis,
        "base_multiple": None,
        "raw_cap": None,
        "formula_cap": None,
        "final_cap": None,
        "optimistic_cap": None,
        "hard_cap": None,
        "floor_cap": None,
        "soft_ceiling_cap": None,
        "ceiling_cap": None,
        "hard_ceiling_cap": None,
        "structural_hard_cap": None,
        "structural_hard_ceiling_cap": None,
        "operable_cap_low": None,
        "operable_cap_high": None,
        "market_condition_hard_adjustment": {
            "adjusted": False,
            "factor": 1.0,
            "reason": "v18.2 禁止市場熱度上修；本股也無可用倍率。",
            "market_implied_forward_pe": None,
        },
        "market_implied_forward_pe": None,
        "market_implied_status": explanation,
        "warnings": [explanation],
        "industry_profile": industry_profile,
        "m10_margin_benchmark": m10_margin_benchmark,
        "report": pd.DataFrame(rows),
        "explanation": explanation,
    }


def build_v18_2_locked_cap_pack(
    *,
    industry_profile: Dict[str, Any],
    stock_id: str,
    stock_name: str,
    cap_row: Dict[str, Any],
    m10_margin_benchmark: Dict[str, Any],
    current_price: Any = None,
    ttm_eps: Any = None,
    system_forward_eps: Any = None,
    ai_forward_eps: Any = None,
    consensus_forward_eps: Any = None,
) -> Dict[str, Any]:
    """Build an exact v18.2 stock-level cap pack without applying dynamic premiums again."""
    floor = _sf(cap_row.get("floor"))
    industry_base = _sf(cap_row.get("industry_base"))
    base = _sf(cap_row.get("company_base"))
    soft = _sf(cap_row.get("company_soft"))
    hard = _sf(cap_row.get("company_hard"))
    if any(value is None for value in (floor, base, soft, hard)):
        return build_v18_2_unavailable_pack(industry_profile, stock_id, stock_name, cap_row, m10_margin_benchmark)

    eps_basis = str(cap_row.get("eps_basis") or "fy1_forward")
    if eps_basis == "ttm_only":
        adopted_eps = _sf(ttm_eps)
        eps_label = "TTM EPS"
    else:
        adopted_eps = _sf(consensus_forward_eps) or _sf(system_forward_eps) or _sf(ai_forward_eps)
        eps_label = "FY1 Forward EPS"
    current = _sf(current_price)
    implied_pe = current / adopted_eps if current and current > 0 and adopted_eps and adopted_eps > 0 else None

    if implied_pe is None:
        implied_status = f"未取得可用 {eps_label}，僅顯示 v18.2 倍率，不產生公式價。"
    elif implied_pe > hard:
        implied_status = f"現價隱含 {eps_label} P/E {implied_pe:.2f}x 高於 Company Hard {hard:.2f}x；僅列為市場過熱，不上修倍率。"
    elif implied_pe > soft:
        implied_status = f"現價隱含 {eps_label} P/E {implied_pe:.2f}x 介於 Company Soft 與 Hard。"
    elif implied_pe > base:
        implied_status = f"現價隱含 {eps_label} P/E {implied_pe:.2f}x 高於 Company Base，但未超過 Soft。"
    else:
        implied_status = f"現價隱含 {eps_label} P/E {implied_pe:.2f}x 未高於 Company Base。"

    warnings: List[str] = []
    if eps_basis == "ttm_only":
        warnings.append("v18.2 本股倍率僅能搭配 TTM EPS；不得乘以 FY1/FY2/FY3 EPS。")
    else:
        warnings.append("v18.2 為暫行 FY1 前瞻估值帶；倍率必須搭配同年度 FY1 EPS。")
    if cap_row.get("special_case_review"):
        warnings.append("本股為估值特例待覆核，應搭配法人預估與財報交叉驗證。")
    if implied_pe is not None and implied_pe > hard:
        warnings.append("現價隱含 P/E 高於 v18.2 Company Hard；市場熱度不會推高正式倍率。")
    if adopted_eps is None or adopted_eps <= 0:
        warnings.append(f"缺少可用 {eps_label}，v18.2 倍率目前不輸出目標價。")

    rows = [
        {"類型": "v18.2 基準", "項目": "產業 Base", "倍率/係數": _fmt_x(industry_base, 2), "說明": cap_row.get("fine_industry") or "v18.2 細產業錨點"},
        {"類型": "v18.2 逐股", "項目": "Company Base", "倍率/係數": _fmt_x(base, 2), "說明": "個股品質／確認成長校準後的正式基準倍率。"},
        {"類型": "v18.2 逐股", "項目": "Company Soft", "倍率/係數": _fmt_x(soft, 2), "說明": "熱度偏高但仍可理解的估值上緣。"},
        {"類型": "v18.2 逐股", "項目": "Company Hard", "倍率/係數": _fmt_x(hard, 2), "說明": "極端上緣，僅作風控，不是買進目標。"},
        {"類型": "v18.2 規則", "項目": "EPS 適用口徑", "倍率/係數": eps_label, "說明": "TTM 參考倍率不得直接乘以 FY1/FY2/FY3。" if eps_basis == "ttm_only" else "與同年度 FY1 EPS 搭配使用。"},
        {"類型": "v18.2 規則", "項目": "市場 hard overlay", "倍率/係數": "關閉", "說明": "市場熱度只判斷現價位置，不永久上修 Base/Soft/Hard。"},
        {"類型": "v18.2 狀態", "項目": "引擎／信心／狀態", "倍率/係數": f"{cap_row.get('engine', '—')} / {cap_row.get('confidence', '—')}", "說明": cap_row.get("status") or "—"},
    ]
    neutral_reason = "v18.2 Company 倍率已納入個股品質與確認成長校準，不重複加成。"
    neutral = _v18_2_neutral_factor(neutral_reason)
    operable_low = max(floor, base * 0.95)
    operable_high = min(soft, base * 1.05)
    if operable_high < operable_low:
        operable_high = operable_low
    return {
        "available": True,
        "valuation_mode": "ttm_pe" if eps_basis == "ttm_only" else "forward_pe",
        "model_version": DYNAMIC_CAP_MODEL_ENGINE_VERSION,
        "stock_id": stock_id,
        "stock_name": stock_name,
        "v18_2_caps_available": True,
        "v18_2_engine": cap_row.get("engine"),
        "v18_2_status": cap_row.get("status"),
        "v18_2_confidence": cap_row.get("confidence"),
        "v18_2_special_case_review": bool(cap_row.get("special_case_review")),
        "cap_eps_basis": eps_basis,
        "base_multiple": base,
        "industry_base_multiple": industry_base,
        "growth_premium": dict(neutral),
        "gross_margin_premium": dict(neutral),
        "roe_quality_premium": dict(neutral),
        "theme_premium": dict(neutral),
        "market_cap_adjustment": dict(neutral),
        "geopolitical_factor": dict(neutral),
        "classification_confidence_factor": dict(neutral),
        "data_confidence_factor": dict(neutral),
        "valuation_risk_factor": dict(neutral),
        "liquidity_factor": dict(neutral),
        "raw_cap": base,
        "pre_clip_cap": base,
        "formula_cap": base,
        "final_cap": base,
        "optimistic_cap": soft,
        "hard_cap": hard,
        "structural_hard_cap": hard,
        "floor_cap": floor,
        "soft_ceiling_cap": soft,
        "ceiling_cap": hard,
        "hard_ceiling_cap": hard,
        "structural_hard_ceiling_cap": hard,
        "operable_cap_low": operable_low,
        "operable_cap_high": operable_high,
        "market_condition_hard_adjustment": {
            "adjusted": False,
            "factor": 1.0,
            "reason": "v18.2 明定市場熱度只判斷價格位置，關閉市場 hard overlay。",
            "market_implied_forward_pe": implied_pe if eps_basis != "ttm_only" else None,
        },
        "adopted_forward_eps_for_implied": adopted_eps if eps_basis != "ttm_only" else None,
        "market_implied_forward_pe": implied_pe,
        "market_implied_eps_basis": eps_label,
        "market_implied_status": implied_status,
        "hit_hard_ceiling": bool(implied_pe is not None and implied_pe > hard),
        "warnings": warnings,
        "industry_profile": industry_profile,
        "m10_margin_benchmark": m10_margin_benchmark,
        "report": pd.DataFrame(rows),
        "explanation": "Dynamic Cap v18.2：正式採用逐股 Company Base / Soft / Hard；不回退舊版，不重複套用成長／品質係數，不以市場熱度上修。",
    }

def calculate_dynamic_cap_v2(
    *,
    stock_id: str = "",
    stock_name: str = "",
    current_price: Any = None,
    info: Dict[str, Any] = None,
    hist_data: Any = None,
    industry_profile: Dict[str, Any] = None,
    gross_margin: Any = None,
    operating_margin: Any = None,
    roe: Any = None,
    debt_to_equity: Any = None,
    revenue_yoy: Any = None,
    free_cash_flow: Any = None,
    ttm_eps: Any = None,
    system_forward_eps: Any = None,
    ai_forward_eps: Any = None,
    consensus_forward_eps: Any = None,
    ai_ttm_eps: Any = None,
    pb_ratio: Any = None,
    divergence_warnings: List[Dict[str, Any]] = None,
    dq_warnings: List[str] = None,
    operable_low: Any = None,
    operable_high: Any = None,
) -> Dict[str, Any]:
    info = info or {}
    p = industry_profile or {}
    c = _calibration(p)
    m10_margin_benchmark = build_m10_margin_benchmark_summary(p, c)

    # v18.2 is a governed stock-level registry. Once coverage is enforced the
    # legacy coefficient engine must never recalculate or backfill its caps.
    if p.get("dynamic_cap_v18_2_coverage_enforced"):
        cap_row = p.get("dynamic_cap_v18_2") if isinstance(p.get("dynamic_cap_v18_2"), dict) else {}
        if not cap_row.get("caps_available"):
            return build_v18_2_unavailable_pack(p, stock_id, stock_name, cap_row, m10_margin_benchmark)
        return build_v18_2_locked_cap_pack(
            industry_profile=p,
            stock_id=stock_id,
            stock_name=stock_name,
            cap_row=cap_row,
            m10_margin_benchmark=m10_margin_benchmark,
            current_price=current_price,
            ttm_eps=ttm_eps,
            system_forward_eps=system_forward_eps,
            ai_forward_eps=ai_forward_eps,
            consensus_forward_eps=consensus_forward_eps,
        )

    warnings: List[str] = []
    themes = list(p.get("themes") or [])
    primary_valuation = str(p.get("primary_valuation") or "forward_pe")
    pe_app = p.get("pe_applicable", True)
    positive_forward_eps = any((_sf(x) or 0) > 0 for x in [consensus_forward_eps, system_forward_eps, ai_forward_eps])
    positive_profit_eps = any((_sf(x) or 0) > 0 for x in [consensus_forward_eps, system_forward_eps, ai_forward_eps, ttm_eps, ai_ttm_eps])
    eps_positive = positive_profit_eps
    warn_count = len(divergence_warnings or []) + len(dq_warnings or [])

    # 17-C-4：只要主要模型是 P/E / Forward P/E，但 Forward EPS 與 TTM EPS 尚未穩定轉正，
    # 不應再輸出 P/E 公式估值，避免出現負合理價、負極限價。
    adopted_forward_eps = _sf(consensus_forward_eps) or _sf(system_forward_eps) or _sf(ai_forward_eps)
    adopted_ttm_eps = _sf(ttm_eps) if _sf(ttm_eps) is not None else _sf(ai_ttm_eps)
    # 17-C-4：負 EPS / 無 Forward EPS 防呆。
    # 若 TTM 與 Forward 都尚未穩定轉正，全面停用 P/E 估值；若 TTM 為負但有明確正 Forward EPS，可保留 Forward P/E 但列高風險。
    if primary_valuation in {"forward_pe", "pe_pb_crosscheck", "forward_pe_pb_cycle"} and ((adopted_forward_eps is None or adopted_forward_eps <= 0) and (adopted_ttm_eps is None or adopted_ttm_eps <= 0)):
        pack = build_turnaround_event_pack(p, "EPS 尚未穩定轉正，Dynamic Cap 停用 P/E 估值，改用轉機 / 事件模型。")
        pack.update({
            "stock_id": stock_id,
            "stock_name": stock_name,
            "model_version": DYNAMIC_CAP_MODEL_ENGINE_VERSION,
            "m10_margin_benchmark": m10_margin_benchmark,
        })
        return pack

    # 17-B-4：低軌衛星、機器人、生技等條件式 P/E 模型，若 EPS / 訂單未落地，直接切換事件模型。
    if p.get("event_model_if_eps_unstable") and not positive_forward_eps:
        pack = build_event_theme_pack(p)
        note = p.get("event_switch_note") or "EPS / 訂單未落地，依 17-B-4 校準規則改用事件模型。"
        pack["warnings"] = list(pack.get("warnings") or []) + [note]
        pack.update({
            "stock_id": stock_id,
            "stock_name": stock_name,
            "industry_profile": p,
            "model_version": DYNAMIC_CAP_MODEL_ENGINE_VERSION,
            "m10_margin_benchmark": m10_margin_benchmark,
        })
        return pack

    if pe_app is False or primary_valuation in {"event_chip", "theme_event"}:
        pack = build_event_theme_pack(p)
        pack.update({
            "stock_id": stock_id,
            "stock_name": stock_name,
            "industry_profile": p,
            "model_version": DYNAMIC_CAP_MODEL_ENGINE_VERSION,
            "m10_margin_benchmark": m10_margin_benchmark,
        })
        return pack
    if primary_valuation.startswith("pb") or primary_valuation in {"pb", "pb_roe"}:
        pack = build_pb_cycle_pack(current_price, pb_ratio, p)
        pack.update({
            "stock_id": stock_id,
            "stock_name": stock_name,
            "industry_profile": p,
            "model_version": DYNAMIC_CAP_MODEL_ENGINE_VERSION,
            "m10_margin_benchmark": m10_margin_benchmark,
        })
        return pack

    base = _sf(c.get("base_pe"), 20.0) or 20.0
    rows: List[Dict[str, Any]] = []
    _add_row(rows, "基準", "產業基準倍率", f"{base:.1f}x", f"{p.get('model_label', p.get('display_name', '一般產業'))} 17-C-9 校準後 base_pe；非買進追價倍率")
    if m10_margin_benchmark.get("available"):
        gross_text = f"毛利率 base/low/high {_fmt_pct(m10_margin_benchmark.get('base_gross_margin_pct'))}/{_fmt_pct(m10_margin_benchmark.get('gross_margin_low_pct'))}/{_fmt_pct(m10_margin_benchmark.get('gross_margin_high_pct'))}"
        op_text = f"營益率 base/low/high {_fmt_pct(m10_margin_benchmark.get('base_operating_margin_pct'))}/{_fmt_pct(m10_margin_benchmark.get('operating_margin_low_pct'))}/{_fmt_pct(m10_margin_benchmark.get('operating_margin_high_pct'))}"
        _add_row(
            rows,
            "品質基準",
            "M10 margin benchmark",
            f"{m10_margin_benchmark.get('status_label')}｜品質 {m10_margin_benchmark.get('margin_quality')}",
            f"{m10_margin_benchmark.get('category_name') or '未標示分類'}；規則 {m10_margin_benchmark.get('margin_rule_label')}；{gross_text}；{op_text}；{m10_margin_benchmark.get('usage_label')}",
        )
    else:
        _add_row(
            rows,
            "品質基準",
            "M10 margin benchmark",
            "未建立",
            "本股尚未匯入 M10 margin benchmark；Dynamic Cap 沿用既有產業品質係數設定。",
        )
    hybrid_summary = c.get("hybrid_summary") or {}
    if hybrid_summary.get("enabled"):
        _add_row(rows, "基準", "混合產業權重", f"base {hybrid_summary.get('mixed_base_pe'):.1f}x / soft {hybrid_summary.get('mixed_soft_ceiling_pe'):.1f}x / hard {hybrid_summary.get('mixed_hard_ceiling_pe'):.1f}x", hybrid_summary.get("reason", ""))
    elif p.get("hybrid_taxons"):
        _add_row(rows, "基準", "混合產業權重", "未啟用", hybrid_summary.get("reason", "混合分類未通過防呆"))

    liq = liquidity_factor(hist_data, info)
    g = growth_factor_hierarchical(
        system_forward_eps=system_forward_eps,
        ai_forward_eps=ai_forward_eps,
        consensus_forward_eps=consensus_forward_eps,
        ttm_eps=ttm_eps,
        ai_ttm_eps=ai_ttm_eps,
        revenue_yoy=revenue_yoy,
        industry_profile=p,
        calibration=c,
        roe=roe,
        gross_margin=gross_margin,
    )
    q = quality_factor_relative(
        gross_margin,
        roe=roe,
        revenue_yoy=revenue_yoy,
        eps_positive=eps_positive,
        debt_to_equity=debt_to_equity,
        warning_count=warn_count,
        calibration=c,
        operating_margin=operating_margin,
        free_cash_flow=free_cash_flow,
    )
    # 17-B-4：循環復甦股通用判斷，避免「未來 EPS 加分」與「當期低 ROE/毛利重扣」雙殺。
    recovery = detect_cycle_recovery_state(p, c, g, gross_margin=gross_margin, roe=roe, revenue_yoy=revenue_yoy)
    if recovery.get("growth_cap") is not None and float(g.get("factor", 1) or 1) > float(recovery.get("growth_cap")):
        g = dict(g)
        g["factor"] = float(recovery.get("growth_cap"))
        g["reason"] = str(g.get("reason", "")) + f"；17-B-4 {recovery.get('label')} 狀態，成長係數上限 ×{float(recovery.get('growth_cap')):.2f}"
    if recovery.get("quality_floor") is not None and float(q.get("factor", 1) or 1) < float(recovery.get("quality_floor")):
        q = dict(q)
        q["factor"] = float(recovery.get("quality_floor"))
        q["reason"] = str(q.get("reason", "")) + f"；17-B-4 {recovery.get('label')} 狀態，避免復甦股被當期低毛利/低ROE雙殺，品質係數下限 ×{float(recovery.get('quality_floor')):.2f}"

    th = theme_order_factor(themes, p, eps_positive=eps_positive, data_warning_count=warn_count, calibration=c)
    sc = scale_growth_flex_factor(info.get("marketCap"), eps_positive=eps_positive, liquidity_ok=(liq.get("factor", 1) >= 0.85), calibration=c)
    geo = geopolitical_factor(p, c)
    cls_factor = float(p.get("classification_confidence_factor", 1.0) or 1.0)
    if cls_factor < 1.0:
        cls_reason = f"產業分類來源：{p.get('classification_source', p.get('mapping_source', '—'))}；可信度 {p.get('classification_confidence', 'low')}；待人工確認，Dynamic Cap 先套分類可信度折扣。"
    else:
        cls_reason = f"產業分類來源：{p.get('classification_source', p.get('mapping_source', '—'))}；不套分類折扣。"
    cls = {"factor": cls_factor, "reason": cls_reason}

    for name, pack in [
        ("成長係數", g),
        ("品質係數（毛利率相對化 + 營益率 + ROE）", q),
        ("題材 / 訂單係數", th),
        ("規模與成長彈性係數", sc),
        ("地緣政治 / 供應鏈風險係數", geo),
        ("產業分類可信度係數", cls),
    ]:
        _add_factor(rows, name, float(pack.get("factor", 1.0) or 1.0), pack.get("reason", ""))

    _add_row(rows, "復甦判斷", "循環 / 訂單復甦狀態", recovery.get("label", "一般成長"), recovery.get("reason", ""))

    raw_cap = base * float(g.get("factor", 1) or 1) * float(q.get("factor", 1) or 1) * float(th.get("factor", 1) or 1) * float(sc.get("factor", 1) or 1) * float(geo.get("factor", 1) or 1) * cls_factor
    fc = pe_floor_ceiling(p, c)
    _add_row(rows, "小計", "原始建議倍率", f"{raw_cap:.1f}x", "產業基準 × 成長係數 × 品質係數 × 題材係數 × 規模係數 × 地緣政治折價 × 分類可信度係數")

    dc = data_confidence_factor(divergence_warnings, dq_warnings)
    vr = valuation_risk_factor(current_price, operable_low, operable_high)
    _add_discount(rows, "資料可信度折扣", dc["factor"], f"{dc['label']}；{dc['reason']}")
    _add_discount(rows, "估值風險折扣", vr["factor"], f"{vr['label']}；{vr['reason']}")
    _add_discount(rows, "流動性折扣", liq["factor"], f"{liq['label']}；{liq['reason']}")

    fc = market_condition_hard_overlay(
        fc,
        current_price=current_price,
        adopted_forward_eps=adopted_forward_eps,
        growth_pack=g,
        revenue_yoy=revenue_yoy,
        industry_profile=p,
        data_confidence_pack=dc,
        liquidity_pack=liq,
        warning_count=warn_count,
    )
    structural_hard = _sf(fc.get("structural_hard_ceiling"), fc.get("hard_ceiling"))
    if fc.get("market_condition_adjusted"):
        warnings.append("市場狀況已上調 hard ceiling；此為市場先行定價 / 極限情境，不等於可操作買點")
        _add_row(
            rows,
            "風控",
            "市場調整 hard ceiling",
            f"{structural_hard:.1f}x → {fc['hard_ceiling']:.1f}x",
            fc.get("market_condition_reason", ""),
        )
    else:
        _add_row(rows, "風控", "市場 hard overlay", "未調整", fc.get("market_condition_reason", ""))

    pre_clip_cap = raw_cap * dc["factor"] * vr["factor"] * liq["factor"]
    final_cap = _clip(pre_clip_cap, fc["floor"], fc["hard_ceiling"])
    hit_floor = final_cap <= fc["floor"] + 1e-9 and pre_clip_cap < fc["floor"]
    hit_hard_ceiling = final_cap >= fc["hard_ceiling"] - 1e-9 and pre_clip_cap > fc["hard_ceiling"]
    if pre_clip_cap > fc["soft_ceiling"]:
        warnings.append("Dynamic Cap 已高於產業 soft ceiling，模型輸入偏樂觀，請保守解讀")
    if hit_hard_ceiling:
        warnings.append("Dynamic Cap 已觸及產業 hard ceiling，已強制截斷；不可直接作為買進乘數")
    if hit_floor:
        warnings.append("Dynamic Cap 低於產業 floor，已套用最低樓地板避免倍率失真")

    hard_ceiling_text = f"hard ceiling {fc['hard_ceiling']:.0f}x"
    if fc.get("market_condition_adjusted"):
        hard_ceiling_text += f"（市場調整；原產業 hard {structural_hard:.0f}x）"

    _add_row(
        rows,
        "結果",
        "最終建議倍率",
        f"{final_cap:.1f}x",
        f"折扣前 {pre_clip_cap:.1f}x；floor {fc['floor']:.0f}x / soft ceiling {fc['soft_ceiling']:.0f}x / {hard_ceiling_text}",
    )

    # 17-C-18：公式合理價需採用資料可信度與估值風險折扣後的 cap；
    # raw cap 只保留在報告中作「折扣前」參考，避免重大分歧時仍輸出樂觀合理價。
    formula_cap = min(final_cap, fc["soft_ceiling"])
    optimistic_cap = fc["soft_ceiling"]
    hard_cap = fc["hard_ceiling"]
    operable_cap_low = max(fc["floor"], final_cap * 0.95)
    if recovery.get("state") in {"cycle_recovery", "low_base_recovery", "cyclical_normal"}:
        operable_cap_high = min(formula_cap, final_cap * 1.18, fc["soft_ceiling"])
    else:
        operable_cap_high = min(formula_cap, final_cap * 1.12, fc["soft_ceiling"])
    if operable_cap_high < operable_cap_low:
        operable_cap_high = operable_cap_low

    if recovery.get("state") in {"cycle_recovery", "low_base_recovery"}:
        warnings.append("循環復甦股：請同時看保守/中性/樂觀倍率區間，不宜只用單點 Cap 判斷。")

    if p.get("pe_trap_warning"):
        warnings.append("本產業存在 P/E 陷阱，低 P/E 不一定代表低估")
    if warn_count >= 3:
        warnings.append("資料分歧或校驗提醒較多，Dynamic Cap 已折扣")
    if liq.get("factor", 1) < 0.9:
        warnings.append("流動性偏低，已套用流動性折扣")

    # 17-C-4：市場隱含倍率。這不是買進倍率，而是用來解釋「現價為何高於系統估值」。
    adopted_forward_eps_for_implied = adopted_forward_eps
    market_implied_forward_pe = None
    market_implied_status = "Forward EPS 缺值或 <= 0，無法反推現價隱含 Forward P/E。"
    cp_for_implied = _sf(current_price)
    if adopted_forward_eps_for_implied is not None and adopted_forward_eps_for_implied > 0 and cp_for_implied is not None and cp_for_implied > 0:
        market_implied_forward_pe = cp_for_implied / adopted_forward_eps_for_implied
        if market_implied_forward_pe > fc["hard_ceiling"]:
            market_implied_status = "現價隱含 Forward P/E 已高於系統 hard ceiling，屬市場重估 / 題材動能區，不可直接當可操作買點。"
            warnings.append("現價隱含 Forward P/E 已高於產業 hard ceiling：列為市場重估 / 題材動能區，不上修買進倍率")
            if p.get("market_momentum_zone_if_above_hard"):
                _add_row(rows, "風控", "市場重估 / 動能區", f"{market_implied_forward_pe:.1f}x", "現價隱含倍率已超過 hard ceiling；模型保留風控上限，不追高上修可操作倍率。")
        elif structural_hard is not None and fc.get("market_condition_adjusted") and market_implied_forward_pe > structural_hard:
            market_implied_status = "現價隱含 Forward P/E 高於原產業 hard，但仍在市場調整 hard 內；屬市場先行定價，不等於可操作買點。"
        elif market_implied_forward_pe > fc["soft_ceiling"]:
            market_implied_status = "現價隱含 Forward P/E 高於 soft ceiling，屬偏樂觀估值區。"
            if p.get("market_momentum_zone_if_above_hard"):
                _add_row(rows, "風控", "估值偏熱區", f"{market_implied_forward_pe:.1f}x", "現價隱含倍率高於 soft ceiling，需 EPS 上修與法人共識支撐。")
        elif market_implied_forward_pe > final_cap:
            market_implied_status = "現價隱含 Forward P/E 高於可操作倍率，但仍低於產業硬上限。"
        else:
            market_implied_status = "現價隱含 Forward P/E 未高於可操作倍率。"
        extreme_guard = _sf(p.get("extreme_implied_pe_guard"))
        if extreme_guard is not None and market_implied_forward_pe > extreme_guard:
            warnings.append(f"現價隱含 Forward P/E 超過 {extreme_guard:.0f}x，疑似 EPS 分母過低或題材化估值，需改用事件/PB 輔助交叉驗證")

    return {
        "available": True,
        "valuation_mode": primary_valuation,
        "model_version": DYNAMIC_CAP_MODEL_ENGINE_VERSION,
        "base_multiple": base,
        "growth_premium": g,  # 保留舊 key，實際為 growth factor pack
        "gross_margin_premium": q,  # 保留舊 key，實際為 quality factor pack
        "roe_quality_premium": q,
        "theme_premium": th,
        "market_cap_adjustment": sc,
        "geopolitical_factor": geo,
        "classification_confidence_factor": cls,
        "data_confidence_factor": dc,
        "valuation_risk_factor": vr,
        "liquidity_factor": liq,
        "raw_cap": raw_cap,
        "formula_cap": formula_cap,
        "optimistic_cap": optimistic_cap,
        "hard_cap": hard_cap,
        "structural_hard_cap": structural_hard,
        "operable_cap_low": operable_cap_low,
        "operable_cap_high": operable_cap_high,
        "cycle_recovery_state": recovery,
        "pre_clip_cap": pre_clip_cap,
        "final_cap": final_cap,
        "floor_cap": fc["floor"],
        "soft_ceiling_cap": fc["soft_ceiling"],
        "ceiling_cap": fc["hard_ceiling"],
        "hard_ceiling_cap": fc["hard_ceiling"],
        "structural_hard_ceiling_cap": structural_hard,
        "market_condition_hard_adjustment": {
            "adjusted": bool(fc.get("market_condition_adjusted")),
            "factor": fc.get("market_condition_hard_factor"),
            "reason": fc.get("market_condition_reason"),
            "market_implied_forward_pe": fc.get("market_implied_forward_pe_for_hard"),
        },
        "adopted_forward_eps_for_implied": adopted_forward_eps_for_implied,
        "market_implied_forward_pe": market_implied_forward_pe,
        "market_implied_status": market_implied_status,
        "hit_hard_ceiling": hit_hard_ceiling,
        "warnings": warnings,
        "industry_profile": p,
        "m10_margin_benchmark": m10_margin_benchmark,
        "report": pd.DataFrame(rows),
        "explanation": "Dynamic Cap 2.0 17-C-23：保留產業結構 hard，並支援 hybrid 欄位級權重與市場調整 hard；M10 margin benchmark 只作品質係數守門與風險提示，不直接改 base/soft/hard。",
    }

# ===== 第 17-C-4：Dynamic Cap 校準覆寫 =====
CALIBRATION_DEFAULTS.update({
    "FOUNDRY_ADVANCED": {"base_pe": 24.0, "floor_pe": 18.0, "soft_ceiling_pe": 30.0, "hard_ceiling_pe": 35.0, "max_growth_factor": 1.14, "max_quality_factor": 1.10, "max_theme_factor": 1.05, "max_scale_factor": 1.00, "gross_margin_baseline": 0.54, "gross_margin_good": 0.58, "gross_margin_excellent": 0.62, "baked_in_themes": ["ai", "hpc", "cowos", "先進製程"], "geopolitical_factor": 0.92},
    "FOUNDRY_MATURE": {"base_pe": 12.0, "floor_pe": 8.0, "soft_ceiling_pe": 18.0, "hard_ceiling_pe": 22.0, "max_growth_factor": 1.10, "max_quality_factor": 1.08, "max_theme_factor": 1.00, "max_scale_factor": 1.00, "gross_margin_baseline": 0.24, "gross_margin_good": 0.32, "gross_margin_excellent": 0.40, "recovery_sensitive": True},
    "IC_DESIGN_ASIC_IP": {"base_pe": 35.0, "floor_pe": 22.0, "soft_ceiling_pe": 55.0, "hard_ceiling_pe": 70.0, "max_growth_factor": 1.25, "max_quality_factor": 1.22, "max_theme_factor": 1.18, "max_scale_factor": 1.08, "gross_margin_baseline": 0.45, "gross_margin_good": 0.55, "gross_margin_excellent": 0.65, "baked_in_themes": ["ai asic", "asic", "ip", "矽智財"], "geopolitical_factor": 0.97},
    "IC_DESIGN_CONSUMER": {"base_pe": 18.0, "floor_pe": 10.0, "soft_ceiling_pe": 26.0, "hard_ceiling_pe": 32.0, "max_growth_factor": 1.12, "max_quality_factor": 1.10, "max_theme_factor": 1.02, "max_scale_factor": 1.03, "gross_margin_baseline": 0.32, "gross_margin_good": 0.40, "gross_margin_excellent": 0.48, "recovery_sensitive": True},
    "PROBE_AI_ASIC": {"base_pe": 45.0, "floor_pe": 24.0, "soft_ceiling_pe": 65.0, "hard_ceiling_pe": 75.0, "max_growth_factor": 1.25, "max_quality_factor": 1.20, "max_theme_factor": 1.10, "max_scale_factor": 1.08, "gross_margin_baseline": 0.45, "gross_margin_good": 0.52, "gross_margin_excellent": 0.58, "baked_in_themes": ["ai asic", "cpo", "mems", "探針卡", "測試介面"], "geopolitical_factor": 0.97},
    "PROBE_STANDARD": {"base_pe": 18.0, "floor_pe": 10.0, "soft_ceiling_pe": 28.0, "hard_ceiling_pe": 35.0, "max_growth_factor": 1.12, "max_quality_factor": 1.10, "max_theme_factor": 1.05, "max_scale_factor": 1.03, "gross_margin_baseline": 0.25, "gross_margin_good": 0.35, "gross_margin_excellent": 0.45, "baked_in_themes": ["探針", "測試"], "recovery_sensitive": True},
    "TURNAROUND_PROBE_TEST_THEME": {"base_pe": None, "floor_pe": None, "soft_ceiling_pe": None, "hard_ceiling_pe": None, "pb_range": (0.8, 2.5)},
    "THERMAL_LIQUID": {"base_pe": 34.0, "floor_pe": 20.0, "soft_ceiling_pe": 48.0, "hard_ceiling_pe": 60.0, "max_growth_factor": 1.20, "max_quality_factor": 1.18, "max_theme_factor": 1.12, "max_scale_factor": 1.08, "gross_margin_baseline": 0.26, "gross_margin_good": 0.32, "gross_margin_excellent": 0.40, "baked_in_themes": ["水冷", "液冷", "ai伺服器"]},
    "THERMAL_AIR": {"base_pe": 18.0, "floor_pe": 10.0, "soft_ceiling_pe": 28.0, "hard_ceiling_pe": 35.0, "max_growth_factor": 1.12, "max_quality_factor": 1.10, "max_theme_factor": 1.03, "max_scale_factor": 1.03, "gross_margin_baseline": 0.20, "gross_margin_good": 0.26, "gross_margin_excellent": 0.32, "recovery_sensitive": True},
    "SEMICAP_COWOS_EQUIPMENT": {"base_pe": 32.0, "floor_pe": 20.0, "soft_ceiling_pe": 50.0, "hard_ceiling_pe": 65.0, "max_growth_factor": 1.22, "max_quality_factor": 1.18, "max_theme_factor": 1.12, "max_scale_factor": 1.08, "gross_margin_baseline": 0.30, "gross_margin_good": 0.38, "gross_margin_excellent": 0.45, "baked_in_themes": ["cowos", "先進封裝", "設備"], "geopolitical_factor": 0.96, "recovery_sensitive": True},
    "GRID_POWER_STORAGE": {"base_pe": 18.0, "floor_pe": 12.0, "soft_ceiling_pe": 30.0, "hard_ceiling_pe": 38.0, "max_growth_factor": 1.14, "max_quality_factor": 1.12, "max_theme_factor": 1.06, "max_scale_factor": 1.04, "gross_margin_baseline": 0.18, "gross_margin_good": 0.24, "gross_margin_excellent": 0.30},
    "OPTICAL_COMM_SILICON_PHOTONICS": {"base_pe": 36.0, "floor_pe": 22.0, "soft_ceiling_pe": 54.0, "hard_ceiling_pe": 68.0, "max_growth_factor": 1.22, "max_quality_factor": 1.18, "max_theme_factor": 1.12, "max_scale_factor": 1.08, "gross_margin_baseline": 0.32, "gross_margin_good": 0.40, "gross_margin_excellent": 0.48, "baked_in_themes": ["矽光子", "cpo", "800g", "1.6t"]},
    "GENERAL": {"base_pe": 15.0, "floor_pe": 8.0, "soft_ceiling_pe": 24.0, "hard_ceiling_pe": 30.0, "max_growth_factor": 1.10, "max_quality_factor": 1.08, "max_theme_factor": 1.02, "max_scale_factor": 1.00, "gross_margin_baseline": None}
})


# ===== 第 17-C-10：補齊新增產業 Dynamic Cap 校準預設 =====
CALIBRATION_DEFAULTS.update({
    "SILICON_WAFER_CYCLE": {
        "base_pe": 18.0, "floor_pe": 10.0, "soft_ceiling_pe": 28.0, "hard_ceiling_pe": 36.0,
        "max_growth_factor": 1.14, "max_quality_factor": 1.12, "max_theme_factor": 1.04, "max_scale_factor": 1.03,
        "gross_margin_baseline": 0.28, "gross_margin_good": 0.35, "gross_margin_excellent": 0.42,
        "baked_in_themes": ["矽晶圓", "半導體材料", "上游材料"],
        "geopolitical_factor": 0.96, "recovery_sensitive": True,
    },
    "WAFER_RECLAIM_THINNING": {
        "base_pe": 26.0, "floor_pe": 16.0, "soft_ceiling_pe": 40.0, "hard_ceiling_pe": 50.0,
        "max_growth_factor": 1.18, "max_quality_factor": 1.14, "max_theme_factor": 1.10, "max_scale_factor": 1.05,
        "gross_margin_baseline": 0.30, "gross_margin_good": 0.38, "gross_margin_excellent": 0.45,
        "baked_in_themes": ["晶圓再生", "晶圓薄化", "先進封裝", "半導體耗材"],
        "geopolitical_factor": 0.96, "recovery_sensitive": True,
    },
    "IPC_EDGE_AI": {
        "base_pe": 22.0, "floor_pe": 14.0, "soft_ceiling_pe": 34.0, "hard_ceiling_pe": 42.0,
        "max_growth_factor": 1.16, "max_quality_factor": 1.16, "max_theme_factor": 1.08, "max_scale_factor": 1.05,
        "gross_margin_baseline": 0.32, "gross_margin_good": 0.38, "gross_margin_excellent": 0.45,
        "baked_in_themes": ["IPC", "工業電腦", "Edge AI", "邊緣運算", "工控"],
        "geopolitical_factor": 0.98,
    },
    "TELECOM_DEFENSIVE": {
        "base_pe": 16.0, "floor_pe": 12.0, "soft_ceiling_pe": 22.0, "hard_ceiling_pe": 26.0,
        "max_growth_factor": 1.06, "max_quality_factor": 1.10, "max_theme_factor": 1.00, "max_scale_factor": 1.03,
        "gross_margin_baseline": 0.35, "gross_margin_good": 0.40, "gross_margin_excellent": 0.45,
        "baked_in_themes": ["電信", "基礎網路", "高殖利率", "防禦型"],
        "geopolitical_factor": 1.00,
    },
})


# ===== 第 17-C-11：第二批上市半導體缺漏股 Dynamic Cap 校準預設 =====
CALIBRATION_DEFAULTS.update({
    "POWER_ANALOG_IC": {
        "base_pe": 22.0, "floor_pe": 12.0, "soft_ceiling_pe": 36.0, "hard_ceiling_pe": 48.0,
        "max_growth_factor": 1.16, "max_quality_factor": 1.16, "max_theme_factor": 1.06, "max_scale_factor": 1.04,
        "gross_margin_baseline": 0.34, "gross_margin_good": 0.42, "gross_margin_excellent": 0.52,
        "baked_in_themes": ["電源管理IC", "類比IC", "功率半導體", "MOSFET", "二極體"],
        "geopolitical_factor": 0.97, "recovery_sensitive": True,
    },
    "COMPOUND_SEMICONDUCTOR_OPTO": {
        "base_pe": 22.0, "floor_pe": 12.0, "soft_ceiling_pe": 34.0, "hard_ceiling_pe": 45.0,
        "max_growth_factor": 1.16, "max_quality_factor": 1.14, "max_theme_factor": 1.08, "max_scale_factor": 1.04,
        "gross_margin_baseline": 0.28, "gross_margin_good": 0.36, "gross_margin_excellent": 0.45,
        "baked_in_themes": ["化合物半導體", "GaAs", "RF功率放大器", "LED", "光電半導體"],
        "geopolitical_factor": 0.97, "recovery_sensitive": True,
    },
})


# ===== 第 17-C-11B：既有 P/B 週期與特殊分類 Dynamic Cap 兜底 =====
# 這些分類的主估值多為 P/B/ROE/事件，P/E 只作低權重輔助，避免落回 GENERAL base_pe。
CALIBRATION_DEFAULTS.update({
    "MEMORY_CYCLE": {
        "base_pe": 12.0, "floor_pe": 6.0, "soft_ceiling_pe": 18.0, "hard_ceiling_pe": 24.0,
        "max_growth_factor": 1.10, "max_quality_factor": 1.08, "max_theme_factor": 1.00, "max_scale_factor": 1.02,
        "gross_margin_baseline": 0.18, "gross_margin_good": 0.28, "gross_margin_excellent": 0.38,
        "baked_in_themes": ["記憶體", "DRAM", "NAND", "記憶體模組"],
        "recovery_sensitive": True,
    },
    "DISPLAY_LED_CYCLE": {
        "base_pe": 10.0, "floor_pe": 5.0, "soft_ceiling_pe": 16.0, "hard_ceiling_pe": 22.0,
        "max_growth_factor": 1.08, "max_quality_factor": 1.08, "max_theme_factor": 1.00, "max_scale_factor": 1.02,
        "gross_margin_baseline": 0.08, "gross_margin_good": 0.15, "gross_margin_excellent": 0.25,
        "baked_in_themes": ["面板", "LED", "光電循環"],
        "recovery_sensitive": True,
    },
    "PASSIVE_COMPONENT_CYCLE": {
        "base_pe": 14.0, "floor_pe": 8.0, "soft_ceiling_pe": 22.0, "hard_ceiling_pe": 30.0,
        "max_growth_factor": 1.10, "max_quality_factor": 1.10, "max_theme_factor": 1.00, "max_scale_factor": 1.02,
        "gross_margin_baseline": 0.25, "gross_margin_good": 0.35, "gross_margin_excellent": 0.45,
        "baked_in_themes": ["被動元件", "MLCC", "電阻", "景氣循環"],
        "recovery_sensitive": True,
    },
    "FINANCIAL": {
        "base_pe": 12.0, "floor_pe": 8.0, "soft_ceiling_pe": 18.0, "hard_ceiling_pe": 24.0,
        "max_growth_factor": 1.06, "max_quality_factor": 1.10, "max_theme_factor": 1.00, "max_scale_factor": 1.03,
        "gross_margin_baseline": None,
        "baked_in_themes": ["金控", "銀行", "保險", "金融"],
    },
    "SHIPPING_CYCLE": {
        "base_pe": 8.0, "floor_pe": 4.0, "soft_ceiling_pe": 14.0, "hard_ceiling_pe": 20.0,
        "max_growth_factor": 1.08, "max_quality_factor": 1.06, "max_theme_factor": 1.00, "max_scale_factor": 1.02,
        "gross_margin_baseline": None,
        "baked_in_themes": ["海運", "航運", "運價循環"],
        "recovery_sensitive": True,
    },
    "BIOTECH_MEDICAL": {
        "base_pe": 22.0, "floor_pe": 12.0, "soft_ceiling_pe": 35.0, "hard_ceiling_pe": 45.0,
        "max_growth_factor": 1.16, "max_quality_factor": 1.14, "max_theme_factor": 1.04, "max_scale_factor": 1.04,
        "gross_margin_baseline": 0.45, "gross_margin_good": 0.55, "gross_margin_excellent": 0.65,
        "baked_in_themes": ["藥廠", "醫材", "生技醫療"],
    },
    "THEME_EVENT": {
        "base_pe": 8.0, "floor_pe": 0.0, "soft_ceiling_pe": 12.0, "hard_ceiling_pe": 18.0,
        "max_growth_factor": 1.00, "max_quality_factor": 1.00, "max_theme_factor": 1.00, "max_scale_factor": 1.00,
        "gross_margin_baseline": None,
        "baked_in_themes": ["題材", "事件"],
    },
})


# ===== 第 17-C-12：高倍率分類拆分 Dynamic Cap 校準預設 =====
CALIBRATION_DEFAULTS.update({
    "OPTICAL_COMM_CPO_HIGH_VISIBILITY": {
        "base_pe": 42.0, "floor_pe": 24.0, "soft_ceiling_pe": 70.0, "hard_ceiling_pe": 90.0,
        "max_growth_factor": 1.25, "max_quality_factor": 1.18, "max_theme_factor": 1.10, "max_scale_factor": 1.08,
        "gross_margin_baseline": 0.34, "gross_margin_good": 0.42, "gross_margin_excellent": 0.50,
        "baked_in_themes": ["CPO", "矽光子", "800G", "1.6T", "AI data center"],
        "geopolitical_factor": 0.97,
    },
    "OPTICAL_COMM_STANDARD": {
        "base_pe": 30.0, "floor_pe": 16.0, "soft_ceiling_pe": 45.0, "hard_ceiling_pe": 58.0,
        "max_growth_factor": 1.18, "max_quality_factor": 1.14, "max_theme_factor": 1.06, "max_scale_factor": 1.05,
        "gross_margin_baseline": 0.28, "gross_margin_good": 0.36, "gross_margin_excellent": 0.44,
        "baked_in_themes": ["光通訊", "光收發", "AI data center"],
        "geopolitical_factor": 0.98, "recovery_sensitive": True,
    },
    "SEMICAP_ADV_PACKAGING_CORE": {
        "base_pe": 38.0, "floor_pe": 22.0, "soft_ceiling_pe": 60.0, "hard_ceiling_pe": 80.0,
        "max_growth_factor": 1.24, "max_quality_factor": 1.18, "max_theme_factor": 1.10, "max_scale_factor": 1.08,
        "gross_margin_baseline": 0.32, "gross_margin_good": 0.40, "gross_margin_excellent": 0.48,
        "baked_in_themes": ["CoWoS", "先進封裝", "濕製程", "設備"],
        "geopolitical_factor": 0.96,
    },
    "SEMICAP_GENERAL_EQUIPMENT": {
        "base_pe": 28.0, "floor_pe": 14.0, "soft_ceiling_pe": 42.0, "hard_ceiling_pe": 55.0,
        "max_growth_factor": 1.16, "max_quality_factor": 1.12, "max_theme_factor": 1.05, "max_scale_factor": 1.04,
        "gross_margin_baseline": 0.26, "gross_margin_good": 0.34, "gross_margin_excellent": 0.42,
        "baked_in_themes": ["半導體設備", "PCB設備", "自動化設備"],
        "geopolitical_factor": 0.97, "recovery_sensitive": True,
    },
    "THERMAL_LIQUID_CORE": {
        "base_pe": 38.0, "floor_pe": 22.0, "soft_ceiling_pe": 60.0, "hard_ceiling_pe": 80.0,
        "max_growth_factor": 1.24, "max_quality_factor": 1.18, "max_theme_factor": 1.10, "max_scale_factor": 1.08,
        "gross_margin_baseline": 0.28, "gross_margin_good": 0.35, "gross_margin_excellent": 0.44,
        "baked_in_themes": ["液冷", "水冷", "AI伺服器", "高階散熱"],
    },
    "THERMAL_AI_COMPONENTS": {
        "base_pe": 30.0, "floor_pe": 16.0, "soft_ceiling_pe": 45.0, "hard_ceiling_pe": 58.0,
        "max_growth_factor": 1.18, "max_quality_factor": 1.14, "max_theme_factor": 1.06, "max_scale_factor": 1.05,
        "gross_margin_baseline": 0.24, "gross_margin_good": 0.30, "gross_margin_excellent": 0.38,
        "baked_in_themes": ["AI散熱", "散熱零組件", "AI伺服器"],
        "recovery_sensitive": "partial",
    },
    "MEMORY_IP_AI": {
        "base_pe": 35.0, "floor_pe": 18.0, "soft_ceiling_pe": 60.0, "hard_ceiling_pe": 75.0,
        "max_growth_factor": 1.22, "max_quality_factor": 1.20, "max_theme_factor": 1.08, "max_scale_factor": 1.06,
        "gross_margin_baseline": 0.45, "gross_margin_good": 0.55, "gross_margin_excellent": 0.65,
        "baked_in_themes": ["記憶體IP", "AI記憶體", "Royalty", "記憶體循環"],
        "geopolitical_factor": 0.97,
    },
})


# ===== 第 17-C-13：第二批半導體中游/週期分類 Dynamic Cap 校準預設 =====
CALIBRATION_DEFAULTS.update({
    "OSAT_AI_HPC_TESTING": {
        "base_pe": 28.0, "floor_pe": 16.0, "soft_ceiling_pe": 45.0, "hard_ceiling_pe": 58.0,
        "max_growth_factor": 1.20, "max_quality_factor": 1.14, "max_theme_factor": 1.08, "max_scale_factor": 1.05,
        "gross_margin_baseline": 0.24, "gross_margin_good": 0.30, "gross_margin_excellent": 0.38,
        "baked_in_themes": ["AI晶片測試", "HPC測試", "先進封裝", "封測"],
        "geopolitical_factor": 0.96, "recovery_sensitive": True,
    },
    "OSAT_MEMORY_DISPLAY_MATURE": {
        "base_pe": 18.0, "floor_pe": 10.0, "soft_ceiling_pe": 30.0, "hard_ceiling_pe": 40.0,
        "max_growth_factor": 1.12, "max_quality_factor": 1.10, "max_theme_factor": 1.02, "max_scale_factor": 1.03,
        "gross_margin_baseline": 0.18, "gross_margin_good": 0.24, "gross_margin_excellent": 0.32,
        "baked_in_themes": ["記憶體封測", "驅動IC封測", "成熟封測"],
        "geopolitical_factor": 0.97, "recovery_sensitive": True,
    },
    "POWER_MANAGEMENT_IC_DESIGN": {
        "base_pe": 26.0, "floor_pe": 14.0, "soft_ceiling_pe": 42.0, "hard_ceiling_pe": 58.0,
        "max_growth_factor": 1.18, "max_quality_factor": 1.16, "max_theme_factor": 1.06, "max_scale_factor": 1.04,
        "gross_margin_baseline": 0.38, "gross_margin_good": 0.46, "gross_margin_excellent": 0.55,
        "baked_in_themes": ["電源管理IC", "類比IC", "PMIC"],
        "geopolitical_factor": 0.97, "recovery_sensitive": True,
    },
    "POWER_DISCRETE_COMPONENT_CYCLE": {
        "base_pe": 18.0, "floor_pe": 10.0, "soft_ceiling_pe": 30.0, "hard_ceiling_pe": 42.0,
        "max_growth_factor": 1.12, "max_quality_factor": 1.10, "max_theme_factor": 1.02, "max_scale_factor": 1.03,
        "gross_margin_baseline": 0.26, "gross_margin_good": 0.34, "gross_margin_excellent": 0.42,
        "baked_in_themes": ["功率半導體", "MOSFET", "二極體", "整流器"],
        "geopolitical_factor": 0.97, "recovery_sensitive": True,
    },
    "SEMIMAT_ADVANCED_CONSUMABLES": {
        "base_pe": 34.0, "floor_pe": 20.0, "soft_ceiling_pe": 55.0, "hard_ceiling_pe": 70.0,
        "max_growth_factor": 1.22, "max_quality_factor": 1.18, "max_theme_factor": 1.08, "max_scale_factor": 1.06,
        "gross_margin_baseline": 0.34, "gross_margin_good": 0.42, "gross_margin_excellent": 0.50,
        "baked_in_themes": ["EUV", "晶圓載具", "CMP", "半導體耗材", "先進製程"],
        "geopolitical_factor": 0.96, "recovery_sensitive": True,
    },
    "SEMIMAT_POWER_LEADFRAME": {
        "base_pe": 22.0, "floor_pe": 12.0, "soft_ceiling_pe": 35.0, "hard_ceiling_pe": 45.0,
        "max_growth_factor": 1.14, "max_quality_factor": 1.12, "max_theme_factor": 1.04, "max_scale_factor": 1.04,
        "gross_margin_baseline": 0.24, "gross_margin_good": 0.32, "gross_margin_excellent": 0.40,
        "baked_in_themes": ["導線架", "功率元件材料", "車用半導體材料"],
        "geopolitical_factor": 0.97, "recovery_sensitive": True,
    },
    "DISPLAY_COF_MATERIALS": {
        "base_pe": 18.0, "floor_pe": 10.0, "soft_ceiling_pe": 30.0, "hard_ceiling_pe": 40.0,
        "max_growth_factor": 1.10, "max_quality_factor": 1.10, "max_theme_factor": 1.00, "max_scale_factor": 1.03,
        "gross_margin_baseline": 0.20, "gross_margin_good": 0.28, "gross_margin_excellent": 0.36,
        "baked_in_themes": ["COF", "顯示材料", "驅動IC材料"],
        "recovery_sensitive": True,
    },
    "IC_DESIGN_SERVER_BMC_HIGH_VISIBILITY": {
        "base_pe": 42.0, "floor_pe": 24.0, "soft_ceiling_pe": 70.0, "hard_ceiling_pe": 90.0,
        "max_growth_factor": 1.25, "max_quality_factor": 1.22, "max_theme_factor": 1.08, "max_scale_factor": 1.08,
        "gross_margin_baseline": 0.55, "gross_margin_good": 0.62, "gross_margin_excellent": 0.70,
        "baked_in_themes": ["Server BMC", "資料中心", "AI伺服器", "高毛利IC"],
        "geopolitical_factor": 0.97,
    },
})


# ===== 第 17-C-14：第三批 AI 伺服器/電子零組件主鏈 Dynamic Cap 校準預設 =====
CALIBRATION_DEFAULTS.update({
    "AI_CCL_HIGH_VISIBILITY": {
        "base_pe": 36.0, "floor_pe": 20.0, "soft_ceiling_pe": 60.0, "hard_ceiling_pe": 80.0,
        "max_growth_factor": 1.24, "max_quality_factor": 1.18, "max_theme_factor": 1.10, "max_scale_factor": 1.06,
        "gross_margin_baseline": 0.28, "gross_margin_good": 0.36, "gross_margin_excellent": 0.45,
        "baked_in_themes": ["AI伺服器", "高速材料", "CCL", "高階PCB材料"],
        "recovery_sensitive": True,
    },
    "CCL_STANDARD_CYCLE": {
        "base_pe": 22.0, "floor_pe": 12.0, "soft_ceiling_pe": 35.0, "hard_ceiling_pe": 45.0,
        "max_growth_factor": 1.14, "max_quality_factor": 1.12, "max_theme_factor": 1.04, "max_scale_factor": 1.03,
        "gross_margin_baseline": 0.20, "gross_margin_good": 0.28, "gross_margin_excellent": 0.36,
        "baked_in_themes": ["CCL", "銅箔基板", "PCB材料"],
        "recovery_sensitive": True,
    },
    "SERVER_RAIL_HIGH_VISIBILITY": {
        "base_pe": 38.0, "floor_pe": 22.0, "soft_ceiling_pe": 60.0, "hard_ceiling_pe": 80.0,
        "max_growth_factor": 1.22, "max_quality_factor": 1.20, "max_theme_factor": 1.08, "max_scale_factor": 1.06,
        "gross_margin_baseline": 0.34, "gross_margin_good": 0.42, "gross_margin_excellent": 0.50,
        "baked_in_themes": ["滑軌", "高階機構件", "AI伺服器"],
    },
    "AI_SERVER_CHASSIS_CORE": {
        "base_pe": 30.0, "floor_pe": 16.0, "soft_ceiling_pe": 45.0, "hard_ceiling_pe": 58.0,
        "max_growth_factor": 1.18, "max_quality_factor": 1.14, "max_theme_factor": 1.06, "max_scale_factor": 1.05,
        "gross_margin_baseline": 0.22, "gross_margin_good": 0.30, "gross_margin_excellent": 0.38,
        "baked_in_themes": ["AI機櫃", "伺服器機殼", "AI伺服器"],
        "recovery_sensitive": True,
    },
    "SERVER_CHASSIS_STANDARD": {
        "base_pe": 18.0, "floor_pe": 10.0, "soft_ceiling_pe": 30.0, "hard_ceiling_pe": 40.0,
        "max_growth_factor": 1.12, "max_quality_factor": 1.10, "max_theme_factor": 1.02, "max_scale_factor": 1.03,
        "gross_margin_baseline": 0.16, "gross_margin_good": 0.22, "gross_margin_excellent": 0.30,
        "baked_in_themes": ["機殼", "伺服器機構件"],
        "recovery_sensitive": True,
    },
    "DATACENTER_POWER_LEADER": {
        "base_pe": 34.0, "floor_pe": 20.0, "soft_ceiling_pe": 55.0, "hard_ceiling_pe": 70.0,
        "max_growth_factor": 1.20, "max_quality_factor": 1.18, "max_theme_factor": 1.08, "max_scale_factor": 1.05,
        "gross_margin_baseline": 0.26, "gross_margin_good": 0.32, "gross_margin_excellent": 0.40,
        "baked_in_themes": ["資料中心電源", "BBU", "能源管理", "電源龍頭"],
    },
    "UPS_POWER_QUALITY": {
        "base_pe": 28.0, "floor_pe": 16.0, "soft_ceiling_pe": 42.0, "hard_ceiling_pe": 55.0,
        "max_growth_factor": 1.14, "max_quality_factor": 1.18, "max_theme_factor": 1.04, "max_scale_factor": 1.04,
        "gross_margin_baseline": 0.30, "gross_margin_good": 0.38, "gross_margin_excellent": 0.45,
        "baked_in_themes": ["UPS", "不斷電系統", "高毛利電源"],
    },
    "POWER_SUPPLY_STANDARD": {
        "base_pe": 18.0, "floor_pe": 10.0, "soft_ceiling_pe": 30.0, "hard_ceiling_pe": 40.0,
        "max_growth_factor": 1.10, "max_quality_factor": 1.10, "max_theme_factor": 1.00, "max_scale_factor": 1.03,
        "gross_margin_baseline": 0.16, "gross_margin_good": 0.22, "gross_margin_excellent": 0.30,
        "baked_in_themes": ["電源", "一般電源"],
        "recovery_sensitive": True,
    },
    "AI_SERVER_PCB_HIGH_VISIBILITY": {
        "base_pe": 34.0, "floor_pe": 20.0, "soft_ceiling_pe": 55.0, "hard_ceiling_pe": 70.0,
        "max_growth_factor": 1.20, "max_quality_factor": 1.16, "max_theme_factor": 1.08, "max_scale_factor": 1.05,
        "gross_margin_baseline": 0.22, "gross_margin_good": 0.30, "gross_margin_excellent": 0.38,
        "baked_in_themes": ["AI伺服器PCB", "高階PCB", "伺服器板"],
        "recovery_sensitive": True,
    },
    "PCB_STANDARD_BOARD": {
        "base_pe": 22.0, "floor_pe": 12.0, "soft_ceiling_pe": 35.0, "hard_ceiling_pe": 45.0,
        "max_growth_factor": 1.14, "max_quality_factor": 1.12, "max_theme_factor": 1.04, "max_scale_factor": 1.03,
        "gross_margin_baseline": 0.16, "gross_margin_good": 0.22, "gross_margin_excellent": 0.30,
        "baked_in_themes": ["PCB", "伺服器板"],
        "recovery_sensitive": True,
    },
    "HIGH_SPEED_CONNECTOR_CORE": {
        "base_pe": 34.0, "floor_pe": 20.0, "soft_ceiling_pe": 55.0, "hard_ceiling_pe": 70.0,
        "max_growth_factor": 1.18, "max_quality_factor": 1.16, "max_theme_factor": 1.08, "max_scale_factor": 1.05,
        "gross_margin_baseline": 0.26, "gross_margin_good": 0.34, "gross_margin_excellent": 0.42,
        "baked_in_themes": ["高速連接器", "高速線材", "AI伺服器"],
        "recovery_sensitive": True,
    },
    "CONNECTOR_STANDARD": {
        "base_pe": 18.0, "floor_pe": 10.0, "soft_ceiling_pe": 30.0, "hard_ceiling_pe": 40.0,
        "max_growth_factor": 1.10, "max_quality_factor": 1.10, "max_theme_factor": 1.00, "max_scale_factor": 1.03,
        "gross_margin_baseline": 0.18, "gross_margin_good": 0.25, "gross_margin_excellent": 0.32,
        "baked_in_themes": ["連接器", "線材"],
        "recovery_sensitive": True,
    },
    "AI_DATACENTER_SWITCH": {
        "base_pe": 36.0, "floor_pe": 20.0, "soft_ceiling_pe": 58.0, "hard_ceiling_pe": 75.0,
        "max_growth_factor": 1.20, "max_quality_factor": 1.16, "max_theme_factor": 1.08, "max_scale_factor": 1.05,
        "gross_margin_baseline": 0.24, "gross_margin_good": 0.32, "gross_margin_excellent": 0.40,
        "baked_in_themes": ["AI交換器", "資料中心網路", "高速交換器"],
    },
    "NETWORK_EQUIPMENT_STANDARD": {
        "base_pe": 20.0, "floor_pe": 10.0, "soft_ceiling_pe": 32.0, "hard_ceiling_pe": 42.0,
        "max_growth_factor": 1.12, "max_quality_factor": 1.10, "max_theme_factor": 1.02, "max_scale_factor": 1.03,
        "gross_margin_baseline": 0.20, "gross_margin_good": 0.28, "gross_margin_excellent": 0.36,
        "baked_in_themes": ["網通", "通訊設備"],
        "recovery_sensitive": True,
    },
})

CALIBRATION_DEFAULTS["ABF_SUBSTRATE"].update({
    "pb_high_warning_threshold": 8.0,
    "extreme_implied_pe_guard": 120.0,
})


# ===== 第 17-C-15：第四批非 AI 主鏈與防禦/循環分類 Dynamic Cap 校準預設 =====
CALIBRATION_DEFAULTS.update({'FINANCIAL_LIFE_INSURANCE_HOLDCO': {'base_pe': 11.0,
                                     'floor_pe': 7.0,
                                     'soft_ceiling_pe': 16.0,
                                     'hard_ceiling_pe': 22.0,
                                     'max_growth_factor': 1.04,
                                     'max_quality_factor': 1.1,
                                     'max_theme_factor': 1.0,
                                     'max_scale_factor': 1.03,
                                     'gross_margin_baseline': None,
                                     'baked_in_themes': ['金控', '壽險', '保險'],
                                     'pb_high_warning_threshold': 2.0},
 'FINANCIAL_BANK_HOLDCO_QUALITY': {'base_pe': 13.0,
                                   'floor_pe': 8.0,
                                   'soft_ceiling_pe': 18.0,
                                   'hard_ceiling_pe': 24.0,
                                   'max_growth_factor': 1.05,
                                   'max_quality_factor': 1.12,
                                   'max_theme_factor': 1.0,
                                   'max_scale_factor': 1.03,
                                   'gross_margin_baseline': None,
                                   'baked_in_themes': ['金控', '銀行', '官股金控'],
                                   'pb_high_warning_threshold': 2.4},
 'PHARMA_DEFENSIVE_GENERIC': {'base_pe': 16.0,
                              'floor_pe': 9.0,
                              'soft_ceiling_pe': 24.0,
                              'hard_ceiling_pe': 28.0,
                              'max_growth_factor': 1.08,
                              'max_quality_factor': 1.1,
                              'max_theme_factor': 1.0,
                              'max_scale_factor': 1.02,
                              'gross_margin_baseline': 0.38,
                              'gross_margin_good': 0.48,
                              'gross_margin_excellent': 0.58,
                              'baked_in_themes': ['成熟製藥', '藥廠'],
                              'pb_high_warning_threshold': 3.0},
 'PHARMA_CDMO_PROFIT': {'base_pe': 24.0,
                        'floor_pe': 12.0,
                        'soft_ceiling_pe': 36.0,
                        'hard_ceiling_pe': 45.0,
                        'max_growth_factor': 1.16,
                        'max_quality_factor': 1.14,
                        'max_theme_factor': 1.04,
                        'max_scale_factor': 1.04,
                        'gross_margin_baseline': 0.45,
                        'gross_margin_good': 0.55,
                        'gross_margin_excellent': 0.65,
                        'baked_in_themes': ['藥廠', 'CDMO', '外銷藥'],
                        'pb_high_warning_threshold': 5.0},
 'BIOTECH_NEW_DRUG_EVENT': {'base_pe': 8.0,
                            'floor_pe': 0.0,
                            'soft_ceiling_pe': 12.0,
                            'hard_ceiling_pe': 18.0,
                            'max_growth_factor': 1.0,
                            'max_quality_factor': 1.0,
                            'max_theme_factor': 1.0,
                            'max_scale_factor': 1.0,
                            'gross_margin_baseline': None,
                            'baked_in_themes': ['新藥', '里程碑'],
                            'event_model_if_eps_unstable': True,
                            'pb_high_warning_threshold': 3.0},
 'BIOTECH_CELL_THERAPY_BIOSIMILAR': {'base_pe': 18.0,
                                     'floor_pe': 0.0,
                                     'soft_ceiling_pe': 28.0,
                                     'hard_ceiling_pe': 35.0,
                                     'max_growth_factor': 1.1,
                                     'max_quality_factor': 1.08,
                                     'max_theme_factor': 1.0,
                                     'max_scale_factor': 1.02,
                                     'gross_margin_baseline': None,
                                     'baked_in_themes': ['細胞治療', '生物相似藥'],
                                     'event_model_if_eps_unstable': True,
                                     'pb_high_warning_threshold': 5.0},
 'CLOUD_SECURITY_SERVICES': {'base_pe': 26.0,
                             'floor_pe': 14.0,
                             'soft_ceiling_pe': 38.0,
                             'hard_ceiling_pe': 45.0,
                             'max_growth_factor': 1.16,
                             'max_quality_factor': 1.16,
                             'max_theme_factor': 1.06,
                             'max_scale_factor': 1.04,
                             'gross_margin_baseline': 0.42,
                             'gross_margin_good': 0.52,
                             'gross_margin_excellent': 0.62,
                             'baked_in_themes': ['資安', '雲端', '軟體'],
                             'pb_high_warning_threshold': 6.0},
 'IT_SERVICES_SYSTEM_INTEGRATION': {'base_pe': 18.0,
                                    'floor_pe': 9.0,
                                    'soft_ceiling_pe': 26.0,
                                    'hard_ceiling_pe': 32.0,
                                    'max_growth_factor': 1.1,
                                    'max_quality_factor': 1.12,
                                    'max_theme_factor': 1.02,
                                    'max_scale_factor': 1.03,
                                    'gross_margin_baseline': 0.28,
                                    'gross_margin_good': 0.36,
                                    'gross_margin_excellent': 0.46,
                                    'baked_in_themes': ['系統整合', '資訊服務'],
                                    'pb_high_warning_threshold': 5.0},
 'INDUSTRIAL_AUTOMATION_CORE': {'base_pe': 22.0,
                                'floor_pe': 12.0,
                                'soft_ceiling_pe': 34.0,
                                'hard_ceiling_pe': 42.0,
                                'max_growth_factor': 1.14,
                                'max_quality_factor': 1.14,
                                'max_theme_factor': 1.05,
                                'max_scale_factor': 1.04,
                                'gross_margin_baseline': 0.28,
                                'gross_margin_good': 0.36,
                                'gross_margin_excellent': 0.45,
                                'baked_in_themes': ['自動化', '工業自動化'],
                                'recovery_sensitive': True,
                                'pb_high_warning_threshold': 6.0},
 'ROBOTICS_THEME_EVENT': {'base_pe': 12.0,
                          'floor_pe': 0.0,
                          'soft_ceiling_pe': 20.0,
                          'hard_ceiling_pe': 28.0,
                          'max_growth_factor': 1.0,
                          'max_quality_factor': 1.0,
                          'max_theme_factor': 1.0,
                          'max_scale_factor': 1.0,
                          'gross_margin_baseline': None,
                          'baked_in_themes': ['機器人題材', 'AI視覺'],
                          'event_model_if_eps_unstable': True,
                          'pb_high_warning_threshold': 5.0},
 'OPTICS_LENS_LEADER': {'base_pe': 24.0,
                        'floor_pe': 14.0,
                        'soft_ceiling_pe': 34.0,
                        'hard_ceiling_pe': 42.0,
                        'max_growth_factor': 1.12,
                        'max_quality_factor': 1.18,
                        'max_theme_factor': 1.04,
                        'max_scale_factor': 1.04,
                        'gross_margin_baseline': 0.38,
                        'gross_margin_good': 0.48,
                        'gross_margin_excellent': 0.58,
                        'baked_in_themes': ['高階鏡頭', '光學'],
                        'recovery_sensitive': True,
                        'pb_high_warning_threshold': 5.0},
 'OPTICS_MODULE_CYCLE': {'base_pe': 16.0,
                         'floor_pe': 8.0,
                         'soft_ceiling_pe': 26.0,
                         'hard_ceiling_pe': 32.0,
                         'max_growth_factor': 1.1,
                         'max_quality_factor': 1.1,
                         'max_theme_factor': 1.0,
                         'max_scale_factor': 1.03,
                         'gross_margin_baseline': 0.22,
                         'gross_margin_good': 0.3,
                         'gross_margin_excellent': 0.4,
                         'baked_in_themes': ['光學模組', '鏡頭'],
                         'recovery_sensitive': True,
                         'pb_high_warning_threshold': 4.0},
 'GRID_EQUIPMENT_CORE': {'base_pe': 24.0,
                         'floor_pe': 14.0,
                         'soft_ceiling_pe': 36.0,
                         'hard_ceiling_pe': 45.0,
                         'max_growth_factor': 1.16,
                         'max_quality_factor': 1.14,
                         'max_theme_factor': 1.06,
                         'max_scale_factor': 1.04,
                         'gross_margin_baseline': 0.18,
                         'gross_margin_good': 0.24,
                         'gross_margin_excellent': 0.3,
                         'baked_in_themes': ['重電', '電網', '儲能'],
                         'pb_high_warning_threshold': 6.0},
 'GRID_TRANSFORMER_HIGH_VISIBILITY': {'base_pe': 30.0,
                                      'floor_pe': 18.0,
                                      'soft_ceiling_pe': 45.0,
                                      'hard_ceiling_pe': 60.0,
                                      'max_growth_factor': 1.18,
                                      'max_quality_factor': 1.16,
                                      'max_theme_factor': 1.08,
                                      'max_scale_factor': 1.05,
                                      'gross_margin_baseline': 0.2,
                                      'gross_margin_good': 0.28,
                                      'gross_margin_excellent': 0.35,
                                      'baked_in_themes': ['變壓器', '重電', '電網'],
                                      'market_momentum_zone_if_above_hard': True,
                                      'pb_high_warning_threshold': 10.0},
 'GRID_ASSET_TURNAROUND': {'base_pe': 10.0,
                           'floor_pe': 5.0,
                           'soft_ceiling_pe': 16.0,
                           'hard_ceiling_pe': 24.0,
                           'max_growth_factor': 1.06,
                           'max_quality_factor': 1.06,
                           'max_theme_factor': 1.0,
                           'max_scale_factor': 1.02,
                           'gross_margin_baseline': None,
                           'baked_in_themes': ['資產', '轉機', '重電'],
                           'event_model_if_eps_unstable': True,
                           'pb_high_warning_threshold': 2.0},
 'WIND_POWER_INFRA': {'base_pe': 18.0,
                      'floor_pe': 8.0,
                      'soft_ceiling_pe': 28.0,
                      'hard_ceiling_pe': 34.0,
                      'max_growth_factor': 1.1,
                      'max_quality_factor': 1.1,
                      'max_theme_factor': 1.02,
                      'max_scale_factor': 1.03,
                      'gross_margin_baseline': 0.15,
                      'gross_margin_good': 0.22,
                      'gross_margin_excellent': 0.28,
                      'baked_in_themes': ['風電', '綠能基建'],
                      'recovery_sensitive': True,
                      'pb_high_warning_threshold': 4.0},
 'GREEN_ENERGY_PROJECT_EPC': {'base_pe': 12.0,
                              'floor_pe': 4.0,
                              'soft_ceiling_pe': 20.0,
                              'hard_ceiling_pe': 28.0,
                              'max_growth_factor': 1.06,
                              'max_quality_factor': 1.06,
                              'max_theme_factor': 1.0,
                              'max_scale_factor': 1.02,
                              'gross_margin_baseline': None,
                              'baked_in_themes': ['綠能工程', '儲能', 'EPC'],
                              'event_model_if_eps_unstable': True,
                              'pb_high_warning_threshold': 5.0}})


# ===== 第 17-C-16：第五批尾端總稽核 Dynamic Cap 校準預設 =====
CALIBRATION_DEFAULTS.update({'CONSUMER_MCU_CONTROL_IC': {'base_pe': 18.0,
                             'floor_pe': 10.0,
                             'soft_ceiling_pe': 28.0,
                             'hard_ceiling_pe': 36.0,
                             'max_growth_factor': 1.12,
                             'max_quality_factor': 1.1,
                             'max_theme_factor': 1.02,
                             'max_scale_factor': 1.03,
                             'gross_margin_baseline': 0.28,
                             'baked_in_themes': ['消費 MCU'],
                             'event_model_if_eps_unstable': False,
                             'pb_high_warning_threshold': 4.0,
                             'recovery_sensitive': True},
 'DISPLAY_DRIVER_IC_CYCLE': {'base_pe': 16.0,
                             'floor_pe': 8.0,
                             'soft_ceiling_pe': 24.0,
                             'hard_ceiling_pe': 32.0,
                             'max_growth_factor': 1.12,
                             'max_quality_factor': 1.1,
                             'max_theme_factor': 1.02,
                             'max_scale_factor': 1.03,
                             'gross_margin_baseline': 0.34,
                             'baked_in_themes': ['Display Driver'],
                             'event_model_if_eps_unstable': False,
                             'pb_high_warning_threshold': 4.5,
                             'recovery_sensitive': True,
                             'gross_margin_good': 0.42,
                             'gross_margin_excellent': 0.5},
 'CONSUMER_INTERFACE_SENSOR_IC': {'base_pe': 20.0,
                                  'floor_pe': 10.0,
                                  'soft_ceiling_pe': 32.0,
                                  'hard_ceiling_pe': 40.0,
                                  'max_growth_factor': 1.12,
                                  'max_quality_factor': 1.1,
                                  'max_theme_factor': 1.02,
                                  'max_scale_factor': 1.03,
                                  'gross_margin_baseline': 0.28,
                                  'baked_in_themes': ['消費介面'],
                                  'event_model_if_eps_unstable': False,
                                  'pb_high_warning_threshold': 5.0,
                                  'recovery_sensitive': True},
 'LEGACY_CONSUMER_IC_TURNAROUND': {'base_pe': 10.0,
                                   'floor_pe': 4.0,
                                   'soft_ceiling_pe': 16.0,
                                   'hard_ceiling_pe': 24.0,
                                   'max_growth_factor': 1.12,
                                   'max_quality_factor': 1.1,
                                   'max_theme_factor': 1.0,
                                   'max_scale_factor': 1.03,
                                   'gross_margin_baseline': 0.28,
                                   'baked_in_themes': ['Legacy 消費 IC'],
                                   'event_model_if_eps_unstable': True,
                                   'pb_high_warning_threshold': 2.5,
                                   'recovery_sensitive': True},
 'PLATFORM_IC_LEADER': {'base_pe': 28.0,
                        'floor_pe': 16.0,
                        'soft_ceiling_pe': 42.0,
                        'hard_ceiling_pe': 55.0,
                        'max_growth_factor': 1.18,
                        'max_quality_factor': 1.16,
                        'max_theme_factor': 1.06,
                        'max_scale_factor': 1.03,
                        'gross_margin_baseline': 0.42,
                        'baked_in_themes': ['平台型 IC 龍頭'],
                        'event_model_if_eps_unstable': False,
                        'pb_high_warning_threshold': 6.0,
                        'recovery_sensitive': True,
                        'gross_margin_good': 0.5,
                        'gross_margin_excellent': 0.58},
 'HIGH_SPEED_INTERFACE_IC': {'base_pe': 26.0,
                             'floor_pe': 14.0,
                             'soft_ceiling_pe': 40.0,
                             'hard_ceiling_pe': 50.0,
                             'max_growth_factor': 1.16,
                             'max_quality_factor': 1.14,
                             'max_theme_factor': 1.06,
                             'max_scale_factor': 1.03,
                             'gross_margin_baseline': 0.38,
                             'baked_in_themes': ['高速介面'],
                             'event_model_if_eps_unstable': False,
                             'pb_high_warning_threshold': 6.0,
                             'recovery_sensitive': True,
                             'gross_margin_good': 0.46,
                             'gross_margin_excellent': 0.54},
 'RF_CONNECTIVITY_IC': {'base_pe': 22.0,
                        'floor_pe': 12.0,
                        'soft_ceiling_pe': 34.0,
                        'hard_ceiling_pe': 45.0,
                        'max_growth_factor': 1.12,
                        'max_quality_factor': 1.1,
                        'max_theme_factor': 1.02,
                        'max_scale_factor': 1.03,
                        'gross_margin_baseline': 0.28,
                        'baked_in_themes': ['RF'],
                        'event_model_if_eps_unstable': False,
                        'pb_high_warning_threshold': 5.0,
                        'recovery_sensitive': True},
 'EDGE_AI_SENSOR_SOC': {'base_pe': 24.0,
                        'floor_pe': 12.0,
                        'soft_ceiling_pe': 38.0,
                        'hard_ceiling_pe': 48.0,
                        'max_growth_factor': 1.12,
                        'max_quality_factor': 1.1,
                        'max_theme_factor': 1.0,
                        'max_scale_factor': 1.03,
                        'gross_margin_baseline': 0.28,
                        'baked_in_themes': ['Edge AI'],
                        'event_model_if_eps_unstable': True,
                        'pb_high_warning_threshold': 6.0,
                        'recovery_sensitive': True},
 'MEMORY_MANUFACTURING_CYCLE': {'base_pe': 10.0,
                                'floor_pe': 4.0,
                                'soft_ceiling_pe': 16.0,
                                'hard_ceiling_pe': 22.0,
                                'max_growth_factor': 1.06,
                                'max_quality_factor': 1.06,
                                'max_theme_factor': 1.0,
                                'max_scale_factor': 1.03,
                                'gross_margin_baseline': None,
                                'baked_in_themes': ['記憶體製造'],
                                'event_model_if_eps_unstable': False,
                                'pb_high_warning_threshold': 2.0,
                                'recovery_sensitive': True},
 'MEMORY_MODULE_STORAGE_BRAND': {'base_pe': 12.0,
                                 'floor_pe': 6.0,
                                 'soft_ceiling_pe': 20.0,
                                 'hard_ceiling_pe': 28.0,
                                 'max_growth_factor': 1.12,
                                 'max_quality_factor': 1.1,
                                 'max_theme_factor': 1.02,
                                 'max_scale_factor': 1.03,
                                 'gross_margin_baseline': 0.28,
                                 'baked_in_themes': ['記憶體模組'],
                                 'event_model_if_eps_unstable': False,
                                 'pb_high_warning_threshold': 3.0,
                                 'recovery_sensitive': True},
 'MEMORY_OSAT_CYCLE': {'base_pe': 16.0,
                       'floor_pe': 8.0,
                       'soft_ceiling_pe': 26.0,
                       'hard_ceiling_pe': 35.0,
                       'max_growth_factor': 1.12,
                       'max_quality_factor': 1.1,
                       'max_theme_factor': 1.02,
                       'max_scale_factor': 1.03,
                       'gross_margin_baseline': 0.28,
                       'baked_in_themes': ['記憶體封測週期'],
                       'event_model_if_eps_unstable': False,
                       'pb_high_warning_threshold': 3.0,
                       'recovery_sensitive': True},
 'GENERAL_OSAT_TEST_LEADFRAME': {'base_pe': 18.0,
                                 'floor_pe': 9.0,
                                 'soft_ceiling_pe': 28.0,
                                 'hard_ceiling_pe': 38.0,
                                 'max_growth_factor': 1.12,
                                 'max_quality_factor': 1.1,
                                 'max_theme_factor': 1.02,
                                 'max_scale_factor': 1.03,
                                 'gross_margin_baseline': 0.28,
                                 'baked_in_themes': ['一般成熟封測'],
                                 'event_model_if_eps_unstable': False,
                                 'pb_high_warning_threshold': 3.5,
                                 'recovery_sensitive': True},
 'DEFENSE_DRONE_EVENT': {'base_pe': 8.0,
                         'floor_pe': 0.0,
                         'soft_ceiling_pe': 14.0,
                         'hard_ceiling_pe': 24.0,
                         'max_growth_factor': 1.0,
                         'max_quality_factor': 1.0,
                         'max_theme_factor': 1.0,
                         'max_scale_factor': 1.03,
                         'gross_margin_baseline': None,
                         'baked_in_themes': ['軍工'],
                         'event_model_if_eps_unstable': True,
                         'pb_high_warning_threshold': 6.0,
                         'recovery_sensitive': False},
 'LEGACY_TECH_REVIEW': {'base_pe': 8.0,
                        'floor_pe': 0.0,
                        'soft_ceiling_pe': 14.0,
                        'hard_ceiling_pe': 22.0,
                        'max_growth_factor': 1.0,
                        'max_quality_factor': 1.0,
                        'max_theme_factor': 1.0,
                        'max_scale_factor': 1.03,
                        'gross_margin_baseline': None,
                        'baked_in_themes': ['舊資料'],
                        'event_model_if_eps_unstable': True,
                        'pb_high_warning_threshold': 2.0,
                        'recovery_sensitive': True}})


# ===== 第 17-C-17：base / soft / hard 倍率寬鬆度收斂與 taxonomy 同步 =====
# 依 2026-06-09 查核，降低高 hard ceiling 與週期型 AI 零組件分類；同時對齊 taxonomy 顯示倍率，避免 UI 與實算不同。
CALIBRATION_DEFAULTS.update({
    "PROBE_TEST_INTERFACE": {
        **CALIBRATION_DEFAULTS["PROBE_TEST_INTERFACE"],
        "base_pe": 32.0, "floor_pe": 22.0, "soft_ceiling_pe": 45.0, "hard_ceiling_pe": 55.0,
        "valuation_tightening_note": "17-C-17：同步 taxonomy 較保守口徑。",
    },
    "FAB_FACILITY_MATERIALS": {
        **CALIBRATION_DEFAULTS["FAB_FACILITY_MATERIALS"],
        "base_pe": 24.0, "floor_pe": 16.0, "soft_ceiling_pe": 36.0, "hard_ceiling_pe": 42.0,
        "valuation_tightening_note": "17-C-17：同步 taxonomy 較保守口徑。",
    },
    "ABF_SUBSTRATE": {
        **CALIBRATION_DEFAULTS["ABF_SUBSTRATE"],
        "base_pe": 24.0, "floor_pe": 12.0, "soft_ceiling_pe": 42.0, "hard_ceiling_pe": 55.0,
        "valuation_tightening_note": "17-C-19：ABF 載板 base 維持 24x；soft/hard 回補至 42/55，以 FY2 樂觀/極限情境容納法人平均與最高目標價。",
    },
    "SERVER_PCB_BOARD": {
        **CALIBRATION_DEFAULTS["SERVER_PCB_BOARD"],
        "base_pe": 28.0, "floor_pe": 16.0, "soft_ceiling_pe": 40.0, "hard_ceiling_pe": 50.0,
        "valuation_tightening_note": "17-C-17：同步 taxonomy 較保守口徑。",
    },
    "CONNECTOR_CABLE": {
        **CALIBRATION_DEFAULTS["CONNECTOR_CABLE"],
        "base_pe": 28.0, "floor_pe": 18.0, "soft_ceiling_pe": 42.0, "hard_ceiling_pe": 50.0,
        "valuation_tightening_note": "17-C-17：同步 taxonomy 較保守口徑。",
    },
    "SERVER_CHASSIS_RAIL": {
        **CALIBRATION_DEFAULTS["SERVER_CHASSIS_RAIL"],
        "base_pe": 24.0, "floor_pe": 16.0, "soft_ceiling_pe": 34.0, "hard_ceiling_pe": 42.0,
        "valuation_tightening_note": "17-C-17：同步 taxonomy 較保守口徑。",
    },
    "POWER_BBU": {
        **CALIBRATION_DEFAULTS["POWER_BBU"],
        "base_pe": 24.0, "floor_pe": 16.0, "soft_ceiling_pe": 36.0, "hard_ceiling_pe": 44.0,
        "valuation_tightening_note": "17-C-17：同步 taxonomy 較保守口徑。",
    },
    "THERMAL_LIQUID_COOLING": {
        **CALIBRATION_DEFAULTS["THERMAL_LIQUID_COOLING"],
        "base_pe": 34.0, "floor_pe": 20.0, "soft_ceiling_pe": 48.0, "hard_ceiling_pe": 60.0,
        "valuation_tightening_note": "17-C-17：同步 taxonomy 較保守口徑；核心液冷另用 THERMAL_LIQUID_CORE。",
    },
    "NETWORK_SWITCH": {
        **CALIBRATION_DEFAULTS["NETWORK_SWITCH"],
        "base_pe": 26.0, "floor_pe": 16.0, "soft_ceiling_pe": 36.0, "hard_ceiling_pe": 45.0,
        "valuation_tightening_note": "17-C-17：一般網通交換器同步 taxonomy，避免錯套 AI switch。",
    },
    "OPTICS_LENS_MODULE": {
        **CALIBRATION_DEFAULTS["OPTICS_LENS_MODULE"],
        "base_pe": 28.0, "floor_pe": 16.0, "soft_ceiling_pe": 40.0, "hard_ceiling_pe": 50.0,
        "valuation_tightening_note": "17-C-17：同步 taxonomy 較保守口徑。",
    },
    "ROBOTICS_AUTOMATION": {
        **CALIBRATION_DEFAULTS["ROBOTICS_AUTOMATION"],
        "base_pe": 24.0, "floor_pe": 16.0, "soft_ceiling_pe": 36.0, "hard_ceiling_pe": 45.0,
        "valuation_tightening_note": "17-C-17：機器人題材需 EPS/訂單落地，Dynamic Cap 同步 taxonomy。",
    },
    "SPACE_LEO_SATELLITE": {
        **CALIBRATION_DEFAULTS["SPACE_LEO_SATELLITE"],
        "base_pe": 28.0, "floor_pe": 16.0, "soft_ceiling_pe": 34.0, "hard_ceiling_pe": 45.0,
        "valuation_tightening_note": "17-C-17：低軌衛星題材以事件模型防呆，P/E 輔助倍率收斂。",
    },
    "EV_AUTO_ELECTRONICS": {
        **CALIBRATION_DEFAULTS["EV_AUTO_ELECTRONICS"],
        "base_pe": 26.0, "floor_pe": 16.0, "soft_ceiling_pe": 36.0, "hard_ceiling_pe": 45.0,
        "valuation_tightening_note": "17-C-17：同步 taxonomy 較保守口徑。",
    },
    "SOFTWARE_SECURITY_CLOUD": {
        **CALIBRATION_DEFAULTS["SOFTWARE_SECURITY_CLOUD"],
        "base_pe": 30.0, "floor_pe": 18.0, "soft_ceiling_pe": 42.0, "hard_ceiling_pe": 50.0,
        "valuation_tightening_note": "17-C-17：台股軟體/資安規模與流動性有限，收斂 hard ceiling。",
    },
    "CONSUMER_TOURISM": {
        "base_pe": 22.0, "floor_pe": 14.0, "soft_ceiling_pe": 32.0, "hard_ceiling_pe": 38.0,
        "max_growth_factor": 1.12, "max_quality_factor": 1.12, "max_theme_factor": 1.02, "max_scale_factor": 1.03,
        "gross_margin_baseline": 0.30, "gross_margin_good": 0.38, "gross_margin_excellent": 0.45,
        "baked_in_themes": ["消費", "觀光", "生活產業"],
        "recovery_sensitive": True,
        "valuation_tightening_note": "17-C-17：補齊 Dynamic Cap defaults，避免落回 GENERAL base_pe。",
    },
    "IC_DESIGN_IP_ROYALTY": {
        **CALIBRATION_DEFAULTS["IC_DESIGN_IP_ROYALTY"],
        "base_pe": 45.0, "floor_pe": 28.0, "soft_ceiling_pe": 68.0, "hard_ceiling_pe": 82.0,
        "valuation_tightening_note": "17-C-17：Royalty/IP hard 從 90 收斂至 82。",
    },
    "IC_DESIGN_ASIC_HIGH_VISIBILITY": {
        **CALIBRATION_DEFAULTS["IC_DESIGN_ASIC_HIGH_VISIBILITY"],
        "base_pe": 45.0, "floor_pe": 28.0, "soft_ceiling_pe": 65.0, "hard_ceiling_pe": 80.0,
        "valuation_tightening_note": "17-C-17：高能見度 ASIC hard 從 85 收斂至 80。",
    },
    "OPTICAL_COMM_CPO_HIGH_VISIBILITY": {
        **CALIBRATION_DEFAULTS["OPTICAL_COMM_CPO_HIGH_VISIBILITY"],
        "base_pe": 42.0, "floor_pe": 24.0, "soft_ceiling_pe": 65.0, "hard_ceiling_pe": 82.0,
        "valuation_tightening_note": "17-C-17：CPO/矽光子 hard 從 90 收斂至 82。",
    },
    "IC_DESIGN_SERVER_BMC_HIGH_VISIBILITY": {
        **CALIBRATION_DEFAULTS["IC_DESIGN_SERVER_BMC_HIGH_VISIBILITY"],
        "base_pe": 40.0, "floor_pe": 24.0, "soft_ceiling_pe": 62.0, "hard_ceiling_pe": 78.0,
        "valuation_tightening_note": "17-C-17：Server BMC hard 從 90 收斂至 78。",
    },
    "SEMICAP_ADV_PACKAGING_CORE": {
        **CALIBRATION_DEFAULTS["SEMICAP_ADV_PACKAGING_CORE"],
        "base_pe": 36.0, "floor_pe": 22.0, "soft_ceiling_pe": 55.0, "hard_ceiling_pe": 72.0,
        "valuation_tightening_note": "17-C-17：先進封裝設備 hard 從 80 收斂至 72。",
    },
    "THERMAL_LIQUID_CORE": {
        **CALIBRATION_DEFAULTS["THERMAL_LIQUID_CORE"],
        "base_pe": 36.0, "floor_pe": 22.0, "soft_ceiling_pe": 55.0, "hard_ceiling_pe": 70.0,
        "valuation_tightening_note": "17-C-17：液冷核心 hard 從 80 收斂至 70。",
    },
    "SERVER_RAIL_HIGH_VISIBILITY": {
        **CALIBRATION_DEFAULTS["SERVER_RAIL_HIGH_VISIBILITY"],
        "base_pe": 36.0, "floor_pe": 22.0, "soft_ceiling_pe": 55.0, "hard_ceiling_pe": 70.0,
        "valuation_tightening_note": "17-C-17：高階滑軌 hard 從 80 收斂至 70。",
    },
    "AI_CCL_HIGH_VISIBILITY": {
        **CALIBRATION_DEFAULTS["AI_CCL_HIGH_VISIBILITY"],
        "base_pe": 34.0, "floor_pe": 20.0, "soft_ceiling_pe": 52.0, "hard_ceiling_pe": 65.0,
        "valuation_tightening_note": "17-C-17：AI CCL hard 從 80 收斂至 65。",
    },
    "MEMORY_IP_AI": {
        **CALIBRATION_DEFAULTS["MEMORY_IP_AI"],
        "base_pe": 30.0, "floor_pe": 16.0, "soft_ceiling_pe": 48.0, "hard_ceiling_pe": 60.0,
        "valuation_tightening_note": "17-C-17：Memory IP/AI hard 從 75 收斂至 60。",
    },
    "AI_SERVER_PCB_HIGH_VISIBILITY": {
        **CALIBRATION_DEFAULTS["AI_SERVER_PCB_HIGH_VISIBILITY"],
        "base_pe": 32.0, "floor_pe": 18.0, "soft_ceiling_pe": 48.0, "hard_ceiling_pe": 62.0,
        "valuation_tightening_note": "17-C-17：AI Server PCB hard 從 70 收斂至 62。",
    },
    "HIGH_SPEED_CONNECTOR_CORE": {
        **CALIBRATION_DEFAULTS["HIGH_SPEED_CONNECTOR_CORE"],
        "base_pe": 32.0, "floor_pe": 18.0, "soft_ceiling_pe": 48.0, "hard_ceiling_pe": 62.0,
        "valuation_tightening_note": "17-C-17：高速連接器 hard 從 70 收斂至 62。",
    },
    "SEMIMAT_ADVANCED_CONSUMABLES": {
        **CALIBRATION_DEFAULTS["SEMIMAT_ADVANCED_CONSUMABLES"],
        "base_pe": 32.0, "floor_pe": 18.0, "soft_ceiling_pe": 48.0, "hard_ceiling_pe": 60.0,
        "valuation_tightening_note": "17-C-17：先進耗材 hard 從 70 收斂至 60。",
    },
    "POWER_MANAGEMENT_IC_DESIGN": {
        **CALIBRATION_DEFAULTS["POWER_MANAGEMENT_IC_DESIGN"],
        "base_pe": 24.0, "floor_pe": 14.0, "soft_ceiling_pe": 36.0, "hard_ceiling_pe": 48.0,
        "valuation_tightening_note": "17-C-17：PMIC/類比 IC hard 從 58 收斂至 48。",
    },
    "OSAT_AI_HPC_TESTING": {
        **CALIBRATION_DEFAULTS["OSAT_AI_HPC_TESTING"],
        "base_pe": 26.0, "floor_pe": 14.0, "soft_ceiling_pe": 40.0, "hard_ceiling_pe": 52.0,
        "valuation_tightening_note": "17-C-17：AI/HPC 封測 hard 從 58 收斂至 52。",
    },
    "AI_DATACENTER_SWITCH": {
        **CALIBRATION_DEFAULTS["AI_DATACENTER_SWITCH"],
        "base_pe": 34.0, "floor_pe": 18.0, "soft_ceiling_pe": 52.0, "hard_ceiling_pe": 68.0,
        "valuation_tightening_note": "17-C-17：AI Data Center Switch hard 從 75 收斂至 68。",
    },
})

# ===== 第 17-C-20：使用者收集 FY2026E / 目標價倍率校準 =====
# 依 tw_stock_90_category_tasks_T86_T90_done.xlsx 中已完成且具 FY EPS / 目標價樣本校準。
# 原則：base 不直接追現價；soft/hard 才容納法人平均目標價與市場 FY2/極限先行定價。
CALIBRATION_DEFAULTS.update({
    "ABF_SUBSTRATE": {
        **CALIBRATION_DEFAULTS["ABF_SUBSTRATE"],
        "base_pe": 24.0, "floor_pe": 12.0, "soft_ceiling_pe": 55.0, "hard_ceiling_pe": 82.0,
        "valuation_tightening_note": "17-C-20：3037/3189/8046 樣本顯示法人目標與現價多落在 FY2 soft/hard；base 維持保守，soft/hard 上修至 55/82。",
    },
    "PROBE_AI_ASIC": {
        **CALIBRATION_DEFAULTS["PROBE_AI_ASIC"],
        "base_pe": 50.0, "floor_pe": 28.0, "soft_ceiling_pe": 85.0, "hard_ceiling_pe": 115.0,
        "valuation_tightening_note": "17-C-20：6223/6510/6515 FactSet 樣本顯示探針卡現價與目標價已高於舊 hard，soft/hard 上修但仍保留極限風控。",
    },
    "SEMICAP_ADV_PACKAGING_CORE": {
        **CALIBRATION_DEFAULTS["SEMICAP_ADV_PACKAGING_CORE"],
        "base_pe": 38.0, "floor_pe": 22.0, "soft_ceiling_pe": 60.0, "hard_ceiling_pe": 82.0,
        "valuation_tightening_note": "17-C-20：先進封裝設備樣本顯示 CoWoS/濕製程設備可容納較高 soft/hard；base 僅小幅上修。",
    },
    "THERMAL_LIQUID_CORE": {
        **CALIBRATION_DEFAULTS["THERMAL_LIQUID_CORE"],
        "base_pe": 40.0, "floor_pe": 22.0, "soft_ceiling_pe": 60.0, "hard_ceiling_pe": 78.0,
        "valuation_tightening_note": "17-C-20：3017/3653/8996 樣本顯示液冷核心法人目標與市場定價高於舊 soft，base 小幅上修、hard 回補至 78。",
    },
    "TEST_AUTOMATION_EQUIPMENT": {
        **CALIBRATION_DEFAULTS["TEST_AUTOMATION_EQUIPMENT"],
        "base_pe": 34.0, "floor_pe": 20.0, "soft_ceiling_pe": 55.0, "hard_ceiling_pe": 65.0,
        "valuation_tightening_note": "17-C-20：2360/3563/5443/7769 樣本支持測試/AOI設備 soft 上修；單一來源與舊目標價仍不拉高 hard 過度。",
    },
    "INDUSTRIAL_AUTOMATION_CORE": {
        **CALIBRATION_DEFAULTS["INDUSTRIAL_AUTOMATION_CORE"],
        "base_pe": 24.0, "floor_pe": 16.0, "soft_ceiling_pe": 40.0, "hard_ceiling_pe": 55.0,
        "valuation_tightening_note": "17-C-20：1590/2049 高品質樣本支持工業自動化 base/soft 小幅上修；低品質高倍數樣本只反映 hard 邊界。",
    },
    "OSAT_AI_HPC_TESTING": {
        **CALIBRATION_DEFAULTS["OSAT_AI_HPC_TESTING"],
        "base_pe": 30.0, "floor_pe": 14.0, "soft_ceiling_pe": 40.0, "hard_ceiling_pe": 52.0,
        "valuation_tightening_note": "17-C-20：2449/3264/3711 樣本顯示 FY2026E 法人目標約 30-38x，base 上修至 30，soft/hard 維持。",
    },
    "DATACENTER_POWER_LEADER": {
        **CALIBRATION_DEFAULTS["DATACENTER_POWER_LEADER"],
        "base_pe": 36.0, "floor_pe": 20.0, "soft_ceiling_pe": 55.0, "hard_ceiling_pe": 70.0,
        "valuation_tightening_note": "17-C-20：2301/2308 樣本支持資料中心電源龍頭 base 小幅上修，soft/hard 維持 AI 主鏈邊界。",
    },
    "PLATFORM_IC_LEADER": {
        **CALIBRATION_DEFAULTS["PLATFORM_IC_LEADER"],
        "base_pe": 30.0, "floor_pe": 18.0, "soft_ceiling_pe": 45.0, "hard_ceiling_pe": 60.0,
        "valuation_tightening_note": "17-C-20：2454/2379 樣本顯示平台型 IC 現價可高於舊 soft；base/soft/hard 小幅回補。",
    },
    "AI_CCL_HIGH_VISIBILITY": {
        **CALIBRATION_DEFAULTS["AI_CCL_HIGH_VISIBILITY"],
        "base_pe": 36.0, "floor_pe": 20.0, "soft_ceiling_pe": 55.0, "hard_ceiling_pe": 70.0,
        "valuation_tightening_note": "17-C-20：2383/6274 樣本支持 AI CCL hard 回補至 70；仍保留材料週期與 P/B 防呆。",
    },
    "FOUNDRY_MATURE": {
        **CALIBRATION_DEFAULTS["FOUNDRY_MATURE"],
        "base_pe": 14.0, "floor_pe": 8.0, "soft_ceiling_pe": 22.0, "hard_ceiling_pe": 30.0,
        "valuation_tightening_note": "17-C-20：2303/5347/6770 法人目標隱含 P/E 高於舊上限，但成熟製程不追現價，僅提高 soft/hard 週期邊界。",
    },
    "FINANCIAL_BANK_HOLDCO_QUALITY": {
        **CALIBRATION_DEFAULTS["FINANCIAL_BANK_HOLDCO_QUALITY"],
        "base_pe": 14.0, "floor_pe": 9.0, "soft_ceiling_pe": 18.0, "hard_ceiling_pe": 24.0,
        "valuation_tightening_note": "17-C-20：2884/2886/2891/2892 FY2026E 樣本顯示銀行型金控合理區間約 14-18x，base 小幅上修。",
    },
    "AI_SERVER_ODM": {
        **CALIBRATION_DEFAULTS["AI_SERVER_ODM"],
        "base_pe": 20.0, "floor_pe": 12.0, "soft_ceiling_pe": 30.0, "hard_ceiling_pe": 38.0,
        "valuation_tightening_note": "17-C-20：3706/6669 樣本顯示 AI ODM 低毛利平台不應套過高 P/E，base/soft/hard 下修。",
    },
    "AI_SERVER_BOARD_SYSTEM": {
        **CALIBRATION_DEFAULTS["AI_SERVER_BOARD_SYSTEM"],
        "base_pe": 22.0, "floor_pe": 14.0, "soft_ceiling_pe": 32.0, "hard_ceiling_pe": 40.0,
        "valuation_tightening_note": "17-C-20：2376/2377 樣本顯示主板/系統品牌 FY2026E 目標價倍數低於舊模型，整體收斂。",
    },
    "THERMAL_AI_COMPONENTS": {
        **CALIBRATION_DEFAULTS["THERMAL_AI_COMPONENTS"],
        "base_pe": 24.0, "floor_pe": 14.0, "soft_ceiling_pe": 36.0, "hard_ceiling_pe": 48.0,
        "valuation_tightening_note": "17-C-20：一般 AI 散熱零組件樣本低於液冷核心，避免與 THERMAL_LIQUID_CORE 共用高倍率。",
    },
    "HIGH_SPEED_INTERFACE_IC": {
        **CALIBRATION_DEFAULTS["HIGH_SPEED_INTERFACE_IC"],
        "base_pe": 22.0, "floor_pe": 14.0, "soft_ceiling_pe": 34.0, "hard_ceiling_pe": 44.0,
        "valuation_tightening_note": "17-C-20：3014/4966/6756 樣本顯示高速介面 IC FY2026E 合理倍數低於舊模型，收斂 soft/hard。",
    },
    "OPTICS_LENS_LEADER": {
        **CALIBRATION_DEFAULTS["OPTICS_LENS_LEADER"],
        "base_pe": 22.0, "floor_pe": 14.0, "soft_ceiling_pe": 32.0, "hard_ceiling_pe": 40.0,
        "valuation_tightening_note": "17-C-20：3008/3406 樣本顯示傳統光學鏡頭 FY2026E 目標倍數偏低；CPO/AI 光學需另走題材重評價，不直接拉高 base。",
    },
    "PHARMA_CDMO_PROFIT": {
        **CALIBRATION_DEFAULTS["PHARMA_CDMO_PROFIT"],
        "base_pe": 20.0, "floor_pe": 12.0, "soft_ceiling_pe": 30.0, "hard_ceiling_pe": 38.0,
        "valuation_tightening_note": "17-C-20：1795/6472 樣本顯示獲利型藥廠/CDMO 倍率低於舊模型，收斂為防禦成長區間。",
    },
    "AI_SERVER_CHASSIS_CORE": {
        **CALIBRATION_DEFAULTS["AI_SERVER_CHASSIS_CORE"],
        "base_pe": 26.0, "floor_pe": 16.0, "soft_ceiling_pe": 38.0, "hard_ceiling_pe": 50.0,
        "valuation_tightening_note": "17-C-20：3013/3693/8210 樣本顯示機殼類 AI 主鏈低於舊高倍率，收斂但保留訂單落地 soft。",
    },
    "FAB_FACILITY_MATERIALS": {
        **CALIBRATION_DEFAULTS["FAB_FACILITY_MATERIALS"],
        "base_pe": 22.0, "floor_pe": 14.0, "soft_ceiling_pe": 32.0, "hard_ceiling_pe": 40.0,
        "valuation_tightening_note": "17-C-20：2404/6139/6196 樣本顯示廠務/材料 FY2026E 倍率低於舊模型，收斂 capex 週期邊界。",
    },
    "SEMICAP_GENERAL_EQUIPMENT": {
        **CALIBRATION_DEFAULTS["SEMICAP_GENERAL_EQUIPMENT"],
        "base_pe": 24.0, "floor_pe": 14.0, "soft_ceiling_pe": 38.0, "hard_ceiling_pe": 50.0,
        "valuation_tightening_note": "17-C-20：一般半導體設備樣本目標倍數低於先進封裝核心，與 SEMICAP_ADV_PACKAGING_CORE 拉開。",
    },
    "POWER_SUPPLY_STANDARD": {
        **CALIBRATION_DEFAULTS["POWER_SUPPLY_STANDARD"],
        "base_pe": 16.0, "floor_pe": 10.0, "soft_ceiling_pe": 26.0, "hard_ceiling_pe": 34.0,
        "valuation_tightening_note": "17-C-20：一般電源樣本顯示不應套資料中心電源龍頭倍率，收斂 base/soft/hard。",
    },
    "NETWORK_EQUIPMENT_STANDARD": {
        **CALIBRATION_DEFAULTS["NETWORK_EQUIPMENT_STANDARD"],
        "base_pe": 18.0, "floor_pe": 10.0, "soft_ceiling_pe": 28.0, "hard_ceiling_pe": 36.0,
        "valuation_tightening_note": "17-C-20：一般網通樣本低於 AI data center switch，收斂一般網通倍率。",
    },
    "PC_BRAND_AI_PC": {
        **CALIBRATION_DEFAULTS["PC_BRAND_AI_PC"],
        "base_pe": 16.0, "floor_pe": 10.0, "soft_ceiling_pe": 24.0, "hard_ceiling_pe": 32.0,
        "valuation_tightening_note": "17-C-20：2353/2357 樣本顯示 PC 品牌 AI PC 題材不應套高 AI 伺服器倍率。",
    },
})
