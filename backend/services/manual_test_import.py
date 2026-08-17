"""
manual_test_import.py
=====================

Pure Playwright-native importer for human-written manual test cases.
Converts CSV/Excel test cases into executable Playwright test steps
grounded against crawled DOM elements (forms, buttons, URLs) without
requiring any LLM/AI dependencies.
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

try:
    from services.clean_test_cases import normalize_csv, to_serializable
    from services.app_context_resolver import AppContext, resolve_case_playwright
except ImportError:
    from clean_test_cases import normalize_csv, to_serializable
    from app_context_resolver import AppContext, resolve_case_playwright


def convert_manual_cases_to_playwright_test_cases(path_or_file, app) -> List[Dict[str, Any]]:
    """
    Parses and grounds manual test cases into standard Playwright test case dicts.
    Runs 100% deterministically using Playwright DOM crawl context (NO AI/LLM).
    """
    cases = normalize_csv(path_or_file)
    app_ctx = AppContext(app.id)

    playwright_test_cases = []
    for case in cases:
        c = _as_dict(case)
        pw_steps = resolve_case_playwright(c, app_ctx, default_url=app.url)

        # Normalize category
        raw_cat = c.get("feature_area") or c.get("type") or "Generic"
        category = "Generic"
        if any(w in raw_cat.lower() for w in ["access", "auth", "login", "permission", "security"]):
            category = "Access Control"
        elif any(w in raw_cat.lower() for w in ["flow", "industry", "checkout", "payment", "booking", "cart"]):
            category = "Industry Flow"

        exp_result = c.get("expected_result") or "Verification successful."

        playwright_test_cases.append({
            "app": app.id,
            "title": c.get("title") or f"Test Case {c.get('test_id', '')}".strip(),
            "category": category,
            "expected_result": exp_result,
            "steps": pw_steps,
            "ai_generated": False,
            "generation_context": {
                "source": "bulk_manual_import",
                "test_id": c.get("test_id"),
                "feature_area": c.get("feature_area"),
                "type": c.get("type"),
                "severity": c.get("severity"),
                "expect_failure": c.get("expect_failure", False),
                "needs_review": c.get("needs_review", False),
                "preconditions": c.get("preconditions_raw", ""),
                "runner": "playwright"
            }
        })

    return playwright_test_cases


def import_manual_test_cases(csv_path_or_file, app_id):
    """
    Parses, grounds with Playwright, and directly saves TestCase objects in the database.
    """
    from core.models import Application, TestCase

    app = Application.objects.get(id=app_id)
    test_case_dicts = convert_manual_cases_to_playwright_test_cases(csv_path_or_file, app)

    objs_to_create = []
    for item in test_case_dicts:
        objs_to_create.append(TestCase(
            app=app,
            title=str(item.get("title"))[:255],
            category=item.get("category", "Generic"),
            expected_result=str(item.get("expected_result")),
            steps=item.get("steps", []),
            ai_generated=False,
            generation_context=item.get("generation_context", {})
        ))

    created = TestCase.objects.bulk_create(objs_to_create)
    logger.info(f"Imported {len(created)} Playwright manual test cases for app {app_id}")

    return {
        "app_id": app_id,
        "created_count": len(created),
        "total": len(test_case_dicts),
        "test_cases": test_case_dicts
    }


def _as_dict(case):
    from dataclasses import asdict, is_dataclass
    return asdict(case) if is_dataclass(case) else case


if __name__ == "__main__":
    import sys
    import json
    if len(sys.argv) < 2:
        print("usage: python manual_test_import.py <cases.csv>")
        raise SystemExit(1)
    cases = normalize_csv(sys.argv[1])
    print(json.dumps(to_serializable(cases), indent=2, ensure_ascii=False))