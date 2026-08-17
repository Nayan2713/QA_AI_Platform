"""
clean_test_cases.py
===================

Stage 0 of the bulk-import pipeline: turn a human-written test-case CSV
(the kind a QA person fills in by hand) into a clean, structured JSON
intermediate that the grounding resolver (app_context_resolver +
llm_step_resolver) can consume.

This file has NO Django / project dependencies. It runs standalone so you
can test it on the real CSV before wiring anything into the platform:

    python clean_test_cases.py input.csv -o normalized.json

What it does
------------
1. Reads the CSV as Windows-1252 and normalises smart quotes / dashes /
   the multiply-sign close icon to plain ASCII, so later string matching
   is not defeated by curly quotes.
2. Drops the human-tracking columns (Status, Actual Result, Defect ID,
   Tester, Date, Notes) and keeps only what matters for execution.
3. Splits the multi-line "Test Steps" cell into ordered step lines.
4. Two-pass classifies every line into a KIND before any keyword scan:
   action / wait / navigate / assert / note — so a "Read the summary row"
   line is never mistaken for a click.
5. Pulls parenthetical notes ("(do NOT save)") and "e.g." examples OUT of
   the step text into separate fields, so they never become fake selectors.
6. Extracts the quoted target label ('Save', 'Ideal Customer') without the
   leading-character truncation bug (uses explicit quote parsing, never a
   lossy \\b regex).
7. Turns the "Expected Result" column into candidate assertions (quoted
   literals -> text_present) and keeps the full expected text for the LLM
   tier to expand.
8. Flags negative / validation cases as expect_failure=True so the executor
   and bug classifier know a blocked action is a PASS, not a bug.

The output is a list of NormalizedCase dicts. It does NOT yet contain real
selectors or real page URLs — that grounding happens in the next stage,
against your crawl data.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional

try:
    import pandas as pd
except ImportError:
    pd = None


# --------------------------------------------------------------------------
# 1. Text normalisation
# --------------------------------------------------------------------------

# Windows-1252 punctuation -> ASCII. These bytes are what made your CSV
# show up as "Non-ISO extended-ASCII".
_PUNCT_MAP = {
    "\u2018": "'", "\u2019": "'",          # curly single quotes
    "\u201c": '"', "\u201d": '"',          # curly double quotes
    "\u2013": "-", "\u2014": "-",          # en / em dash
    "\u2026": "...",                        # ellipsis
    "\u00b7": "-",                          # middle dot (used as a separator)
    "\u00d7": "x",                          # multiply sign (chip close icon)
    "\u00a0": " ",                          # non-breaking space
}


def normalize_text(s) -> str:
    if s is None:
        return ""
    s = str(s)
    for bad, good in _PUNCT_MAP.items():
        s = s.replace(bad, good)
    # collapse runs of whitespace but keep newlines meaningful for step splitting
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


# --------------------------------------------------------------------------
# 2. Line classification (two-pass: KIND first, target second)
# --------------------------------------------------------------------------

# Order matters: assertion / wait checks run BEFORE the action check, so a
# "Verify that ..." or "Read the ..." line can never fall through to CLICK.
_ASSERT_LEADS = (
    "verify", "check that", "confirm that", "ensure that", "observe that",
    "see that", "validate that", "should see", "should be", "should have",
    "must see", "must have", "must display", "must show",
)
_WAIT_LEADS = ("wait", "reload", "refresh", "sleep", "pause")
_NAV_LEADS = ("go to", "open", "navigate", "visit", "return to", "back to")
_ACTION_VERBS = (
    "click", "tap", "press", "edit", "add", "remove", "delete", "clear",
    "type", "enter", "fill", "select", "choose", "toggle", "paste",
    "upload", "drag", "hover", "check", "uncheck", "switch", "change",
    "update", "set", "execute", "run", "search", "filter", "save",
    "cancel", "submit", "apply", "confirm", "open", "close", "start",
)


# tentative phrasings that hide a real action verb
_GERUND_MAP = {
    "typing": "type", "adding": "add", "clicking": "click", "saving": "save",
    "confirming": "confirm", "selecting": "select", "entering": "enter",
    "filling": "fill", "toggling": "toggle", "removing": "remove",
    "deleting": "delete", "clearing": "clear", "pasting": "paste",
    "choosing": "choose", "uploading": "upload", "editing": "edit",
    "updating": "update", "changing": "change", "setting": "set",
}


def canonicalize(text: str) -> str:
    """Rewrite tentative phrasings to plain imperative so classification and
    target extraction see the real verb. 'Attempt to Save' -> 'Save',
    'Try typing X' -> 'type X'. Non-destructive: used for parsing only, the
    original text is still stored on the step."""
    t = re.sub(r"^\s*\d+[\.\)]\s*", "", text).strip()
    t = re.sub(r"(?i)^(?:attempt|try)\s+to\s+", "", t)
    # "try typing X" / "try adding X" -> "type X"
    m = re.match(r"(?i)^try\s+(\w+ing)\b(.*)$", t)
    if m:
        base = _GERUND_MAP.get(m.group(1).lower())
        if base:
            t = base + m.group(2)
        else:
            t = re.sub(r"(?i)^try\s+", "", t)
    return t


def classify_line(text: str) -> str:
    t = canonicalize(text).lower()
    for lead in _WAIT_LEADS:
        if t.startswith(lead):
            return "wait"
    for lead in _ASSERT_LEADS:
        if t.startswith(lead):
            return "assert"
    for lead in _NAV_LEADS:
        if t.startswith(lead):
            return "navigate"
    for verb in _ACTION_VERBS:
        if t.startswith(verb):
            return "action"
    if any(v in t for v in ("click", "select", "toggle", "type", "enter", "fill", "clear", "choose", "update", "set")):
        return "action"
    return "assert"


# --------------------------------------------------------------------------
# 3. Pulling notes / examples / target labels / test values out of a step line
# --------------------------------------------------------------------------

def _extract_parentheticals(text: str):
    """Return (clean_text, note, example). '(e.g. X)' -> example, other
    '(...)' -> note. Removes them from the step body."""
    note = None
    example = None
    parens = re.findall(r"\(([^)]*)\)", text)
    for p in parens:
        p_stripped = p.strip()
        if re.match(r"(?i)^e\.?g\.?[:\s]", p_stripped):
            example = re.sub(r"(?i)^e\.?g\.?[:\s]+", "", p_stripped).strip().strip("'\"")
        else:
            note = p_stripped
    clean = re.sub(r"\s*\([^)]*\)", "", text).strip()
    return clean, note, example


def _extract_target_label(text: str) -> Optional[str]:
    """Extracts the button, field, or dropdown name without confusing it with the test value."""
    # 1. Key = Value pattern e.g. "Select DND = Yes" -> "DND"
    eq_match = re.match(r"(?i)^\s*\d*[\.\)]?\s*(?:select|choose|filter|set|toggle)\s+(.+?)\s*=", text)
    if eq_match:
        return eq_match.group(1).strip()

    # 2. Pattern: Paste ... into <field>
    paste_match = re.search(r"(?i)\binto\s+(['\"]?[a-zA-Z0-9_\s-]+?['\"]?)(?:\.|$|\s+and)", text)
    if paste_match:
        return paste_match.group(1).strip().strip("'\"")

    # 3. Pattern: Leave the <field> blank
    leave_match = re.search(r"(?i)\bleave\s+(?:the\s+)?(.+?)\s+blank", text)
    if leave_match:
        return leave_match.group(1).strip()

    # 4. Pattern: Add '<value>' as an <field> chip
    chip_match = re.search(r"(?i)\bas\s+(?:an?\s+)?(.+?)\s+chip", text)
    if chip_match:
        return chip_match.group(1).strip()

    # 5. Pattern: <verb> <target_label> (with|to|as|into|from) <value>
    val_clause = re.match(
        r"(?i)^\s*\d*[\.\)]?\s*"
        r"(?:click|tap|press|toggle|select|choose|open|go to|add|edit|clear|fill|type|enter|update|change|set|filter|hover|trigger)\s+"
        r"(?:the\s+|a\s+|an\s+|on\s+|into\s+|all\s+|multiple\s+|over\s+|each\s+of\s+the\s+|each\s+of\s+)?"
        r"(['\"]?[^'\"]+?['\"]?)"
        r"\s+(?:with|to|as|into|from|for|field|dropdown|button|tab|link)\b",
        text
    )
    if val_clause:
        raw = val_clause.group(1).strip().strip("'\"")
        raw = re.sub(r"(?i)\s+(?:field|dropdown|button|tab|link)$", "", raw).strip()
        if raw:
            return raw

    # 6. Quotes if directly mentioned without with/to: e.g. Click "Save", Clear 'Job Titles', Confirm 'Delete'
    quotes = re.findall(r"['\"]([^'\"]+)['\"]", text)
    if quotes and not any(w in text.lower() for w in [" with ", " to "]):
        return quotes[0].strip()

    # 7. Leading action verb e.g. "Click Save", "Hover over Enrich", "Select all companies"
    m = re.match(
        r"(?i)^\s*\d*[\.\)]?\s*"
        r"(?:click|tap|press|toggle|select|choose|open|go to|add|edit|clear|fill|type|enter|update|change|set|filter|hover|trigger)\s+"
        r"(?:the\s+|a\s+|an\s+|on\s+|into\s+|all\s+|multiple\s+|over\s+|each\s+of\s+the\s+|each\s+of\s+)?"
        r"(.+)$",
        text,
    )
    if m:
        raw_target = m.group(1)
        obj = re.split(r"\s+(?:in|on|under|from|to|with|and then|then|for)\s+|(?:\bfield\b|\bdropdown\b|\bbutton\b|\btab\b|\blink\b)", raw_target, maxsplit=1, flags=re.IGNORECASE)[0]
        return obj.strip().rstrip(".").strip().strip("'\"")

    return None


def _extract_test_value(text: str) -> Optional[str]:
    """Extracts explicit test value from phrasing like 'with X', 'to X', '= Yes'."""
    # 1. Quoted value after with/to/as/into/enter/type/fill
    m = re.search(r"(?i)\b(?:with|to|as|into|enter|type|fill)\s+['\"]([^'\"]+)['\"]", text)
    if m:
        return m.group(1).strip()
    # 2. Key = Value pattern e.g. DND = Yes, Has Leads = No
    m = re.search(r"=\s*([A-Za-z0-9_-]+)", text)
    if m:
        return m.group(1).strip()
    # 3. Quoted literal anywhere in the text
    quotes = re.findall(r"['\"]([^'\"]+)['\"]", text)
    if len(quotes) >= 2:
        return quotes[-1].strip()
    elif len(quotes) == 1 and any(w in text.lower() for w in ["with", "to", "as", "enter", "type", "fill"]):
        return quotes[0].strip()
    return None


def _extract_location_hint(text: str) -> Optional[str]:
    """'in the left sidebar', 'top right', 'under the header' -> hint."""
    m = re.search(r"(?i)\b(?:in|on|under|at)\s+the\s+([a-z ]+?)(?:\.|$)", text)
    if m:
        return m.group(1).strip()
    return None


# --------------------------------------------------------------------------
# 4. Expected Result -> candidate assertions
# --------------------------------------------------------------------------

def expected_to_assertions(expected: str):
    assertions = []
    for lit in re.findall(r"['\"]([^'\"]+)['\"]", expected):
        lit = lit.strip()
        if lit:
            assertions.append({"type": "text_present", "value": lit})
    return assertions


# --------------------------------------------------------------------------
# 5. Preconditions -> setup step hints
# --------------------------------------------------------------------------

def preconditions_to_hints(precond: str):
    hints = []
    p = precond.lower()
    if "edit mode" in p:
        hints.append({"kind": "action", "verb": "click", "target_label": "Edit",
                      "reason": "precondition: In Edit mode"})
    if "generated-icp review" in p or "review screen" in p:
        hints.append({"kind": "navigate", "target_hint": "ICP review screen",
                      "reason": "precondition: on review screen"})
    return hints


# --------------------------------------------------------------------------
# 6. Data structures
# --------------------------------------------------------------------------

@dataclass
class Step:
    order: int
    kind: str                 # action | wait | navigate | assert
    text: str                 # cleaned step text (notes/examples removed)
    verb: Optional[str] = None
    target_label: Optional[str] = None
    test_value: Optional[str] = None
    location_hint: Optional[str] = None
    note: Optional[str] = None
    example: Optional[str] = None
    resolution: str = "pending"


@dataclass
class NormalizedCase:
    test_id: str
    title: str
    feature_area: str
    type: str
    severity: str
    expect_failure: bool
    preconditions_raw: str
    precondition_hints: list = field(default_factory=list)
    test_data: str = ""
    expected_result: str = ""
    assertions_from_expected: list = field(default_factory=list)
    raw_steps: list = field(default_factory=list)
    steps: list = field(default_factory=list)
    needs_review: bool = False    # set True when a step could not extract a target


_NEGATIVE_TYPES = {"negative", "validation"}
_NEGATIVE_AREAS = {"validation"}

# verbs whose button label is the verb itself -> no separate target needed
_SELF_NAMING_VERBS = {
    "save", "cancel", "submit", "apply", "reload", "refresh", "continue",
    "next", "back", "skip", "close", "logout", "login", "reset", "confirm",
}


def _leading_verb(text: str) -> Optional[str]:
    m = re.match(r"(?i)^\s*\d*[\.\)]?\s*([a-z]+)", text)
    return m.group(1).lower() if m else None


def build_case(row: dict) -> NormalizedCase:
    test_id = normalize_text(row.get("Test ID"))
    ttype = normalize_text(row.get("Type"))
    area = normalize_text(row.get("Feature Area"))
    expected = normalize_text(row.get("Expected Result"))

    expect_failure = (ttype.lower() in _NEGATIVE_TYPES
                      or area.lower() in _NEGATIVE_AREAS)

    case = NormalizedCase(
        test_id=test_id,
        title=normalize_text(row.get("Title")),
        feature_area=area,
        type=ttype,
        severity=normalize_text(row.get("Severity")),
        expect_failure=expect_failure,
        preconditions_raw=normalize_text(row.get("Preconditions")),
        precondition_hints=preconditions_to_hints(normalize_text(row.get("Preconditions"))),
        test_data=normalize_text(row.get("Test Data")),
        expected_result=expected,
        assertions_from_expected=expected_to_assertions(expected),
    )

    raw = normalize_text(row.get("Test Steps"))
    # split on newlines OR on a numbered enumerator anywhere in the cell
    lines = re.split(r"\n+|(?=\b\d+[\.\)]\s)", raw)
    lines = [l.strip() for l in lines if l and l.strip()]
    case.raw_steps = lines

    order = 0
    for line in lines:
        clean, note, example = _extract_parentheticals(line)
        # drop the leading enumerator from the stored text
        clean_body = re.sub(r"^\s*\d+[\.\)]\s*", "", clean).strip()
        if not clean_body:
            continue
        order += 1
        canon = canonicalize(clean_body)
        kind = classify_line(clean_body)
        step = Step(
            order=order,
            kind=kind,
            text=clean_body,
            verb=_leading_verb(canon) if kind in ("action", "navigate") else None,
            target_label=_extract_target_label(canon) if kind in ("action", "navigate") else None,
            test_value=_extract_test_value(clean_body),
            location_hint=_extract_location_hint(clean_body),
            note=note,
            example=example,
        )
        # a missing target only matters for generic interaction verbs; verbs
        # like "save"/"cancel"/"apply" name their own button, and an example
        # ('e.g. Company name') gives the resolver something to match on.
        if (kind in ("action", "navigate")
                and not step.target_label
                and not step.example
                and (step.verb or "") not in _SELF_NAMING_VERBS):
            case.needs_review = True
        case.steps.append(step)

    # Flag for review only when there is genuinely nothing to check: no
    # assert step, no quoted literal, AND an empty Expected Result. Prose
    # Expected Results are fine here -- the LLM tier turns them into
    # structural assertions downstream, so they are NOT a review reason.
    has_assert = (any(s.kind == "assert" for s in case.steps)
                  or case.assertions_from_expected
                  or bool(case.expected_result.strip()))
    if not has_assert:
        case.needs_review = True

    return case


# --------------------------------------------------------------------------
# 7. Entry point
# --------------------------------------------------------------------------

_DROP_COLUMNS = {"Status", "Actual Result", "Defect ID", "Tester", "Date", "Notes"}


def load_rows(path_or_file):
    """Loads CSV rows from a file path, file-like object, or string."""
    import io
    import csv

    if isinstance(path_or_file, str) and ('\n' in path_or_file or '\r' in path_or_file):
        # Raw text content passed directly
        stream = io.StringIO(path_or_file)
        return list(csv.DictReader(stream))

    if hasattr(path_or_file, 'read'):
        raw = path_or_file.read()
        if isinstance(raw, bytes):
            text = ""
            for enc in ['utf-8-sig', 'cp1252', 'utf-8', 'latin-1']:
                try:
                    text = raw.decode(enc)
                    if text:
                        break
                except Exception:
                    continue
            if not text:
                text = raw.decode('latin-1', errors='replace')
        else:
            text = str(raw)
        stream = io.StringIO(text)
        return list(csv.DictReader(stream))

    if isinstance(path_or_file, str):
        if pd is not None:
            for enc in ['cp1252', 'utf-8-sig', 'utf-8', 'latin-1']:
                try:
                    df = pd.read_csv(path_or_file, encoding=enc, dtype=str, keep_default_na=False)
                    return df.to_dict("records")
                except Exception:
                    continue
        for enc in ['cp1252', 'utf-8-sig', 'utf-8', 'latin-1']:
            try:
                with open(path_or_file, encoding=enc, newline="") as fh:
                    return list(csv.DictReader(fh))
            except Exception:
                continue

    return []


def normalize_csv(path_or_file):
    rows = load_rows(path_or_file)
    cases = []
    for idx, row in enumerate(rows):
        row = {k: v for k, v in row.items() if k not in _DROP_COLUMNS}
        # Fall back to Title or Scenario if Test ID column is missing
        test_id = normalize_text(row.get("Test ID")) or normalize_text(row.get("ID")) or f"TC-{idx+1:03d}"
        row["Test ID"] = test_id
        if not normalize_text(row.get("Title")) and not normalize_text(row.get("Test Steps")) and not normalize_text(row.get("Steps")):
            continue
        cases.append(build_case(row))
    return cases


def to_serializable(cases):
    out = []
    for c in cases:
        d = asdict(c)
        out.append(d)
    return out


def main():
    ap = argparse.ArgumentParser(description="Normalise a human test-case CSV.")
    ap.add_argument("csv", help="path to the test-case CSV")
    ap.add_argument("-o", "--out", default="normalized.json", help="output JSON path")
    args = ap.parse_args()

    cases = normalize_csv(args.csv)
    data = to_serializable(cases)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)

    review = [c.test_id for c in cases if c.needs_review]
    print(f"Normalised {len(cases)} cases -> {args.out}")
    print(f"  negative/validation (expect_failure): "
          f"{sum(1 for c in cases if c.expect_failure)}")
    print(f"  flagged needs_review: {len(review)} {review}")


if __name__ == "__main__":
    main()