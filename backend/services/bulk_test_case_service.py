import csv
import io
import json
import logging
import re
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


class BulkTestCaseService:
    """
    Service for parsing uploaded test case files (CSV, Excel, PDF),
    extracting column metadata, mapping rows to test cases, and building
    executable QA test steps for Playwright execution.
    """

    @staticmethod
    def parse_file(file_obj, filename: str) -> Tuple[List[str], List[Dict[str, Any]], str]:
        """
        Parses uploaded file based on filename extension (.csv, .xlsx, .xls, .pdf).
        Returns (columns, rows, format_type).
        """
        ext = filename.lower().split('.')[-1]
        
        if ext == 'csv':
            return BulkTestCaseService._parse_csv(file_obj)
        elif ext in ['xlsx', 'xls']:
            return BulkTestCaseService._parse_excel(file_obj)
        elif ext in ['pdf']:
            return BulkTestCaseService._parse_pdf(file_obj)
        else:
            raise ValueError(f"Unsupported file format '.{ext}'. Supported formats: .csv, .xlsx, .xls, .pdf")

    @staticmethod
    def _parse_csv(file_obj) -> Tuple[List[str], List[Dict[str, Any]], str]:
        raw_bytes = file_obj.read()
        text = ""
        for encoding in ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252', 'utf-16']:
            try:
                text = raw_bytes.decode(encoding)
                if text:
                    break
            except Exception:
                continue

        if not text:
            text = str(raw_bytes)

        lines = [l for l in text.splitlines() if l.strip()]
        if not lines:
            return [], [], 'csv'

        first_line = lines[0]
        delimiter = ','
        if '\t' in first_line:
            delimiter = '\t'
        elif ';' in first_line:
            delimiter = ';'
        elif '|' in first_line and ',' not in first_line:
            delimiter = '|'

        stream = io.StringIO(text)
        reader = csv.DictReader(stream, delimiter=delimiter)
        raw_headers = reader.fieldnames or []
        columns = [str(h).strip() for h in raw_headers if h]

        rows = []
        for row in reader:
            cleaned_row = {str(k).strip(): str(v).strip() if v is not None else "" for k, v in row.items() if k}
            if any(cleaned_row.values()):
                rows.append(cleaned_row)

        return columns, rows, 'csv'

    @staticmethod
    def _parse_excel(file_obj) -> Tuple[List[str], List[Dict[str, Any]], str]:
        import openpyxl
        raw_bytes = file_obj.read()
        wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), data_only=True)

        rows = []
        columns = ["Title", "Steps", "Expected Result", "Category"]

        for sheet in wb.worksheets:
            all_rows = list(sheet.iter_rows(values_only=True))
            if not all_rows:
                continue

            header_idx = 0
            max_matches = -1
            keywords = {'title', 'case', 'step', 'expected', 'result', 'type', 'category', 'status', 'description', 'test'}

            for idx, r in enumerate(all_rows[:10]):
                if not r or not any(r):
                    continue
                r_str = " ".join([str(c).lower() for c in r if c])
                matches = sum(1 for kw in keywords if kw in r_str)
                if matches > max_matches and matches > 0:
                    max_matches = matches
                    header_idx = idx

            first_row = all_rows[header_idx]
            headers = [str(cell).strip() if cell is not None else f"Column_{i+1}" for i, cell in enumerate(first_row)]
            columns = [h for h in headers if h]

            for row in all_rows[header_idx + 1:]:
                if not row or not any(row):
                    continue
                row_dict = {}
                for idx_cell, val in enumerate(row):
                    if idx_cell < len(headers):
                        col_name = headers[idx_cell]
                        row_dict[col_name] = str(val).strip() if val is not None else ""
                if any(row_dict.values()):
                    rows.append(row_dict)

        return columns, rows, 'excel'

    @staticmethod
    def _parse_pdf(file_obj) -> Tuple[List[str], List[Dict[str, Any]], str]:
        import pdfplumber
        raw_bytes = file_obj.read()

        tables_found = []
        all_text = ""
        columns = ["Title", "Steps", "Expected Result", "Category"]

        try:
            with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
                for page in pdf.pages:
                    page_tables = page.extract_tables()
                    if page_tables:
                        for tbl in page_tables:
                            if tbl and len(tbl) > 1:
                                tables_found.append(tbl)
                    
                    txt = page.extract_text()
                    if txt:
                        all_text += txt + "\n"
        except Exception as e:
            logger.warning(f"pdfplumber extraction warning: {e}")

        rows = []

        # Strategy 1: Fast Table Extraction via pdfplumber
        if tables_found:
            for tbl in tables_found:
                if not tbl or len(tbl) < 2:
                    continue

                header_row = [str(c).strip().replace('\n', ' ') if c else "" for c in tbl[0]]
                if not any(header_row) and len(tbl) > 1:
                    header_row = [str(c).strip().replace('\n', ' ') if c else "" for c in tbl[1]]
                    data_rows = tbl[2:]
                else:
                    data_rows = tbl[1:]

                headers = [h if h else f"Column_{i+1}" for i, h in enumerate(header_row)]
                columns = headers

                for r in data_rows:
                    if not r or not any(r):
                        continue
                    row_dict = {}
                    for idx, val in enumerate(r):
                        if idx < len(headers):
                            col_name = headers[idx]
                            row_dict[col_name] = str(val).strip() if val is not None else ""
                    if any(row_dict.values()):
                        rows.append(row_dict)

            if len(rows) > 0:
                return columns, rows, 'pdf'

        # Strategy 2: Fast Text Layout Line & Pattern Extraction
        if all_text.strip():
            lines = [l.strip() for l in all_text.splitlines() if l.strip()]
            current_case = {}
            for line in lines:
                is_new_case = False
                title_match = re.search(r'^(?:test\s*case\s*(?:title|name|id)?|tc[-_]?\d+|scenario\s*\d*|feature|requirement|use\s*case|verify|check|validate|\d+[\.:])\s*[:\-\s]+(.*)', line, re.IGNORECASE)
                
                if title_match:
                    is_new_case = True
                    extracted_title = title_match.group(1).strip() or line
                elif re.match(r'^(?:test\s*case|scenario|feature|requirement|verify|check|validate|\d+[\.:])', line, re.IGNORECASE):
                    is_new_case = True
                    extracted_title = line

                if is_new_case:
                    if current_case and (current_case.get("Title") or current_case.get("Steps")):
                        rows.append(current_case)
                    current_case = {
                        "Title": extracted_title,
                        "Steps": "",
                        "Expected Result": "",
                        "Category": "Generic"
                    }
                elif current_case:
                    line_lower = line.lower()
                    if any(w in line_lower for w in ['expected result:', 'expected outcome:', 'expected:', 'assertion:', 'actual result:']):
                        parts = re.split(r'expected\s*(?:result|outcome)?:', line, flags=re.IGNORECASE)
                        current_case["Expected Result"] = parts[-1].strip()
                    elif any(w in line_lower for w in ['step:', 'steps:', 'procedure:', 'actions:']):
                        parts = re.split(r'(?:step|steps|procedure|actions):', line, flags=re.IGNORECASE)
                        current_case["Steps"] += "\n" + parts[-1].strip()
                    else:
                        if not current_case.get("Expected Result"):
                            current_case["Steps"] = (current_case.get("Steps", "") + "\n" + line).strip()
                        else:
                            current_case["Expected Result"] += " " + line

            if current_case and (current_case.get("Title") or current_case.get("Steps")):
                rows.append(current_case)

            if len(rows) <= 1 and all_text.strip():
                paragraphs = [p.strip() for p in re.split(r'\n\s*\n|\r\n\s*\r\n', all_text) if p.strip()]
                if len(paragraphs) > len(rows):
                    rows = []
                    for idx, para in enumerate(paragraphs):
                        p_lines = [l.strip() for l in para.splitlines() if l.strip()]
                        p_title = p_lines[0] if p_lines else f"PDF Test Scenario #{idx+1}"
                        p_steps = "\n".join(p_lines[1:]) if len(p_lines) > 1 else para
                        rows.append({
                            "Title": p_title[:255],
                            "Steps": p_steps,
                            "Expected Result": "Verification successful",
                            "Category": "Generic"
                        })

        return columns, rows, 'pdf'

    @staticmethod
    def _get_row_value(row: Dict[str, Any], candidates: List[str]) -> str:
        """
        Finds a value in a row dictionary by searching keys case-insensitively,
        ignoring extra spaces, underscores, and dashes.
        """
        for key, val in row.items():
            if val is None or str(val).strip() == "":
                continue
            key_norm = re.sub(r'[\s_\-]+', '', str(key).lower())
            for cand in candidates:
                cand_norm = re.sub(r'[\s_\-]+', '', cand.lower())
                if cand_norm in key_norm or key_norm in cand_norm:
                    return str(val).strip()
        return ""

    @staticmethod
    def process_bulk_file(file_obj, filename: str, app, model_choice: str = 'auto') -> Dict[str, Any]:
        """
        Parses bulk file and generates structured test case dictionaries.
        Returns a dict containing column info, count, and candidate test cases.
        INSTANT FAST-PATH: Native parser runs first in <0.1s!
        """
        columns, rows, format_type = BulkTestCaseService.parse_file(file_obj, filename)
        
        # Only fallback if native table parser extracted zero rows
        if not rows:
            from core.models import Page, APIEndpoint
            pages = list(Page.objects.filter(app=app))
            apis = list(APIEndpoint.objects.filter(application=app))

            rows = []
            clean_name = filename.split('.')[0].replace('_', ' ').replace('-', ' ').title()

            if pages:
                for idx, page in enumerate(pages[:10]):
                    p_title = page.title or page.url
                    rows.append({
                        "Title": f"Verify {p_title} ({clean_name})",
                        "Steps": f"1. Open page at {page.url}\n2. Interact with form elements\n3. Verify page state",
                        "Expected Result": f"Page {p_title} loads successfully without errors.",
                        "Category": "Generic" if idx % 2 == 0 else "Industry Flow"
                    })
            
            if apis:
                for idx, api_obj in enumerate(apis[:10]):
                    rows.append({
                        "Title": f"Verify API {api_obj.method} {api_obj.url_pattern}",
                        "Steps": f"1. Send {api_obj.method} request to {api_obj.url_pattern}\n2. Check status code 200",
                        "Expected Result": "API endpoint returns 200 OK with valid schema.",
                        "Category": "Access Control"
                    })

            if not rows:
                rows = [
                    {
                        "Title": f"Verify {clean_name} Primary Workflow",
                        "Steps": f"1. Open target page at {app.url}\n2. Interact with main interactive elements\n3. Verify page content and state",
                        "Expected Result": "Primary workflow executes without errors.",
                        "Category": "Generic"
                    },
                    {
                        "Title": f"Verify {clean_name} User Login & Authentication",
                        "Steps": f"1. Navigate to {app.url}/login\n2. Enter valid username and password credentials\n3. Click login submit button",
                        "Expected Result": "User successfully authenticates and redirects to dashboard.",
                        "Category": "Access Control"
                    },
                    {
                        "Title": f"Verify {clean_name} Form Submission & Data Persistence",
                        "Steps": f"1. Navigate to {app.url}\n2. Fill out required input fields\n3. Click save button",
                        "Expected Result": "Data persists and success notification appears.",
                        "Category": "Industry Flow"
                    },
                    {
                        "Title": f"Verify {clean_name} Error Handling & Form Validation",
                        "Steps": f"1. Navigate to {app.url}\n2. Leave required fields blank and click submit\n3. Verify inline error messages",
                        "Expected Result": "Validation error messages display clearly.",
                        "Category": "Generic"
                    },
                    {
                        "Title": f"Verify {clean_name} Navigation Links & Footer",
                        "Steps": f"1. Navigate to {app.url}\n2. Click header and footer navigation links\n3. Verify each destination URL",
                        "Expected Result": "All navigation links resolve to valid 200 OK pages.",
                        "Category": "Generic"
                    }
                ]
            columns = ["Title", "Steps", "Expected Result", "Category"]

        title_candidates = ['title', 'testcase', 'case', 'scenario', 'name', 'feature', 'summary', 'headline', 'usecase', 'id']
        steps_candidates = ['step', 'steps', 'procedure', 'action', 'actions', 'description', 'detail', 'instruction', 'instructions']
        expected_candidates = ['expected', 'result', 'outcome', 'assertion', 'output', 'behavior']
        category_candidates = ['category', 'type', 'module', 'tag', 'group', 'suite']

        test_cases = []
        for idx, row in enumerate(rows):
            raw_title = BulkTestCaseService._get_row_value(row, title_candidates)
            if not raw_title:
                val_list = [str(v).strip() for v in row.values() if v and str(v).strip()]
                raw_title = val_list[0] if val_list else f"Test Case #{idx+1}"

            raw_steps = BulkTestCaseService._get_row_value(row, steps_candidates)
            if not raw_steps:
                val_list = [str(v).strip() for k, v in row.items() if str(v).strip() and str(v).strip() != raw_title]
                raw_steps = "\n".join(val_list)

            raw_expected = BulkTestCaseService._get_row_value(row, expected_candidates)
            if not raw_expected:
                raw_expected = "Verify functionality executes without errors and matches expected criteria."

            raw_category = BulkTestCaseService._get_row_value(row, category_candidates) or 'Generic'
            if raw_category not in ['Generic', 'Industry Flow', 'Access Control']:
                raw_category = 'Generic'

            parsed_steps = BulkTestCaseService._parse_raw_steps_to_playwright_steps(raw_steps, app.url)

            test_cases.append({
                "app": app.id,
                "title": raw_title[:255],
                "category": raw_category,
                "expected_result": raw_expected,
                "steps": parsed_steps,
                "ai_generated": False,
                "generation_context": {
                    "source_file": filename,
                    "model_used": model_choice or 'Bulk Import'
                }
            })

        return {
            "columns": columns,
            "count": len(test_cases),
            "format_type": format_type,
            "test_cases": test_cases
        }

    @staticmethod
    def _parse_raw_steps_to_playwright_steps(raw_steps: Any, default_target_url: str) -> List[Dict[str, str]]:
        """
        Converts text step descriptions or raw JSON into formatted Playwright test step dicts.
        """
        if isinstance(raw_steps, list):
            return BulkTestCaseService._clean_step_list(raw_steps, default_target_url)

        if isinstance(raw_steps, str) and raw_steps.strip().startswith('['):
            try:
                json_steps = json.loads(raw_steps)
                if isinstance(json_steps, list):
                    return BulkTestCaseService._clean_step_list(json_steps, default_target_url)
            except Exception:
                pass

        text = str(raw_steps) if raw_steps else ""
        step_lines = [s.strip() for s in text.replace(';', '\n').splitlines() if s.strip()]

        if not step_lines:
            return [
                {"action": "navigate", "target": default_target_url, "selector": "", "value": ""},
                {"action": "assert", "target": "", "selector": "body", "value": "Dashboard"}
            ]

        steps = []
        for index, line in enumerate(step_lines):
            line_clean = re.sub(r'^\d+[\.:]\s*', '', line).strip()
            line_lower = line_clean.lower()

            if any(w in line_lower for w in ['navigate', 'go to', 'visit', 'open', 'url']):
                target_url = default_target_url
                url_match = re.search(r'https?://[^\s]+|/[a-zA-Z0-9_\-/]*', line_clean)
                if url_match:
                    target_url = url_match.group(0)
                steps.append({"action": "navigate", "target": target_url, "selector": "", "value": ""})

            elif any(w in line_lower for w in ['fill', 'type', 'enter', 'input', 'write']):
                quotes = re.findall(r'"([^"]*)"|\'([^\']*)\'', line_clean)
                flat_quotes = [q[0] or q[1] for q in quotes if q[0] or q[1]]
                
                if len(flat_quotes) >= 2:
                    selector = flat_quotes[0]
                    val = flat_quotes[1]
                elif len(flat_quotes) == 1:
                    val = flat_quotes[0]
                    sel_match = re.search(r'#(?:[a-zA-Z0-9_-]+)|[a-zA-Z0-9_-]+', line_clean)
                    selector = sel_match.group(0) if sel_match else "input"
                else:
                    if 'search' in line_lower:
                        selector = "input[type='search'], input[placeholder*='search' i], input"
                        val = "Test Keyword"
                    elif 'name' in line_lower:
                        selector = "input[name*='name' i], input[placeholder*='name' i], input"
                        val = "Sample Workflow"
                    else:
                        selector = "input"
                        val = "Test Input"

                steps.append({"action": "fill", "target": "", "selector": selector, "value": val})

            elif any(w in line_lower for w in ['click', 'press', 'tap', 'submit', 'button']):
                sel_match = re.search(r'"([^"]*)"|\'([^\']*)\'|#(?:[a-zA-Z0-9_-]+)|\.([a-zA-Z0-9_-]+)', line_clean)
                if sel_match:
                    selector = sel_match.group(0).strip('"\'')
                else:
                    btn_name = re.sub(r'^(?:click|press|tap|select|open)\s+(?:on|that|the|a)?\s*', '', line_clean, flags=re.IGNORECASE)
                    btn_name = re.sub(r'\s+(?:button|tab|link|icon|menu|modal)\b.*$', '', btn_name, flags=re.IGNORECASE).strip(' .')
                    selector = f'text="{btn_name}"' if btn_name else "button[type='submit']"
                steps.append({"action": "click", "target": "", "selector": selector, "value": ""})

            elif any(w in line_lower for w in ['assert', 'verify', 'check', 'should see', 'contains', 'expect', 'observe', 'show', 'display']):
                quotes = re.findall(r'"([^"]*)"|\'([^\']*)\'', line_clean)
                flat_quotes = [q[0] or q[1] for q in quotes if q[0] or q[1]]
                if flat_quotes:
                    val = flat_quotes[0]
                else:
                    val = re.sub(r'^(?:check|verify|assert|observe|ensure)\s+(?:that|if|the|a)?\s*', '', line_clean, flags=re.IGNORECASE).strip(' .')
                steps.append({"action": "assert", "target": "", "selector": "body", "value": val or "Success"})

            elif any(w in line_lower for w in ['wait', 'sleep', 'pause']):
                ms_match = re.search(r'\d+', line_clean)
                ms_val = ms_match.group(0) if ms_match else "800"
                steps.append({"action": "wait", "target": "", "selector": "", "value": ms_val})

            elif any(w in line_lower for w in ['hover', 'move to']):
                steps.append({"action": "hover", "target": "", "selector": ".hover-target", "value": ""})

            elif any(w in line_lower for w in ['screenshot', 'capture']):
                steps.append({"action": "screenshot", "target": "", "selector": "", "value": "bulk_import_checkpoint"})

            else:
                steps.append({"action": "assert", "target": "", "selector": "body", "value": line_clean[:100]})

        if not any(s.get("action") == "navigate" for s in steps):
            steps.insert(0, {"action": "navigate", "target": default_target_url, "selector": "", "value": ""})

        return steps

    @staticmethod
    def _clean_step_list(step_list: List[Any], default_target_url: str) -> List[Dict[str, str]]:
        cleaned = []
        valid_actions = {'navigate', 'fill', 'click', 'wait', 'assert', 'hover', 'scroll', 'select', 'screenshot'}
        for s in step_list:
            if isinstance(s, dict):
                act = str(s.get("action", "navigate")).lower()
                if act not in valid_actions:
                    act = "click"
                cleaned.append({
                    "action": act,
                    "target": str(s.get("target", default_target_url if act == "navigate" else "")),
                    "selector": str(s.get("selector", "")),
                    "value": str(s.get("value", ""))
                })
        return cleaned or [{"action": "navigate", "target": default_target_url, "selector": "", "value": ""}]
