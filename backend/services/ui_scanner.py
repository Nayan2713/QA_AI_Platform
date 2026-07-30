import os
import time
import uuid
import base64
import logging
from urllib.parse import urlparse
from django.conf import settings
from core.models import Application, Page, Bug, BugSeverity

logger = logging.getLogger(__name__)

# Buttons whose text matches these are skipped by the dead-click check —
# clicking them for real on someone's live app would be destructive
# (deletes data, logs the session out, charges a card, etc).
_DESTRUCTIVE_KEYWORDS = [
    'delete', 'remove', 'unsubscribe', 'deactivat', 'terminate', 'cancel subscription',
    'cancel plan', 'close account', 'log out', 'logout', 'sign out', 'signout',
    'pay', 'purchase', 'checkout', 'place order', 'confirm order', 'buy now',
    'charge', 'transfer', 'withdraw', 'send money', 'submit payment', 'reset password',
]

# Hard cap on how many buttons get click-tested per page — keeps scan time and
# blast radius bounded even on pages with dozens of interactive elements.
_MAX_BUTTONS_PER_PAGE = 8


def _is_probably_destructive(text: str) -> bool:
    t = (text or '').lower()
    return any(kw in t for kw in _DESTRUCTIVE_KEYWORDS)


def save_ui_screenshot(page, selector=None, prefix="ui_bug"):
    """
    Captures a screenshot of the page or a specific DOM element in memory and returns a base64 encoded string suitable for Bug.screenshot.
    """
    try:
        ss_bytes = None
        if selector:
            try:
                element = page.locator(selector).first
                if element and element.is_visible():
                    ss_bytes = element.screenshot(timeout=3000)
                else:
                    ss_bytes = page.screenshot(full_page=False)
            except Exception:
                ss_bytes = page.screenshot(full_page=False)
        else:
            ss_bytes = page.screenshot(full_page=False)

        if ss_bytes:
            media_path = os.path.join(settings.MEDIA_ROOT, 'bugs')
            os.makedirs(media_path, exist_ok=True)
            filename = f"{prefix}_{int(time.time() * 1000)}.png"
            filepath = os.path.join(media_path, filename)
            with open(filepath, 'wb') as f:
                f.write(ss_bytes)
            return f"bugs/{filename}"
        return None
    except Exception as e:
        logger.error(f"Failed to capture UI bug screenshot: {e}")
        return None


def run_ui_scan(application: Application, max_pages: int = 5, task_id: str = None):
    """
    Runs automated UI defect and visual issue detection on the application pages using Playwright.
    Detects:
    1. Broken Images & Assets (naturalWidth === 0)
    2. Horizontal Viewport Overflows & Layout Breakages
    3. Low Contrast / Invisible Text (text color matches background or opacity < 0.1)
    4. Asset Load Errors (404 CSS/Fonts/Scripts/Images)
    5. Dead / Non-Functional Buttons (click-and-verify — see _MAX_BUTTONS_PER_PAGE
       and _DESTRUCTIVE_KEYWORDS below for the safety cap and skip-list)
    """
    logger.info(f"Starting automated UI scan for Application ID {application.id} ({application.url})")

    from playwright.sync_api import sync_playwright
    from tasks.cancellation import check_cancelled

    # Delete previous auto-scanned UI bugs for this app to avoid duplication
    Bug.objects.filter(application=application, bug_type='ui', test_run__isnull=True).delete()

    # Collect target URLs (app.url + top pages discovered)
    target_urls = [application.url]
    discovered_pages = Page.objects.filter(app=application).exclude(url=application.url)[:max_pages - 1]
    for p in discovered_pages:
        target_urls.append(p.url)

    bugs_created = []
    seen_bug_keys = set()

    playwright = None
    browser = None
    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )

        for target_url in target_urls:
            if task_id:
                check_cancelled(task_id)
            logger.info(f"Scanning UI defects on: {target_url}")
            page_bugs_created = 0
            page_errors = []
            failed_assets = []
            dialog_events = []      # native confirm()/alert()/prompt() triggered by a click
            request_log = []        # (timestamp, url) for every network request on this page

            context_kwargs = {
                "viewport": {"width": 1280, "height": 800},
                "ignore_https_errors": True,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) QA-Platform-UI-Scanner/1.0"
            }

            # Issue 5: Use Playwright's native browser.new_context(storage_state=state_obj)
            if application.storage_state:
                try:
                    import json
                    if isinstance(application.storage_state, dict):
                        context_kwargs["storage_state"] = application.storage_state
                    elif isinstance(application.storage_state, str):
                        context_kwargs["storage_state"] = json.loads(application.storage_state)
                except Exception as err:
                    logger.warning(f"Could not load session storage for UI scan: {err}")

            context = browser.new_context(**context_kwargs)

            page = context.new_page()

            # Listen to console & network failure events
            def on_page_error(exc):
                page_errors.append(str(exc))

            def on_response(response):
                if response.status >= 400 and response.request.resource_type in ['stylesheet', 'font', 'script', 'image']:
                    failed_assets.append({
                        "url": response.url,
                        "status": response.status,
                        "type": response.request.resource_type
                    })

            def on_dialog(dialog):
                dialog_events.append(time.time())
                try:
                    dialog.dismiss()
                except Exception:
                    pass

            def on_request(req):
                request_log.append((time.time(), req.url))

            page.on("pageerror", on_page_error)
            page.on("response", on_response)
            page.on("dialog", on_dialog)
            page.on("request", on_request)

            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(1500)  # Allow initial CSS animations/rendering
            except Exception as goto_err:
                logger.error(f"UI Scanner failed navigating to {target_url}: {goto_err}")
                context.close()
                continue

            # -------------------------------------------------------------
            # Check 1: Broken Images / Media
            # -------------------------------------------------------------
            try:
                broken_images = page.evaluate("""
                    () => {
                        return Array.from(document.querySelectorAll('img')).map(img => {
                            const rect = img.getBoundingClientRect();
                            return {
                                src: img.src || img.getAttribute('src') || '',
                                alt: img.alt || '',
                                isBroken: img.complete && (img.naturalWidth === 0 || img.naturalHeight === 0),
                                width: rect.width,
                                height: rect.height,
                                id: img.id,
                                className: img.className
                            };
                        }).filter(i => i.isBroken && i.src && i.src.indexOf('data:image') !== 0);
                    }
                """)

                for b_img in broken_images[:5]:  # Cap at 5 broken images per page
                    src_short = b_img['src'].split('/')[-1] or b_img['src'][:30]
                    selector = f"img[src*='{src_short}']" if src_short else "img"
                    key = ('broken_image', target_url, selector)

                    if key not in seen_bug_keys:
                        seen_bug_keys.add(key)
                        ss_path = save_ui_screenshot(page, selector=selector, prefix="ui_broken_img")
                        
                        bug = Bug.objects.create(
                            application=application,
                            bug_type='ui',
                            severity=BugSeverity.MEDIUM,
                            title=f"[Broken Media] Image failed to render: {src_short}",
                            description=f"An image element on page {target_url} failed to load or has naturalWidth 0.\n\nImage Source: {b_img['src']}\nAlt Text: {b_img['alt'] or 'None'}",
                            element_selector=selector,
                            screenshot=ss_path,
                            status='open',
                            steps_to_reproduce=[
                                f"Navigate to {target_url}",
                                f"Locate image element matching selector '{selector}'",
                                "Inspect network response and image natural dimensions"
                            ]
                        )
                        bugs_created.append(bug)
                        page_bugs_created += 1
            except Exception as e:
                logger.error(f"Error checking broken images: {e}")

            # -------------------------------------------------------------
            # Check 2: Viewport Horizontal Layout Overflow
            # -------------------------------------------------------------
            try:
                overflow_elements = page.evaluate("""
                    () => {
                        const docWidth = document.documentElement.clientWidth || window.innerWidth;
                        const overflowed = [];
                        const allEls = document.querySelectorAll('div, section, header, nav, main, table, form');
                        
                        for (let el of allEls) {
                            const rect = el.getBoundingClientRect();
                            if (rect.right > docWidth + 10 && rect.width > 0 && rect.height > 0) {
                                let sel = el.id ? '#' + el.id : (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/)[0] : el.tagName.toLowerCase());
                                overflowed.push({
                                    selector: sel,
                                    right: rect.right,
                                    docWidth: docWidth,
                                    tag: el.tagName.toLowerCase()
                                });
                                if (overflowed.length >= 3) break;
                            }
                        }
                        return overflowed;
                    }
                """)

                for ov in overflow_elements:
                    key = ('overflow', ov['selector'])
                    if key not in seen_bug_keys:
                        seen_bug_keys.add(key)
                        ss_path = save_ui_screenshot(page, selector=ov['selector'], prefix="ui_overflow")
                        
                        bug = Bug.objects.create(
                            application=application,
                            bug_type='ui',
                            severity=BugSeverity.HIGH,
                            title=f"[Layout Overflow] Container exceeds viewport width: {ov['selector']}",
                            description=f"DOM element extending beyond right edge of viewport on page {target_url}.\n\nElement Right Boundary: {ov['right']}px\nViewport Width: {ov['docWidth']}px\nSelector: {ov['selector']}",
                            element_selector=ov['selector'],
                            screenshot=ss_path,
                            status='open',
                            steps_to_reproduce=[
                                f"Open page {target_url} at viewport 1280x800",
                                f"Inspect element {ov['selector']}",
                                f"Verify horizontal scrollbar appears due to bounding right edge {ov['right']}px"
                            ]
                        )
                        bugs_created.append(bug)
                        page_bugs_created += 1
            except Exception as e:
                logger.error(f"Error checking layout overflow: {e}")

            # -------------------------------------------------------------
            # Check 3: Color Contrast / Low Visibility Text
            # -------------------------------------------------------------
            try:
                invisible_text_elements = page.evaluate("""
                    () => {
                        const issues = [];
                        const textEls = document.querySelectorAll('p, h1, h2, h3, h4, button, a, label, span');
                        
                        for (let el of textEls) {
                            if (!el.textContent || !el.textContent.trim()) continue;
                            const style = window.getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            if (rect.width === 0 || rect.height === 0 || style.display === 'none' || style.visibility === 'hidden') continue;
                            
                            const opacity = parseFloat(style.opacity);
                            if (opacity > 0 && opacity < 0.12) {
                                let sel = el.id ? '#' + el.id : (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/)[0] : el.tagName.toLowerCase());
                                issues.push({
                                    selector: sel,
                                    text: el.textContent.trim().substring(0, 40),
                                    reason: `Nearly invisible text (opacity: ${opacity})`
                                });
                            } else if (style.color === style.backgroundColor && style.color !== 'rgba(0, 0, 0, 0)') {
                                let sel = el.id ? '#' + el.id : (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/)[0] : el.tagName.toLowerCase());
                                issues.push({
                                    selector: sel,
                                    text: el.textContent.trim().substring(0, 40),
                                    reason: 'Text color matches background color'
                                });
                            }
                            if (issues.length >= 3) break;
                        }
                        return issues;
                    }
                """)

                for vis in invisible_text_elements:
                    key = ('contrast', vis['selector'])
                    if key not in seen_bug_keys:
                        seen_bug_keys.add(key)
                        ss_path = save_ui_screenshot(page, selector=vis['selector'], prefix="ui_contrast")

                        bug = Bug.objects.create(
                            application=application,
                            bug_type='ui',
                            severity=BugSeverity.MEDIUM,
                            title=f"[Color & Contrast] {vis['reason']} on '{vis['text']}'",
                            description=f"Text element on page {target_url} has contrast/visibility issues.\n\nText Content: '{vis['text']}'\nIssue Detail: {vis['reason']}\nSelector: {vis['selector']}",
                            element_selector=vis['selector'],
                            screenshot=ss_path,
                            status='open',
                            steps_to_reproduce=[
                                f"Navigate to {target_url}",
                                f"Locate text element '{vis['text']}' ({vis['selector']})",
                                f"Inspect computed CSS style: {vis['reason']}"
                            ]
                        )
                        bugs_created.append(bug)
                        page_bugs_created += 1
            except Exception as e:
                logger.error(f"Error checking text contrast: {e}")

            # -------------------------------------------------------------
            # Check 4: Failed Asset Loads (404 CSS / Fonts)
            # -------------------------------------------------------------
            for asset in failed_assets[:3]:
                key = ('failed_asset', asset['url'])
                if key not in seen_bug_keys:
                    seen_bug_keys.add(key)
                    bug = Bug.objects.create(
                        application=application,
                        bug_type='ui',
                        severity=BugSeverity.MEDIUM,
                        title=f"[Broken Asset] Failed loading {asset['type']}: HTTP {asset['status']}",
                        description=f"Critical UI asset failed to load on page {target_url}.\n\nAsset URL: {asset['url']}\nResource Type: {asset['type']}\nHTTP Status: {asset['status']}",
                        element_selector=f"link[href*='{asset['url'].split('/')[-1]}']" if asset['type'] == 'stylesheet' else None,
                        status='open',
                        steps_to_reproduce=[
                            f"Open page {target_url}",
                            f"Check Network tab for failed {asset['type']} request: {asset['url']}",
                            f"HTTP Response code: {asset['status']}"
                        ]
                    )
                    bugs_created.append(bug)

            # -------------------------------------------------------------
            # Check 5: Dead / Non-Functional Buttons (click-and-verify)
            #
            # Finds visible, enabled button-like elements, clicks each one,
            # and checks whether the click had *any* observable effect:
            # URL change, DOM mutation, a new network request, a new tab, or
            # a native dialog. If none of those happen, the button is very
            # likely wired to nothing (missing handler, dead JS, etc) and
            # gets logged as a bug. Heuristic, so it can false-positive on
            # buttons whose only effect is invisible (e.g. clipboard copy
            # with no toast) — treat results as "needs a look", not gospel.
            # -------------------------------------------------------------
            try:
                candidates = page.evaluate("""
                    () => {
                        const out = [];
                        const sel = 'button, [role="button"], input[type="submit"], input[type="button"], input[type="reset"]';
                        const els = document.querySelectorAll(sel);
                        let idx = 0;
                        for (const el of els) {
                            const rect = el.getBoundingClientRect();
                            const style = window.getComputedStyle(el);
                            if (rect.width === 0 || rect.height === 0) continue;
                            if (style.display === 'none' || style.visibility === 'hidden') continue;
                            if (style.pointerEvents === 'none') continue;
                            if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;

                            const text = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().substring(0, 60);
                            let selector;
                            if (el.id) {
                                selector = '#' + CSS.escape(el.id);
                            } else {
                                el.setAttribute('data-qa-scan-idx', String(idx));
                                selector = '[data-qa-scan-idx="' + idx + '"]';
                            }
                            out.push({selector, text});
                            idx++;
                        }
                        return out;
                    }
                """)
            except Exception as e:
                logger.error(f"Error collecting clickable elements: {e}")
                candidates = []

            tested = 0
            for cand in candidates:
                if tested >= _MAX_BUTTONS_PER_PAGE:
                    break
                selector = cand.get('selector')
                text = cand.get('text') or '(no label)'

                if _is_probably_destructive(text):
                    continue  # skip delete/logout/pay/etc. — see _DESTRUCTIVE_KEYWORDS

                key = ('dead_click', text)
                if key in seen_bug_keys:
                    continue

                try:
                    loc = page.locator(selector).first
                    if not loc.is_visible():
                        continue

                    # Reset the per-element mutation flag right before clicking.
                    page.evaluate(
                        """(sel) => {
                            window.__qaScanMutated = false;
                            const target = document.querySelector(sel);
                            if (!target) return;
                            if (window.__qaScanObserver) window.__qaScanObserver.disconnect();
                            window.__qaScanObserver = new MutationObserver(() => { window.__qaScanMutated = true; });
                            window.__qaScanObserver.observe(document.body, {childList: true, subtree: true, attributes: true});
                        }""",
                        selector,
                    )

                    before_url = page.url
                    before_page_count = len(context.pages)
                    click_time = time.time()

                    try:
                        loc.click(timeout=2000)
                    except Exception:
                        try:
                            loc.click(force=True, timeout=1500)
                        except Exception:
                            loc.evaluate("el => el.click()")

                    page.wait_for_timeout(700)
                    tested += 1

                    # Close any popup/new-tab the click opened; that alone counts as "worked".
                    opened_popup = len(context.pages) > before_page_count
                    if opened_popup:
                        for extra_page in context.pages[before_page_count:]:
                            try:
                                extra_page.close()
                            except Exception:
                                pass

                    fired_dialog = any(t >= click_time for t in dialog_events)
                    fired_request = any(t >= click_time for t, _ in request_log)
                    try:
                        mutated = bool(page.evaluate("() => window.__qaScanMutated === true"))
                    except Exception:
                        mutated = False  # page likely navigated away — treat separately below
                    navigated = page.url != before_url

                    worked = navigated or mutated or fired_request or fired_dialog or opened_popup

                    if not worked:
                        seen_bug_keys.add(key)
                        ss_path = save_ui_screenshot(page, selector=selector, prefix="ui_dead_click")
                        bug = Bug.objects.create(
                            application=application,
                            bug_type='ui',
                            severity=BugSeverity.MEDIUM,
                            title=f"[Dead Click] Button appears non-functional: \"{text}\"",
                            description=(
                                f"Clicking the button/element labeled \"{text}\" on page {target_url} produced no "
                                f"observable effect — no URL change, DOM update, network request, dialog, or new tab.\n\n"
                                f"Selector: {selector}\n"
                                f"This is a heuristic check: some buttons legitimately have invisible effects "
                                f"(e.g. clipboard copy with no toast). Please verify manually before treating as confirmed."
                            ),
                            element_selector=selector,
                            screenshot=ss_path,
                            status='open',
                            steps_to_reproduce=[
                                f"Navigate to {target_url}",
                                f"Click the element \"{text}\" ({selector})",
                                "Observe that nothing happens: no navigation, no visible UI change, no network activity",
                            ],
                        )
                        bugs_created.append(bug)
                        page_bugs_created += 1

                    if navigated:
                        # Restore the page so remaining candidates can still be tested.
                        try:
                            page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                            page.wait_for_timeout(500)
                        except Exception as nav_err:
                            logger.warning(f"Could not restore {target_url} after dead-click test: {nav_err}")
                            break  # page is in an unknown state — stop testing buttons on it

                except Exception as click_err:
                    logger.warning(f"Dead-click check failed for \"{text}\" on {target_url}: {click_err}")
                    continue

            # -------------------------------------------------------------
            # Check 6: Automated Input Character Fuzzing & Boundary Check
            # -------------------------------------------------------------
            try:
                import re
                input_candidates = page.evaluate("""
                    () => {
                        return Array.from(document.querySelectorAll('input')).map((el, idx) => {
                            const rect = el.getBoundingClientRect();
                            const isVisible = rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden';
                            return {
                                idx,
                                type: (el.type || 'text').toLowerCase(),
                                name: el.name || '',
                                id: el.id || '',
                                placeholder: el.placeholder || '',
                                isVisible,
                                isDisabled: el.disabled || el.readOnly,
                                selector: el.id ? `#${el.id}` : (el.name ? `input[name="${el.name}"]` : `input:nth-of-type(${idx + 1})`)
                            };
                        }).filter(i => i.isVisible && !i.isDisabled && !['hidden', 'submit', 'button', 'checkbox', 'radio', 'file', 'image', 'reset'].includes(i.type));
                    }
                """)

                for inp in input_candidates[:6]:  # Limit to 6 inputs per page
                    sel = inp['selector']
                    attr_text = f"{inp['type']} {inp['name']} {inp['id']} {inp['placeholder']}".lower()
                    
                    is_phone_field = inp['type'] == 'tel' or any(k in attr_text for k in ['phone', 'mobile', 'cell', 'contact', 'whatsapp', 'phone_number'])
                    is_email_field = inp['type'] == 'email' or any(k in attr_text for k in ['email', 'mail'])

                    if not (is_phone_field or is_email_field):
                        continue

                    try:
                        loc = page.locator(sel).first
                        if not loc.is_visible():
                            continue

                        if is_phone_field:
                            key = ('input_fuzz_phone', target_url, sel)
                            if key not in seen_bug_keys:
                                test_payload = "ABC#$@9876543210"
                                loc.fill('')
                                loc.type(test_payload, delay=50)
                                loc.evaluate("el => el.dispatchEvent(new Event('blur'))")
                                page.wait_for_timeout(300)

                                val_after = loc.input_value()
                                has_invalid_chars = bool(re.search(r'[A-Za-z#$@]', val_after))
                                is_html5_valid = loc.evaluate("el => el.validity ? el.validity.valid : true")

                                if has_invalid_chars and is_html5_valid:
                                    seen_bug_keys.add(key)
                                    ss_path = save_ui_screenshot(page, selector=sel, prefix="ui_input_fuzz")
                                    field_label = inp['name'] or inp['id'] or inp['placeholder'] or sel
                                    bug = Bug.objects.create(
                                        application=application,
                                        bug_type='ui',
                                        severity=BugSeverity.HIGH,
                                        title=f"[Input Validation Defect] Mobile/Phone field accepts invalid characters: \"{field_label}\"",
                                        description=(
                                            f"The mobile/phone number input field '{field_label}' on page {target_url} accepts non-numeric characters.\n\n"
                                            f"Selector: {sel}\n"
                                            f"Tested Payload: '{test_payload}'\n"
                                            f"Value Accepted in Input: '{val_after}'\n\n"
                                            f"Mobile number input fields should enforce strict numeric validation and reject or strip non-numeric symbols."
                                        ),
                                        element_selector=sel,
                                        screenshot=ss_path,
                                        status='open',
                                        steps_to_reproduce=[
                                            f"Navigate to {target_url}",
                                            f"Locate input field '{field_label}' ({sel})",
                                            f"Type invalid non-numeric string '{test_payload}'",
                                            f"Observe that non-numeric characters '{val_after}' were accepted without validation error."
                                        ]
                                    )
                                    bugs_created.append(bug)
                                    page_bugs_created += 1

                                # Clean up field
                                loc.fill('')

                    except Exception as fuzz_err:
                        logger.warning(f"Input fuzzing check failed for {sel} on {target_url}: {fuzz_err}")

            except Exception as fuzz_outer_err:
                logger.warning(f"Failed scanning input fuzzing candidates on {target_url}: {fuzz_outer_err}")

            context.close()

    except Exception as scan_err:
        logger.error(f"Error in UI scan execution: {scan_err}")
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        if playwright:
            try:
                playwright.stop()
            except Exception:
                pass

    logger.info(f"UI scan finished for App {application.id}. Created {len(bugs_created)} UI bug entries.")
    return bugs_created