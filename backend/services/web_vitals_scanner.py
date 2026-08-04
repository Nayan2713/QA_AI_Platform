# backend/services/web_vitals_scanner.py
import json
import logging
from typing import Dict, Any, List
from playwright.sync_api import sync_playwright
from core.models import Application, Page, WebVitalsResult, Bug
from core.enums import BugSeverity
from tasks.cancellation import check_cancelled

logger = logging.getLogger(__name__)

# Script to inject PerformanceObserver and collect Web Vitals metrics (LCP, CLS, TTFB)
_WEB_VITALS_JS = """
async () => {
    return new Promise((resolve) => {
        let lcp = 0;
        let cls = 0;
        let ttfb = 0;

        // Navigation Timing for TTFB
        const navEntries = performance.getEntriesByType('navigation');
        if (navEntries.length > 0) {
            ttfb = navEntries[0].responseStart - navEntries[0].requestStart;
            if (ttfb < 0) ttfb = navEntries[0].responseStart;
        }

        let lcpObserver;
        let clsObserver;

        try {
            lcpObserver = new PerformanceObserver((entryList) => {
                const entries = entryList.getEntries();
                if (entries.length > 0) {
                    lcp = entries[entries.length - 1].startTime;
                }
            });
            lcpObserver.observe({ type: 'largest-contentful-paint', buffered: true });
        } catch (e) {}

        try {
            clsObserver = new PerformanceObserver((entryList) => {
                for (const entry of entryList.getEntries()) {
                    if (!entry.hadRecentInput) {
                        cls += entry.value;
                    }
                }
            });
            clsObserver.observe({ type: 'layout-shift', buffered: true });
        } catch (e) {}

        // Resolve after 2.5 seconds to capture buffered observer events
        setTimeout(() => {
            if (lcpObserver) lcpObserver.disconnect();
            if (clsObserver) clsObserver.disconnect();
            resolve({
                lcp_ms: Math.round(lcp || 0),
                cls: Math.round(cls * 1000) / 1000,
                ttfb_ms: Math.round(ttfb || 0)
            });
        }, 2500);
    });
}
"""

def compute_vitals_score(lcp_ms: float, cls: float, ttfb_ms: float) -> int:
    """
    Computes a 0-100 performance score based on Google Core Web Vitals thresholds:
    - LCP: Good <= 2500ms, Poor > 4000ms
    - CLS: Good <= 0.1, Poor > 0.25
    - TTFB: Good <= 800ms, Poor > 1800ms
    Weights: 45% LCP, 35% CLS, 20% TTFB
    """
    # LCP score (0-100)
    if lcp_ms <= 2500:
        lcp_score = 100
    elif lcp_ms <= 4000:
        lcp_score = 50 + 50 * (4000 - lcp_ms) / 1500
    else:
        lcp_score = max(0, 50 - 50 * (lcp_ms - 4000) / 4000)

    # CLS score (0-100)
    if cls <= 0.1:
        cls_score = 100
    elif cls <= 0.25:
        cls_score = 50 + 50 * (0.25 - cls) / 0.15
    else:
        cls_score = max(0, 50 - 50 * (cls - 0.25) / 0.5)

    # TTFB score (0-100)
    if ttfb_ms <= 800:
        ttfb_score = 100
    elif ttfb_ms <= 1800:
        ttfb_score = 50 + 50 * (1800 - ttfb_ms) / 1000
    else:
        ttfb_score = max(0, 50 - 50 * (ttfb_ms - 1800) / 2000)

    overall = 0.45 * lcp_score + 0.35 * cls_score + 0.20 * ttfb_score
    return int(round(max(0, min(100, overall))))

def run_web_vitals_scan(application: Application, task_id: str = None) -> List[WebVitalsResult]:
    """
    Scans application pages using Playwright to evaluate Core Web Vitals metrics.
    Gathers all results in memory first; bulk-creates records and bugs only after full scan succeeds.
    """
    pages_to_scan = list(Page.objects.filter(app=application))

    scan_targets = []

    if application.url:
        scan_targets.append({'url': application.url, 'page_obj': None})

    for p in pages_to_scan:
        if p.url and p.url != application.url:
            scan_targets.append({'url': p.url, 'page_obj': p})

    if not scan_targets:
        logger.warning(f"No pages found to scan Web Vitals for app #{application.id}")
        return []

    results_to_create = []
    bugs_to_create = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        context_kwargs = {"viewport": {"width": 1280, "height": 800}}

        if application.storage_state:
            try:
                context_kwargs["storage_state"] = json.loads(application.storage_state)
            except Exception as e:
                logger.warning(f"Failed to load storage state for web vitals: {e}")

        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        try:
            for target in scan_targets:
                if task_id:
                    check_cancelled(task_id)

                target_url = target['url']
                page_obj = target['page_obj']

                try:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(1000)
                    metrics = page.evaluate(_WEB_VITALS_JS)
                except Exception as err:
                    logger.warning(f"Failed to capture Web Vitals for {target_url}: {err}")
                    continue

                lcp = metrics.get('lcp_ms', 0)
                cls = metrics.get('cls', 0.0)
                ttfb = metrics.get('ttfb_ms', 0)
                score = compute_vitals_score(lcp, cls, ttfb)

                wv_res = WebVitalsResult(
                    application=application,
                    page=page_obj,
                    url=target_url,
                    lcp_ms=lcp,
                    cls=cls,
                    ttfb_ms=ttfb,
                    performance_score=score
                )
                results_to_create.append(wv_res)

                # Check for CWV breaches to raise bugs
                if lcp > 4000:
                    bugs_to_create.append(Bug(
                        application=application,
                        bug_type='performance',
                        severity=BugSeverity.HIGH,
                        title=f"[Poor CWV LCP] {target_url} Largest Contentful Paint took {lcp}ms",
                        description=f"LCP exceeded the 4000ms poor threshold (Observed: {lcp}ms, Score: {score}/100).",
                        steps_to_reproduce=[f"1. Navigate to {target_url}", f"2. Measure LCP (Observed: {lcp}ms)"],
                        status='open'
                    ))
                elif lcp > 2500:
                    bugs_to_create.append(Bug(
                        application=application,
                        bug_type='performance',
                        severity=BugSeverity.MEDIUM,
                        title=f"[Slow LCP] {target_url} Largest Contentful Paint took {lcp}ms",
                        description=f"LCP exceeded the 2500ms good threshold (Observed: {lcp}ms, Score: {score}/100).",
                        steps_to_reproduce=[f"1. Navigate to {target_url}", f"2. Measure LCP (Observed: {lcp}ms)"],
                        status='open'
                    ))

                if cls > 0.25:
                    bugs_to_create.append(Bug(
                        application=application,
                        bug_type='performance',
                        severity=BugSeverity.HIGH,
                        title=f"[Poor CWV CLS] {target_url} Cumulative Layout Shift is {cls}",
                        description=f"CLS exceeded the 0.25 poor threshold (Observed: {cls}).",
                        steps_to_reproduce=[f"1. Navigate to {target_url}", f"2. Observe layout stability (CLS: {cls})"],
                        status='open'
                    ))

        finally:
            browser.close()

    # Bulk-create results and bugs ONLY after full loop completes
    if results_to_create:
        created_results = WebVitalsResult.objects.bulk_create(results_to_create)
        if bugs_to_create:
            Bug.objects.bulk_create(bugs_to_create)
        logger.info(f"Successfully saved {len(created_results)} Web Vitals result(s) and {len(bugs_to_create)} bug(s).")
        return created_results

    return []
