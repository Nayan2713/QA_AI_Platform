import logging
import time

from core.models import Application, Page, Bug, WebVitalsResult
from core.enums import BugSeverity

logger = logging.getLogger(__name__)

# Google's published Core Web Vitals "good" / "needs improvement" cutoffs.
# https://web.dev/articles/vitals — used only to compute a simple 0-100
# performance_score and to decide when a threshold-breach Bug is warranted;
# not an attempt to reproduce Lighthouse's exact scoring curve.
LCP_GOOD_MS = 2500
LCP_POOR_MS = 4000
CLS_GOOD = 0.1
CLS_POOR = 0.25
TTFB_GOOD_MS = 800
TTFB_POOR_MS = 1800

_WEB_VITALS_SCRIPT = """
() => new Promise((resolve) => {
    const result = { lcp: null, cls: 0, ttfb: null, transferSizeKb: 0 };

    try {
        const nav = performance.getEntriesByType('navigation')[0];
        if (nav) result.ttfb = nav.responseStart;
    } catch (e) {}

    try {
        const resources = performance.getEntriesByType('resource');
        let totalBytes = 0;
        for (const r of resources) totalBytes += (r.transferSize || 0);
        result.transferSizeKb = totalBytes / 1024;
    } catch (e) {}

    try {
        let lcpValue = null;
        const lcpObserver = new PerformanceObserver((list) => {
            const entries = list.getEntries();
            const last = entries[entries.length - 1];
            if (last) lcpValue = last.renderTime || last.loadTime;
        });
        lcpObserver.observe({ type: 'largest-contentful-paint', buffered: true });

        let clsValue = 0;
        const clsObserver = new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
                if (!entry.hadRecentInput) clsValue += entry.value;
            }
        });
        clsObserver.observe({ type: 'layout-shift', buffered: true });

        // Give buffered entries + any late shifts a moment to settle.
        setTimeout(() => {
            lcpObserver.disconnect();
            clsObserver.disconnect();
            result.lcp = lcpValue;
            result.cls = clsValue;
            resolve(result);
        }, 2000);
    } catch (e) {
        resolve(result);
    }
})
"""


def _score(lcp_ms, cls, ttfb_ms):
    """Simple weighted 0-100 score from the three signals we capture.
    Each signal maps 100 at the "good" cutoff down to 0 at the "poor"
    cutoff, matching Google's traffic-light bands, then weighted roughly
    the way Lighthouse weights LCP/CLS/TTFB-adjacent metrics."""
    def band(value, good, poor):
        if value is None:
            return 50  # unknown — don't punish or reward
        if value <= good:
            return 100
        if value >= poor:
            return 0
        return 100 * (poor - value) / (poor - good)

    lcp_score = band(lcp_ms, LCP_GOOD_MS, LCP_POOR_MS)
    cls_score = band(cls, CLS_GOOD, CLS_POOR)
    ttfb_score = band(ttfb_ms, TTFB_GOOD_MS, TTFB_POOR_MS)
    return round(lcp_score * 0.45 + cls_score * 0.25 + ttfb_score * 0.30, 1)


def run_web_vitals_scan(application: Application, max_pages: int = 5, task_id: str = None):
    """
    Visits application.url + up to max_pages-1 discovered Page rows and
    captures LCP / CLS / TTFB via the browser's own PerformanceObserver
    API — no Lighthouse/Node dependency needed since Playwright is already
    installed in this image.

    Same rule as every other scanner here: gather everything in memory,
    only touch the DB once the full scan succeeds. A failure partway
    through must leave prior WebVitalsResult/Bug rows untouched.
    """
    logger.info(f"Starting Web Vitals scan for Application ID {application.id} ({application.url})")

    from playwright.sync_api import sync_playwright
    from tasks.cancellation import check_cancelled
    from tasks.discovery import get_url_pattern

    target_pages = [(application.url, None)]
    discovered_pages = Page.objects.filter(app=application).exclude(url=application.url)[:max_pages - 1]
    for p in discovered_pages:
        target_pages.append((p.url, p.id))

    vitals_to_create = []
    bugs_to_create = []

    threshold = None
    try:
        from core.models import PerformanceThreshold
        threshold = PerformanceThreshold.for_application(application)
    except Exception:
        pass

    playwright = None
    browser = None
    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )

        for target_url, page_id in target_pages:
            if task_id:
                check_cancelled(task_id)

            context = browser.new_context(viewport={"width": 1280, "height": 800}, ignore_https_errors=True)
            page = context.new_page()

            try:
                page.goto(target_url, wait_until="load", timeout=15000)
                metrics = page.evaluate(_WEB_VITALS_SCRIPT)
            except Exception as e:
                logger.error(f"Web Vitals scan failed navigating to {target_url}: {e}")
                context.close()
                continue

            context.close()

            lcp_ms = metrics.get('lcp')
            cls_score = metrics.get('cls')
            ttfb_ms = metrics.get('ttfb')
            transfer_kb = metrics.get('transferSizeKb')
            score = _score(lcp_ms, cls_score, ttfb_ms)

            vitals_to_create.append(WebVitalsResult(
                application=application,
                page_id=page_id,
                url=target_url,
                lcp_ms=lcp_ms,
                cls_score=cls_score,
                ttfb_ms=ttfb_ms,
                transfer_size_kb=transfer_kb,
                performance_score=score,
            ))

            if threshold and lcp_ms is not None:
                pattern = get_url_pattern(target_url, application.url)
                if lcp_ms >= threshold.page_load_critical_ms:
                    severity, label, limit = BugSeverity.HIGH, 'critical', threshold.page_load_critical_ms
                elif lcp_ms >= threshold.page_load_warning_ms:
                    severity, label, limit = BugSeverity.MEDIUM, 'warning', threshold.page_load_warning_ms
                else:
                    severity = None

                if severity:
                    bugs_to_create.append(Bug(
                        application=application,
                        bug_type='performance',
                        severity=severity,
                        title=f"[Slow Page Load] {pattern} — LCP {int(lcp_ms)}ms",
                        description=(
                            f"Largest Contentful Paint exceeded the {label} page-load threshold "
                            f"({limit}ms) configured for this application.\n\n"
                            f"URL: {target_url}\nLCP: {int(lcp_ms)}ms\n"
                            f"CLS: {cls_score}\nTTFB: {ttfb_ms}ms\nPerformance score: {score}/100"
                        ),
                        status='open',
                        steps_to_reproduce=[
                            f"Navigate to {target_url}",
                            f"Measure Largest Contentful Paint: {int(lcp_ms)}ms",
                            f"Compare against the configured {label} threshold of {limit}ms",
                        ],
                    ))

    finally:
        try:
            if browser:
                browser.close()
        except Exception:
            pass
        try:
            if playwright:
                playwright.stop()
        except Exception:
            pass

    # Only touch the DB after the full scan has succeeded in memory.
    # Wrapped in its own atomic() so it creates a SAVEPOINT, not a new outer
    # transaction — this function is called from inside discovery.py's own
    # `with transaction.atomic():` block. Without this, any DB error here
    # (e.g. a constraint violation) poisons that entire outer transaction,
    # silently breaking unrelated writes later in the same request (this is
    # exactly what happened: a NOT NULL violation here caused "Failed to
    # save pages to DB" right after, wiping out an otherwise-successful
    # discovery run). With the savepoint, a failure here rolls back only
    # this insert — the outer transaction stays healthy.
    from django.db import transaction
    try:
        with transaction.atomic():
            if vitals_to_create:
                WebVitalsResult.objects.bulk_create(vitals_to_create, batch_size=50)
            if bugs_to_create:
                Bug.objects.bulk_create(bugs_to_create, batch_size=50)
    except Exception as db_err:
        logger.error(f"Web Vitals scan produced results but failed to save them: {db_err}")
        return []

    return vitals_to_create