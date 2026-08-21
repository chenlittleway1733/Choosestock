import json
import datetime
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path
from zipfile import ZipFile

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


if "plotly" not in sys.modules:
    sys.modules["plotly"] = types.ModuleType("plotly")
    sys.modules["plotly.graph_objects"] = types.ModuleType("plotly.graph_objects")
    plotly_subplots = types.ModuleType("plotly.subplots")
    plotly_subplots.make_subplots = lambda *args, **kwargs: None
    sys.modules["plotly.subplots"] = plotly_subplots

if "streamlit" not in sys.modules:
    def _identity_decorator(*dargs, **dkwargs):
        if dargs and callable(dargs[0]) and len(dargs) == 1 and not dkwargs:
            return dargs[0]
        return lambda fn: fn

    streamlit_stub = types.ModuleType("streamlit")
    streamlit_stub.session_state = _SessionState()
    streamlit_stub.cache_data = _identity_decorator
    sys.modules["streamlit"] = streamlit_stub
    sys.modules["streamlit.components"] = types.ModuleType("streamlit.components")
    sys.modules["streamlit.components.v1"] = types.ModuleType("streamlit.components.v1")

if "requests" not in sys.modules:
    requests_stub = types.ModuleType("requests")
    requests_stub.get = lambda *args, **kwargs: types.SimpleNamespace(status_code=599, json=lambda: {})
    requests_stub.post = lambda *args, **kwargs: types.SimpleNamespace(status_code=599, json=lambda: {})
    sys.modules["requests"] = requests_stub

if "yfinance" not in sys.modules:
    sys.modules["yfinance"] = types.ModuleType("yfinance")

if "google" not in sys.modules:
    google_stub = types.ModuleType("google")
    genai_stub = types.ModuleType("google.genai")
    genai_types_stub = types.ModuleType("google.genai.types")
    genai_types_stub.Tool = lambda *args, **kwargs: {"tool": kwargs}
    genai_types_stub.GoogleSearch = lambda *args, **kwargs: {"google_search": kwargs}
    genai_stub.types = genai_types_stub
    google_stub.genai = genai_stub
    sys.modules["google"] = google_stub
    sys.modules["google.genai"] = genai_stub
    sys.modules["google.genai.types"] = genai_types_stub


import stock_mapping
import industry_taxonomy
import services
import ui_context.financial_context as financial_context
from app_version import APP_DISPLAY_NAME, APP_DISPLAY_VERSION, APP_PAGE_TITLE
from ai_services.financial_filler import postprocess_financial_ai_payload
from ai_services.financial_schema import normalize_ai_source_metadata
from dynamic_cap_model import (
    CALIBRATION_DEFAULTS,
    build_m10_margin_benchmark_summary,
    calculate_dynamic_cap_v2,
    get_dynamic_cap_version_info,
    quality_factor_relative,
)
from industry_model import get_industry_valuation_profile
from model_data_loader import (
    get_dynamic_cap_v18_2_by_stock_id,
    build_margin_benchmark_profile,
    get_stock_model_margin_by_stock_id,
    validate_dynamic_cap_v18_2_data,
    validate_m10_model_data,
)
from services import (
    build_margin_credit_summary,
    merge_mops_latest_revenue,
    parse_mops_monthly_revenue_csv,
    parse_mops_monthly_revenue_html,
    reconcile_price_history_with_reference,
)
from ui_context.prompt_context import (
    build_essential_version_prompt,
    prompt_chip_panel_summary,
    prompt_dynamic_cap_core,
    prompt_etf_panel_summary,
    prompt_eps_adoption_sync_summary,
    prompt_m10_margin_benchmark_summary,
    prompt_model_gap_trigger_conditions,
    prompt_model_library_feedback_request,
    prompt_peg_valuation_layers,
    prompt_technical_suffix,
)
from ui_context.multiple_context import build_multiple_context
from validators.candidate_review import build_financial_candidate_data as modular_build_financial_candidate_data
from validators.financial_validation import validate_ai_financial_json as modular_validate_ai_financial_json
from utils import (
    build_field_source_priority_report,
    build_candidate_data_report,
    build_financial_candidate_data,
    build_financial_quality_report,
    build_forward_eps_calendar_notice,
    build_ttm_eps_adoption,
    build_forward_eps_tiered_valuation_report,
    build_divergence_warnings,
    build_divergence_warning_report,
    build_final_operation_signal,
    calculate_future_evidence_score,
    calc_monthly_revenue_growth,
    detect_forward_eps_period_mismatch,
    format_field_source_priority_for_prompt,
    infer_pricing_horizon,
    summarize_data_quality_levels,
    apply_financial_candidate_reviews,
    load_financial_candidate_review_cache,
    normalize_candidate_review_status,
    source_priority_summary_for_field,
    update_financial_candidate_review,
    validate_ai_financial_json,
    validate_and_correct_financial_metrics,
)


def _parse_stocklist():
    rows = []
    current_category = "未分類"
    for line_no, raw in enumerate((ROOT / "stocklist.txt").read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if "," not in line:
            current_category = line
            continue
        code, name = [x.strip() for x in line.split(",", 1)]
        rows.append({"code": code, "name": name, "category": current_category, "line": line_no})
    return rows


class ApplicationBrandAndNavigationTests(unittest.TestCase):
    def test_display_name_is_way_investment_war_room_25(self):
        self.assertEqual(APP_DISPLAY_NAME, "WAY投資戰情室")
        self.assertEqual(APP_DISPLAY_VERSION, "2.5版")
        self.assertEqual(APP_PAGE_TITLE, "WAY投資戰情室-2.5版")

        visible_files = [ROOT / "app.py", ROOT / "ui_main.py", ROOT / "README.md"]
        visible_text = "\n".join(path.read_text(encoding="utf-8") for path in visible_files)
        self.assertNotIn("WAY AI 投資戰情室", visible_text)
        self.assertNotIn("2.4 Slim R6", visible_text)

    def test_quick_navigation_bar_and_anchors_are_removed(self):
        main_source = (ROOT / "ui_main.py").read_text(encoding="utf-8")
        self.assertNotIn("快速跳轉", main_source)
        self.assertNotIn("way-top-nav", main_source)
        self.assertNotIn("_section_anchor", main_source)

    def test_financial_forecast_heading_is_renamed(self):
        source = (ROOT / "ui_panels" / "financials.py").read_text(encoding="utf-8")
        self.assertIn("股票預估價", source)
        self.assertNotIn("財務基本面與獲利基準微調", source)

    def test_ui_main_imports_with_previous_panel_modules(self):
        """Regression for Streamlit partial-deploy ImportError at ui_main.py line 9."""
        import importlib.util
        import ui_context.prompt_context as real_prompt
        import ui_panels.financials as real_financials

        old_financials = types.ModuleType("ui_panels.financials")
        for name in (
            "render_ai_financial_audit_control", "render_anomaly_detection_panel",
            "render_defense_health_cards", "render_eps_breakdown_panel",
            "render_final_signal_panel", "render_financial_metric_cards",
            "render_financial_quality_report_panel", "render_target_price_panel",
            "render_valuation_detail_panel",
        ):
            setattr(old_financials, name, getattr(real_financials, name))

        old_prompt = types.ModuleType("ui_context.prompt_context")
        for name in (
            "build_prompt_target_context", "prompt_ai_source_summary", "prompt_dynamic_cap_core",
            "prompt_df", "prompt_buy_decision_gap_risk_conditions", "prompt_defense_panel_summary",
            "prompt_etf_panel_summary", "prompt_eps_adoption_sync_summary",
            "prompt_field_source_priority_summary", "prompt_forward_eps_tier_core",
            "prompt_chip_panel_summary", "prompt_model_gap_trigger_conditions",
            "prompt_model_library_feedback_request", "prompt_panel_sync_audit",
            "prompt_peg_valuation_layers", "prompt_quality_summary", "prompt_snapshot_audit_core",
            "prompt_snapshot_audit_summary", "prompt_target_price_panel_summary",
            "prompt_technical_suffix", "prompt_warnings",
        ):
            setattr(old_prompt, name, getattr(real_prompt, name))

        saved_financials = sys.modules.get("ui_panels.financials")
        saved_prompt = sys.modules.get("ui_context.prompt_context")
        try:
            sys.modules["ui_panels.financials"] = old_financials
            sys.modules["ui_context.prompt_context"] = old_prompt
            spec = importlib.util.spec_from_file_location("ui_main_compat_probe", ROOT / "ui_main.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            if saved_financials is not None:
                sys.modules["ui_panels.financials"] = saved_financials
            else:
                sys.modules.pop("ui_panels.financials", None)
            if saved_prompt is not None:
                sys.modules["ui_context.prompt_context"] = saved_prompt
            else:
                sys.modules.pop("ui_context.prompt_context", None)

        self.assertTrue(callable(module.build_eps_price_calculation_rows))
        self.assertTrue(callable(module.build_essential_version_prompt))
        self.assertEqual(len(module._DEPLOYMENT_COMPAT_WARNINGS), 2)

    def test_deployment_zip_uses_streamlit_repository_root_layout(self):
        from tools.build_clean_package import build_package

        with tempfile.TemporaryDirectory() as temp_dir:
            package_path = Path(temp_dir) / "WAY_Stock_2.5.zip"
            build_package(package_path)
            with ZipFile(package_path) as archive:
                names = set(archive.namelist())

        self.assertIn("app.py", names)
        self.assertIn("ui_main.py", names)
        self.assertIn("ui_panels/financials.py", names)
        self.assertIn("ui_context/prompt_context.py", names)
        self.assertFalse(any(name.startswith("way_stock/") for name in names))


class StockMappingConsistencyTests(unittest.TestCase):
    def test_stocklist_mapping_and_taxonomy_are_in_sync(self):
        rows = _parse_stocklist()
        stocklist_codes = [r["code"] for r in rows]
        mapping_codes = set(stock_mapping.STOCK_MAPPING)
        taxonomy_codes = set(industry_taxonomy.INDUSTRY_TAXONOMY)

        self.assertGreater(len(rows), 0)
        self.assertEqual(len(stocklist_codes), len(set(stocklist_codes)), "stocklist.txt has duplicate stock codes")
        self.assertEqual(set(stocklist_codes), mapping_codes, "stocklist.txt and stock_mapping.py stock codes differ")

        for row in rows:
            self.assertRegex(row["code"], r"^\d{4}$", f"invalid stock code at line {row['line']}")
            self.assertTrue(row["name"], f"missing stock name at line {row['line']}")

        for code, entry in stock_mapping.STOCK_MAPPING.items():
            primary = entry.get("primary_taxon")
            self.assertIn(primary, taxonomy_codes, f"{code} primary_taxon not found in taxonomy: {primary}")

            total_weight = 0.0
            for hybrid in entry.get("hybrid_taxons") or []:
                taxon = hybrid.get("taxon")
                weight = float(hybrid.get("weight", 0) or 0)
                self.assertIn(taxon, taxonomy_codes, f"{code} hybrid taxon not found in taxonomy: {taxon}")
                self.assertGreaterEqual(weight, 0.0, f"{code} hybrid weight below zero")
                self.assertLessEqual(weight, 0.50, f"{code} hybrid weight exceeds 50%")
                total_weight += weight
            self.assertLessEqual(total_weight, 0.50 + 1e-9, f"{code} total hybrid weight exceeds 50%")

    def test_7828_innovation_service_uses_semiconductor_test_model(self):
        rows = {r["code"]: r for r in _parse_stocklist()}
        self.assertIn("7828", rows)
        self.assertEqual(rows["7828"]["name"], "創新服務")
        self.assertIn("測試 / AOI / 自動化檢測設備", rows["7828"]["category"])

        profile = get_industry_valuation_profile("7828", "創新服務")
        self.assertEqual(profile["primary_taxon"], "TEST_AUTOMATION_EQUIPMENT")
        self.assertEqual(profile["model_label"], "測試 / AOI / 自動化檢測設備")
        self.assertEqual(profile["classification_source"], "stock_mapping.py")
        self.assertEqual(profile["m10_margin_status"], "stock_not_valuation_ready")

    def test_2454_cloud_ai_asic_re_rating_keeps_platform_primary_and_hard_cap_locked(self):
        profile = get_industry_valuation_profile("2454", "聯發科")

        self.assertEqual(profile["primary_taxon"], "PLATFORM_IC_LEADER")
        self.assertEqual(profile["re_rating_status"], "CLOUD_AI_ASIC_RE_RATING")
        self.assertIn("IC_DESIGN_ASIC_HIGH_VISIBILITY 35%（hard 0%）", profile["hybrid_taxons_text"])
        self.assertTrue(profile["disable_market_hard_overlay"])
        self.assertIn("FY2_SOFT_PRICED", profile["pricing_horizon_policy"])
        self.assertAlmostEqual(profile["hybrid_cap_display"]["mixed_hard_ceiling_pe"], 60.0)
        self.assertGreater(profile["hybrid_cap_display"]["mixed_soft_ceiling_pe"], 45.0)

        cap_pack = calculate_dynamic_cap_v2(
            stock_id="2454",
            stock_name="聯發科",
            current_price=5000,
            industry_profile=profile,
            ttm_eps=100,
            system_forward_eps=100,
            revenue_yoy=0.80,
            gross_margin=0.50,
            operating_margin=0.25,
            roe=0.25,
            divergence_warnings=[],
            dq_warnings=[],
        )
        self.assertEqual(cap_pack["model_version"], "Dynamic Cap 2.0 calibration 18.2")
        self.assertAlmostEqual(cap_pack["base_multiple"], 31.07)
        self.assertAlmostEqual(cap_pack["optimistic_cap"], 36.51)
        self.assertAlmostEqual(cap_pack["structural_hard_ceiling_cap"], 38.38)
        self.assertAlmostEqual(cap_pack["hard_ceiling_cap"], 38.38)
        self.assertFalse(cap_pack["market_condition_hard_adjustment"]["adjusted"])
        self.assertIn("關閉市場 hard overlay", cap_pack["market_condition_hard_adjustment"]["reason"])
        self.assertTrue(cap_pack["v18_2_special_case_review"])

    def test_taxonomy_pe_caps_are_ordered_when_present(self):
        for taxon, profile in industry_taxonomy.INDUSTRY_TAXONOMY.items():
            base = profile.get("base_pe")
            floor = profile.get("floor_pe")
            soft = profile.get("soft_ceiling_pe")
            hard = profile.get("hard_ceiling_pe")
            if base is None or floor is None or soft is None or hard is None:
                continue
            self.assertLessEqual(float(floor), float(base), f"{taxon} floor > base")
            self.assertLessEqual(float(base), float(soft), f"{taxon} base > soft")
            self.assertLessEqual(float(soft), float(hard), f"{taxon} soft > hard")

    def test_industry_profile_exposes_primary_taxon_for_prompt_context(self):
        profile = get_industry_valuation_profile("3017", "奇鋐", "科技業", "散熱")

        self.assertEqual(profile.get("primary_taxon"), "THERMAL_LIQUID_CORE")
        self.assertEqual(profile.get("model_key"), "THERMAL_LIQUID_CORE")
        self.assertEqual(profile.get("taxon_key"), "THERMAL_LIQUID_CORE")
        self.assertEqual(profile.get("model_build_version"), "18.2")


class DynamicCapV182RegistryTests(unittest.TestCase):
    def test_registry_counts_and_sample_caps_match_supplied_pdf(self):
        validation = validate_dynamic_cap_v18_2_data()
        self.assertTrue(validation["ok"], validation["issues"])
        self.assertEqual(validation["stock_count"], 277)
        self.assertEqual(validation["caps_available_count"], 249)
        self.assertEqual(validation["unavailable_or_not_applicable_count"], 28)
        self.assertEqual(validation["special_case_review_count"], 25)

        expected = {
            "2330": (24.82, 26.06, 27.37),
            "2368": (35.62, 39.61, 44.21),
            "8046": (70.41, 87.58, 94.42),
        }
        for stock_id, caps in expected.items():
            row = get_dynamic_cap_v18_2_by_stock_id(stock_id)
            self.assertIsNotNone(row)
            self.assertEqual(
                (row["company_base"], row["company_soft"], row["company_hard"]),
                caps,
            )
        self.assertEqual(get_dynamic_cap_v18_2_by_stock_id("9958")["eps_basis"], "ttm_only")
        self.assertEqual(get_dynamic_cap_v18_2_by_stock_id("2408")["eps_basis"], "not_applicable")
        self.assertEqual(get_dynamic_cap_v18_2_by_stock_id("2201")["eps_basis"], "insufficient")

    def test_stock_profile_and_engine_use_exact_caps_without_dynamic_overlay(self):
        profile = get_industry_valuation_profile("2330", "台積電")
        self.assertEqual(profile["model_build_version"], "18.2")
        self.assertEqual(profile["base_pe"], 24.82)
        self.assertEqual(profile["soft_ceiling_pe"], 26.06)
        self.assertEqual(profile["hard_ceiling_pe"], 27.37)
        self.assertTrue(profile["disable_market_hard_overlay"])

        pack = calculate_dynamic_cap_v2(
            stock_id="2330",
            stock_name="台積電",
            current_price=9999,
            industry_profile=profile,
            gross_margin=0.99,
            roe=0.99,
            revenue_yoy=3.0,
            ttm_eps=50,
            system_forward_eps=60,
        )
        self.assertEqual(pack["base_multiple"], 24.82)
        self.assertEqual(pack["formula_cap"], 24.82)
        self.assertEqual(pack["optimistic_cap"], 26.06)
        self.assertEqual(pack["hard_ceiling_cap"], 27.37)
        self.assertFalse(pack["market_condition_hard_adjustment"]["adjusted"])
        self.assertEqual(pack["growth_premium"]["factor"], 1.0)
        self.assertTrue(pack["hit_hard_ceiling"])

    def test_ttm_only_caps_suppress_all_forward_year_prices(self):
        profile = get_industry_valuation_profile("9958", "世紀鋼")
        pack = calculate_dynamic_cap_v2(
            stock_id="9958",
            stock_name="世紀鋼",
            current_price=120,
            industry_profile=profile,
            ttm_eps=5,
            system_forward_eps=12,
            consensus_forward_eps=14,
        )
        self.assertEqual(pack["cap_eps_basis"], "ttm_only")
        self.assertEqual(pack["market_implied_eps_basis"], "TTM EPS")

        context = build_multiple_context(
            target_pe_cap=pack["final_cap"],
            suggested_cap=pack["final_cap"],
            dynamic_cap_pack=pack,
            industry_profile=profile,
            eff_f_eps=12,
            has_ai_fin_fetch=True,
            ai_f_eps_calc=14,
            ai_forward_eps_fy1=14,
            ai_forward_eps_fy2=16,
            ai_forward_eps_fy3=18,
            cap_adopted_forward_eps=14,
            eff_t_eps=5,
            ai_latest_month_eps=2,
            ai_latest_quarter_eps=4,
        )
        self.assertEqual(context["formula_eps_for_calc"], 5)
        self.assertEqual(context["current_eps_source"], "TTM EPS")
        self.assertAlmostEqual(context["sys_target_price_est"], 5 * 8.88)
        self.assertIsNone(context["ai_target_price_est"])
        self.assertIsNone(context["run_rate_reference_target_price"])
        for key in (
            "fy1_formula_target_price", "fy2_formula_target_price", "fy3_formula_target_price",
            "fy1_base_target_price", "fy1_soft_target_price", "fy1_hard_target_price",
            "fy2_base_target_price", "fy2_soft_target_price", "fy2_hard_target_price",
            "fy3_base_target_price", "fy3_soft_target_price", "fy3_hard_target_price",
            "fy1_manual_target_price",
        ):
            self.assertIsNone(context[key], key)

        tiered = build_forward_eps_tiered_valuation_report(
            current_price=120,
            ttm_eps=5,
            fy1_eps=14,
            fy2_eps=16,
            fy3_eps=18,
            base_cap=8.88,
            soft_ceiling=10.52,
            hard_ceiling=55.28,
            eps_basis="ttm_only",
        )
        self.assertEqual(tiered["summary"]["ttm_eps"], 5)
        self.assertIsNone(tiered["summary"]["fy1_eps"])
        self.assertIsNone(tiered["summary"]["fy2_eps"])
        self.assertIsNone(tiered["summary"]["fy3_eps"])
        self.assertIn("僅能搭配 TTM EPS", tiered["summary"]["fy_definition"])

    def test_not_applicable_and_insufficient_rows_never_fall_back(self):
        for stock_id, name, basis in [("2408", "南亞科", "not_applicable"), ("2201", "裕隆", "insufficient")]:
            profile = get_industry_valuation_profile(stock_id, name)
            pack = calculate_dynamic_cap_v2(
                stock_id=stock_id,
                stock_name=name,
                current_price=100,
                industry_profile=profile,
                ttm_eps=10,
                system_forward_eps=12,
            )
            self.assertFalse(pack["available"])
            self.assertFalse(pack["v18_2_caps_available"])
            self.assertEqual(pack["cap_eps_basis"], basis)
            self.assertIsNone(pack["base_multiple"])
            self.assertIsNone(pack["hard_ceiling_cap"])
            self.assertIn("不回退 v18.1", pack["explanation"])


class ModelVersionTableTests(unittest.TestCase):
    def test_taxonomy_and_dynamic_cap_version_tables_are_current_and_ordered(self):
        tax_info = industry_taxonomy.get_taxonomy_version_info()
        cap_info = get_dynamic_cap_version_info()
        expected_taxonomy_stages = [
            "17-B-2",
            "17-C",
            "17-C-4",
            "17-C-6",
            "17-C-7B",
            "17-C-10",
            "17-C-11",
            "17-C-12",
            "17-C-13",
            "17-C-14",
            "17-C-15",
            "17-C-16",
            "17-C-17",
            "17-C-18",
            "17-C-19",
            "17-C-20",
            "17-C-21",
            "17-C-22",
        ]
        expected_dynamic_cap_stages = [
            "17-C-4",
            "17-C-5",
            "17-C-6",
            "17-C-7A",
            "17-C-9",
            "17-C-10",
            "17-C-11",
            "17-C-11B",
            "17-C-12",
            "17-C-13",
            "17-C-14",
            "17-C-15",
            "17-C-16",
            "17-C-17",
            "17-C-18",
            "17-C-19",
            "17-C-20",
            "17-C-21",
            "17-C-22",
            "17-C-23",
            "18.2",
        ]

        for info in (tax_info,):
            table = info["version_table"]
            orders = [row["order"] for row in table]
            self.assertGreaterEqual(len(table), 5)
            self.assertEqual(info["version"], "17-C-22")
            self.assertEqual(info["latest_stage"], "17-C-22")
            self.assertEqual(info["build_date"], "2026-06-20")
            self.assertEqual(table[-1]["stage"], info["latest_stage"])
            self.assertEqual(orders, sorted(orders))

        table = cap_info["version_table"]
        orders = [row["order"] for row in table]
        self.assertGreaterEqual(len(table), 5)
        self.assertEqual(cap_info["version"], "18.2")
        self.assertEqual(cap_info["latest_stage"], "18.2")
        self.assertEqual(cap_info["build_date"], "2026-08-20")
        self.assertEqual(table[-1]["stage"], cap_info["latest_stage"])
        self.assertEqual(orders, sorted(orders))

        self.assertEqual([row["stage"] for row in tax_info["version_table"]], expected_taxonomy_stages)
        self.assertEqual([row["stage"] for row in cap_info["version_table"]], expected_dynamic_cap_stages)
        self.assertEqual(cap_info["engine_version"], "Dynamic Cap 2.0 calibration 18.2")

    def test_multiplier_tightening_stage_keeps_taxonomy_and_dynamic_cap_in_sync(self):
        expected_caps = {
            "IC_DESIGN_IP_ROYALTY": (45.0, 68.0, 82.0),
            "IC_DESIGN_ASIC_HIGH_VISIBILITY": (45.0, 65.0, 80.0),
            "OPTICAL_COMM_CPO_HIGH_VISIBILITY": (42.0, 65.0, 82.0),
            "IC_DESIGN_SERVER_BMC_HIGH_VISIBILITY": (40.0, 62.0, 78.0),
            "SEMICAP_ADV_PACKAGING_CORE": (38.0, 60.0, 82.0),
            "THERMAL_LIQUID_CORE": (40.0, 60.0, 78.0),
            "TEST_AUTOMATION_EQUIPMENT": (34.0, 55.0, 65.0),
            "INDUSTRIAL_AUTOMATION_CORE": (24.0, 40.0, 55.0),
            "SERVER_RAIL_HIGH_VISIBILITY": (36.0, 55.0, 70.0),
            "AI_CCL_HIGH_VISIBILITY": (36.0, 55.0, 70.0),
            "MEMORY_IP_AI": (30.0, 48.0, 60.0),
            "AI_SERVER_PCB_HIGH_VISIBILITY": (32.0, 48.0, 62.0),
            "HIGH_SPEED_CONNECTOR_CORE": (32.0, 48.0, 62.0),
            "SEMIMAT_ADVANCED_CONSUMABLES": (32.0, 48.0, 60.0),
            "POWER_MANAGEMENT_IC_DESIGN": (24.0, 36.0, 48.0),
            "OSAT_AI_HPC_TESTING": (30.0, 40.0, 52.0),
            "AI_DATACENTER_SWITCH": (34.0, 52.0, 68.0),
            "CONSUMER_TOURISM": (22.0, 32.0, 38.0),
            "ABF_SUBSTRATE": (24.0, 55.0, 82.0),
            "PROBE_AI_ASIC": (50.0, 85.0, 115.0),
            "AI_SERVER_ODM": (20.0, 30.0, 38.0),
            "AI_SERVER_BOARD_SYSTEM": (22.0, 32.0, 40.0),
        }
        user_fy2026_source = "17-C-20 使用者收集 FY2026E / 目標價倍率校準"
        expected_sources = {
            "SEMICAP_ADV_PACKAGING_CORE": user_fy2026_source,
            "THERMAL_LIQUID_CORE": user_fy2026_source,
            "TEST_AUTOMATION_EQUIPMENT": user_fy2026_source,
            "INDUSTRIAL_AUTOMATION_CORE": user_fy2026_source,
            "AI_CCL_HIGH_VISIBILITY": user_fy2026_source,
            "OSAT_AI_HPC_TESTING": user_fy2026_source,
            "ABF_SUBSTRATE": user_fy2026_source,
            "PROBE_AI_ASIC": user_fy2026_source,
            "AI_SERVER_ODM": user_fy2026_source,
            "AI_SERVER_BOARD_SYSTEM": user_fy2026_source,
        }

        for taxon, expected in expected_caps.items():
            tax_profile = industry_taxonomy.INDUSTRY_TAXONOMY[taxon]
            dyn_profile = CALIBRATION_DEFAULTS[taxon]
            tax_caps = (
                float(tax_profile["base_pe"]),
                float(tax_profile["soft_ceiling_pe"]),
                float(tax_profile["hard_ceiling_pe"]),
            )
            dyn_caps = (
                float(dyn_profile["base_pe"]),
                float(dyn_profile["soft_ceiling_pe"]),
                float(dyn_profile["hard_ceiling_pe"]),
            )
            self.assertEqual(tax_caps, expected, taxon)
            self.assertEqual(dyn_caps, expected, taxon)
            self.assertEqual(tax_profile.get("calibration_source"), expected_sources.get(taxon, "17-C-17 倍率寬鬆度收斂"), taxon)

        high_hard_taxons = {
            taxon
            for taxon, profile in industry_taxonomy.INDUSTRY_TAXONOMY.items()
            if profile.get("hard_ceiling_pe") is not None and float(profile["hard_ceiling_pe"]) > 82.0
        }
        high_hard_dyn_taxons = {
            taxon
            for taxon, profile in CALIBRATION_DEFAULTS.items()
            if profile.get("hard_ceiling_pe") is not None and float(profile["hard_ceiling_pe"]) > 82.0
        }
        self.assertEqual(high_hard_taxons, {"PROBE_AI_ASIC"})
        self.assertEqual(high_hard_dyn_taxons, {"PROBE_AI_ASIC"})


class M10ModelDataLoaderTests(unittest.TestCase):
    def test_m10_model_data_loader_validates_expected_counts(self):
        summary = validate_m10_model_data()

        self.assertTrue(summary["ok"], summary["issues"])
        self.assertEqual(summary["industry_category_count"], 90)
        self.assertEqual(summary["stock_model_count"], 276)
        self.assertEqual(summary["valuation_universe_count"], 157)
        self.assertEqual(summary["margin_quality_counts"], {"A": 37, "B": 35, "C": 15, "N/A": 3})

    def test_m10_stock_margin_profiles_apply_usage_guards(self):
        tsmc = build_margin_benchmark_profile("2330")
        bank = build_margin_benchmark_profile("2884")
        biotech_mismatch = build_margin_benchmark_profile("4128")

        self.assertTrue(tsmc["m10_margin_available"])
        self.assertEqual(tsmc["m10_task_id"], "T01")
        self.assertEqual(tsmc["base_gross_margin_pct"], 45)
        self.assertAlmostEqual(tsmc["base_gross_margin_ratio"], 0.45)
        self.assertEqual(tsmc["base_operating_margin_pct"], 35)
        self.assertTrue(tsmc["margin_model_applicable"])
        self.assertTrue(tsmc["margin_can_affect_valuation"])

        self.assertEqual(bank["margin_rule"], "margin_not_applicable")
        self.assertEqual(bank["margin_quality"], "N/A")
        self.assertFalse(bank["margin_model_applicable"])
        self.assertFalse(bank["margin_can_affect_valuation"])

        self.assertEqual(biotech_mismatch["margin_quality"], "C")
        self.assertEqual(biotech_mismatch["m10_data_quality_grade"], "C")
        self.assertEqual(biotech_mismatch["m10_margin_status"], "stock_not_valuation_ready")
        self.assertFalse(biotech_mismatch["margin_can_affect_valuation"])

    def test_industry_profile_attaches_m10_margin_without_replacing_taxon(self):
        profile = get_industry_valuation_profile("2330", "台積電", "科技業", "半導體")

        self.assertEqual(profile["primary_taxon"], "FOUNDRY_ADVANCED")
        self.assertEqual(profile["m10_task_id"], "T01")
        self.assertEqual(profile["m10_category_name"], "半導體｜晶圓代工 / HPC / 先進製程")
        self.assertEqual(profile["base_gross_margin_pct"], 45)
        self.assertEqual(profile["base_operating_margin_pct"], 35)
        self.assertEqual(profile["margin_quality"], "A")
        self.assertEqual(profile["margin_rule"], "high_operating_margin_cap")
        self.assertTrue(profile["margin_can_affect_valuation"])

    def test_m10_old_code_rows_are_available_but_not_valuation_uplift(self):
        old_code = get_stock_model_margin_by_stock_id("1701")
        margin = build_margin_benchmark_profile("1701")

        self.assertEqual(old_code["data_quality_grade"], "D")
        self.assertEqual(old_code["valuation_ready_flag"], "not_ready")
        self.assertEqual(margin["m10_margin_status"], "stock_not_valuation_ready")
        self.assertFalse(margin["margin_can_affect_valuation"])


class FieldSourcePriorityTests(unittest.TestCase):
    def test_price_history_cross_check_flags_large_source_divergence_without_replacing(self):
        dates = pd.to_datetime(["2026-06-17", "2026-06-18"])
        primary = pd.DataFrame({
            "Open": [960.0, 965.0],
            "High": [970.0, 975.0],
            "Low": [950.0, 960.0],
            "Close": [960.0, 968.0],
            "Volume": [1000, 1200],
        }, index=dates)
        reference = pd.DataFrame({
            "Open": [162.0, 164.0],
            "High": [166.0, 167.0],
            "Low": [160.0, 163.0],
            "Close": [163.0, 165.0],
            "Volume": [3000, 3500],
        }, index=dates)

        checked, note = reconcile_price_history_with_reference(
            primary,
            reference,
            stock_id="3037",
            primary_source="Yahoo Finance",
            reference_source="FinMind",
            divergence_threshold=0.35,
        )

        self.assertIs(checked, primary)
        self.assertEqual(float(checked["Close"].iloc[-1]), 968.0)
        self.assertIn("3037", note)
        self.assertIn("不自動覆蓋現價", note)

    def test_price_history_cross_check_keeps_close_sources(self):
        dates = pd.to_datetime(["2026-06-17", "2026-06-18"])
        primary = pd.DataFrame({"Close": [160.0, 168.0]}, index=dates)
        reference = pd.DataFrame({"Close": [159.0, 165.0]}, index=dates)

        checked, note = reconcile_price_history_with_reference(primary, reference)

        self.assertIs(checked, primary)
        self.assertIsNone(note)

    def test_field_source_priority_report_contains_core_adoption_rules(self):
        report = build_field_source_priority_report(["營收 YoY", "Forward EPS－FY1", "TTM EPS", "D/E"])

        self.assertEqual(len(report), 4)
        revenue = report[report["資料欄位"] == "營收 YoY"].iloc[0]
        fy1 = report[report["資料欄位"] == "Forward EPS－FY1"].iloc[0]
        ttm = report[report["資料欄位"] == "TTM EPS"].iloc[0]
        de = report[report["資料欄位"] == "D/E"].iloc[0]

        self.assertIn("FinMind TaiwanStockMonthRevenue", revenue["來源優先序"])
        self.assertIn("yfinance revenueGrowth 只作診斷備註", revenue["採用規則"])
        self.assertIn("法人 FY1 年度共識 EPS", fy1["來源優先序"])
        self.assertIn("FY1 是前瞻 PEG 年度估值", fy1["採用規則"])
        ttm_priority = str(ttm["來源優先序"])
        self.assertLess(ttm_priority.find("近四季財報 EPS 合計"), ttm_priority.find("yfinance trailingEps"))
        self.assertIn("yfinance trailingEps 僅作備援", ttm["採用規則"])
        self.assertIn("標準化成倍數", de["採用規則"])
        self.assertIn("D/E > 8", de["校驗/降權規則"])

    def test_forward_eps_calendar_notice_flags_h2_and_q4_without_changing_fy_sequence(self):
        june = build_forward_eps_calendar_notice(
            current_date="2026-06-15",
            fy1_year="2026",
            fy2_year="2027",
            fy3_year="2028",
        )
        july = build_forward_eps_calendar_notice(
            current_date="2026-07-15",
            fy1_year="2026",
            fy2_year="2027",
            fy3_year="2028",
        )
        october = build_forward_eps_calendar_notice(
            current_date="2026-10-15",
            fy1_year="2026",
            fy2_year="2027",
            fy3_year="2028",
        )

        self.assertEqual(june["phase"], "h1_fy1_primary")
        self.assertEqual(june["ui_notice"], "")
        self.assertEqual(july["fy_sequence_text"], "FY1=2026E / FY2=2027E / FY3=2028E")
        self.assertIn("同步參考 FY2", july["ui_notice"])
        self.assertEqual(october["phase"], "q4_fy2_primary_reference")
        self.assertIn("FY2 作主要前瞻參考", october["ui_notice"])
        self.assertIn("FY1/FY2/FY3 EPS 計算方式不變", october["prompt_notice"])

    def test_financial_base_context_uses_monthly_yoy_not_yfinance_revenue_growth(self):
        old_monthly = financial_context.get_monthly_revenue
        old_pepb = financial_context.get_pe_pb_data
        old_health = financial_context.get_finmind_financial_health
        try:
            financial_context.get_monthly_revenue = lambda *args, **kwargs: pd.DataFrame({
                "Month": ["2026/05"],
                "YoY": [42.67],
                "MoM": [3.2],
                "revenue_source": ["FinMind TaiwanStockMonthRevenue"],
                "source_url": ["https://example.test/monthly-revenue"],
                "source_rule": ["monthly revenue only; not yfinance revenueGrowth"],
                "announce_month": ["2026/06"],
                "revenue_month": ["2026/05"],
            })
            financial_context.get_pe_pb_data = lambda *args, **kwargs: pd.DataFrame()
            financial_context.get_finmind_financial_health = lambda *args, **kwargs: {}

            context = financial_context.build_financial_base_context(
                stock_id="3008",
                info={"revenueGrowth": 0.2257},
                current_price=2500,
                finmind_key="",
            )
        finally:
            financial_context.get_monthly_revenue = old_monthly
            financial_context.get_pe_pb_data = old_pepb
            financial_context.get_finmind_financial_health = old_health

        self.assertAlmostEqual(context["rev_growth"], 0.4267)
        self.assertEqual(context["latest_rev_display_label"], "公告月份：2026/05")
        self.assertEqual(context["latest_rev_source_url"], "https://example.test/monthly-revenue")
        self.assertEqual(context["latest_rev_source_rule"], "monthly revenue only; not yfinance revenueGrowth")
        self.assertEqual(context["latest_rev_announce_month"], "2026/06")
        self.assertEqual(context["latest_rev_revenue_month"], "2026/05")

    def test_ttm_eps_adoption_prefers_traced_four_quarter_sum_over_yfinance(self):
        result = build_ttm_eps_adoption(
            system_ttm_eps=6.51,
            ai_ttm_eps=7.37,
            system_source="yfinance trailingEps",
            ai_source="AI/外部校對近四季 EPS 合計",
            ai_has_trace=True,
        )

        self.assertEqual(result["adopted_value"], 7.37)
        self.assertIn("近四季", result["adopted_source"])
        self.assertTrue(result["warnings"])
        self.assertIn("可能過舊", result["warnings"][0])

    def test_ttm_eps_adoption_marks_price_pe_inference_as_backup(self):
        result = build_ttm_eps_adoption(
            system_ttm_eps=None,
            ai_ttm_eps=None,
            current_price=120,
            pe_ratio=20,
        )

        self.assertEqual(result["adopted_value"], 6.0)
        self.assertEqual(result["adopted_source"], "現價 / P/E 反推")
        self.assertTrue(result["system_is_inferred"])
        self.assertIn("反推", "；".join(result["notes"]))

    def test_ai_financial_context_derives_last_two_quarter_eps(self):
        context = financial_context.build_ai_financial_context(
            stock_id="2330",
            info={},
            ai_financial_store={
                "2330": {
                    "_stock_id": "2330",
                    "latest_month_eps": 1.1,
                    "latest_quarter_eps": 3.2,
                    "previous_quarter_eps": 2.8,
                }
            },
        )

        self.assertEqual(context["ai_latest_month_eps"], 1.1)
        self.assertEqual(context["ai_latest_quarter_eps"], 3.2)
        self.assertEqual(context["ai_previous_quarter_eps"], 2.8)
        self.assertEqual(context["ai_last_two_quarter_eps"], 6.0)

    def test_yfinance_analyst_snapshot_uses_dedicated_tables_and_info_fallback(self):
        class FakeTicker:
            analyst_price_targets = {"high": 135, "mean": 120}
            earnings_estimate = pd.DataFrame(
                {
                    "avg": [10.5, 12.0],
                    "numberOfAnalysts": [14, 11],
                },
                index=["0y", "+1y"],
            )
            eps_trend = pd.DataFrame(
                {"current": [10.4, 11.9, 13.8]},
                index=["0y", "+1y", "+2y"],
            )

        snapshot = services.extract_yfinance_analyst_snapshot(
            FakeTicker(),
            base_info={
                "targetLowPrice": 95,
                "numberOfAnalystOpinions": 14,
                "lastFiscalYearEnd": datetime.date(2025, 12, 31),
            },
            today=datetime.date(2026, 8, 21),
        )

        self.assertEqual(snapshot["targetHighPrice"], 135)
        self.assertEqual(snapshot["targetMeanPrice"], 120)
        self.assertEqual(snapshot["targetLowPrice"], 95)
        self.assertEqual(snapshot["numberOfAnalystOpinions"], 14)
        self.assertEqual(snapshot["forwardEpsFY1"], 10.5)
        self.assertEqual(snapshot["forwardEpsFY2"], 12.0)
        self.assertEqual(snapshot["forwardEpsFY3"], 13.8)
        self.assertEqual(snapshot["forwardEpsFY1Year"], 2026)
        self.assertEqual(snapshot["forwardEpsFY2Year"], 2027)
        self.assertEqual(snapshot["forwardEpsFY3Year"], 2028)
        self.assertIn("analyst_price_targets", snapshot["targetHighPriceSource"])
        self.assertIn("Ticker.info", snapshot["targetLowPriceSource"])
        self.assertIn("eps_trend", snapshot["forwardEpsFY3Source"])

    def test_financial_context_keeps_programmatic_values_and_uses_ai_only_for_gaps(self):
        source_trace = {
            field: {
                "source": "最新券商報告彙整",
                "published_date": "2026/08/20",
                "source_url": "https://example.test/research",
            }
            for field in (
                "target_price_avg",
                "forward_eps_fy1",
                "forward_eps_fy2",
                "forward_eps_fy3",
            )
        }
        context = financial_context.build_ai_financial_context(
            stock_id="2330",
            info={
                "targetHighPrice": 180,
                "targetMeanPrice": 160,
                "numberOfAnalystOpinions": 12,
                "targetPriceSource": "Yahoo Finance / yfinance analyst_price_targets",
                "forwardEpsFY1": 10,
                "forwardEpsFY1Year": 2026,
                "forwardEpsFY1Source": "yfinance earnings_estimate (0y)",
                "forwardEpsFY2": 12,
                "forwardEpsFY2Year": 2027,
                "forwardEpsFY2Source": "yfinance earnings_estimate (+1y)",
                "forwardEpsFYBasis": "程式抓取法人年度 EPS",
            },
            ai_financial_store={
                "2330": {
                    "_stock_id": "2330",
                    "target_price_high": 999,
                    "target_price_avg": 998,
                    "target_price_low": 140,
                    "target_price_analyst_count": 4,
                    "forward_eps_fy1": 99,
                    "forward_eps_fy1_year": 2026,
                    "forward_eps_fy2": 98,
                    "forward_eps_fy2_year": 2027,
                    "forward_eps_fy3": 15,
                    "forward_eps_fy3_year": 2028,
                    "_ai_source_trace": source_trace,
                }
            },
        )

        self.assertEqual(context["ai_hi_val"], 180)
        self.assertEqual(context["ai_me_val"], 160)
        self.assertEqual(context["ai_lo_val"], 140)
        self.assertEqual(context["ai_analyst_count"], 12)
        self.assertEqual(context["ai_forward_eps_fy1"], 10)
        self.assertEqual(context["ai_forward_eps_fy2"], 12)
        self.assertEqual(context["ai_forward_eps_fy3"], 15)
        self.assertIn("AI 全方位校對補缺", context["target_price_source"])
        self.assertIn("yfinance earnings_estimate", context["ai_forward_eps_fy1_source"])
        self.assertIn("最新券商報告彙整", context["ai_forward_eps_fy3_source"])

    def test_financial_context_does_not_promote_legacy_consensus_to_fy1(self):
        context = financial_context.build_ai_financial_context(
            stock_id="2330",
            info={},
            ai_financial_store={
                "2330": {
                    "_stock_id": "2330",
                    "forward_eps_consensus": 20,
                    "forward_eps_ai": 21,
                }
            },
        )

        self.assertIsNone(context["ai_forward_eps_fy1"])
        self.assertEqual(context["ai_forward_eps_consensus"], 20)

    def test_financial_context_rejects_unsourced_ai_target_and_fy_values(self):
        context = financial_context.build_ai_financial_context(
            stock_id="2330",
            info={},
            ai_financial_store={
                "2330": {
                    "_stock_id": "2330",
                    "target_price_avg": 160,
                    "forward_eps_fy1": 10,
                    "forward_eps_fy1_year": 2026,
                }
            },
        )

        self.assertIsNone(context["ai_me_val"])
        self.assertIsNone(context["ai_forward_eps_fy1"])
        self.assertEqual(context["target_price_source"], "無可用法人目標價")

    def test_get_monthly_revenue_finmind_fallback_has_source_meta(self):
        class FakeResponse:
            def __init__(self, status_code, payload=None, text=""):
                self.status_code = status_code
                self._payload = payload or {}
                self.text = text
                self.content = text.encode("utf-8")

            def json(self):
                return self._payload

        old_mops = services.get_mops_monthly_revenue
        old_get = services.requests.get
        try:
            def unexpected_mops(*args, **kwargs):
                self.fail("FinMind succeeded, so the slow MOPS fallback must not run")

            services.get_mops_monthly_revenue = unexpected_mops

            def fake_get(url, *args, **kwargs):
                if "tw.stock.yahoo.com" in url:
                    return FakeResponse(404, text="")
                self.assertIn("TaiwanStockMonthRevenue", url)
                return FakeResponse(200, {
                    "status": 200,
                    "data": [
                        {"date": "2025-05-01", "revenue": 700880000},
                        {"date": "2026-04-01", "revenue": 773500000},
                        {"date": "2026-05-01", "revenue": 814000000},
                    ],
                })

            services.requests.get = fake_get
            df = services.get_monthly_revenue("6789", "")
        finally:
            services.get_mops_monthly_revenue = old_mops
            services.requests.get = old_get

        self.assertFalse(df.empty)
        latest = df.iloc[-1]
        self.assertEqual(latest["revenue_source"], "FinMind TaiwanStockMonthRevenue")
        self.assertIn("api.finmindtrade.com", latest["source_url"])
        self.assertEqual(latest["source_rule"], "FinMind TaiwanStockMonthRevenue; same-month YoY/MoM; not yfinance revenueGrowth")
        self.assertEqual(latest["announce_date"], "來源未提供")
        self.assertEqual(latest["announce_month"], "來源未提供")
        self.assertEqual(latest["revenue_month"], "2026/05")

    def test_mops_fast_path_never_starts_legacy_month_crawl_by_default(self):
        class FakeResponse:
            status_code = 503
            content = b""
            text = ""

        urls = []
        timeouts = []
        old_get = services.requests.get
        try:
            def fake_get(url, *args, **kwargs):
                urls.append(url)
                timeouts.append(kwargs.get("timeout"))
                return FakeResponse()

            services.requests.get = fake_get
            result = services.get_mops_monthly_revenue("2330")
        finally:
            services.requests.get = old_get

        self.assertTrue(result.empty)
        self.assertEqual(len(urls), 3)
        self.assertTrue(all("mopsfin.twse.com.tw/opendata" in url for url in urls))
        self.assertTrue(all("/nas/t21/" not in url for url in urls))
        self.assertEqual(timeouts, [(0.8, 1.8)] * 3)

    def test_calc_monthly_revenue_growth_uses_same_month_last_year(self):
        df = pd.DataFrame([
            {"date": "2025-05-01", "revenue": 700_880_000},
            {"date": "2026-04-01", "revenue": 773_500_000},
            {"date": "2026-05-01", "revenue": 814_000_000},
        ])

        result = calc_monthly_revenue_growth(df)

        self.assertEqual(result["revenue_month"], "2026/05")
        self.assertAlmostEqual(result["monthly_revenue_yoy"], 16.14, places=2)
        self.assertAlmostEqual(result["monthly_revenue_mom"], 5.24, places=2)
        self.assertEqual(result["source_rule"], "monthly revenue only; not yfinance revenueGrowth")

    def test_parse_mops_monthly_revenue_html_calculates_yoy_and_mom(self):
        html = """
        <table>
          <tr>
            <th>公司代號</th><th>公司名稱</th><th>當月營收</th><th>上月營收</th>
            <th>去年當月營收</th><th>上月比較增減(%)</th><th>去年同月增減(%)</th>
          </tr>
          <tr><td>6789</td><td>采鈺</td><td>814000</td><td>773500</td><td>700880</td><td>5.23</td><td>16.14</td></tr>
        </table>
        """

        df = parse_mops_monthly_revenue_html(html, "6789", "2026/05")

        self.assertFalse(df.empty)
        self.assertEqual(df.iloc[0]["Month"], "2026/05")
        self.assertAlmostEqual(df.iloc[0]["monthly_revenue_yoy"], 16.14, places=2)
        self.assertAlmostEqual(df.iloc[0]["monthly_revenue_mom"], 5.24, places=2)
        self.assertEqual(df.iloc[0]["revenue_source"], "MOPS 公開資訊觀測站月營收")

    def test_parse_mops_monthly_revenue_csv_calculates_yoy_and_source_meta(self):
        csv_text = """出表日期,資料年月,公司代號,公司名稱,產業別,營業收入-當月營收,營業收入-上月營收,營業收入-去年當月營收,營業收入-上月比較增減(%),營業收入-去年同月增減(%)
"1150617","11505","6789","采鈺","半導體業","814000","773500","700880","5.23594","16.14094"
"""

        df = parse_mops_monthly_revenue_csv(csv_text, "6789", "上市", "https://mopsfin.twse.com.tw/opendata/t187ap05_L.csv")

        self.assertFalse(df.empty)
        self.assertEqual(df.iloc[0]["Month"], "2026/05")
        self.assertAlmostEqual(df.iloc[0]["monthly_revenue_yoy"], 16.14, places=2)
        self.assertAlmostEqual(df.iloc[0]["monthly_revenue_mom"], 5.24, places=2)
        self.assertEqual(df.iloc[0]["revenue_source"], "MOPS 開放資料月營收(上市)")
        self.assertEqual(df.iloc[0]["source_rule"], "MOPS OpenData monthly revenue; same-month YoY/MoM")
        self.assertEqual(df.iloc[0]["announce_date"], "2026/06/17")
        self.assertEqual(df.iloc[0]["announce_month"], "2026/06")
        self.assertEqual(df.iloc[0]["source_url"], "https://mopsfin.twse.com.tw/opendata/t187ap05_L.csv")

    def test_mops_latest_revenue_overrides_same_month_history_row(self):
        history = pd.DataFrame([
            {"Month": "2026/04", "Revenue": 7.735, "YoY": 2.0, "MoM": 1.0, "revenue_source": "FinMind TaiwanStockMonthRevenue"},
            {"Month": "2026/05", "Revenue": 8.14, "YoY": -0.62, "MoM": 5.23, "revenue_source": "FinMind TaiwanStockMonthRevenue"},
        ])
        mops = pd.DataFrame([
            {
                "Month": "2026/05",
                "Revenue": 8.14,
                "YoY": 16.14,
                "MoM": 5.24,
                "monthly_revenue_yoy": 16.14,
                "monthly_revenue_mom": 5.24,
                "revenue_source": "MOPS 公開資訊觀測站月營收(上市)",
            }
        ])

        merged = merge_mops_latest_revenue(history, mops)

        self.assertEqual(len(merged), 2)
        latest = merged[merged["Month"] == "2026/05"].iloc[0]
        self.assertEqual(latest["revenue_source"], "MOPS 公開資訊觀測站月營收(上市)")
        self.assertAlmostEqual(latest["monthly_revenue_yoy"], 16.14)

    def test_financial_quality_report_includes_source_priority_column(self):
        report = build_financial_quality_report([
            {
                "field": "營收 YoY",
                "system_source": "MOPS/FinMind/Yahoo 月營收",
                "system_source_url": "https://mops.twse.com.tw/nas/t21/sii/t21sc03_115_5_0.html",
                "source_rule": "MOPS monthly revenue; same-month YoY/MoM",
                "announce_date": "2026/06/10",
                "announce_month": "2026/06",
                "revenue_month": "2026/05",
                "system_value": 0.71,
                "ai_source": "AI補齊",
                "ai_value": 0.69,
                "adopted_value": 0.71,
                "adopted_source": "FinMind/yfinance",
                "period": "公告月份：2026/05",
                "fmt": "pct",
            }
        ])

        self.assertIn("來源優先序", report.columns)
        self.assertIn("系統來源網址", report.columns)
        self.assertIn("來源規則", report.columns)
        self.assertIn("公告日", report.columns)
        self.assertIn("公告月份", report.columns)
        self.assertIn("營收所屬月份", report.columns)
        self.assertIn("FinMind TaiwanStockMonthRevenue", report.iloc[0]["來源優先序"])
        self.assertEqual(report.iloc[0]["系統來源網址"], "https://mops.twse.com.tw/nas/t21/sii/t21sc03_115_5_0.html")
        self.assertEqual(report.iloc[0]["來源規則"], "MOPS monthly revenue; same-month YoY/MoM")
        self.assertEqual(report.iloc[0]["公告月份"], "2026/06")
        self.assertEqual(report.iloc[0]["營收所屬月份"], "2026/05")
        self.assertIn("系統+AI交叉", report.iloc[0]["品質狀態"])

    def test_prompt_source_priority_summary_is_compact_and_includes_critical_fields(self):
        prompt = format_field_source_priority_for_prompt(["營收 YoY", "Forward EPS－FY2", "D/E"], max_rows=5)

        self.assertIn("欄位=營收 YoY", prompt)
        self.assertIn("yfinance revenueGrowth", prompt)
        self.assertIn("欄位=Forward EPS－FY2", prompt)
        self.assertIn("FY2 只作市場先行定價", prompt)
        self.assertIn("欄位=D/E", prompt)

    def test_source_priority_summary_handles_aliases(self):
        summary = source_priority_summary_for_field("forward_eps_fy1")

        self.assertIn("法人 FY1 年度共識 EPS", summary)
        self.assertIn("FY1 是前瞻 PEG 年度估值", summary)

    def test_financial_candidate_data_standardizes_review_status_and_source_tier(self):
        ai_fin = {
            "_stock_id": "3008",
            "_stock_name": "大立光",
            "ttm_eps": 48.12,
            "yoy": 0.4267,
            "target_price_avg": 3200,
            "data_period": "2026Q1",
            "_ai_source_trace": {
                "ttm_eps": {
                    "source": "公開資訊觀測站公司財報",
                    "published_date": "2026Q1",
                    "source_url": "https://mops.example.test",
                    "note": "近四季 EPS 合計",
                    "confidence": "high",
                },
                "yoy": {
                    "source": "AI依成長率推估",
                    "published_date": "2026/05",
                    "note": "非公告單月 YoY",
                },
            },
        }

        candidates = build_financial_candidate_data(
            ai_fin,
            system_values={"ttm_eps": 48.12, "yoy": 0.2257},
            stock_id="3008",
            stock_name="大立光",
            retrieved_at="2026-06-18T15:00:00",
        )

        by_field = {row["field_name"]: row for row in candidates}
        self.assertEqual(by_field["ttm_eps"]["review_status"], "pending")
        self.assertEqual(by_field["ttm_eps"]["source_tier"], 1)
        self.assertEqual(by_field["ttm_eps"]["conflict_status"], "same_as_system")
        self.assertEqual(by_field["ttm_eps"]["unit"], "NTD/share")
        self.assertEqual(by_field["yoy"]["source_tier"], 5)
        self.assertEqual(by_field["yoy"]["unit"], "ratio_decimal")
        self.assertEqual(by_field["yoy"]["conflict_status"], "different_from_system")
        self.assertAlmostEqual(by_field["yoy"]["difference_pct"], (0.4267 - 0.2257) / 0.2257)
        self.assertEqual(by_field["target_price_avg"]["conflict_status"], "not_compared")
        self.assertTrue(by_field["target_price_avg"]["candidate_id"].startswith("fin:3008:target_price_avg:"))

    def test_candidate_data_report_exposes_review_status(self):
        candidates = build_financial_candidate_data(
            {
                "forward_eps_fy1": 120.5,
                "_ai_source_trace": {
                    "forward_eps_fy1": {
                        "source": "券商報告摘要",
                        "published_date": "2026/06/10",
                        "review_status": "needs_followup",
                    }
                },
            },
            stock_id="2330",
            stock_name="台積電",
            retrieved_at="2026-06-18T15:00:00",
        )

        report = build_candidate_data_report(candidates)

        self.assertIn("審核狀態", report.columns)
        self.assertIn("來源層級", report.columns)
        self.assertEqual(report.iloc[0]["審核狀態"], "需追查")
        self.assertEqual(report.iloc[0]["來源層級"], "Level 4")
        self.assertEqual(normalize_candidate_review_status("保留原值"), "kept_original")

    def test_candidate_review_cache_persists_and_applies_status(self):
        candidates = build_financial_candidate_data(
            {"ttm_eps": 10.5, "_ai_source_trace": {"ttm_eps": {"source": "公開資訊觀測站"}}},
            stock_id="3008",
            stock_name="大立光",
            retrieved_at="2026-06-18T15:00:00",
        )
        candidate = candidates[0]

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "candidate_reviews.json"
            record = update_financial_candidate_review(
                stock_id="3008",
                candidate_id=candidate["candidate_id"],
                review_status="accepted",
                decision_note="unit test accept",
                candidate_snapshot=candidate,
                cache_path=cache_path,
            )
            loaded = load_financial_candidate_review_cache(cache_path)
            applied = apply_financial_candidate_reviews(candidates, loaded, stock_id="3008")

        self.assertEqual(record["review_status"], "accepted")
        self.assertIn("reviews", loaded)
        self.assertEqual(applied[0]["review_status"], "accepted")
        self.assertEqual(applied[0]["decision_note"], "unit test accept")

    def test_modular_validator_boundaries_reexport_financial_helpers(self):
        payload = {"gross_margin": "25.5", "operating_margin": "12.0"}

        validated = modular_validate_ai_financial_json(payload, stock_id="TEST", stock_name="測試股")
        candidates = modular_build_financial_candidate_data(
            {"ttm_eps": 10.0, "_ai_source_trace": {"ttm_eps": {"source": "公開資訊觀測站"}}},
            stock_id="TEST",
            stock_name="測試股",
            retrieved_at="2026-06-18T15:00:00",
        )

        self.assertAlmostEqual(validated["gross_margin"], 0.255)
        self.assertAlmostEqual(validated["operating_margin"], 0.12)
        self.assertEqual(candidates[0]["field_name"], "ttm_eps")
        self.assertEqual(candidates[0]["source_tier"], 1)

    def test_ai_financial_postprocess_module_adds_sources_candidates_and_query_payload(self):
        parsed = {
            "ttm_eps": 5.4,
            "target_price_high": 90,
            "target_price_avg": 120,
            "target_price_low": 150,
            "data_period": "2026Q1",
            "_sources": {
                "ttm_eps": {
                    "source": "公開資訊觀測站",
                    "published_date": "2026Q1",
                    "source_url": "https://mops.example.test",
                    "note": "近四季合計",
                }
            },
        }

        result = postprocess_financial_ai_payload(
            parsed,
            marker_data={"target_price_avg": 130},
            stock_id="3008",
            stock_name="大立光",
            target_year=2026,
            used_model="gemini-3.1-pro-preview",
            used_search=True,
            attempts=[{"ok": True}],
            prompt_text="PROMPT",
            system_prompt="SYSTEM",
        )

        self.assertIn("_ai_source_trace", result)
        self.assertEqual(result["_ai_source_trace"]["ttm_eps"]["source"], "公開資訊觀測站")
        self.assertEqual(result["target_price_high"], 150)
        self.assertEqual(result["target_price_avg"], 120)
        self.assertEqual(result["target_price_low"], 90)
        self.assertTrue(result["_candidate_data"])
        self.assertIn("pending_review_candidates=", result["_candidate_data_status"])
        self.assertIn('"target_year": 2026', result["query_payload"])

    def test_ai_financial_schema_normalizes_source_metadata(self):
        result = normalize_ai_source_metadata({
            "ttm_eps": 12.3,
            "data_period": "2026Q1",
            "_sources": {"ttm_eps": "公開資訊觀測站"},
        })

        self.assertEqual(result["_ai_source_trace"]["ttm_eps"]["source"], "公開資訊觀測站")
        self.assertEqual(result["_ai_source_trace"]["ttm_eps"]["published_date"], "2026Q1")


class ValuationLogicTests(unittest.TestCase):
    def test_m10_margin_not_applicable_skips_margin_uplift_and_guard(self):
        result = quality_factor_relative(
            gross_margin=0.80,
            operating_margin=0.60,
            roe=0.20,
            calibration={
                "margin_quality": "N/A",
                "margin_rule": "margin_not_applicable",
                "margin_model_applicable": False,
                "margin_can_affect_valuation": False,
                "max_quality_factor": 1.30,
            },
        )

        self.assertAlmostEqual(result["factor"], 1.03, places=4)
        self.assertIn("不適用製造業毛利率 / 營益率模型", result["reason"])
        self.assertIn("跳過營益率防呆", result["reason"])

    def test_m10_tracking_only_zeroes_positive_margin_uplift(self):
        result = quality_factor_relative(
            gross_margin=0.70,
            operating_margin=0.45,
            roe=None,
            calibration={
                "gross_margin_baseline": 0.30,
                "gross_margin_good": 0.40,
                "gross_margin_excellent": 0.50,
                "base_operating_margin_ratio": 0.10,
                "operating_margin_low_ratio": 0.00,
                "operating_margin_high_ratio": 0.20,
                "margin_quality": "C",
                "margin_rule": "event_or_cycle_tracking_only",
                "margin_model_applicable": True,
                "margin_can_affect_valuation": False,
                "m10_margin_status": "tracking_only",
                "max_quality_factor": 1.30,
            },
        )

        self.assertAlmostEqual(result["factor"], 1.00, places=4)
        self.assertIn("正向 margin 加分歸零", result["reason"])

    def test_m10_operating_margin_benchmark_adds_small_adjustment(self):
        result = quality_factor_relative(
            gross_margin=0.45,
            operating_margin=0.30,
            roe=None,
            calibration={
                "gross_margin_baseline": 0.40,
                "gross_margin_good": 0.45,
                "gross_margin_excellent": 0.55,
                "base_operating_margin_ratio": 0.20,
                "operating_margin_low_ratio": 0.08,
                "operating_margin_high_ratio": 0.28,
                "margin_quality": "A",
                "margin_rule": "standard_margin_benchmark",
                "margin_model_applicable": True,
                "margin_can_affect_valuation": True,
                "max_quality_factor": 1.30,
            },
        )

        self.assertGreater(result["factor"], 1.00)
        self.assertIn("M10 分類", result["reason"])

    def test_dynamic_cap_pack_exposes_m10_margin_benchmark_for_ui_and_prompt(self):
        profile = {
            "model_key": "FOUNDRY",
            "model_label": "晶圓代工測試分類",
            "primary_valuation": "forward_pe",
            "pe_applicable": True,
            "themes": ["HPC"],
            "classification_confidence_factor": 1.0,
            "classification_source": "unit_test",
            "m10_margin_available": True,
            "m10_margin_status": "usable",
            "m10_task_id": "T01",
            "m10_category_name": "半導體｜晶圓代工 / HPC / 先進製程",
            "base_gross_margin_pct": 45,
            "gross_margin_low_pct": 35,
            "gross_margin_high_pct": 60,
            "base_operating_margin_pct": 35,
            "operating_margin_low_pct": 20,
            "operating_margin_high_pct": 50,
            "margin_quality": "A",
            "margin_rule": "high_operating_margin_cap",
            "margin_model_applicable": True,
            "margin_can_affect_valuation": True,
            "margin_reference_stocks": "2330 台積電；2303 聯電",
        }

        summary = build_m10_margin_benchmark_summary(profile)
        self.assertEqual(summary["status"], "usable")
        self.assertEqual(summary["base_gross_margin_pct"], 45.0)
        self.assertTrue(summary["can_affect_valuation"])

        pack = calculate_dynamic_cap_v2(
            stock_id="TEST",
            stock_name="M10測試股",
            current_price=120,
            info={"marketCap": 300_000_000_000},
            industry_profile=profile,
            gross_margin=0.50,
            operating_margin=0.38,
            roe=0.22,
            debt_to_equity=0.30,
            revenue_yoy=0.18,
            free_cash_flow=1_000_000_000,
            ttm_eps=5.0,
            system_forward_eps=6.0,
            consensus_forward_eps=6.2,
        )

        self.assertEqual(pack["m10_margin_benchmark"]["status"], "usable")
        report_text = " ".join(str(x) for x in pack["report"]["項目"].tolist())
        self.assertIn("M10 margin benchmark", report_text)
        prompt_text = prompt_dynamic_cap_core(pack, mode="research")
        self.assertIn("M10 margin benchmark", prompt_text)
        self.assertIn("晶圓代工 / HPC", prompt_text)
        self.assertIn("2330 台積電", prompt_text)

    def test_prompt_m10_margin_benchmark_summary_marks_not_applicable(self):
        text = prompt_m10_margin_benchmark_summary({
            "m10_margin_benchmark": {
                "available": True,
                "status": "not_applicable",
                "status_label": "不適用 margin 模型",
                "category_name": "金融業｜金控",
                "margin_quality": "N/A",
                "margin_rule_label": "不適用 margin 模型",
                "model_applicable": False,
                "can_affect_valuation": False,
                "usage_label": "不適用製造業毛利率 / 營益率模型；品質係數只採 ROE 與財務風險",
            }
        })

        self.assertIn("不適用 margin 模型", text)
        self.assertIn("品質係數只採 ROE", text)

    def test_dynamic_cap_returns_bounded_forward_pe_pack(self):
        profile = dict(industry_taxonomy.get_taxonomy("AI_SERVER_ODM"))
        profile.update({
            "model_key": "AI_SERVER_ODM",
            "model_label": profile.get("display_name", "AI Server ODM"),
            "themes": ["AI伺服器"],
            "classification_confidence_factor": 1.0,
            "classification_source": "unit_test",
        })

        pack = calculate_dynamic_cap_v2(
            stock_id="TEST",
            stock_name="測試股",
            current_price=300,
            info={"marketCap": 300_000_000_000},
            industry_profile=profile,
            gross_margin=0.22,
            operating_margin=0.09,
            roe=0.18,
            debt_to_equity=0.45,
            revenue_yoy=0.30,
            free_cash_flow=1_000_000_000,
            ttm_eps=8.0,
            system_forward_eps=10.0,
            consensus_forward_eps=10.5,
            pb_ratio=3.0,
        )

        self.assertTrue(pack.get("available"))
        self.assertEqual(pack.get("valuation_mode"), profile.get("primary_valuation"))
        self.assertGreater(pack.get("final_cap"), 0)
        self.assertGreaterEqual(pack.get("final_cap"), pack.get("floor_cap"))
        self.assertLessEqual(pack.get("final_cap"), pack.get("hard_ceiling_cap"))
        self.assertEqual(pack.get("model_version"), "Dynamic Cap 2.0 calibration 18.2")
        self.assertFalse(pack.get("report").empty)

    def test_dynamic_cap_market_condition_can_expand_hard_ceiling(self):
        profile = dict(industry_taxonomy.get_taxonomy("PROBE_AI_ASIC"))
        profile.update({
            "model_key": "PROBE_AI_ASIC",
            "model_label": profile.get("display_name", "AI ASIC 探針卡"),
            "themes": ["AI ASIC", "探針卡"],
            "classification_confidence_factor": 1.0,
            "classification_source": "unit_test",
        })

        pack = calculate_dynamic_cap_v2(
            stock_id="TEST",
            stock_name="測試探針卡",
            current_price=1600,
            info={"marketCap": 250_000_000_000, "averageVolume": 8_000_000},
            industry_profile=profile,
            gross_margin=0.56,
            operating_margin=0.34,
            roe=0.32,
            debt_to_equity=0.20,
            revenue_yoy=0.70,
            free_cash_flow=2_000_000_000,
            ttm_eps=4.0,
            consensus_forward_eps=10.0,
            pb_ratio=12.0,
        )

        adjustment = pack.get("market_condition_hard_adjustment") or {}
        self.assertTrue(adjustment.get("adjusted"))
        self.assertEqual(pack.get("structural_hard_ceiling_cap"), 115.0)
        self.assertGreater(pack.get("hard_ceiling_cap"), pack.get("structural_hard_ceiling_cap"))
        self.assertLessEqual(pack.get("final_cap"), pack.get("hard_ceiling_cap"))

    def test_dynamic_cap_market_condition_does_not_expand_hard_ceiling_when_data_is_weak(self):
        profile = dict(industry_taxonomy.get_taxonomy("PROBE_AI_ASIC"))
        profile.update({
            "model_key": "PROBE_AI_ASIC",
            "model_label": profile.get("display_name", "AI ASIC 探針卡"),
            "themes": ["AI ASIC", "探針卡"],
            "classification_confidence_factor": 1.0,
            "classification_source": "unit_test",
        })

        warnings = [
            {"規則": "EPS 分歧", "嚴重度": "warning", "警告文字": "EPS 差距過大"},
            {"規則": "Forward P/E 分歧", "嚴重度": "warning", "警告文字": "倍率差距過大"},
            {"規則": "YoY 分歧", "嚴重度": "warning", "警告文字": "營收口徑不同"},
        ]
        pack = calculate_dynamic_cap_v2(
            stock_id="TEST",
            stock_name="測試探針卡",
            current_price=1600,
            info={"marketCap": 250_000_000_000, "averageVolume": 8_000_000},
            industry_profile=profile,
            gross_margin=0.56,
            operating_margin=0.34,
            roe=0.32,
            debt_to_equity=0.20,
            revenue_yoy=0.70,
            free_cash_flow=2_000_000_000,
            ttm_eps=4.0,
            consensus_forward_eps=10.0,
            pb_ratio=12.0,
            divergence_warnings=warnings,
        )

        adjustment = pack.get("market_condition_hard_adjustment") or {}
        self.assertFalse(adjustment.get("adjusted"))
        self.assertEqual(pack.get("structural_hard_ceiling_cap"), 115.0)
        self.assertEqual(pack.get("hard_ceiling_cap"), 115.0)

    def test_forward_eps_tiered_valuation_calculates_base_soft_hard(self):
        result = build_forward_eps_tiered_valuation_report(
            current_price=100,
            broker_target_avg=120,
            broker_target_high=150,
            broker_target_low=90,
            ttm_eps=4,
            fy1_eps=5,
            fy2_eps=6,
            fy3_eps=7,
            fy1_year=2026,
            fy2_year=2027,
            fy3_year=2028,
            base_cap=18,
            soft_ceiling=22,
            hard_ceiling=28,
            current_date="2026-10-15",
        )
        report = result["report"]

        self.assertEqual(len(report), 4)
        fy1 = report[report["EPS口徑"] == "FY1 EPS"].iloc[0]
        self.assertEqual(fy1["基礎估值"], 90)
        self.assertEqual(fy1["樂觀估值"], 110)
        self.assertEqual(fy1["極限估值"], 140)
        self.assertEqual(result["summary"]["base_cap"], 18)
        self.assertEqual(result["summary"]["soft_cap"], 22)
        self.assertEqual(result["summary"]["hard_cap"], 28)
        self.assertEqual(result["summary"]["fy_sequence_text"], "FY1=2026E / FY2=2027E / FY3=2028E")
        self.assertIn("FY2 作主要前瞻參考", result["summary"]["fy_calendar_ui_notice"])

    def test_infer_pricing_horizon_detects_fy2_pricing(self):
        result = infer_pricing_horizon(
            price=150,
            ttm_eps=3,
            fy1_eps=5,
            fy2_eps=9,
            fy3_eps=10,
            base_pe=18,
            soft_pe=22,
            hard_pe=28,
        )

        self.assertEqual(result["code"], "FY2_PRICED")
        self.assertTrue(result["is_future_priced"])
        self.assertIn("新買", result["decision_rule"])

    def test_infer_pricing_horizon_detects_fy2_soft_pricing(self):
        result = infer_pricing_horizon(
            price=1000,
            ttm_eps=13.12,
            fy1_eps=14.29,
            fy2_eps=28.24,
            fy3_eps=None,
            base_pe=24,
            soft_pe=42,
            hard_pe=55,
        )

        self.assertEqual(result["code"], "FY2_SOFT_PRICED")
        self.assertEqual(result["rank"], 2)
        self.assertIn("soft", result["explanation"])
        self.assertIn("降權", result["decision_rule"])

    def test_infer_pricing_horizon_keeps_fy1_soft_separate_from_fy2(self):
        result = infer_pricing_horizon(
            price=3040,
            ttm_eps=39.59,
            fy1_eps=68.29,
            fy2_eps=100.0,
            fy3_eps=None,
            base_pe=38,
            soft_pe=60,
            hard_pe=60,
        )

        self.assertEqual(result["code"], "FY1_SOFT_PRICED")
        self.assertEqual(result["rank"], 1)
        self.assertFalse(result["is_future_priced"])
        self.assertIn("不代表必須用 FY2", result["explanation"])

    def test_future_evidence_score_rewards_landing_but_penalizes_data_risk(self):
        strong = calculate_future_evidence_score(
            revenue_yoy=0.52,
            revenue_mom=0.08,
            gross_margin=0.42,
            operating_margin=0.22,
            roe=0.25,
            fy1_eps=5,
            fy2_eps=7,
            analyst_count=12,
            target_confidence={"rank": 5, "label": "高可信"},
        )
        weak = calculate_future_evidence_score(
            revenue_yoy=-0.05,
            revenue_mom=-0.12,
            gross_margin=0.12,
            operating_margin=0.03,
            roe=0.04,
            fy1_eps=5,
            fy2_eps=4,
            analyst_count=1,
            target_confidence={"rank": 1, "label": "低可信"},
            divergence_warnings=[{"嚴重度": "danger"}],
        )

        self.assertGreaterEqual(strong["score"], 80)
        self.assertEqual(strong["label"], "未來高度落地")
        self.assertLess(weak["score"], 40)
        self.assertEqual(weak["label"], "純題材或證據反轉")

    def test_forward_eps_tiered_summary_includes_pricing_horizon_and_future_evidence(self):
        result = build_forward_eps_tiered_valuation_report(
            current_price=150,
            ttm_eps=3,
            fy1_eps=5,
            fy2_eps=9,
            fy3_eps=10,
            base_cap=18,
            soft_ceiling=22,
            hard_ceiling=28,
            revenue_yoy=0.30,
            revenue_mom=0.05,
            gross_margin=0.35,
            operating_margin=0.18,
            roe=0.20,
            analyst_count=8,
            target_confidence={"rank": 4, "label": "中高可信"},
        )

        summary = result["summary"]
        self.assertEqual(summary["pricing_horizon_code"], "FY2_PRICED")
        self.assertIn("FY2", summary["pricing_horizon_label"])
        self.assertGreaterEqual(summary["future_evidence_score"], 60)
        self.assertIn("future_evidence", summary)

    def test_current_eps_valuation_prefers_latest_month_annualized_eps(self):
        result = build_multiple_context(
            target_pe_cap=20,
            suggested_cap=20,
            dynamic_cap_pack={
                "formula_cap": 18,
                "base_multiple": 18,
                "optimistic_cap": 22,
                "hard_ceiling_cap": 28,
            },
            industry_profile={},
            eff_f_eps=5,
            has_ai_fin_fetch=True,
            ai_f_eps_calc=5.5,
            ai_forward_eps_fy1=6,
            ai_forward_eps_fy2=7,
            ai_forward_eps_fy3=8,
            cap_adopted_forward_eps=6,
            sys_latest_quarter_eps=None,
            ai_latest_month_eps=1.5,
            ai_latest_quarter_eps=2.5,
            eff_t_eps=8,
            raw_ai_period="2026/04",
        )

        self.assertEqual(result["current_eps_raw"], 1.5)
        self.assertEqual(result["current_eps_for_valuation"], 18.0)
        self.assertEqual(result["current_target_price_est"], 324.0)
        self.assertEqual(result["current_eps_source"], "最新單月 EPS 年化")
        self.assertIn("×12 年化值", result["current_eps_source_detail"])
        self.assertIn("原始單月 EPS=1.50", result["current_eps_formula_note"])
        self.assertIn("年化 EPS=18.00", result["current_eps_formula_note"])

    def test_current_eps_valuation_prefers_latest_quarter_annualized_eps(self):
        result = build_multiple_context(
            target_pe_cap=20,
            suggested_cap=20,
            dynamic_cap_pack={
                "formula_cap": 18,
                "base_multiple": 18,
                "optimistic_cap": 22,
                "hard_ceiling_cap": 28,
            },
            industry_profile={},
            eff_f_eps=5,
            has_ai_fin_fetch=True,
            ai_f_eps_calc=5.5,
            ai_forward_eps_fy1=6,
            ai_forward_eps_fy2=7,
            ai_forward_eps_fy3=8,
            cap_adopted_forward_eps=6,
            sys_latest_quarter_eps=None,
            ai_latest_quarter_eps=2.5,
            eff_t_eps=8,
            raw_ai_period="2026Q1",
        )

        self.assertEqual(result["current_eps_raw"], 2.5)
        self.assertEqual(result["current_eps_for_valuation"], 10.0)
        self.assertEqual(result["current_target_price_est"], 180.0)
        self.assertEqual(result["current_eps_source"], "最新單季 EPS 年化")
        self.assertIn("×4 年化值", result["current_eps_source_detail"])
        self.assertIn("原始單季 EPS=2.50", result["current_eps_formula_note"])
        self.assertIn("年化 EPS=10.00", result["current_eps_formula_note"])
        self.assertEqual(result["current_eps_period"], "2026Q1")

    def test_run_rate_eps_uses_latest_two_quarters_without_replacing_current_eps(self):
        result = build_multiple_context(
            target_pe_cap=20,
            suggested_cap=20,
            dynamic_cap_pack={
                "formula_cap": 18,
                "base_multiple": 18,
                "optimistic_cap": 22,
                "hard_ceiling_cap": 28,
            },
            industry_profile={},
            eff_f_eps=10,
            has_ai_fin_fetch=True,
            ai_f_eps_calc=10,
            ai_forward_eps_fy1=12,
            ai_forward_eps_fy2=14,
            ai_forward_eps_fy3=16,
            cap_adopted_forward_eps=12,
            ai_latest_quarter_eps=2.5,
            ai_previous_quarter_eps=2.3,
            eff_t_eps=7,
            raw_ai_period="2026Q1",
        )

        self.assertEqual(result["current_eps_for_valuation"], 10.0)
        self.assertAlmostEqual(result["run_rate_2q_eps_annualized"], 9.6)
        self.assertAlmostEqual(result["run_rate_reference_eps"], 9.6)
        self.assertAlmostEqual(result["run_rate_2q_target_price"], 172.8)
        self.assertEqual(result["run_rate_label"], "獲利動能加速")

    def test_run_rate_eps_flags_single_quarter_overheat(self):
        result = build_multiple_context(
            target_pe_cap=20,
            suggested_cap=20,
            dynamic_cap_pack={"formula_cap": 18, "base_multiple": 18},
            industry_profile={},
            eff_f_eps=10,
            has_ai_fin_fetch=True,
            ai_f_eps_calc=10,
            ai_forward_eps_fy1=10,
            ai_forward_eps_fy2=None,
            ai_forward_eps_fy3=None,
            cap_adopted_forward_eps=10,
            ai_latest_quarter_eps=4,
            ai_previous_quarter_eps=2,
            eff_t_eps=8,
            raw_ai_period="2026Q1",
        )

        self.assertEqual(result["run_rate_label"], "單季過熱需確認")
        self.assertIn("一次性因素", result["run_rate_action"])

    def test_current_eps_valuation_falls_back_to_ttm_eps(self):
        result = build_multiple_context(
            target_pe_cap=20,
            suggested_cap=20,
            dynamic_cap_pack={"formula_cap": 18, "base_multiple": 18},
            industry_profile={},
            eff_f_eps=5,
            has_ai_fin_fetch=False,
            ai_f_eps_calc=None,
            ai_forward_eps_fy1=None,
            ai_forward_eps_fy2=None,
            ai_forward_eps_fy3=None,
            cap_adopted_forward_eps=5,
            sys_latest_quarter_eps=None,
            ai_latest_quarter_eps=None,
            eff_t_eps=8,
        )

        self.assertEqual(result["current_eps_raw"], 8.0)
        self.assertEqual(result["current_eps_for_valuation"], 8.0)
        self.assertEqual(result["current_target_price_est"], 144.0)
        self.assertEqual(result["current_eps_source"], "TTM EPS")
        self.assertIn("直接採 TTM EPS", result["current_eps_formula_note"])

    def test_forward_eps_period_mismatch_detects_system_eps_closer_to_fy2(self):
        result = detect_forward_eps_period_mismatch(
            system_forward_eps=135.21,
            fy1_eps=93.75,
            fy2_eps=131.10,
        )

        self.assertTrue(result["has_mismatch"])
        self.assertEqual(result["recommended_eps"], 93.75)
        self.assertIn("更接近 FY2", result["note"])

    def test_divergence_report_adds_l1_l5_data_quality_levels(self):
        warnings = [
            {"規則": "Forward EPS 年期錯位", "嚴重度": "warning", "警告文字": "系統 Forward EPS 更接近 FY2"},
            {"規則": "EPS 分歧", "嚴重度": "danger", "警告文字": "EPS 差距過大"},
            {"規則": "合理價分歧", "嚴重度": "danger", "警告文字": "合理價差距過大"},
        ]

        report = build_divergence_warning_report(warnings)
        summary = summarize_data_quality_levels(warnings)

        self.assertIn("資料等級", report.columns)
        self.assertEqual(report.iloc[0]["資料等級"], "L3")
        self.assertEqual(report.iloc[1]["資料等級"], "L4")
        self.assertEqual(summary["level"], "L5")

    def test_formula_valuation_is_downgraded_when_forward_eps_matches_fy2(self):
        result = build_multiple_context(
            target_pe_cap=36,
            suggested_cap=36,
            dynamic_cap_pack={
                "formula_cap": 36,
                "base_multiple": 36,
                "optimistic_cap": 55,
                "hard_ceiling_cap": 70,
            },
            industry_profile={},
            eff_f_eps=135.21,
            has_ai_fin_fetch=True,
            ai_f_eps_calc=93.75,
            ai_forward_eps_fy1=93.75,
            ai_forward_eps_fy2=131.10,
            ai_forward_eps_fy3=150.0,
            cap_adopted_forward_eps=93.75,
        )

        self.assertTrue(result["forward_eps_period_mismatch"]["has_mismatch"])
        self.assertAlmostEqual(result["sys_target_price_raw"], 4867.56)
        self.assertAlmostEqual(result["sys_target_price_est"], 3375.0)
        self.assertEqual(result["formula_eps_for_calc"], 93.75)
        self.assertIn("FY1 EPS", result["formula_eps_source"])

    def test_final_signal_uses_unjudgeable_grade_only_for_critical_data_breaks(self):
        result = build_final_operation_signal(
            current_price=100,
            valuation_separation={"warning_count": 0, "danger_count": 0},
            divergence_warnings=[],
            target_confidence={"rank": 5},
            industry_profile={"pe_model_suitable": True},
            forward_pe=18,
            peg=1.1,
            gross_margin=0.20,
            operating_margin=0.35,
        )

        self.assertEqual(result["signal"], "資料異常-不可判斷")
        self.assertEqual(result["data_grade_label"], "資料異常-不可判斷")
        self.assertIn("營益率高於毛利率", "；".join(result["reasons"]))

    def test_final_signal_downgrades_divergent_data_without_hard_stopping(self):
        result = build_final_operation_signal(
            current_price=100,
            valuation_separation={"operable_low": 90, "operable_mid": 105, "operable_high": 120, "warning_count": 1, "danger_count": 1},
            divergence_warnings=[{"嚴重度": "danger", "規則": "EPS 分歧"}],
            target_confidence={"rank": 5},
            industry_profile={"pe_model_suitable": True},
            forward_pe=24,
            peg=1.2,
            roe=0.20,
            revenue_yoy=0.20,
            gross_margin=0.30,
            operating_margin=0.20,
        )

        self.assertEqual(result["signal"], "資料分歧-降權判斷")
        self.assertEqual(result["data_grade_label"], "資料分歧-降權判斷")
        self.assertEqual(result["data_quality_level"]["level"], "L4")
        self.assertIn("保守估值", result["advice"])

    def test_yoy_divergence_over_ten_points_blocks_buy_signal(self):
        warnings = build_divergence_warnings(
            system_yoy=0.1614,
            ai_yoy=-0.0062,
            stock_id="6789",
            stock_name="采鈺",
        )

        self.assertEqual(warnings[0]["規則"], "YoY 分歧")
        self.assertEqual(warnings[0]["嚴重度"], "danger")

        result = build_final_operation_signal(
            current_price=85,
            valuation_separation={"operable_low": 90, "operable_mid": 105, "operable_high": 120, "warning_count": 1, "danger_count": 1},
            divergence_warnings=warnings,
            target_confidence={"rank": 5},
            industry_profile={"pe_model_suitable": True},
            forward_pe=16,
            peg=0.9,
            roe=0.20,
            revenue_yoy=0.1614,
            gross_margin=0.30,
            operating_margin=0.20,
        )

        self.assertEqual(result["signal"], "資料分歧-降權判斷")
        self.assertNotEqual(result["signal"], "可買-小量分批")

    def test_final_signal_can_remain_small_batch_buy_with_light_data_warnings(self):
        result = build_final_operation_signal(
            current_price=85,
            valuation_separation={"operable_low": 90, "operable_mid": 105, "operable_high": 120, "warning_count": 1, "danger_count": 0},
            divergence_warnings=[{"嚴重度": "warning", "規則": "YoY 分歧"}],
            target_confidence={"rank": 5},
            industry_profile={"pe_model_suitable": True},
            forward_pe=16,
            peg=0.9,
            roe=0.20,
            revenue_yoy=0.20,
            gross_margin=0.30,
            operating_margin=0.20,
        )

        self.assertEqual(result["signal"], "可買-小量分批")
        self.assertEqual(result["data_grade_label"], "觀望-資料待確認")
        self.assertIn("不可一次買滿", result["advice"])

    def test_final_signal_blocks_buy_when_fy2_priced_with_weak_evidence(self):
        result = build_final_operation_signal(
            current_price=85,
            valuation_separation={"operable_low": 90, "operable_mid": 105, "operable_high": 120, "warning_count": 0, "danger_count": 0},
            divergence_warnings=[],
            target_confidence={"rank": 5},
            industry_profile={"pe_model_suitable": True},
            forward_pe=16,
            peg=0.9,
            roe=0.20,
            revenue_yoy=0.20,
            gross_margin=0.30,
            operating_margin=0.20,
            pricing_horizon={"code": "FY2_PRICED", "label": "FY2 先行定價", "explanation": "需 FY2 EPS 才能解釋", "decision_rule": "新買需降權"},
            future_evidence={"score": 35, "label": "純題材或證據反轉", "action": "不可用 FY2 支撐買進"},
        )

        self.assertEqual(result["signal"], "不建議")
        self.assertIn("未來證據不足", result["advice"])
        self.assertEqual(result["pricing_horizon_code"], "FY2_PRICED")

    def test_final_signal_downgrades_fy2_priced_buy_even_with_strong_evidence(self):
        result = build_final_operation_signal(
            current_price=85,
            valuation_separation={"operable_low": 90, "operable_mid": 105, "operable_high": 120, "warning_count": 0, "danger_count": 0},
            divergence_warnings=[],
            target_confidence={"rank": 5},
            industry_profile={"pe_model_suitable": True},
            forward_pe=16,
            peg=0.9,
            roe=0.25,
            revenue_yoy=0.50,
            gross_margin=0.45,
            operating_margin=0.25,
            pricing_horizon={"code": "FY2_PRICED", "label": "FY2 先行定價", "explanation": "需 FY2 EPS 才能解釋", "decision_rule": "新買需降權"},
            future_evidence={"score": 85, "label": "未來高度落地", "action": "只可小部位或既有續抱"},
        )

        self.assertEqual(result["signal"], "資料分歧-降權判斷")
        self.assertIn("小部位", result["advice"])
        self.assertEqual(result["future_evidence_score"], 85)

    def test_final_signal_does_not_treat_fy1_soft_as_fy2_future_pricing(self):
        result = build_final_operation_signal(
            current_price=85,
            valuation_separation={"operable_low": 90, "operable_mid": 105, "operable_high": 120, "warning_count": 0, "danger_count": 0},
            divergence_warnings=[],
            target_confidence={"rank": 5},
            industry_profile={"pe_model_suitable": True},
            forward_pe=24,
            peg=0.9,
            roe=0.20,
            revenue_yoy=0.20,
            gross_margin=0.30,
            operating_margin=0.20,
            pricing_horizon={"code": "FY1_SOFT_PRICED", "label": "FY1 樂觀定價", "explanation": "FY1 soft 可解釋", "decision_rule": "安全邊際不足"},
            future_evidence={"score": 35, "label": "證據不足", "action": "不可追價"},
        )

        self.assertEqual(result["pricing_horizon_code"], "FY1_SOFT_PRICED")
        self.assertNotIn("需 FY2", result["advice"])
        self.assertNotIn("FY2", "；".join(result["reasons"]))
        self.assertIn("FY1 樂觀區", "；".join(result["reasons"]))

    def test_final_signal_normalizes_legacy_fy1_soft_or_fy2_watch_code(self):
        result = build_final_operation_signal(
            current_price=85,
            valuation_separation={"operable_low": 90, "operable_mid": 105, "operable_high": 120, "warning_count": 0, "danger_count": 0},
            divergence_warnings=[],
            target_confidence={"rank": 5},
            industry_profile={"pe_model_suitable": True},
            forward_pe=24,
            peg=0.9,
            roe=0.20,
            revenue_yoy=0.20,
            gross_margin=0.30,
            operating_margin=0.20,
            pricing_horizon={"code": "FY1_SOFT_OR_FY2_WATCH", "label": "FY1 樂觀 / FY2 觀察", "explanation": "舊版 code", "decision_rule": "舊版規則"},
            future_evidence={"score": 35, "label": "證據不足", "action": "不可追價"},
        )

        self.assertEqual(result["pricing_horizon_code"], "FY1_SOFT_PRICED")
        self.assertIn("FY1 樂觀定價", result["pricing_horizon_label"])
        self.assertNotIn("需 FY2", result["advice"])
        self.assertNotIn("FY2", "；".join(result["reasons"]))

    def test_final_signal_never_upgrades_buy_for_fy2_soft_priced(self):
        result = build_final_operation_signal(
            current_price=85,
            valuation_separation={"operable_low": 90, "operable_mid": 105, "operable_high": 120, "warning_count": 0, "danger_count": 0},
            divergence_warnings=[],
            target_confidence={"rank": 5},
            industry_profile={"pe_model_suitable": True},
            forward_pe=16,
            peg=0.9,
            roe=0.25,
            revenue_yoy=0.50,
            gross_margin=0.45,
            operating_margin=0.25,
            pricing_horizon={"code": "FY2_SOFT_PRICED", "label": "FY2 樂觀先行定價", "explanation": "需 FY2 soft 才能解釋", "decision_rule": "不得升級買進"},
            future_evidence={"score": 90, "label": "未來高度落地", "action": "續抱或回檔小量"},
        )

        self.assertNotEqual(result["signal"], "可買-小量分批")
        self.assertEqual(result["signal"], "資料分歧-降權判斷")
        self.assertIn("不得直接升級", result["advice"])
        self.assertIn("回檔小量", result["advice"])

    def test_margin_credit_summary_calculates_ratios_and_risk(self):
        df = pd.DataFrame({
            "date": pd.date_range("2026-05-01", periods=6, freq="B"),
            "stock_id": ["2330"] * 6,
            "MarginPurchaseBuy": [100, 120, 130, 140, 150, 160],
            "MarginPurchaseCashRepayment": [0, 0, 0, 0, 0, 0],
            "MarginPurchaseLimit": [5000] * 6,
            "MarginPurchaseSell": [50, 60, 70, 80, 90, 100],
            "MarginPurchaseTodayBalance": [1000, 1120, 1250, 1400, 1600, 1800],
            "MarginPurchaseYesterdayBalance": [950, 1000, 1120, 1250, 1400, 1600],
            "OffsetLoanAndShort": [0] * 6,
            "ShortSaleBuy": [0] * 6,
            "ShortSaleCashRepayment": [0] * 6,
            "ShortSaleLimit": [5000] * 6,
            "ShortSaleSell": [10, 20, 20, 30, 40, 50],
            "ShortSaleTodayBalance": [80, 90, 100, 120, 150, 180],
            "ShortSaleYesterdayBalance": [70, 80, 90, 100, 120, 150],
        })

        summary = build_margin_credit_summary(df, shares_outstanding=20_000_000)

        self.assertTrue(summary["available"])
        self.assertAlmostEqual(summary["margin_usage_ratio"], 0.36)
        self.assertAlmostEqual(summary["margin_to_shares_ratio"], 0.09)
        self.assertEqual(summary["margin_change_1d"], 200)
        self.assertEqual(summary["margin_change_5d"], 800)
        self.assertAlmostEqual(summary["short_margin_ratio"], 0.10)
        self.assertEqual(summary["risk_label"], "偏熱")
        self.assertFalse(summary["report"].empty)

    def test_monthly_revenue_yoy_replaces_yfinance_without_warning(self):
        monthly_rev_df = pd.DataFrame({
            "Month": ["2026-05"],
            "YoY": [71.62],
        })

        corrected_sys, corrected_ai, warnings = validate_and_correct_financial_metrics(
            {"rev_growth": 1.102, "gross_margin": 0.26, "operating_margin": 0.20, "debt_to_equity": 0.3},
            {"rev_growth": None},
            monthly_rev_df=monthly_rev_df,
            stock_id="3017",
            stock_name="奇鋐",
        )

        self.assertAlmostEqual(corrected_sys["rev_growth"], 0.7162)
        self.assertAlmostEqual(corrected_sys["revenue_yoy"], 0.7162)
        self.assertEqual(warnings, [])

    def test_ai_financial_json_validation_normalizes_and_blocks_bad_values(self):
        payload = {
            "forward_eps_fy1": "6.2",
            "forward_eps_fy2": "7.4",
            "forward_eps_fy3": "8.6",
            "forward_eps_fy1_year": "FY2026E",
            "forward_eps_fy2_year": 2027,
            "forward_eps_fy3_year": "2028E",
            "gross_margin": "25.5",
            "operating_margin": "12.3",
            "roe": "18.0",
            "target_price_high": 90,
            "target_price_avg": 120,
            "target_price_low": 150,
            "industry_classification": {
                "suggested_primary_taxon": "NOT_A_REAL_TAXON",
                "confidence": "medium",
                "suggested_themes": "AI伺服器",
            },
        }

        result = validate_ai_financial_json(payload, stock_id="TEST", stock_name="測試股")

        self.assertEqual(result["forward_eps_fy1"], 6.2)
        self.assertAlmostEqual(result["gross_margin"], 0.255)
        self.assertAlmostEqual(result["operating_margin"], 0.123)
        self.assertAlmostEqual(result["roe"], 0.18)
        self.assertEqual(result["target_price_high"], 150)
        self.assertEqual(result["target_price_avg"], 120)
        self.assertEqual(result["target_price_low"], 90)
        self.assertEqual(result["industry_classification"]["suggested_primary_taxon"], "GENERAL")
        self.assertTrue(result.get("_ai_validation_warnings"))

    def test_ai_financial_json_validation_rejects_missing_and_out_of_sequence_fy_years(self):
        result = validate_ai_financial_json(
            {
                "forward_eps_fy1": 6.2,
                "forward_eps_fy1_year": 2026,
                "forward_eps_fy2": 7.4,
                "forward_eps_fy2_year": 2026,
                "forward_eps_fy3": 8.6,
            },
            stock_id="TEST",
            stock_name="測試股",
        )

        self.assertEqual(result["forward_eps_fy1"], 6.2)
        self.assertIsNone(result["forward_eps_fy2"])
        self.assertIsNone(result["forward_eps_fy2_year"])
        self.assertIsNone(result["forward_eps_fy3"])
        self.assertTrue(any("FY 序列" in warning for warning in result["_ai_validation_warnings"]))
        self.assertTrue(any("缺少可解析" in warning for warning in result["_ai_validation_warnings"]))


class PromptContextTests(unittest.TestCase):
    def test_etf_prompt_summary_includes_fast_and_ai_rows(self):
        summary = prompt_etf_panel_summary(
            etf_holders=[
                {"etf_code": "00999", "etf_name": "測試ETF", "weight": 3.456, "data_date": "2026-06-01", "source": "unit"},
            ],
            ai_etf_data={
                "etf_holders_ai": [
                    {"etf_code": "00888", "etf_name": "AI補查ETF", "weight": 1.2, "data_date": "2026-06-02", "source": "ai"},
                ],
                "summary": "AI 補查摘要",
            },
        )

        self.assertIn("快速ETF｜00999 測試ETF", summary)
        self.assertIn("持股=3.46%", summary)
        self.assertIn("AI ETF｜00888 AI補查ETF", summary)
        self.assertIn("AI ETF 摘要｜AI 補查摘要", summary)

    def test_chip_prompt_summary_uses_panel_state(self):
        summary = prompt_chip_panel_summary({
            "has_institutional_data": True,
            "f_10d": 1200,
            "t_10d": -300,
            "f_status": "連買",
            "t_status": "連賣",
            "trap_warning": "<div>籌碼警示文字</div>",
            "inst_str": "22.0%",
            "inst_eval": "穩定認可",
            "insider_str": "18.0%",
            "in_eval": "相對穩健",
            "share_capital": 2_500_000_000,
            "cap_type": "中小型",
            "driver": "投信主導",
            "driver_desc": "股本輕",
            "margin_credit": {
                "available": True,
                "risk_label": "偏熱",
                "latest_date": "2026-06-08",
                "margin_balance": 1800,
                "margin_usage_ratio": 0.36,
                "margin_to_shares_ratio": 0.09,
                "margin_change_5d": 800,
                "margin_change_5d_pct": 0.80,
                "margin_change_20d": 1000,
                "margin_change_20d_pct": 1.25,
                "short_margin_ratio": 0.10,
                "risk_note": "融資籌碼已有升溫跡象",
            },
        })

        self.assertIn("外資近10日淨買賣: 1200", summary)
        self.assertIn("投信近10日淨買賣: -300", summary)
        self.assertIn("外資+投信近10日合計: 900", summary)
        self.assertIn("籌碼警示文字", summary)
        self.assertIn("融資融券風險: 等級=偏熱", summary)
        self.assertIn("融資使用率=36.00%", summary)
        self.assertIn("融資占股本=9.00%", summary)
        self.assertIn("股本/控盤類型: 25.0 億｜中小型｜投信主導", summary)

    def test_model_library_feedback_prompt_includes_profile_context(self):
        summary = prompt_model_library_feedback_request({
            "primary_taxon": "AI_TEST_EQUIPMENT",
            "model_label": "AI 測試設備",
            "hybrid_taxons_text": "ADVANCED_PACKAGING 20%",
            "hybrid_mixed_caps_text": "base 25 / floor 18 / soft 35 / hard 45",
            "classification_source": "stock_mapping.py",
            "classification_confidence": "high",
            "soft_ceiling_pe": 35,
            "hard_ceiling_pe": 45,
        })
        gap_rules = prompt_model_gap_trigger_conditions()

        self.assertIn("目前 primary_taxon: AI_TEST_EQUIPMENT", summary)
        self.assertIn("目前 hybrid_taxons / 權重: ADVANCED_PACKAGING 20%", summary)
        self.assertIn("主模型 soft / hard ceiling: 35 / 45", summary)
        self.assertIn("primary_taxon_review", summary)
        self.assertIn("不可因單次股價上漲就建議調高模型", summary)
        self.assertIn("啟動模型落差診斷", gap_rules)

    def test_prompt_peg_layers_include_current_eps_valuation(self):
        summary = prompt_peg_valuation_layers(
            system_eps=5,
            system_eps_raw=7,
            system_raw_price=126,
            formula_eps_source="FY1 EPS（系統 Forward EPS 疑似 FY2，已降權）",
            forward_eps_mismatch_note="系統 Forward EPS 更接近 FY2",
            current_eps=10,
            current_eps_raw=2.5,
            current_eps_source="最新單季 EPS 年化",
            current_eps_formula_note="原始單季 EPS=2.50；年化 EPS=10.00",
            current_eps_period="2026Q1",
            current_price=180,
            run_rate_1q_eps=10,
            run_rate_2q_eps=9.6,
            run_rate_reference_eps=9.6,
            run_rate_1q_price=180,
            run_rate_2q_price=172.8,
            run_rate_reference_price=172.8,
            run_rate_label="獲利動能加速",
            run_rate_action="近二季年化高於 TTM",
            fy1_eps=6,
            fy1_year="2026",
            fy2_year="2027",
            fy3_year="2028",
            formula_cap=18,
            base_cap=18,
            soft_cap=22,
            hard_cap=28,
            system_price=90,
            fy1_base_price=108,
            fy1_soft_price=132,
            fy1_hard_price=168,
            current_date="2026-10-15",
        )

        self.assertIn("1-1. 目前估值", summary)
        self.assertIn("1-2. Run-rate EPS 動能估值", summary)
        self.assertIn("近二季年化EPS=9.60", summary)
        self.assertIn("不取代 TTM", summary)
        self.assertIn("最新單季 EPS 年化", summary)
        self.assertIn("原始EPS=2.50", summary)
        self.assertIn("計算=原始單季 EPS=2.50；年化 EPS=10.00", summary)
        self.assertIn("目前實際獲利支撐度", summary)
        self.assertIn("系統原始公式價=126.0元", summary)
        self.assertIn("系統 Forward EPS 更接近 FY2", summary)
        self.assertIn("目前台北時間月份=10月", summary)
        self.assertIn("FY1=2026E / FY2=2027E / FY3=2028E", summary)
        self.assertIn("FY2 可作主要前瞻參考", summary)

    def test_eps_adoption_summary_includes_current_valuation_price(self):
        summary = prompt_eps_adoption_sync_summary(
            sys_forward_eps_system_val=5,
            eff_f_eps_val=5,
            current_eps_for_valuation_val=10,
            current_eps_raw_val=2.5,
            current_eps_source_val="最新單季 EPS 年化",
            current_eps_formula_note_val="原始單季 EPS=2.50；年化 EPS=10.00",
            current_eps_period_val="2026Q1",
            formula_pe_cap_val=18,
            sys_target_price_est_val=90,
            current_target_price_est_val=180,
            run_rate_1q_eps_val=10,
            run_rate_2q_eps_val=9.6,
            run_rate_reference_eps_val=9.6,
            run_rate_1q_target_price_val=180,
            run_rate_2q_target_price_val=172.8,
            run_rate_reference_target_price_val=172.8,
            run_rate_label_val="獲利動能加速",
            run_rate_action_val="近二季年化高於 TTM",
        )

        self.assertIn("目前估值 EPS", summary)
        self.assertIn("計算=原始單季 EPS=2.50；年化 EPS=10.00", summary)
        self.assertIn("Run-rate EPS 動能", summary)
        self.assertIn("Run-rate參考=172.8元", summary)
        self.assertIn("目前估值=180.0元", summary)
        self.assertIn("最新單季 EPS 年化", summary)

    def test_technical_suffix_respects_mode_and_builds_summary(self):
        hist = pd.DataFrame({
            "Open": [100 + i for i in range(80)],
            "High": [102 + i for i in range(80)],
            "Low": [98 + i for i in range(80)],
            "Close": [101 + i for i in range(80)],
            "Volume": [1000 + i * 10 for i in range(80)],
        })

        self.assertEqual(prompt_technical_suffix("不加入技術面", hist=hist, curr_p=180), "")

        summary = prompt_technical_suffix("加入技術面摘要與線圖輔助規則", hist=hist, curr_p=180)
        self.assertIn("技術面與進出場節奏", summary)
        self.assertIn("收盤價與均線", summary)
        self.assertIn("KD 狀態", summary)
        self.assertIn("技術線圖輔助規則", summary)
        self.assertIn("不可覆蓋", summary)


class _FakePanelContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakePromptPackStreamlit:
    def __init__(self, radio_values):
        self.radio_values = radio_values
        self.expander_calls = []
        self.radio_calls = []
        self.caption_calls = []
        self.text_area_calls = []

    def expander(self, label, expanded=False):
        self.expander_calls.append({"label": label, "expanded": expanded})
        return _FakePanelContext()

    def radio(self, label, options, horizontal=False, key=None):
        self.radio_calls.append({"label": label, "options": list(options), "horizontal": horizontal, "key": key})
        return self.radio_values.get(label, options[0])

    def caption(self, text):
        self.caption_calls.append(text)

    def text_area(self, label, value, height=None, label_visibility=None, key=None):
        self.text_area_calls.append({
            "label": label,
            "value": value,
            "height": height,
            "label_visibility": label_visibility,
            "key": key,
        })


class _FakePromptPackComponents:
    def __init__(self):
        self.html_calls = []

    def html(self, body, height=None):
        self.html_calls.append({"body": body, "height": height})


class _FakePanelStreamlit:
    def __init__(self, *, session_state=None, button_values=None):
        self.session_state = _SessionState(session_state or {})
        self.button_values = button_values or {}
        self.columns_calls = []
        self.expander_calls = []
        self.markdown_calls = []
        self.caption_calls = []
        self.warning_calls = []
        self.info_calls = []
        self.error_calls = []
        self.success_calls = []
        self.write_calls = []
        self.dataframe_calls = []
        self.button_calls = []
        self.spinner_calls = []
        self.json_calls = []
        self.code_calls = []
        self.rerun_called = False
        self.stop_called = False

    def columns(self, spec):
        self.columns_calls.append(spec)
        count = spec if isinstance(spec, int) else len(spec)
        return [_FakePanelContext() for _ in range(count)]

    def expander(self, label, expanded=False):
        self.expander_calls.append({"label": label, "expanded": expanded})
        return _FakePanelContext()

    def spinner(self, text):
        self.spinner_calls.append(text)
        return _FakePanelContext()

    def button(self, label, **kwargs):
        self.button_calls.append({"label": label, **kwargs})
        if kwargs.get("disabled"):
            return False
        key = kwargs.get("key")
        return bool(self.button_values.get(key, self.button_values.get(label, False)))

    def markdown(self, text, **kwargs):
        self.markdown_calls.append({"text": text, **kwargs})

    def caption(self, text):
        self.caption_calls.append(text)

    def warning(self, text):
        self.warning_calls.append(text)

    def info(self, text):
        self.info_calls.append(text)

    def error(self, text):
        self.error_calls.append(text)

    def success(self, text):
        self.success_calls.append(text)

    def write(self, value):
        self.write_calls.append(value)

    def dataframe(self, data, **kwargs):
        self.dataframe_calls.append({"data": data, **kwargs})

    def json(self, value):
        self.json_calls.append(value)

    def code(self, body, language=None):
        self.code_calls.append({"body": body, "language": language})

    def rerun(self):
        self.rerun_called = True

    def stop(self):
        self.stop_called = True
        raise RuntimeError("streamlit stop called")


class UIRegressionTests(unittest.TestCase):
    def test_ai_fill_scope_covers_exact_core_fields_and_ignores_yfinance_growth(self):
        from ui_panels.financials import _build_programmatic_analyst_fill_scope

        snapshot, missing = _build_programmatic_analyst_fill_scope(
            {
                "trailingEps": 40,
                "forwardEpsFY1": 45,
                "forwardEpsFY1Year": 2026,
                "grossMargins": 0.58,
                "operatingMargins": 0.47,
                "revenueGrowth": 0.99,
                "targetMeanPrice": 1100,
                "targetLowPrice": 900,
                "targetHighPrice": 1250,
            },
            current_price=980,
        )

        self.assertEqual(snapshot["current_price"], 980)
        self.assertEqual(snapshot["ttm_eps"], 40)
        self.assertEqual(snapshot["forward_eps_fy1"], 45)
        self.assertEqual(snapshot["gross_margin"], 0.58)
        self.assertEqual(snapshot["operating_margin"], 0.47)
        self.assertEqual(snapshot["target_price"], 1100)
        self.assertNotIn("yoy", snapshot)
        self.assertIn("yoy", missing)
        self.assertIn("forward_eps_fy2", missing)
        self.assertIn("forward_eps_fy3", missing)

    def test_eps_price_panel_rows_calculate_all_four_tiers(self):
        from ui_panels.financials import build_eps_price_calculation_rows

        rows = build_eps_price_calculation_rows(
            ttm_eps=10,
            fy1_eps=12,
            fy2_eps=14,
            fy3_eps=16,
            fy1_year=2026,
            fy2_year=2027,
            fy3_year=2028,
            base_cap=20,
            soft_cap=24,
            hard_cap=28,
            cap_eps_basis="ttm_only",
        )

        self.assertEqual([row["tier"] for row in rows], ["TTM", "FY1", "FY2", "FY3"])
        self.assertEqual(rows[0]["base_price"], 200)
        self.assertEqual(rows[1]["soft_price"], 288)
        self.assertEqual(rows[2]["hard_price"], 392)
        self.assertEqual(rows[3]["base_price"], 320)
        self.assertIn("正式 TTM", rows[0]["position"])
        self.assertIn("非正式估值", rows[1]["position"])

    def _render_prompt_pack_with_fakes(self, *, prompt):
        from ui_panels import prompt_pack

        fake_st = _FakePromptPackStreamlit({})
        fake_components = _FakePromptPackComponents()

        original_st = prompt_pack.st
        original_components = prompt_pack.components
        try:
            prompt_pack.st = fake_st
            prompt_pack.components = fake_components
            prompt_pack.render_prompt_pack_panel(
                curr_id="2330",
                prompt=prompt,
            )
        finally:
            prompt_pack.st = original_st
            prompt_pack.components = original_components

        return fake_st, fake_components

    def test_prompt_pack_panel_renders_one_essential_prompt(self):
        fake_st, fake_components = self._render_prompt_pack_with_fakes(prompt="ESSENTIAL_PROMPT")

        self.assertEqual(fake_st.expander_calls[0]["label"], "📋 點此複製【精簡提示詞】至 Gemini Advanced 或 ChatGPT 發問")
        self.assertEqual(fake_st.text_area_calls[0]["value"], "ESSENTIAL_PROMPT")
        self.assertIn("copy_prompt_textarea_2330_", fake_st.text_area_calls[0]["key"])
        self.assertIn(json.dumps("ESSENTIAL_PROMPT", ensure_ascii=False), fake_components.html_calls[0]["body"])
        self.assertEqual(fake_components.html_calls[0]["height"], 105)

    def test_essential_prompt_builder_omits_every_missing_field(self):
        prompt = build_essential_version_prompt(
            app_title="WAY投資戰情室-2.5版",
            stock_id="2330",
            stock_name="台積電",
            fields=[
                ("現價", "980.00元"),
                ("TTM EPS", None),
                ("FY1 EPS", "N/A"),
                ("毛利率", "58.20%"),
                ("法人最低目標價", "未取得"),
            ],
        )

        self.assertIn("現價：980.00元", prompt)
        self.assertIn("毛利率：58.20%", prompt)
        self.assertNotIn("TTM EPS：", prompt)
        self.assertNotIn("FY1 EPS：", prompt)
        self.assertNotIn("法人最低目標價：", prompt)
        self.assertNotIn("N/A", prompt)

    def test_financial_panel_m10_margin_summary_renders_with_fake_streamlit(self):
        from ui_panels import financials

        fake_st = _FakePanelStreamlit()
        summary = {
            "available": True,
            "status": "usable",
            "status_label": "可納入品質係數",
            "category_name": "半導體｜晶圓代工 / HPC / 先進製程",
            "margin_quality": "A",
            "margin_rule_label": "高營益率 cap",
            "base_gross_margin_pct": 45,
            "gross_margin_low_pct": 35,
            "gross_margin_high_pct": 60,
            "base_operating_margin_pct": 35,
            "operating_margin_low_pct": 20,
            "operating_margin_high_pct": 50,
            "usage_label": "可納入 Dynamic Cap 品質係數",
        }

        original_st = financials.st
        try:
            financials.st = fake_st
            financials._render_m10_margin_benchmark_summary(summary)
            report = financials._build_m10_margin_benchmark_report(summary)
        finally:
            financials.st = original_st

        markdown_text = "\n".join(call["text"] for call in fake_st.markdown_calls)
        self.assertIn("M10 margin benchmark", markdown_text)
        self.assertIn("可納入品質係數", markdown_text)
        self.assertFalse(report.empty)
        self.assertIn("營益率 base / low / high", report["項目"].tolist())

    def test_stock_header_panel_renders_title_classification_and_summary(self):
        from ui_panels import stock_header

        fake_st = _FakePanelStreamlit(session_state={
            "ai_fetched_financials": {
                "2330": {"_stock_id": "2330", "forward_eps": 45.0},
            },
        })
        captured = {}
        profile = {
            "model_label": "晶圓代工 / HPC",
            "themes_text": "AI, HPC",
            "classification_source": "stock_mapping.py",
            "classification_needs_manual_review": False,
            "pe_trap_warning": False,
            "pe_model_suitable": True,
        }

        def fake_get_industry_profile(curr_id, stock_name, sector_disp, industry, ai_financials=None):
            captured.update({
                "curr_id": curr_id,
                "stock_name": stock_name,
                "sector_disp": sector_disp,
                "industry": industry,
                "ai_financials": ai_financials,
            })
            return profile

        original_st = stock_header.st
        original_get_watchlist = stock_header.get_watchlist
        original_toggle_watchlist = stock_header.toggle_watchlist
        original_get_industry_profile = stock_header.get_industry_valuation_profile
        original_translate = stock_header.translate_to_zh
        try:
            stock_header.st = fake_st
            stock_header.get_watchlist = lambda: []
            stock_header.toggle_watchlist = lambda *args, **kwargs: None
            stock_header.get_industry_valuation_profile = fake_get_industry_profile
            stock_header.translate_to_zh = lambda text: "中文公司簡介"
            sector_disp, rendered_profile = stock_header.render_stock_header_panel(
                curr_id="2330",
                stock_name="台積電",
                info={
                    "sector": "科技業",
                    "industry": "半導體",
                    "longBusinessSummary": "English business summary",
                },
            )
        finally:
            stock_header.st = original_st
            stock_header.get_watchlist = original_get_watchlist
            stock_header.toggle_watchlist = original_toggle_watchlist
            stock_header.get_industry_valuation_profile = original_get_industry_profile
            stock_header.translate_to_zh = original_translate

        markdown_text = "\n".join(call["text"] for call in fake_st.markdown_calls)
        self.assertEqual(sector_disp, "科技業")
        self.assertIs(rendered_profile, profile)
        self.assertEqual(captured["ai_financials"]["forward_eps"], 45.0)
        self.assertEqual(fake_st.button_calls[0]["label"], "☆ 加入自選")
        self.assertIn("台積電 (2330)", markdown_text)
        self.assertIn("估值模型：晶圓代工 / HPC", markdown_text)
        self.assertIn("題材標籤：AI, HPC", markdown_text)
        self.assertIn("分類來源：stock_mapping.py", markdown_text)
        self.assertEqual(fake_st.expander_calls[0]["label"], "📖 查看公司詳細營業項目簡介 (自動英翻中)")
        self.assertEqual(fake_st.write_calls, ["中文公司簡介"])

    def test_etf_panel_renders_fast_and_ai_holder_tables(self):
        from ui_panels import etf

        fast_rows = [{
            "etf_name": "元大台灣50",
            "etf_code": "0050",
            "weight": 7.123,
            "data_date": "2026-06-09",
            "source": "Yahoo",
        }]
        ai_rows = [{
            "etf_name": "主動統一台股增長",
            "etf_code": "00981A",
            "weight": 1.5,
            "data_date": "2026-06-09",
            "source": "投信公告",
            "data_type": "AI交叉補查",
        }]
        fake_st = _FakePanelStreamlit(session_state={
            "api_key": "TEST_KEY",
            "ai_etf_holders": {
                "2330": {
                    "etf_holders_ai": ai_rows,
                    "summary": "已交叉查詢主動式 ETF。",
                },
            },
        })

        original_st = etf.st
        original_get_stock_etf_holders = etf.get_stock_etf_holders
        try:
            etf.st = fake_st
            etf.get_stock_etf_holders = lambda curr_id, stock_name: fast_rows
            returned_rows = etf.render_etf_exposure_panel(curr_id="2330", stock_name="台積電")
        finally:
            etf.st = original_st
            etf.get_stock_etf_holders = original_get_stock_etf_holders

        self.assertEqual(returned_rows, fast_rows)
        self.assertEqual(len(fake_st.dataframe_calls), 2)
        fast_df = fake_st.dataframe_calls[0]["data"]
        ai_df = fake_st.dataframe_calls[1]["data"]
        self.assertEqual(fast_df.iloc[0]["ETF名稱"], "元大台灣50")
        self.assertEqual(fast_df.iloc[0]["持股比例"], "7.12%")
        self.assertEqual(ai_df.iloc[0]["代號"], "00981A")
        self.assertEqual(ai_df.iloc[0]["資料性質"], "AI交叉補查")
        self.assertEqual(fake_st.button_calls[0]["key"], "ai_etf_lookup_2330")
        self.assertFalse(fake_st.button_calls[0]["disabled"])
        self.assertTrue(any("AI 摘要：已交叉查詢主動式 ETF。" == text for text in fake_st.caption_calls))

    def test_chip_panel_renders_margin_credit_summary(self):
        from ui_panels import chips

        dates = pd.date_range("2026-05-01", periods=6, freq="B")
        inst_df = pd.DataFrame(
            {"Foreign": [100, 120, 80, 90, 110, 130], "Trust": [10, 20, 30, 40, 50, 60]},
            index=dates,
        )
        margin_df = pd.DataFrame({
            "date": dates,
            "stock_id": ["2330"] * 6,
            "MarginPurchaseBuy": [100, 120, 130, 140, 150, 160],
            "MarginPurchaseCashRepayment": [0, 0, 0, 0, 0, 0],
            "MarginPurchaseLimit": [5000] * 6,
            "MarginPurchaseSell": [50, 60, 70, 80, 90, 100],
            "MarginPurchaseTodayBalance": [1000, 1120, 1250, 1400, 1600, 1800],
            "MarginPurchaseYesterdayBalance": [950, 1000, 1120, 1250, 1400, 1600],
            "OffsetLoanAndShort": [0] * 6,
            "ShortSaleBuy": [0] * 6,
            "ShortSaleCashRepayment": [0] * 6,
            "ShortSaleLimit": [5000] * 6,
            "ShortSaleSell": [10, 20, 20, 30, 40, 50],
            "ShortSaleTodayBalance": [80, 90, 100, 120, 150, 180],
            "ShortSaleYesterdayBalance": [70, 80, 90, 100, 120, 150],
        })
        fake_st = _FakePanelStreamlit(session_state={"finmind_key": "TEST_TOKEN"})

        original_st = chips.st
        original_get_inst_data = chips.get_inst_data
        original_get_margin_credit_data = chips.get_margin_credit_data
        try:
            chips.st = fake_st
            chips.get_inst_data = lambda curr_id, fm_key="": inst_df
            chips.get_margin_credit_data = lambda curr_id, fm_key="": margin_df
            result = chips.render_chip_panels(
                curr_id="2330",
                info={"sharesOutstanding": 20_000_000, "heldPercentInsiders": 0.18, "heldPercentInstitutions": 0.22},
                ai_shares=None,
                eff_eg=0.20,
            )
        finally:
            chips.st = original_st
            chips.get_inst_data = original_get_inst_data
            chips.get_margin_credit_data = original_get_margin_credit_data

        markdown_text = "\n".join(call["text"] for call in fake_st.markdown_calls)
        self.assertTrue(result["margin_credit"]["available"])
        self.assertEqual(result["margin_credit"]["risk_label"], "偏熱")
        self.assertIn("信用交易風險", markdown_text)
        self.assertIn("融資使用率", markdown_text)
        self.assertEqual(len(fake_st.dataframe_calls), 1)

    def test_financial_audit_control_renders_existing_ai_snapshot(self):
        from ui_panels import financials

        ai_snapshot = {
            "_stock_id": "2330",
            "_stock_name": "台積電",
            "model_used": "Gemini 3.1 Pro Preview (付費版)",
            "forward_eps": 45.0,
            "_ai_validation_warnings": ["target_price_low 已自動排序"],
            "_ai_validation_status": "AI 欄位已校正",
        }
        fake_st = _FakePanelStreamlit(session_state={
            "api_key": "",
            "ai_fetched_financials": {"2330": dict(ai_snapshot)},
        })

        original_st = financials.st
        try:
            financials.st = fake_st
            temp_ai_fin, has_ai_fin_fetch = financials.render_ai_financial_audit_control(
                curr_id="2330",
                stock_name="台積電",
            )
        finally:
            financials.st = original_st

        markdown_text = "\n".join(call["text"] for call in fake_st.markdown_calls)
        self.assertTrue(has_ai_fin_fetch)
        self.assertEqual(temp_ai_fin["forward_eps"], 45.0)
        self.assertEqual(fake_st.button_calls[0]["label"], "🪄 啟動 AI 全方位校對與補齊財報")
        self.assertTrue(fake_st.button_calls[0]["disabled"])
        self.assertEqual(fake_st.button_calls[1]["key"], "toggle_ai_raw_btn_2330")
        self.assertFalse(fake_st.session_state["show_ai_raw_panel_2330"])
        self.assertIn("已校對", markdown_text)
        self.assertIn("Gemini 3.1 Pro Preview", markdown_text)
        self.assertTrue(any("AI 財報 JSON 已觸發合理性校驗" in text for text in fake_st.warning_calls))

    def test_financial_candidate_review_panel_updates_status(self):
        from ui_panels import financials

        candidates = build_financial_candidate_data(
            {"ttm_eps": 42.0, "_ai_source_trace": {"ttm_eps": {"source": "公開資訊觀測站"}}},
            stock_id="2330",
            stock_name="台積電",
            retrieved_at="2026-06-18T15:00:00",
        )
        candidate = candidates[0]
        safe_key = re.sub(r"[^A-Za-z0-9_]+", "_", candidate["candidate_id"])
        ai_snapshot = {
            "_stock_id": "2330",
            "_stock_name": "台積電",
            "model_used": "Gemini 3.1 Pro Preview (付費版)",
            "ttm_eps": 42.0,
            "_candidate_data": candidates,
        }
        fake_st = _FakePanelStreamlit(
            session_state={
                "api_key": "",
                "show_ai_raw_panel_2330": True,
                "ai_fetched_financials": {"2330": dict(ai_snapshot)},
                "financial_candidate_reviews": {},
            },
            button_values={
                f"candidate_review_2330_{safe_key}_accepted": True,
            },
        )
        updates = []

        def fake_update(**kwargs):
            updates.append(kwargs)
            return {
                "stock_id": kwargs["stock_id"],
                "candidate_id": kwargs["candidate_id"],
                "review_status": kwargs["review_status"],
                "decision_note": kwargs["decision_note"],
            }

        original_st = financials.st
        original_load_cache = financials.load_financial_candidate_review_cache
        original_update = financials.update_financial_candidate_review
        try:
            financials.st = fake_st
            financials.load_financial_candidate_review_cache = lambda *args, **kwargs: {"version": "test", "updated_at": "", "reviews": {}}
            financials.update_financial_candidate_review = fake_update
            temp_ai_fin, has_ai_fin_fetch = financials.render_ai_financial_audit_control(
                curr_id="2330",
                stock_name="台積電",
            )
        finally:
            financials.st = original_st
            financials.load_financial_candidate_review_cache = original_load_cache
            financials.update_financial_candidate_review = original_update

        self.assertTrue(has_ai_fin_fetch)
        self.assertEqual(updates[0]["review_status"], "accepted")
        self.assertTrue(fake_st.rerun_called)
        self.assertIn("審核狀態", fake_st.dataframe_calls[0]["data"].columns)
        review_key = f"2330::{candidate['candidate_id']}"
        self.assertEqual(fake_st.session_state.financial_candidate_reviews[review_key]["review_status"], "accepted")
        self.assertEqual(temp_ai_fin["_candidate_data"][0]["review_status"], "accepted")


if __name__ == "__main__":
    unittest.main()
