"""
llm_step_resolver.py
====================

Stage 2 (Tier 2) + orchestration for the bulk-import pipeline.

Responsibilities:
  1. resolve_case(case, app_ctx)  -- the orchestrator. Runs Tier-1
     deterministic grounding (app_context_resolver.ground_step); for every
     step Tier-1 couldn't confidently resolve, and for every prose
     Expected Result, it asks the local LLM to resolve against the SAME
     crawl data. Whatever the LLM can't resolve is flagged, never guessed.
  2. A keyword-only fallback so that if Ollama is offline the import still
     produces runnable (if less precise) steps -- mirroring the platform's
     existing deterministic-fallback philosophy.
  3. to_executor_step()  -- maps a grounded step to the exact JSON shape
     your Playwright/browser-use executor consumes.

======================  CONFIRM THESE  ======================
- LLM import path (get_llm) -- point it at your real llm service.
- to_executor_step() -- match your executor's action schema.
=============================================================
"""

import json
import re

from app_context_resolver import ground_step, pick_start_page, TIER1_ACCEPT

# ---- CONFIRM: your LLM helper. Same one test generation already uses. ----
try:
    from services.llm_service import get_llm          # <-- adjust path
except Exception:
    get_llm = None


# --------------------------------------------------------------------------
# Compact crawl context for the LLM prompt
# --------------------------------------------------------------------------

def _page_context_block(page, limit=40):
    if not page:
        return "(no page resolved)"
    lines = [f"PAGE url={page.url!r} title={page.title!r}", "BUTTONS:"]
    for text, sel in page.buttons[:limit]:
        lines.append(f"  - label={text!r} selector={sel!r}")
    lines.append("FIELDS:")
    for label, sel in page.fields[:limit]:
        lines.append(f"  - label={label!r} selector={sel!r}")
    return "\n".join(lines)


_SYSTEM = (
    "You convert one human QA step into a single concrete browser action "
    "grounded in the provided page data. You may ONLY use selectors that "
    "appear in BUTTONS/FIELDS. If nothing fits, return resolved=false. "
    "Respond with ONE JSON object and nothing else."
)

_STEP_PROMPT = """Page data:
{ctx}

Human step: {text}
Verb hint: {verb}
Target hint: {label}

Return JSON:
{{"resolved": true|false, "action": "click|fill|clear|select|toggle|navigate|wait",
  "selector": "<one selector copied verbatim from the data, or null>",
  "value": "<text to type / url, or null>",
  "confidence": 0.0-1.0}}"""

_ASSERT_PROMPT = """Page data:
{ctx}

Expected result (human): {expected}

Turn this into concrete assertions using ONLY things checkable on the page.
Return JSON: {{"assertions": [
  {{"type": "text_present|element_visible|count_equals|url_contains",
    "value": "<literal text / selector / number / url fragment>"}} ]}}"""


def _call_llm(prompt):
    if get_llm is None:
        return None
    try:
        llm = get_llm()
        resp = llm.invoke([{"role": "system", "content": _SYSTEM},
                           {"role": "user", "content": prompt}])
        return getattr(resp, "content", None) or str(resp)
    except Exception:
        return None


def _parse_json(text):
    if not text:
        return None
    text = re.sub(r"^```[a-z]*|```$", "", text.strip(), flags=re.MULTILINE).strip()
    # grab the first {...} block
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _llm_resolve_step(step, page):
    prompt = _STEP_PROMPT.format(
        ctx=_page_context_block(page),
        text=step.get("text", ""),
        verb=step.get("verb") or "",
        label=step.get("example") or step.get("target_label") or "",
    )
    data = _parse_json(_call_llm(prompt))
    if not data or not data.get("resolved"):
        return None
    sel = data.get("selector")
    # guard: the LLM must not invent a selector outside the page data
    known = {s for _, s in (page.buttons + page.fields)} if page else set()
    if sel and known and sel not in known:
        return None
    return {"resolved": True, "action": data.get("action"), "selector": sel,
            "value": data.get("value"),
            "score": float(data.get("confidence") or 0.6), "source": "llm"}


def _llm_assertions(expected, page):
    if not expected:
        return []
    data = _parse_json(_call_llm(_ASSERT_PROMPT.format(
        ctx=_page_context_block(page), expected=expected)))
    return (data or {}).get("assertions", []) or []


# --------------------------------------------------------------------------
# Keyword fallback (Ollama offline) -- ungrounded but runnable
# --------------------------------------------------------------------------

def _keyword_step(step):
    verb = (step.get("verb") or "").lower()
    label = step.get("example") or step.get("target_label") or verb
    if step.get("kind") == "wait":
        return {"action": "wait", "selector": None, "value": step.get("text"),
                "source": "keyword", "score": 0.3}
    if verb in ("fill", "type", "enter", "paste", "clear"):
        act = "clear" if verb == "clear" else "fill"
        return {"action": act, "selector": f"text={label}", "value": None,
                "source": "keyword", "score": 0.3}
    return {"action": "click", "selector": f"text={label}", "value": None,
            "source": "keyword", "score": 0.3}


# --------------------------------------------------------------------------
# Executor schema mapping  -- CONFIRM against your runner
# --------------------------------------------------------------------------

def to_executor_step(grounded, description="", expect_failure=False):
    """Map a grounded step to your executor's step schema. This is the one
    place to edit if your Playwright/browser-use runner expects different
    keys."""
    return {
        "action": grounded.get("action"),
        "selector": grounded.get("selector"),
        "value": grounded.get("value"),
        "assertion": grounded.get("assertion"),
        "description": description,
        "expect_failure": expect_failure,
        "meta": {
            "source": grounded.get("source"),
            "confidence": round(float(grounded.get("score") or 0.0), 3),
        },
    }


# --------------------------------------------------------------------------
# Orchestrator: normalized case -> grounded, executor-ready steps
# --------------------------------------------------------------------------

def resolve_case(case, app_ctx, use_llm=True):
    """Ground a single normalized case (dict from clean_test_cases) against
    crawl data. Returns:

        {"actions": [...executor steps...],
         "needs_review": bool,
         "provenance": {"matched": n, "llm": n, "keyword": n, "unresolved": n}}
    """
    start_page, _ = pick_start_page(case, app_ctx)
    expect_failure = bool(case.get("expect_failure"))
    actions, prov = [], {"matched": 0, "llm": 0, "keyword": 0, "unresolved": 0}
    needs_review = bool(case.get("needs_review"))

    # 0. always start by navigating to the resolved start page
    if start_page:
        actions.append(to_executor_step(
            {"action": "navigate", "selector": None, "value": start_page.url,
             "source": "matched", "score": 1.0},
            description=f"Go to {start_page.title or start_page.url}"))
        prov["matched"] += 1

    # 1. expand precondition hints (e.g. "In Edit mode" -> click Edit)
    for hint in case.get("precondition_hints", []):
        g = ground_step({"kind": hint.get("kind", "action"),
                          "verb": hint.get("verb"),
                          "target_label": hint.get("target_label"),
                          "text": hint.get("reason", "")},
                         start_page, app_ctx)
        actions.append(to_executor_step(g, description=hint.get("reason", ""),
                                        expect_failure=expect_failure))
        prov[g["source"] if g["resolved"] else "unresolved"] += 1

    # 2. the actual steps
    for step in case.get("steps", []):
        if step.get("kind") == "assert":
            continue  # assertions handled from Expected Result below
        g = ground_step(step, start_page, app_ctx)
        if not g["resolved"] and use_llm:
            llm_g = _llm_resolve_step(step, start_page)
            if llm_g:
                g = llm_g
        if not g["resolved"] and g.get("source") != "llm":
            kw = _keyword_step(step)
            g = {**kw, "resolved": False}
            needs_review = True
        actions.append(to_executor_step(g, description=step.get("text", ""),
                                        expect_failure=expect_failure))
        key = g.get("source", "unresolved")
        prov[key if key in prov else "unresolved"] += 1

    # 3. assertions: quoted literals from Expected + LLM-expanded structural ones
    assertions = list(case.get("assertions_from_expected", []))
    if use_llm:
        assertions += _llm_assertions(case.get("expected_result", ""), start_page)
    for a in assertions:
        actions.append(to_executor_step(
            {"action": "assert", "selector": None, "value": None,
             "assertion": a, "source": "expected", "score": 0.8},
            description=f"Assert: {a.get('type')} {a.get('value')}",
            expect_failure=expect_failure))
    if not assertions:
        needs_review = True   # a test that checks nothing is not a test

    return {"actions": actions, "needs_review": needs_review, "provenance": prov}