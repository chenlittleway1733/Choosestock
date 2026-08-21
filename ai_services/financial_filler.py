"""Post-processing for AI financial-fill responses."""

import datetime
import json

from ai_services.financial_schema import normalize_ai_source_metadata
from validators.candidate_review import build_financial_candidate_data
from validators.financial_validation import validate_ai_financial_json


def postprocess_financial_ai_payload(
    parsed,
    *,
    marker_data=None,
    stock_id="",
    stock_name="",
    target_year=None,
    used_model="",
    used_search=True,
    fallback_reason="",
    attempts=None,
    prompt_text="",
    system_prompt="",
):
    """Validate, source-normalize and candidate-wrap one AI financial payload."""
    if not isinstance(parsed, dict):
        return parsed

    marker_data = marker_data or {}
    parsed.update({k: v for k, v in marker_data.items() if v is not None and parsed.get(k) is None})
    parsed = normalize_ai_source_metadata(parsed)
    parsed = validate_ai_financial_json(parsed, stock_id=stock_id, stock_name=stock_name)
    parsed = normalize_ai_source_metadata(parsed)

    retrieved_at = datetime.datetime.now().isoformat(timespec="seconds")
    parsed["model_used"] = used_model
    parsed["ai_search_enabled"] = bool(used_search)
    parsed["fallback_reason"] = fallback_reason
    parsed["retrieved_at"] = retrieved_at
    parsed["attempts"] = attempts or []
    parsed["retry_policy"] = "Pro Only：gemini-3.1-pro-preview + Google Search；最多 3 次；不降級。"
    parsed["_candidate_data"] = build_financial_candidate_data(
        parsed,
        stock_id=stock_id,
        stock_name=stock_name,
        retrieved_at=retrieved_at,
        default_review_status="pending",
    )
    parsed["_candidate_data_status"] = f"pending_review_candidates={len(parsed['_candidate_data'])}"
    parsed["query_payload"] = json.dumps({
        "stock": f"{stock_name} ({stock_id})",
        "target_year": target_year,
        "model_used": used_model,
        "google_search_enabled": bool(used_search),
        "fallback_reason": fallback_reason or "無",
        "retry_policy": "Pro Only same-model retry: delays 0s, 3s, 8s; no downgrade.",
        "prompt": prompt_text,
        "system_instruction": system_prompt,
    }, ensure_ascii=False, indent=2)
    return parsed

