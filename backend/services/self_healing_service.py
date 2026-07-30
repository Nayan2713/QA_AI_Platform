import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class SelfHealingService:
    """
    Self-Healing Engine for Playwright Automated Tests.

    When a DOM selector fails (due to UI redesigns, ID/class renaming, or DOM structural shifts),
    this service evaluates the live page DOM to discover candidate replacement elements using
    fuzzy attribute matching, tag action compatibility, and locator verification.
    """

    @staticmethod
    def heal_selector(page, step: Dict[str, Any]) -> Dict[str, Any]:
        """
        Attempts to discover and verify a replacement selector for a failing test step.

        Returns:
            dict: {
                "success": bool,
                "healed_selector": str,
                "confidence": float,
                "original_selector": str,
                "reason": str
            }
        """
        original_selector = step.get('selector', '')
        action = step.get('action', 'click').lower()
        target_name = step.get('target', '') or original_selector

        logger.info(f"[SELF-HEALING] Attempting selector repair for action '{action}' on broken selector: '{original_selector}'")

        try:
            # 1. Extract DOM interactive candidate elements from the live page
            candidates = page.evaluate("""
                () => {
                    const elements = Array.from(document.querySelectorAll('input, button, a, select, textarea, [role="button"], [onclick]'));
                    return elements.map((el, index) => {
                        const rect = el.getBoundingClientRect();
                        const isVisible = rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden';
                        return {
                            index,
                            tagName: el.tagName.toLowerCase(),
                            id: el.id || '',
                            name: el.getAttribute('name') || '',
                            type: el.getAttribute('type') || '',
                            placeholder: el.getAttribute('placeholder') || '',
                            ariaLabel: el.getAttribute('aria-label') || '',
                            dataTestId: el.getAttribute('data-testid') || el.getAttribute('data-test') || '',
                            text: (el.innerText || el.value || '').trim().substring(0, 100),
                            className: (el.className && typeof el.className === 'string') ? el.className : '',
                            isVisible
                        };
                    }).filter(e => e.isVisible);
                }
            """)

            if not candidates:
                logger.warning("[SELF-HEALING] No visible candidate elements found on live page.")
                return {"success": False, "original_selector": original_selector, "reason": "No visible DOM candidates found."}

            best_candidate = None
            best_score = 0.0
            best_reason = ""

            # Extract key tokens from broken selector and target name
            tokens = set(re.findall(r'[a-zA-Z0-9_\-]+', f"{original_selector} {target_name}".lower()))
            tokens.discard('input')
            tokens.discard('button')
            tokens.discard('form')
            tokens.discard('div')

            for cand in candidates:
                score = 0.0
                reasons = []

                # Tag compatibility score
                if action == 'fill' and cand['tagName'] in ['input', 'textarea']:
                    score += 0.25
                elif action in ['click', 'submit'] and cand['tagName'] in ['button', 'a', 'input']:
                    score += 0.25
                elif action == 'select' and cand['tagName'] == 'select':
                    score += 0.30

                cand_text_blob = f"{cand['id']} {cand['name']} {cand['placeholder']} {cand['ariaLabel']} {cand['dataTestId']} {cand['text']} {cand['className']}".lower()

                # Attribute token match
                matched_tokens = [t for t in tokens if t in cand_text_blob]
                if matched_tokens:
                    token_boost = min(0.50, len(matched_tokens) * 0.20)
                    score += token_boost
                    reasons.append(f"Matched attributes: {', '.join(matched_tokens)}")

                # ID fuzzy match
                ids_in_orig = re.findall(r'#([a-zA-Z0-9_\-]+)', original_selector)
                for orig_id in ids_in_orig:
                    if cand['id'] and (orig_id in cand['id'] or cand['id'] in orig_id):
                        score += 0.35
                        reasons.append(f"Fuzzy ID match: '{cand['id']}' ~ '{orig_id}'")

                # Name attribute match
                names_in_orig = re.findall(r'name=["\']?([a-zA-Z0-9_\-]+)["\']?', original_selector)
                for orig_name in names_in_orig:
                    if cand['name'] and (orig_name in cand['name'] or cand['name'] in orig_name):
                        score += 0.35
                        reasons.append(f"Name attribute match: '{cand['name']}'")

                # Direct text match for buttons/links
                if cand['text'] and any(t in cand['text'].lower() for t in tokens):
                    score += 0.30
                    reasons.append(f"Text content match: '{cand['text']}'")

                if score > best_score:
                    best_score = score
                    best_candidate = cand
                    best_reason = "; ".join(reasons) if reasons else "Tag & DOM proximity match"

            if best_candidate and best_score >= 0.40:
                # Construct verified healed CSS selector
                cand = best_candidate
                healed_selector = ""

                if cand['id']:
                    healed_selector = f"#{cand['id']}"
                elif cand['dataTestId']:
                    healed_selector = f"[data-testid='{cand['dataTestId']}']"
                elif cand['name']:
                    healed_selector = f"{cand['tagName']}[name='{cand['name']}']"
                elif cand['placeholder']:
                    healed_selector = f"{cand['tagName']}[placeholder='{cand['placeholder']}']"
                elif cand['text'] and len(cand['text']) <= 30:
                    healed_selector = f"{cand['tagName']}:has-text('{cand['text']}')"
                elif cand['className']:
                    first_class = cand['className'].strip().split()[0]
                    healed_selector = f"{cand['tagName']}.{first_class}"
                else:
                    healed_selector = f"{cand['tagName']}:nth-of-type({cand['index'] + 1})"

                # Verify selector validity with Playwright locator
                try:
                    loc = page.locator(healed_selector).first
                    if loc and loc.is_visible():
                        confidence = min(0.98, round(best_score, 2))
                        logger.info(f"[SELF-HEALING SUCCESS] Healed selector: '{original_selector}' ➔ '{healed_selector}' (confidence: {confidence})")
                        return {
                            "success": True,
                            "healed_selector": healed_selector,
                            "confidence": confidence,
                            "original_selector": original_selector,
                            "reason": best_reason
                        }
                except Exception as eval_err:
                    logger.warning(f"[SELF-HEALING] Verification failed for candidate '{healed_selector}': {eval_err}")

            return {
                "success": False,
                "original_selector": original_selector,
                "reason": "Highest confidence candidate did not meet verification threshold."
            }

        except Exception as e:
            logger.error(f"[SELF-HEALING ERROR] Exception during selector repair: {e}")
            return {"success": False, "original_selector": original_selector, "reason": str(e)}
