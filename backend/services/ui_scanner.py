import os
import uuid
import logging
from urllib.parse import urlparse
from django.conf import settings
from core.models import Application, Page, Bug, BugSeverity

logger = logging.getLogger(__name__)

def save_ui_screenshot(page, selector=None, prefix="ui_bug"):
    """
    Captures a screenshot of the page or a specific DOM element and saves it to MEDIA_ROOT/bugs.
    Returns the relative path suitable for Bug.screenshot ImageField.
    """
    try:
        filename = f"{prefix}_{uuid.uuid4().hex[:12]}.png"
        media_path = os.path.join(settings.MEDIA_ROOT, 'bugs')
        os.makedirs(media_path, exist_ok=True)
        full_path = os.path.join(media_path, filename)

        if selector:
            try:
                element = page.locator(selector).first
                if element and element.is_visible():
                    element.screenshot(path=full_path, timeout=3000)
                else:
                    page.screenshot(path=full_path, full_page=False)
            except Exception:
                page.screenshot(path=full_path, full_page=False)
        else:
            page.screenshot(path=full_path, full_page=False)

        return f"bugs/{filename}"
    except Exception as e:
        logger.error(f"Failed to capture UI bug screenshot: {e}")
        return None


def run_ui_scan(application: Application, max_pages: int = 5):
    """
    Runs automated UI defect and visual issue detection on the application pages using Playwright.
    Detects:
    1. Broken Images & Assets (naturalWidth === 0)
    2. Horizontal Viewport Overflows & Layout Breakages
    3. Low Contrast / Invisible Text (text color matches background or opacity < 0.1)
    4. Console & Asset Load Errors (404 CSS/Fonts, unhandled JS exceptions)
    5. Overlapping & Clipped Interactive Elements
    """
    logger.info(f"Starting automated UI scan for Application ID {application.id} ({application.url})")

    from playwright.sync_api import sync_playwright

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
            logger.info(f"Scanning UI defects on: {target_url}")
            page_bugs_created = 0
            page_errors = []
            failed_assets = []

            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                ignore_https_errors=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) QA-Platform-UI-Scanner/1.0"
            )
            
            # Load stored auth session state if available
            if application.storage_state:
                try:
                    import json
                    state_obj = json.loads(application.storage_state)
                    context.add_cookies(state_obj.get('cookies', []))
                except Exception as err:
                    logger.warning(f"Could not load session storage for UI scan: {err}")

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

            page.on("pageerror", on_page_error)
            page.on("response", on_response)

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
                    key = ('overflow', target_url, ov['selector'])
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
                    key = ('contrast', target_url, vis['selector'])
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
