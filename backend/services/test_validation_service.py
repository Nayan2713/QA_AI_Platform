import re
import json
import logging
from urllib.parse import urlparse
from core.models import TestCase, Page
from services.llm_service import LLMService

logger = logging.getLogger(__name__)

class TestValidationService:
    @staticmethod
    def get_discovered_selectors(app):
        """
        Retrieves all crawled page elements (selectors, IDs, names, text labels)
        for a given application.
        """
        pages = Page.objects.filter(app=app)
        elements = []
        
        for page in pages:
            # Extract from buttons
            buttons = page.buttons or []
            if isinstance(buttons, str):
                try:
                    buttons = json.loads(buttons)
                except:
                    buttons = []
            for b in buttons:
                if isinstance(b, dict) and b.get('selector'):
                    elements.append({
                        "type": "button",
                        "text": b.get("text", ""),
                        "selector": b.get("selector")
                    })
            
            # Extract from forms
            forms = page.forms or []
            if isinstance(forms, str):
                try:
                    forms = json.loads(forms)
                except:
                    forms = []
            for f in forms:
                if isinstance(f, dict):
                    form_id = f.get('id', '')
                    for field in f.get('fields', []):
                        if isinstance(field, dict):
                            f_id = field.get('id')
                            f_name = field.get('name')
                            f_type = field.get('type', 'text')
                            
                            selector = ""
                            if f_id:
                                selector = f"#{f_id}"
                            elif f_name:
                                selector = f"input[name='{f_name}']"
                                
                            elements.append({
                                "type": "input",
                                "id": f_id or "",
                                "name": f_name or "",
                                "input_type": f_type,
                                "form_id": form_id,
                                "selector": selector
                            })
        return elements

    @classmethod
    def validate_test_case(cls, test_case_id):
        """
        Validates if a test case's selectors match elements on crawled pages.
        Returns a dict of validation results and updates the TestCase status.
        """
        try:
            test_case = TestCase.objects.get(id=test_case_id)
            app = test_case.app
            
            # Get discovered elements
            elements = cls.get_discovered_selectors(app)
            detected_selectors = [el.get('selector') for el in elements if el.get('selector')]
            
            steps = test_case.steps or []
            if isinstance(steps, str):
                try:
                    steps = json.loads(steps)
                except:
                    steps = []
                    
            validation_details = []
            matched_count = 0
            
            for idx, step in enumerate(steps):
                action = step.get('action')
                selector = step.get('selector', '')
                target = step.get('target', '')
                
                # Navigation actions don't need elements check
                if action == 'navigate':
                    validation_details.append({
                        "step_index": idx,
                        "action": action,
                        "selector": selector,
                        "valid": True,
                        "reason": "Navigation step - does not require element matching."
                    })
                    matched_count += 1
                    continue
                    
                if not selector:
                    validation_details.append({
                        "step_index": idx,
                        "action": action,
                        "selector": selector,
                        "valid": False,
                        "reason": "Missing selector for interactive action."
                    })
                    continue
                
                # Check for selector presence
                found = False
                # Direct check
                if selector in detected_selectors:
                    found = True
                else:
                    # Fuzzy match check
                    # Check if ID selector exists (e.g. #username inside nested selector)
                    ids = re.findall(r'#([a-zA-Z0-9_\-]+)', selector)
                    for id_val in ids:
                        if any(id_val in s for s in detected_selectors):
                            found = True
                            break
                            
                    # Check if name selector exists
                    names = re.findall(r'name=["\']?([a-zA-Z0-9_\-]+)["\']?', selector)
                    for name_val in names:
                        if any(name_val in s for s in detected_selectors):
                            found = True
                            break
                            
                    # Tag selectors that are always relevant
                    if not found and selector.strip() in ['body', 'html', 'head', 'main']:
                        found = True
                        
                if found:
                    validation_details.append({
                        "step_index": idx,
                        "action": action,
                        "selector": selector,
                        "valid": True
                    })
                    matched_count += 1
                else:
                    validation_details.append({
                        "step_index": idx,
                        "action": action,
                        "selector": selector,
                        "valid": False,
                        "reason": f"Selector '{selector}' not found in crawled page structure."
                    })
                    
            total_interactive = sum(1 for step in steps if step.get('action') != 'navigate')
            relevance = (matched_count / len(steps) * 100) if steps else 0
            
            # Update TestCase model status
            if relevance >= 90:
                test_case.validation_status = 'VERIFIED'
            else:
                test_case.validation_status = 'BROKEN'
            test_case.save()
            
            return {
                "test_case_id": test_case_id,
                "relevance_score": relevance,
                "validation_status": test_case.validation_status,
                "steps": validation_details,
                "success": True
            }
        except TestCase.DoesNotExist:
            return {"success": False, "error": "Test case not found."}
        except Exception as e:
            logger.error(f"Error validating test case: {e}")
            return {"success": False, "error": str(e)}

    @classmethod
    def find_best_matching_selector(cls, hallucinated_selector, elements):
        """
        Deterministic fuzzy matching logic to map invalid selectors to crawled elements.
        """
        raw_h = hallucinated_selector.replace('#', '').replace('.', '').lower()
        attr_match = re.findall(r'name=["\']?([a-zA-Z0-9_\-]+)["\']?', hallucinated_selector)
        if attr_match:
            raw_h = attr_match[0].lower()
            
        best_match = None
        best_score = 0
        
        for el in elements:
            score = 0
            sel = el.get("selector", "")
            if not sel:
                continue
                
            if sel == hallucinated_selector:
                return sel
                
            el_id = el.get("id", "").lower()
            el_name = el.get("name", "").lower()
            el_text = el.get("text", "").lower()
            
            if el_id and el_id in raw_h:
                score += 80
            if el_name and el_name in raw_h:
                score += 70
            if el_text and el_text in raw_h:
                score += 60
            if sel.lower() in hallucinated_selector.lower() or hallucinated_selector.lower() in sel.lower():
                score += 50
                
            if score > best_score:
                best_score = score
                best_match = sel
                
        if best_score >= 50:
            return best_match
        return None

    @classmethod
    def auto_fix_test_case(cls, test_case_id):
        """
        Auto-corrects invalid selectors inside a test case using fuzzy matching
        with an LLM fallback, then runs validation to verify relevance.
        """
        try:
            test_case = TestCase.objects.get(id=test_case_id)
            app = test_case.app
            
            elements = cls.get_discovered_selectors(app)
            steps = test_case.steps or []
            if isinstance(steps, str):
                try:
                    steps = json.loads(steps)
                except:
                    steps = []
            
            fixed_steps = []
            corrections_made = 0
            
            for step in steps:
                action = step.get('action')
                selector = step.get('selector', '')
                
                if action == 'navigate' or not selector:
                    fixed_steps.append(step)
                    continue
                    
                # Verify if selector is valid
                detected_selectors = [el.get('selector') for el in elements if el.get('selector')]
                
                # Check directly
                if selector in detected_selectors or selector.strip() in ['body', 'html', 'head', 'main']:
                    fixed_steps.append(step)
                    continue
                
                # Not valid - attempt fuzzy match
                best_match = cls.find_best_matching_selector(selector, elements)
                
                if best_match:
                    new_step = step.copy()
                    new_step['selector'] = best_match
                    fixed_steps.append(new_step)
                    corrections_made += 1
                    logger.info(f"Fuzzy-corrected selector '{selector}' to '{best_match}' in test {test_case_id}")
                else:
                    # Fuzzy match failed - trigger LLM fallback
                    llm_fixed_selector = cls.llm_fix_selector(selector, action, step.get('value', ''), elements)
                    if llm_fixed_selector and llm_fixed_selector in detected_selectors:
                        new_step = step.copy()
                        new_step['selector'] = llm_fixed_selector
                        fixed_steps.append(new_step)
                        corrections_made += 1
                        logger.info(f"LLM-corrected selector '{selector}' to '{llm_fixed_selector}' in test {test_case_id}")
                    else:
                        # Keep original if all else fails
                        fixed_steps.append(step)
            
            # Save fixed steps
            test_case.steps = fixed_steps
            test_case.save()
            
            # Re-validate
            validation_res = cls.validate_test_case(test_case_id)
            validation_res["corrections_made"] = corrections_made
            return validation_res
            
        except TestCase.DoesNotExist:
            return {"success": False, "error": "Test case not found."}
        except Exception as e:
            logger.error(f"Error auto-fixing test case: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def llm_fix_selector(invalid_selector, action, value, elements):
        """
        Asks the local Ollama LLM to map an invalid selector to a list of crawled elements.
        """
        import requests
        from django.conf import settings
        
        api_url = getattr(settings, 'OLLAMA_API_URL', 'http://localhost:11434/api/generate')
        model = getattr(settings, 'OLLAMA_MODEL', 'qwen:7b')
        
        elements_context = json.dumps(elements[:30], indent=1) # Limit to first 30 elements to prevent prompt bloating
        
        prompt = f"""You are a QA Automation script selector auditor.
Your task is to fix an invalid CSS selector.

We tried to run a test step with action '{action}' (value: '{value}') but the CSS selector '{invalid_selector}' was not found on the page.

Here is the list of discovered valid selectors on this page:
{elements_context}

Choose the single best selector from the list above that matches the intent of the failed selector '{invalid_selector}'.
For example:
- If failed selector is '#email-input' and the list has '#email', select '#email'.
- If action is click and failed selector is '#submit', look for a submit button in the list.

Respond with ONLY the selector string itself (e.g., "#email" or "button[type='submit']"). Do not write any explanations, markdown code blocks, or conversational text.
"""
        try:
            response = requests.post(
                api_url,
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 30
                    }
                },
                timeout=4
            )
            if response.status_code == 200:
                verdict = response.json().get("response", "").strip()
                # Clean clean response of quotes or markdown backticks
                verdict = verdict.replace("`", "").replace('"', "").replace("'", "")
                return verdict
        except Exception as e:
            logger.warning(f"Ollama selector auto-fix failed: {e}")
        return None
