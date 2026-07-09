export interface User {
  id: number;
  username: string;
  email: string;
}

export interface Application {
  id: number;
  user: User;
  url: string;
  base_url: string;
  login_url: string | null;
  username: string | null;
  password: string | null;
  status: 'IDLE' | 'DISCOVERING' | 'DISCOVERED' | 'FAILED';
  discovery_source: 'mcp' | 'browser' | null;
  login_status: 'NOT_ATTEMPTED' | 'SUCCESS' | 'FAILED';
  login_error: string | null;
  storage_state: string | null;
  page_count: number;
  api_count: number;
  test_case_count: number;
  bug_count: number;
  industry?: string | null;
  created_at: string;
}

export interface Page {
  id: number;
  app: number;
  url: string;
  title: string | null;
  forms: Form[];
  buttons: Button[];
  page_type?: string;
  elements?: Record<string, any>;
  workflows?: string[];
  created_at: string;
}

export type PageDetail = Page;

export interface FormField {
  name: string;
  type: string;
  id: string;
  placeholder?: string;
}

export interface Form {
  id: string;
  action: string;
  method: string;
  fields: FormField[];
}

export interface Button {
  text: string;
  selector: string;
}

export interface TestStep {
  action: 'navigate' | 'fill' | 'click' | 'wait' | 'assert' | 'hover' | 'scroll' | 'select' | 'screenshot';
  selector: string;
  target: string;
  value: string;
}

// export interface TestCase {
//   id: number;
//   app: number;
//   title: string;
//   category?: 'Generic' | 'Industry Flow' | 'Access Control';
//   steps: TestStep[];
//   expected_result: string;
//   ai_generated: boolean;
//   validation_status: 'DRAFT' | 'VERIFIED' | 'BROKEN';
//   model_used?: string;
//   created_at: string;
// }

export interface TestCase {
  id?: number;
  app: number;
  title: string;
  category?: 'Generic' | 'Industry Flow' | 'Access Control';
  steps: TestStep[];
  expected_result: string;
  ai_generated: boolean;
  validation_status?: 'DRAFT' | 'VERIFIED' | 'BROKEN';
  model_used?: string;
  created_at?: string;
}

export interface TestResult {
  id: number;
  test_run: number;
  step_number: number;
  status: 'PASSED' | 'FAILED';
  error: string | null;
  screenshot: string | null;
  created_at: string;
}

export interface TestRun {
  id: number;
  test_case: number;
  test_case_title: string;
  app_url: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
  metadata: Record<string, unknown>;
  results: TestResult[];
  bugs_found: number;
  created_at: string;
}

export interface APIEndpoint {
  id: number;
  application: number;
  method: string;
  url_pattern: string;
  request_schema: Record<string, string>;
  response_schema: Record<string, string>;
  auth_type: string | null;
  created_at: string;
  updated_at: string;
}

export interface Bug {
  id: number;
  application?: number;
  test_run: number | null;
  test_case_id: number | null;
  app_id: number | null;
  test_case_title: string | null;
  app_url: string | null;
  title: string;
  description: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  api_endpoint: number | null;
  test_case_steps: TestStep[];
  test_run_results: TestResult[];
  bug_type?: string;
  steps_to_reproduce?: string[];
  screenshot?: string | null;
  element_selector?: string | null;
  status?: 'open' | 'confirmed' | 'resolved';
  created_at: string;
}

export interface CeleryTask {
  id: number;
  task_id: string;
  task_type: string;
  status: 'pending' | 'progress' | 'success' | 'failed';
  progress: number;
  result: {
    status_text?: string;
    step_number?: number;
    total_steps?: number;
    pages_discovered?: number;
    tests_generated?: number;
    [key: string]: unknown;
  };
  error: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface AgentSession {
  id: number;
  application: number;
  task_type: string;
  status: 'running' | 'completed' | 'failed';
  llm_model: string;
  steps_taken: {
    step: number;
    action: string;
    result: string;
  }[];
  tokens_used: number;
  duration_seconds: number | null;
  result_summary: string | null;
  created_at: string;
}
