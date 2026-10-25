/** Typed API client for the SENTINEL-X backend. */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8010";

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
      cache: "no-store",
    });
  } catch (err) {
    throw new ApiError(
      0,
      `Cannot reach SENTINEL-X API at ${API_BASE} (${String(err)})`,
      "network_error",
    );
  }
  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!res.ok) {
    const b = body as { message?: string; detail?: unknown; error?: string } | null;
    const message =
      b?.message ||
      (typeof b?.detail === "string" ? b.detail : JSON.stringify(b?.detail)) ||
      `HTTP ${res.status}`;
    throw new ApiError(res.status, message, b?.error);
  }
  return body as T;
}

export const apiGet = <T>(path: string) => request<T>(path);

export const apiPost = <T>(path: string, body?: unknown) =>
  request<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });

/* ------------------------------------------------------------------ types */

export type Decision =
  | "ALLOW"
  | "BLOCK"
  | "REQUIRE_APPROVAL"
  | "APPROVED"
  | "REJECTED"
  | "EXPIRED";

export interface EventItem {
  id: number;
  ts: string | null;
  run_id: string | null;
  scenario_id: string | null;
  session_id: string;
  agent_id: string;
  step_index: number | null;
  tool: string;
  resource: string | null;
  destination: string | null;
  sensitivity: string | null;
  action_summary: string;
  risk_score: number;
  risk_level: string;
  decision: Decision | string;
  policies: string[];
  explanation: string;
  executed: boolean;
  side_effect: boolean;
  approval_id: string | null;
  latency_ms: number;
  result: unknown;
  index?: number;
}

export interface EventsResponse {
  items: EventItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApprovalItem {
  id: string;
  run_id: string | null;
  step_index: number | null;
  session_id: string;
  agent_id: string;
  tool: string;
  params: Record<string, unknown>;
  resource: string | null;
  destination: string | null;
  sensitivity: string | null;
  risk_score: number;
  risk_level: string;
  explanation: string;
  policies: string[];
  fingerprint: string;
  status: string;
  requested_at: string | null;
  expires_at: string | null;
  decided_at: string | null;
  decision: string | null;
  decided_by: string | null;
  consumed: boolean;
  execution_event_id: number | null;
  outcome: string | null;
}

export interface IncidentItem {
  id: string;
  run_id: string | null;
  scenario_id: string | null;
  session_id: string;
  created_at: string | null;
  severity: string;
  title: string;
  trigger_policy: string;
  trigger_policy_name: string | null;
  trigger_policy_description: string | null;
  blocked_tool: string;
  blocked_resource: string | null;
  destination: string | null;
  explanation: string;
  sequence_summary: string;
  protected_tool_executed: boolean;
  blocked_event_id: number | null;
  status: string;
}

export interface StepItem {
  step_index: number;
  label: string;
  tool: string;
  params: Record<string, unknown>;
  status: string;
  decision: string | null;
  executed: boolean;
  risk_score: number;
  risk_level: string;
  explanation: string;
  policies: string[];
  event_id: number | null;
  approval_id: string | null;
}

export interface RunSummary {
  id: string;
  scenario_id: string;
  title: string;
  status: string;
  session_id: string;
  agent_id: string;
  summary: string;
  started_at: string | null;
  finished_at: string | null;
  incident_id: string | null;
  allowed_count: number;
  blocked_count: number;
  approval_count: number;
  executed_count: number;
}

export interface RunDetail extends RunSummary {
  steps: StepItem[];
  approvals: ApprovalItem[];
  events?: EventItem[];
  incident?: IncidentItem | null;
}

export interface IncidentDetail {
  incident: IncidentItem;
  timeline: EventItem[];
  steps: StepItem[];
  run: RunSummary | null;
  attack_explanation: string;
}

export interface EvaluationMetrics {
  available: boolean;
  suite?: string;
  total_cases: number;
  passed_cases: number;
  detection_rate: number | null;
  false_positive_rate: number | null;
  prevention_rate: number | null;
  decision_latency_avg_ms: number | null;
  decision_latency_p95_ms: number | null;
  attacks: number;
  benign: number;
  false_positives: number;
  cases?: { case: string; kind: string; passed: boolean }[];
  rows?: {
    case: string;
    kind: string;
    expected: string;
    actual: string;
    passed: boolean;
    latency_ms: number;
    detail: string;
  }[];
}

export interface Metrics {
  generated_at: string;
  actions_evaluated: number;
  allowed: number;
  blocked: number;
  approval_required: number;
  approved_executed: number;
  rejected: number;
  expired: number;
  executed_actions: number;
  side_effects_realized: number;
  prevented_side_effects: number;
  pending_approvals: number;
  open_incidents: number;
  avg_decision_latency_ms: number;
  by_scenario: Record<string, Record<string, number>>;
  evaluation: EvaluationMetrics;
}

export interface AgentItem {
  id: string;
  name: string;
  role: string;
  clearance: string;
  granted_tools: string[];
  description: string;
}

export interface PolicyItem {
  id: string;
  name: string;
  category: string;
  severity: string;
  description: string;
  effect: string;
  enabled: boolean;
}

export interface PoliciesResponse {
  items: PolicyItem[];
  total: number;
  engine: string;
  thresholds: {
    approval_threshold: number;
    block_threshold: number;
    approval_ttl_minutes: number;
  };
  fail_closed: boolean;
}

export interface ScenarioInfo {
  id: string;
  title: string;
  description: string;
  attack: boolean;
  agent_id: string;
  steps: { index: number; label: string; tool: string }[];
}

export interface DecisionResponse {
  approval: ApprovalItem;
  result: {
    decision: string;
    event_id: number | null;
    risk_score: number;
    risk_level: string;
    policies: string[];
    explanation: string;
    executed: boolean;
    side_effect: boolean;
    approval_id: string | null;
    result: unknown;
    latency_ms: number;
    error: string | null;
  };
}
