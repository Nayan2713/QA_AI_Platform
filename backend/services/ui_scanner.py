import os
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
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
_DESTRUCTIVE_KEYWORDS = [
    'delete', 'remove', 'unsubscribe', 'deactivat', 'terminate', 'cancel subscription',
    'cancel plan', 'close account', 'log out', 'logout', 'sign out', 'signout',
    'pay', 'purchase', 'checkout', 'place order', 'confirm order', 'buy now',
    'charge', 'transfer', 'withdraw', 'send money', 'submit payment', 'reset password',
]

# Hard cap on how many buttons get click-tested per page
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


# JavaScript function to compute effective background color & WCAG contrast ratio
_CONTRAST_AND_VISIBILITY_JS = """
() => {
    const issues = [];

    function parseRGBA(colorStr) {
        if (!colorStr || colorStr === 'transparent') return [0, 0, 0, 0];
        const match = colorStr.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)(?:,\\s*([\\d.]+))?\\)/);
        if (match) {
            return [
                parseInt(match[1], 10),
                parseInt(match[2], 10),
                parseInt(match[3], 10),
                match[4] !== undefined ? parseFloat(match[4]) : 1.0
            ];
        }
        return [0, 0, 0, 1.0];
    }

    function hasBackgroundGraphic(element) {
        let curr = element;
        while (curr && curr !== document.documentElement) {
            const style = window.getComputedStyle(curr);
            if (style.backgroundImage && style.backgroundImage !== 'none' && (style.backgroundImage.includes('gradient') || style.backgroundImage.includes('url('))) {
                return true;
            }
            curr = curr.parentElement;
        }
        return false;
    }

    function getEffectiveBgColor(element) {
        let curr = element;
        while (curr && curr !== document.documentElement) {
            const style = window.getComputedStyle(curr);
            const [r, g, b, a] = parseRGBA(style.backgroundColor);
            if (a > 0.05) return [r, g, b, a];
            curr = curr.parentElement;
        }
        // Fallback to body or document background color
        const bodyStyle = window.getComputedStyle(document.body);
        const [br, bg, bb, ba] = parseRGBA(bodyStyle.backgroundColor);
        if (ba > 0.05) return [br, bg, bb, ba];

        const htmlStyle = window.getComputedStyle(document.documentElement);
        const [hr, hg, hb, ha] = parseRGBA(htmlStyle.backgroundColor);
        if (ha > 0.05) return [hr, hg, hb, ha];

        return [255, 255, 255, 1.0];
    }

    function getLuminance(r, g, b) {
        const a = [r, g, b].map(v => {
            v /= 255;
            return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
        });
        return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722;
    }

    function getContrastRatio(rgb1, rgb2) {
        const lum1 = getLuminance(rgb1[0], rgb1[1], rgb1[2]);
        const lum2 = getLuminance(rgb2[0], rgb2[1], rgb2[2]);
        const brightest = Math.max(lum1, lum2);
        const darkest = Math.min(lum1, lum2);
        return (brightest + 0.05) / (darkest + 0.05);
    }

    const textEls = document.querySelectorAll('p, h1, h2, h3, h4, h5, h6, button, a, label, span, th, td');
    let count = 0;

    for (let el of textEls) {
        if (count >= 5) break;
        if (!el.textContent || !el.textContent.trim()) continue;
        const textSnippet = el.textContent.trim().substring(0, 50);
        if (textSnippet.length < 3) continue;

        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();

        if (rect.width === 0 || rect.height === 0 || style.display === 'none' || style.visibility === 'hidden') continue;

        // Skip contrast checks if rendered over a CSS background gradient or background image
        if (hasBackgroundGraphic(el)) continue;

        const opacity = parseFloat(style.opacity);
        let sel = el.id ? '#' + CSS.escape(el.id) : (el.className && typeof el.className === 'string' && el.className.trim() ? '.' + CSS.escape(el.className.trim().split(/\\s+/)[0]) : el.tagName.toLowerCase());

        if (opacity > 0 && opacity < 0.15) {
            issues.push({
                selector: sel,
                text: textSnippet,
                reason: `Extremely low opacity text (opacity: ${opacity.toFixed(2)})`,
                contrastRatio: 1.0
            });
            count++;
            continue;
        }

        const textColor = parseRGBA(style.color);
        const bgColor = getEffectiveBgColor(el);

        // Check exact match (invisible text)
        if (textColor[0] === bgColor[0] && textColor[1] === bgColor[1] && textColor[2] === bgColor[2] && textColor[3] > 0.5) {
            issues.push({
                selector: sel,
                text: textSnippet,
                reason: `Text color matches background color (${style.color})`,
                contrastRatio: 1.0
            });
            count++;
            continue;
        }

        // Calculate WCAG contrast ratio
        const ratio = getContrastRatio(textColor, bgColor);
        if (ratio < 2.5 && textColor[3] > 0.5) {
            issues.push({
                selector: sel,
                text: textSnippet,
                reason: `Poor color contrast ratio: ${ratio.toFixed(2)}:1 (WCAG AA minimum is 4.5:1)`,
                contrastRatio: parseFloat(ratio.toFixed(2))
            });
            count++;
        }
    }

    return issues;
}
"""

# JavaScript function to check vertical text truncation in fixed containers
_TEXT_TRUNCATION_JS = """
() => {
    const issues = [];
    const containers = document.querySelectorAll('div, section, article, p, card');
    let count = 0;

    for (let el of containers) {
        if (count >= 3) break;
        const style = window.getComputedStyle(el);
        if (style.overflow === 'hidden' || style.overflowY === 'hidden') {
            const rect = el.getBoundingClientRect();
            if (rect.height > 20 && el.scrollHeight > el.clientHeight + 8 && el.textContent.trim().length > 20) {
                let sel = el.id ? '#' + CSS.escape(el.id) : (el.className && typeof el.className === 'string' && el.className.trim() ? '.' + CSS.escape(el.className.trim().split(/\\s+/)[0]) : el.tagName.toLowerCase());
                issues.push({
                    selector: sel,
                    text: el.textContent.trim().substring(0, 60),
                    scrollHeight: el.scrollHeight,
                    clientHeight: el.clientHeight
                });
                count++;
            }
        }
    }
    return issues;
}
"""


def run_ui_scan(application: Application, max_pages: int = 5, task_id: str = None):
    from services.sync_helper import run_sync_in_thread

    def _do_ui_scan():
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

            viewports_to_test = [
                {"name": "Desktop (1280x800)", "viewport": {"width": 1280, "height": 800}},
                {"name": "Mobile (375x812)", "viewport": {"width": 375, "height": 812}, "is_mobile": True}
            ]

            for target_url in target_urls:
                if task_id:
                    check_cancelled(task_id)

                for vp_config in viewports_to_test:
                    vp_name = vp_config["name"]
                    logger.info(f"Scanning UI defects on: {target_url} [{vp_name}]")
                    page_bugs_created = 0
                    failed_assets = []
                    dialog_events = []
                    request_log = []

                    context_kwargs = {
                        "viewport": vp_config["viewport"],
                        "ignore_https_errors": True,
                    }
                    if vp_config.get("is_mobile"):
                        context_kwargs["is_mobile"] = True

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

                    page.on("response", on_response)
                    page.on("dialog", on_dialog)
                    page.on("request", on_request)

                    try:
                        try:
                            page.goto(target_url, wait_until="networkidle", timeout=15000)
                        except Exception:
                            page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
                        page.wait_for_timeout(2500)

                        # Auto-login if landing on a protected page with a login form
                        if application.username and application.password:
                            try:
                                has_login = page.locator("input[type='password']").first.is_visible(timeout=1500)
                                if has_login:
                                    logger.info(f"UI Scanner detected login form on {target_url} — performing login...")
                                    from tasks.execution import perform_login
                                    if perform_login(page, context, application):
                                        try:
                                            page.goto(target_url, wait_until="networkidle", timeout=15000)
                                        except Exception:
                                            page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
                                        page.wait_for_timeout(2500)
                            except Exception as l_err:
                                logger.warning(f"UI Scanner login attempt notice: {l_err}")
                    except Exception as goto_err:
                        logger.error(f"UI Scanner failed navigating to {target_url} [{vp_name}]: {goto_err}")
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

                    for b_img in broken_images[:5]:
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
                    logger.error(f"Error checking broken images on {target_url}: {e}")

                # -------------------------------------------------------------
                # Check 2: Viewport Horizontal Layout Overflow
                # -------------------------------------------------------------
                try:
                    overflow_elements = page.evaluate("""
                        () => {
                            const docWidth = document.documentElement.clientWidth || window.innerWidth;
                            const bodyStyle = window.getComputedStyle(document.body);
                            const htmlStyle = window.getComputedStyle(document.documentElement);

                            // If document has no horizontal scrollbar or is clipped at root, no layout overflow!
                            if (bodyStyle.overflowX === 'hidden' || htmlStyle.overflowX === 'hidden' || document.documentElement.scrollWidth <= docWidth + 4) {
                                return [];
                            }

                            function isClippedByParent(element) {
                                let curr = element.parentElement;
                                while (curr && curr !== document.documentElement) {
                                    const style = window.getComputedStyle(curr);
                                    if (style.overflowX === 'hidden' || style.overflowX === 'auto' || style.overflowX === 'scroll' || style.overflow === 'hidden') {
                                        return true;
                                    }
                                    curr = curr.parentElement;
                                }
                                return false;
                            }

                            const overflowed = [];
                            const allEls = document.querySelectorAll('div, section, header, nav, main, table, form');
                            
                            for (let el of allEls) {
                                const rect = el.getBoundingClientRect();
                                if (rect.right > docWidth + 12 && rect.width > 0 && rect.height > 0) {
                                    if (isClippedByParent(el)) continue;

                                    let sel = el.id ? '#' + CSS.escape(el.id) : (el.className && typeof el.className === 'string' && el.className.trim() ? '.' + CSS.escape(el.className.trim().split(/\\s+/)[0]) : el.tagName.toLowerCase());
                                    overflowed.push({
                                        selector: sel,
                                        right: Math.round(rect.right),
                                        docWidth: Math.round(docWidth),
                                        tag: el.tagName.toLowerCase()
                                    });
                                    if (overflowed.length >= 3) break;
                                }
                            }
                            return overflowed;
                        }
                    """)

                    for ov in overflow_elements:
                        key = ('overflow', target_url, ov['selector'], vp_name)
                        if key not in seen_bug_keys:
                            seen_bug_keys.add(key)
                            ss_path = save_ui_screenshot(page, selector=ov['selector'], prefix="ui_overflow")

                            bug = Bug.objects.create(
                                application=application,
                                bug_type='ui',
                                severity=BugSeverity.HIGH,
                                title=f"[Layout Overflow - {vp_name}] Container exceeds viewport width: {ov['selector']}",
                                description=f"DOM element extending beyond right edge of viewport on page {target_url} in {vp_name}.\n\nElement Right Edge: {ov['right']}px\nViewport Width: {ov['docWidth']}px\nSelector: {ov['selector']}",
                                element_selector=ov['selector'],
                                screenshot=ss_path,
                                status='open',
                                steps_to_reproduce=[
                                    f"Open page {target_url} at viewport {vp_name}",
                                    f"Inspect element {ov['selector']}",
                                    f"Verify horizontal scrollbar appears due to right edge boundary {ov['right']}px"
                                ]
                            )
                            bugs_created.append(bug)
                            page_bugs_created += 1
                except Exception as e:
                    logger.error(f"Error checking layout overflow on {target_url}: {e}")

                # -------------------------------------------------------------
                # Check 3: Color Contrast / Low Visibility & Truncated Text
                # -------------------------------------------------------------
                try:
                    contrast_issues = page.evaluate(_CONTRAST_AND_VISIBILITY_JS)
                    for vis in contrast_issues:
                        key = ('contrast', target_url, vis['selector'])
                        if key not in seen_bug_keys:
                            seen_bug_keys.add(key)
                            ss_path = save_ui_screenshot(page, selector=vis['selector'], prefix="ui_contrast")

                            bug = Bug.objects.create(
                                application=application,
                                bug_type='ui',
                                severity=BugSeverity.MEDIUM,
                                title=f"[Color & Contrast] {vis['reason']} on '{vis['text']}'",
                                description=f"Text element on page {target_url} has visibility/contrast issues.\n\nText Content: '{vis['text']}'\nIssue Detail: {vis['reason']}\nSelector: {vis['selector']}",
                                element_selector=vis['selector'],
                                screenshot=ss_path,
                                status='open',
                                steps_to_reproduce=[
                                    f"Navigate to {target_url}",
                                    f"Locate text element '{vis['text']}' ({vis['selector']})",
                                    f"Inspect computed style and contrast ratio: {vis['reason']}"
                                ]
                            )
                            bugs_created.append(bug)
                            page_bugs_created += 1
                except Exception as e:
                    logger.error(f"Error checking text contrast on {target_url}: {e}")

                try:
                    truncation_issues = page.evaluate(_TEXT_TRUNCATION_JS)
                    for trunc in truncation_issues:
                        key = ('truncation', target_url, trunc['selector'])
                        if key not in seen_bug_keys:
                            seen_bug_keys.add(key)
                            ss_path = save_ui_screenshot(page, selector=trunc['selector'], prefix="ui_truncation")

                            bug = Bug.objects.create(
                                application=application,
                                bug_type='ui',
                                severity=BugSeverity.MEDIUM,
                                title=f"[Text Truncation] Content clipped in fixed container: {trunc['selector']}",
                                description=f"Text content is truncated inside fixed height container with overflow hidden on {target_url}.\n\nContainer Text: '{trunc['text']}'\nScroll Height: {trunc['scrollHeight']}px vs Client Height: {trunc['clientHeight']}px\nSelector: {trunc['selector']}",
                                element_selector=trunc['selector'],
                                screenshot=ss_path,
                                status='open',
                                steps_to_reproduce=[
                                    f"Navigate to {target_url}",
                                    f"Inspect container '{trunc['selector']}'",
                                    f"Observe content height ({trunc['scrollHeight']}px) exceeds element height ({trunc['clientHeight']}px)"
                                ]
                            )
                            bugs_created.append(bug)
                            page_bugs_created += 1
                except Exception as e:
                    logger.error(f"Error checking text truncation on {target_url}: {e}")

                # -------------------------------------------------------------
                # Check 4: Failed Asset Loads (404 CSS / Fonts / Scripts)
                # -------------------------------------------------------------
                for asset in failed_assets[:3]:
                    key = ('failed_asset', target_url, asset['url'])
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
                # Check 5: Dead / Non-Functional Buttons & Links
                # -------------------------------------------------------------
                try:
                    candidates = page.evaluate("""
                        () => {
                            const out = [];
                            const sel = 'button, [role="button"], input[type="submit"], input[type="button"], input[type="reset"], a[href="#"], a[href^="javascript:"]';
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
                        continue

                    key = ('dead_click', target_url, selector, text)
                    if key in seen_bug_keys:
                        continue

                    try:
                        loc = page.locator(selector).first
                        if not loc.is_visible():
                            continue

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
                            mutated = False
                        navigated = page.url != before_url

                        worked = navigated or mutated or fired_request or fired_dialog or opened_popup

                        if not worked:
                            seen_bug_keys.add(key)
                            ss_path = save_ui_screenshot(page, selector=selector, prefix="ui_dead_click")
                            bug = Bug.objects.create(
                                application=application,
                                bug_type='ui',
                                severity=BugSeverity.MEDIUM,
                                title=f"[Dead Click] Button/Link appears non-functional: \"{text}\"",
                                description=(
                                    f"Clicking the interactive element labeled \"{text}\" on page {target_url} produced no "
                                    f"observable effect — no URL change, DOM update, network request, dialog, or new tab.\n\n"
                                    f"Selector: {selector}\n"
                                    f"Please verify manually before treating as confirmed."
                                ),
                                element_selector=selector,
                                screenshot=ss_path,
                                status='open',
                                steps_to_reproduce=[
                                    f"Navigate to {target_url}",
                                    f"Click the element \"{text}\" ({selector})",
                                    "Observe that no navigation, DOM change, or network activity occurs.",
                                ],
                            )
                            bugs_created.append(bug)
                            page_bugs_created += 1

                        if navigated:
                            try:
                                page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                                page.wait_for_timeout(500)
                            except Exception as nav_err:
                                logger.warning(f"Could not restore {target_url} after dead-click test: {nav_err}")
                                break

                    except Exception as click_err:
                        logger.warning(f"Dead-click check failed for \"{text}\" on {target_url}: {click_err}")
                        continue

                # -------------------------------------------------------------
                # Check 6: Automated Input Fuzzing & Boundary Check
                # -------------------------------------------------------------
                try:
                    import re
                    input_candidates = page.evaluate("""
                        () => {
                            return Array.from(document.querySelectorAll('input, textarea')).map((el, idx) => {
                                const rect = el.getBoundingClientRect();
                                const isVisible = rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden';
                                return {
                                    idx,
                                    tagName: el.tagName.toLowerCase(),
                                    type: (el.type || 'text').toLowerCase(),
                                    name: el.name || '',
                                    id: el.id || '',
                                    placeholder: el.placeholder || '',
                                    isVisible,
                                    isDisabled: el.disabled || el.readOnly,
                                    selector: el.id ? `#${CSS.escape(el.id)}` : (el.name ? `${el.tagName.toLowerCase()}[name="${CSS.escape(el.name)}"]` : `${el.tagName.toLowerCase()}:nth-of-type(${idx + 1})`)
                                };
                            }).filter(i => i.isVisible && !i.isDisabled && !['hidden', 'submit', 'button', 'checkbox', 'radio', 'file', 'image', 'reset'].includes(i.type));
                        }
                    """)

                    for inp in input_candidates[:6]:
                        sel = inp['selector']
                        attr_text = f"{inp['type']} {inp['name']} {inp['id']} {inp['placeholder']}".lower()

                        is_phone_field = inp['type'] == 'tel' or any(k in attr_text for k in ['phone', 'mobile', 'cell', 'contact', 'whatsapp', 'phone_number'])
                        is_email_field = inp['type'] == 'email' or any(k in attr_text for k in ['email', 'mail'])

                        try:
                            loc = page.locator(sel).first
                            if not loc.is_visible():
                                continue

                            field_label = inp['name'] or inp['id'] or inp['placeholder'] or sel

                            # Case A: Phone/Mobile Field Fuzzing
                            if is_phone_field:
                                key = ('input_fuzz_phone', target_url, sel)
                                if key not in seen_bug_keys:
                                    test_payload = "ABC#$@9876543210"
                                    loc.fill('')
                                    loc.type(test_payload, delay=30)
                                    loc.evaluate("el => el.dispatchEvent(new Event('blur'))")
                                    page.wait_for_timeout(200)

                                    val_after = loc.input_value()
                                    has_invalid_chars = bool(re.search(r'[A-Za-z#$@]', val_after))
                                    is_html5_valid = loc.evaluate("el => el.validity ? el.validity.valid : true")

                                    if has_invalid_chars and is_html5_valid:
                                        seen_bug_keys.add(key)
                                        ss_path = save_ui_screenshot(page, selector=sel, prefix="ui_input_fuzz")
                                        bug = Bug.objects.create(
                                            application=application,
                                            bug_type='ui',
                                            severity=BugSeverity.HIGH,
                                            title=f"[Input Validation Defect] Mobile/Phone field accepts invalid characters: \"{field_label}\"",
                                            description=(
                                                f"The mobile/phone number input field '{field_label}' on page {target_url} accepts non-numeric characters.\n\n"
                                                f"Selector: {sel}\n"
                                                f"Tested Payload: '{test_payload}'\n"
                                                f"Value Accepted in Input: '{val_after}'"
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

                                    loc.fill('')

                            # Case B: Email Field Fuzzing
                            elif is_email_field:
                                key = ('input_fuzz_email', target_url, sel)
                                if key not in seen_bug_keys:
                                    invalid_email = "invalid_email_test_123"
                                    loc.fill('')
                                    loc.type(invalid_email, delay=30)
                                    loc.evaluate("el => el.dispatchEvent(new Event('blur'))")
                                    page.wait_for_timeout(200)

                                    is_html5_valid = loc.evaluate("el => el.validity ? el.validity.valid : true")
                                    val_after = loc.input_value()

                                    if is_html5_valid and val_after == invalid_email:
                                        seen_bug_keys.add(key)
                                        ss_path = save_ui_screenshot(page, selector=sel, prefix="ui_email_fuzz")
                                        bug = Bug.objects.create(
                                            application=application,
                                            bug_type='ui',
                                            severity=BugSeverity.HIGH,
                                            title=f"[Input Validation Defect] Email field accepts malformed email format: \"{field_label}\"",
                                            description=(
                                                f"The email input field '{field_label}' on page {target_url} accepts malformed email string without HTML5/JS validation.\n\n"
                                                f"Selector: {sel}\n"
                                                f"Tested Payload: '{invalid_email}'"
                                            ),
                                            element_selector=sel,
                                            screenshot=ss_path,
                                            status='open',
                                            steps_to_reproduce=[
                                                f"Navigate to {target_url}",
                                                f"Type invalid email string '{invalid_email}' into field '{field_label}' ({sel})",
                                                "Trigger blur event and observe missing validation warning."
                                            ]
                                        )
                                        bugs_created.append(bug)
                                        page_bugs_created += 1

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

    try:
        return run_sync_in_thread(_do_ui_scan)
    except Exception as e:
        logger.error(f"Error executing run_ui_scan in thread: {e}")
        return []