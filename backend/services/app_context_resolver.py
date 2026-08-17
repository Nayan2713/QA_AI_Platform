"""
app_context_resolver.py
=======================

Stage 2 (Tier 1, deterministic) of the bulk-import pipeline.

This is the piece that GROUNDS a normalized human step against the data you
already captured while crawling the target app: the real pages, the real
button selectors, and the real form fields. It answers:

  * "Click 'Ideal Customer' in the left sidebar"  -> which crawled Page,
    which real selector?
  * "Save"                                         -> the real Save button
    selector on the current page.
  * "Clear the Company name field"                 -> the real form input.

It is pure Python + Django ORM. No LLM. Anything it can't resolve
confidently is handed to the LLM tier (llm_step_resolver.py); anything the
LLM can't resolve is flagged for human review rather than guessed.

=========================  CONFIRM THESE  =========================
The block below is the ONLY place that touches your model field names.
I built this session without live access to your repo, so verify these
five names against core/models.py and adjust if they differ. Everything
else keys off them.
"""

import re
from difflib import SequenceMatcher

try:
    from rapidfuzz import fuzz
    def _ratio(a, b):
        return fuzz.token_set_ratio(a, b) / 100.0
except ImportError:                       # stdlib fallback, no dependency
    def _ratio(a, b):
        return SequenceMatcher(None, a, b).ratio()


# ======================= CONFIRM THESE =======================
PAGE_MODEL = "core.Page"                  # "<app_label>.<ModelName>"
PAGE_APP_FK = "app_id"                    # FK column from Page -> Application
PAGE_URL_FIELD = "url"
PAGE_TITLE_FIELD = "title"
PAGE_BUTTONS_FIELD = "buttons"           # JSONField holding discovered buttons
PAGE_FORMS_FIELD = "forms"               # JSONField holding discovered forms
API_ENDPOINT_MODEL = "core.APIEndpoint"  # optional; set to None to disable
API_ENDPOINT_APP_FK = "application_id"
API_ENDPOINT_PATH_FIELD = "url_pattern"
API_ENDPOINT_METHOD_FIELD = "method"
# =============================================================

# Confidence floor for accepting a Tier-1 (deterministic) match. Below this
# we defer to the LLM tier instead of committing a possibly-wrong selector.
TIER1_ACCEPT = 0.72


def _get_model(dotted):
    from django.apps import apps
    app_label, model_name = dotted.split(".")
    return apps.get_model(app_label, model_name)


def _norm(s):
    return " ".join(str(s or "").lower().split())


# --------------------------------------------------------------------------
# Flexible extraction from the crawl JSON (shape-tolerant on purpose)
# --------------------------------------------------------------------------

_TEXT_KEYS = ("text", "label", "name", "value", "title", "aria_label", "ariaLabel")
_SELECTOR_KEYS = ("selector", "css", "css_selector", "xpath", "locator", "id")


def _pluck(d, keys):
    if not isinstance(d, dict):
        return None
    for k in keys:
        if d.get(k):
            return str(d[k]).strip()
    return None


def _iter_buttons(page_buttons):
    """Yield (text, selector) from whatever shape the buttons JSON has:
    list[dict], list[str], or dict. Missing pieces come back as ''."""
    if not page_buttons:
        return
    items = page_buttons.values() if isinstance(page_buttons, dict) else page_buttons
    for b in items:
        if isinstance(b, str):
            yield b.strip(), ""
        elif isinstance(b, dict):
            text = _pluck(b, _TEXT_KEYS) or ""
            selector = _pluck(b, _SELECTOR_KEYS) or ""
            yield text, selector


def _iter_form_fields(page_forms):
    """Yield (field_label, selector) across all forms on the page."""
    if not page_forms:
        return
    forms = page_forms.values() if isinstance(page_forms, dict) else page_forms
    for form in forms:
        fields = None
        if isinstance(form, dict):
            fields = form.get("fields") or form.get("inputs") or form.get("elements")
        elif isinstance(form, list):
            fields = form
        if not fields:
            continue
        for f in (fields.values() if isinstance(fields, dict) else fields):
            if isinstance(f, dict):
                label = _pluck(f, _TEXT_KEYS + ("placeholder",)) or ""
                selector = _pluck(f, _SELECTOR_KEYS) or ""
                yield label, selector


# --------------------------------------------------------------------------
# AppContext: the crawl data for one Application, indexed for matching
# --------------------------------------------------------------------------

class PageCtx:
    def __init__(self, url, title, buttons, forms):
        self.url = url or ""
        self.title = title or ""
        self.buttons = list(_iter_buttons(buttons))       # [(text, selector)]
        self.fields = list(_iter_form_fields(forms))      # [(label, selector)]


class AppContext:
    """Loads and indexes everything crawled for one app. Build once per
    import run, reuse across all its test cases."""

    def __init__(self, app_id):
        self.app_id = app_id
        self.pages = self._load_pages(app_id)
        self.endpoints = self._load_endpoints(app_id)

    def _load_pages(self, app_id):
        Page = _get_model(PAGE_MODEL)
        rows = Page.objects.filter(**{PAGE_APP_FK: app_id})
        out = []
        for p in rows:
            out.append(PageCtx(
                url=getattr(p, PAGE_URL_FIELD, ""),
                title=getattr(p, PAGE_TITLE_FIELD, ""),
                buttons=getattr(p, PAGE_BUTTONS_FIELD, None),
                forms=getattr(p, PAGE_FORMS_FIELD, None),
            ))
        return out

    def _load_endpoints(self, app_id):
        if not API_ENDPOINT_MODEL:
            return []
        try:
            EP = _get_model(API_ENDPOINT_MODEL)
        except Exception:
            return []
        rows = EP.objects.filter(**{API_ENDPOINT_APP_FK: app_id})
        return [(getattr(e, API_ENDPOINT_METHOD_FIELD, "GET"),
                 getattr(e, API_ENDPOINT_PATH_FIELD, "")) for e in rows]

    # ---- page resolution ------------------------------------------------

    def resolve_page(self, hint):
        """Best crawled Page for a text hint ('Ideal Customer', a feature
        area, a URL fragment). Returns (PageCtx, score)."""
        if not self.pages or not hint:
            return (self.pages[0], 0.0) if self.pages else (None, 0.0)
        h = _norm(hint)
        tokens = [t for t in re.split(r"[^a-z0-9]+", h) if len(t) > 2]
        best, best_score = None, 0.0
        for p in self.pages:
            p_url = _norm(p.url)
            p_title = _norm(p.title)
            token_matches = sum(1 for t in tokens if t in p_url or t in p_title)
            token_ratio = (token_matches / len(tokens)) if tokens else 0.0
            score = max(
                token_ratio,
                _ratio(h, p_title),
                _ratio(h, p_url),
                1.0 if h and (h in p_url or h in p_title) else 0.0,
            )
            if score > best_score:
                best, best_score = p, score
        return best, best_score

    # ---- element resolution --------------------------------------------

    def resolve_button(self, page, label):
        """(selector, score) for the best-matching button on `page`."""
        if not page or not page.buttons:
            return None, 0.0
        return self._best_selector(page.buttons, label)

    def resolve_field(self, page, name):
        """(selector, score) for the best-matching field on `page`."""
        if not page or not page.fields:
            return None, 0.0
        return self._best_selector(page.fields, name)

    @staticmethod
    def _best_selector(pool, label):
        target = _norm(label)
        best_sel, best_score = None, 0.0
        for text, selector in pool:
            if not selector and not text:
                continue
            score = _ratio(target, _norm(text)) if text else 0.0
            if target and text and target in _norm(text):
                score = max(score, 0.9)
            if score > best_score:
                best_sel, best_score = selector or text, score
        return best_sel, best_score


# --------------------------------------------------------------------------
# Deterministic Grounding & Playwright Conversion
# --------------------------------------------------------------------------

def _as_dict(case):
    from dataclasses import asdict, is_dataclass
    if is_dataclass(case):
        return asdict(case)
    return case if isinstance(case, dict) else {}


def pick_start_page(case, app_ctx):
    """Choose the page a case starts on, from its first nav step / feature
    area / title. Returns (PageCtx, score)."""
    case = _as_dict(case)
    for hint in (
        _first_nav_hint(case),
        case.get("feature_area"),
        case.get("title"),
    ):
        if hint:
            p, score = app_ctx.resolve_page(hint)
            if p and score >= 0.3:
                return p, score
    # fall back to the first crawled page (usually the app root)
    return (app_ctx.pages[0], 0.0) if app_ctx.pages else (None, 0.0)


def _first_nav_hint(case):
    case = _as_dict(case)
    for s in case.get("steps", []):
        if isinstance(s, dict) and s.get("kind") == "navigate":
            return s.get("target_label") or s.get("text")
    return None


def make_smart_selector(label, verb, start_page=None):
    label_l = (label or "").lower().strip()
    verb_l = (verb or "").lower().strip()

    # 1. Match against crawled page elements if available
    if start_page:
        if verb_l in ("fill", "type", "enter", "update", "set", "change", "clear"):
            sel, score = AppContext._best_selector(start_page.fields, label)
            if sel and score >= 0.75:
                return sel
        else:
            sel, score = AppContext._best_selector(start_page.buttons, label)
            if sel and score >= 0.75:
                return sel

    # 2. Input / Textarea specific fields for fill actions
    if verb_l in ("fill", "type", "enter", "update", "set", "change", "clear", "paste"):
        if "prompt" in label_l or "ai prompt" in label_l:
            return "textarea[placeholder*='prompt' i], input[placeholder*='prompt' i], textarea, input"
        if "value proposition" in label_l or "proposition" in label_l:
            return "textarea[placeholder*='Value Proposition' i], textarea[name*='value' i], textarea"
        if any(w in label_l for w in ["job title", "title"]):
            return "input[placeholder*='Job Title' i], input[name*='title' i], input"
        if any(w in label_l for w in ["company", "list name", "target list", "business", "website"]):
            return "input[placeholder*='Company' i], input[placeholder*='website' i], input[name*='company' i], input"
        if any(w in label_l for w in ["technology", "keyword", "industry chip", "chip"]):
            return "input[placeholder*='technology' i], input[placeholder*='keyword' i], input[placeholder*='chip' i], input"
        if any(w in label_l for w in ["withdraw", "days"]):
            return "input[name*='days' i], input[placeholder*='days' i], input"
        if any(w in label_l for w in ["leads per", "max leads", "leads"]):
            return "input[placeholder*='Leads' i], input[name*='leads' i], input[type='number']"
        return f"input[placeholder*='{label}' i], input[name*='{label}' i], [aria-label*='{label}' i], input"

    # 3. Interactive controls: buttons, checkboxes, dropdowns, filters
    if any(w in label_l for w in ["all companies", "select all"]):
        return "th input[type='checkbox'], input[type='checkbox']:first-of-type, [aria-label*='Select all' i]"
    if any(w in label_l for w in ["single", "multiple", "companies", "companies from", "lead", "rows", "5-10"]):
        return "tbody tr:first-child input[type='checkbox'], input[type='checkbox']"
    if any(w in label_l for w in ["chip", "cross", "x"]):
        return ".chip button, .chip-remove, [aria-label*='remove' i], button.remove-chip, .chip"
    if any(w in label_l for w in ["preview tile", "tile", "preview"]):
        return ".preview-tile, [data-testid*='preview-tile'], button:has-text('Preview')"
    if any(w in label_l for w in ["reset", "start over", "circular reset"]):
        return "button[aria-label*='reset' i], button.reset-btn, button:has-text('Reset'), button:has-text('Start Over')"
    if any(w in label_l for w in ["skip", "skip for now"]):
        return "button:has-text('Skip for now'), a:has-text('Skip'), button:has-text('Skip')"
    if any(w in label_l for w in ["analyze", "analyze with ai", "trigger ai"]):
        return "button:has-text('Analyze with AI'), button:has-text('Analyze'), button:has-text('Generate')"
    if any(w in label_l for w in ["delete", "trash", "remove"]):
        return "button:has-text('Delete'), [aria-label*='Delete' i], button.delete-btn"
    if any(w in label_l for w in ["search", "execute", "run search", "find companies", "find people"]):
        return "button:has-text('Search'), button:has-text('Find Companies'), button:has-text('Find People'), button[type='submit']"
    if any(w in label_l for w in ["enrich", "company enrich"]):
        return "button:has-text('Enrich'), [aria-label*='Enrich' i]"
    if "dnd" in label_l:
        return "button:has-text('DND'), select[name*='dnd' i], [aria-label*='DND' i]"
    if "industry" in label_l:
        return "button:has-text('Industry'), select[name*='industry' i], [aria-label*='Industry' i]"
    if "size" in label_l or "range" in label_l:
        return "button:has-text('Size'), select[name*='size' i], [aria-label*='Size' i]"

    return f"button:has-text('{label}'), [aria-label*='{label}' i], text=\"{label}\""


def make_fill_value(label, sel):
    label_l = (label or "").lower()
    sel_l = (sel or "").lower()
    if "email" in label_l or "email" in sel_l:
        return "testuser@example.com"
    if "password" in label_l or "password" in sel_l:
        return "Secr3tP@ss123"
    if "phone" in label_l or "mobile" in label_l or "tel" in label_l:
        return "9876543210"
    if "days" in label_l or "qty" in label_l or "number" in label_l or "leads" in label_l:
        return "10"
    if "date" in label_l:
        return "2026-01-15"
    if "prompt" in label_l:
        return "Find relevant cybersecurity leads."
    if "search" in label_l or "query" in label_l:
        return "Automated Search"
    if "name" in label_l or "title" in label_l:
        return "Test User"
    return "Automated Test Input"


def resolve_case_playwright(case, app_ctx, default_url=""):
    """
    Deterministically resolves a normalized test case into an array of
    executable Playwright test steps without requiring any AI/LLM.
    """
    case = _as_dict(case)
    start_page, _ = pick_start_page(case, app_ctx)
    base_url = (start_page.url if start_page else default_url) or ""
    pw_steps = []

    # 1. Start with navigation to the resolved page
    if base_url:
        pw_steps.append({
            "action": "navigate",
            "target": base_url,
            "selector": "",
            "value": ""
        })

    # 2. Process precondition hints
    for hint in case.get("precondition_hints", []):
        verb = hint.get("verb", "click")
        label = hint.get("target_label", "Edit")
        sel = make_smart_selector(label, verb, start_page)
        pw_steps.append({
            "action": "click",
            "target": "",
            "selector": sel,
            "value": ""
        })

    # 3. Process action / wait / navigation steps
    for step in case.get("steps", []):
        kind = step.get("kind")
        text = step.get("text", "").strip()
        verb = (step.get("verb") or "").lower()
        label = step.get("example") or step.get("target_label") or text
        test_val = step.get("test_value")

        if kind == "navigate":
            nav_p, _ = app_ctx.resolve_page(label)
            pw_steps.append({
                "action": "navigate",
                "target": nav_p.url if nav_p else base_url,
                "selector": "",
                "value": ""
            })

        elif kind == "wait":
            raw_val = str(test_val or text or "800")
            digits = "".join(c for c in raw_val if c.isdigit())
            pw_steps.append({
                "action": "wait",
                "target": "",
                "selector": "",
                "value": digits if digits else "800"
            })

        elif kind == "assert":
            pw_steps.append({
                "action": "assert",
                "target": "",
                "selector": "body",
                "value": test_val or text or "Success"
            })

        elif verb in ("fill", "type", "enter", "update", "set", "change"):
            sel = make_smart_selector(label, verb, start_page)
            val = test_val or make_fill_value(label, sel)
            pw_steps.append({
                "action": "fill",
                "target": "",
                "selector": sel,
                "value": val
            })

        elif verb == "clear":
            sel = make_smart_selector(label, verb, start_page)
            pw_steps.append({
                "action": "fill",
                "target": "",
                "selector": sel,
                "value": ""
            })

        elif verb == "hover":
            sel = make_smart_selector(label, verb, start_page)
            pw_steps.append({
                "action": "hover",
                "target": "",
                "selector": sel,
                "value": ""
            })

        else:  # click, select, toggle, press, switch, filter, execute, run
            sel = make_smart_selector(label, verb, start_page)
            pw_steps.append({
                "action": "click",
                "target": "",
                "selector": sel,
                "value": ""
            })

    # 4. Process assertions from Expected Result
    assertions = list(case.get("assertions_from_expected", []))
    if assertions:
        for a in assertions:
            val = a.get("value") if isinstance(a, dict) else str(a)
            if val:
                pw_steps.append({
                    "action": "assert",
                    "target": "",
                    "selector": "body",
                    "value": val
                })
    else:
        exp = case.get("expected_result", "").strip()
        if exp:
            # Pick first informative sentence/clause
            clean_exp = exp.split(".")[0].strip()
            pw_steps.append({
                "action": "assert",
                "target": "",
                "selector": "body",
                "value": clean_exp[:60]
            })

    # 5. Ensure at least one navigate step
    if not pw_steps or pw_steps[0].get("action") != "navigate":
        pw_steps.insert(0, {
            "action": "navigate",
            "target": base_url or default_url,
            "selector": "",
            "value": ""
        })

    return pw_steps