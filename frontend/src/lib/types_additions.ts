// ─────────────────────────────────────────────────────────────────────────────
// ADD THESE to the bottom of frontend/src/lib/types.ts
// ─────────────────────────────────────────────────────────────────────────────

export interface VisualBaseline {
    id: number;
    page: number;
    step_number: number;
    screenshot_path: string;
    width: number;
    height: number;
    created_at: string;
    updated_at: string;
}

export interface VisualDiff {
    id: number;
    test_run: number;
    baseline: number | null;
    step_number: number;
    diff_percentage: number;
    diff_screenshot_path: string;
    status: 'PASSED' | 'FAILED' | 'NO_BASELINE';
    created_at: string;
}

export interface APITestCase {
    id: number;
    application: number;
    api_endpoint: number | null;
    title: string;
    method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
    url: string;
    headers: Record<string, string>;
    body: Record<string, any>;
    expected_status: number;
    expected_body_contains: string[];
    auth_required: boolean;
    ai_generated: boolean;
    created_at: string;
}

export interface APITestRun {
    id: number;
    api_test_case: number;
    status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
    actual_status_code: number | null;
    response_body: string;
    response_time_ms: number | null;
    error: string;
    passed: boolean;
    failure_reason: string;
    created_at: string;
}