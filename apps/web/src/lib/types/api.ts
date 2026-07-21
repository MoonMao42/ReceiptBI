/**
 * API 类型定义
 * 消除 any 类型，提供类型安全
 */

import type {
  ChartSpec,
  LegacyVisualization,
} from "@/lib/charts";

export type {
  ChartAggregation,
  ChartDataPoint,
  ChartDataRef,
  ChartEncoding,
  ChartFieldKind,
  ChartOrientation,
  ChartPaletteId,
  ChartPresentation,
  ChartSpec,
  ChartStack,
  ChartType,
  ChartValueFormat,
  ChartXEncoding,
  ChartYEncoding,
  LegacyVisualization,
} from "@/lib/charts";

// ===== 通用类型 =====

/** 数据库查询结果行 */
export type DataRow = Record<string, string | number | boolean | null>;

export interface ModelExtraOptions {
  api_format?: "openai_compatible" | "anthropic_native" | "ollama_local" | "custom";
  headers?: Record<string, string>;
  query_params?: Record<string, string>;
  api_key_optional?: boolean;
  healthcheck_mode?: "chat_completion" | "models_list";
}

export type ConnectionSSLMode =
  | "disable"
  | "prefer"
  | "require"
  | "verify-ca"
  | "verify-full";

export interface ConnectionExtraOptions {
  sslmode?: ConnectionSSLMode;
  sslrootcert?: string | null;
  sslcert?: string | null;
  sslkey?: string | null;
  schema?: string | null;
}

export interface ConnectionSummary {
  id: string;
  name: string;
  driver: string;
  host?: string | null;
  /** Serialized name used by the live connection API. */
  database: string | null;
  /** Compatibility fallback for legacy payloads. */
  database_name?: string | null;
  extra_options?: ConnectionExtraOptions;
  is_default: boolean;
}

export interface ConfiguredConnection extends ConnectionSummary {
  host: string | null;
  port: number | null;
  username: string | null;
  created_at: string;
}

export interface ModelSummary {
  id: string;
  name: string;
  provider: string;
  model_id: string;
  is_default: boolean;
  is_active?: boolean;
  api_key_configured?: boolean;
  credential_state?: "missing" | "readable" | "unreadable" | "not_required";
  health_status?: "unknown" | "healthy" | "unhealthy";
  last_checked_at?: string | null;
  last_error_category?:
    | "auth"
    | "timeout"
    | "connection"
    | "model_endpoint"
    | "model_not_found"
    | "rate_limited"
    | "provider_format"
    | "unknown"
    | null;
  last_response_time_ms?: number | null;
  extra_options?: ModelExtraOptions;
}

export interface ConfiguredModel extends ModelSummary {
  base_url?: string;
  created_at: string;
}

export interface ModelDiagnostics {
  resolved_provider?: string;
  resolved_base_url?: string;
  api_format?: string;
  api_key_required?: boolean;
  error_category?: string;
}

export interface AgentTraceEntry {
  attempt?: number;
  phase?: string;
  status?: "success" | "error" | "repaired" | "info";
  message?: string;
  error_code?: string;
  error_category?: string;
  recoverable?: boolean;
  sql?: string;
  python?: string;
}

export interface ExecutionContextSummary {
  model_id?: string;
  model_name?: string;
  model_identifier?: string;
  source_provider?: string;
  resolved_provider?: string;
  provider_summary?: string;
  connection_id?: string;
  connection_name?: string;
  connection_driver?: string;
  connection_host?: string;
  database_name?: string;
  context_rounds?: number;
  api_format?: string;
  project_id?: string;
}

export interface ReportMetric {
  label: string;
  value: string;
  context?: string | null;
}

export interface ConfirmationRequest {
  key: string;
  question: string;
  options: string[];
  reason: string;
}

export interface BusinessConfirmationResponse {
  analysis_run_id: string;
  resume_run_id: string;
  project_id: string;
  conversation_id: string;
  key: string;
  selected_option: string;
  ready_to_continue: boolean;
}

export interface ReportAction {
  kind: "add_data" | "confirm";
  label: string;
  reason: string;
  requested_data: string[];
  confirmation_key?: string | null;
  options: string[];
}

export interface ReportNextAction {
  kind: "deepen" | "compare" | "verify" | "repeat";
  label: string;
  prompt: string;
  reason: string;
  recommended: boolean;
}

export interface AnalysisReport {
  status: "completed" | "waiting_confirmation" | "needs_data";
  title: string;
  summary: string;
  primary_result?: string | null;
  findings: string[];
  metrics: ReportMetric[];
  evidence: string[];
  action?: ReportAction | null;
  next_actions?: ReportNextAction[];
  follow_ups: string[];
  confirmation?: ConfirmationRequest | null;
  visualization?: Visualization | null;
}

export type CorrectionApplicationStatus = "verified" | "definition_only" | "failed";

/**
 * System-owned receipt for a correction rerun. This must be produced from
 * execution evidence, never inferred from report prose.
 */
export interface CorrectionApplication {
  version?: number;
  kind?: "correction_application";
  correction_id: string | null;
  source_run_id: string | null;
  semantic_entry_id?: string | null;
  rule_key?: string | null;
  rule_value?: string | null;
  definition_hash?: string | null;
  final_result_name?: string | null;
  application_result_name?: string | null;
  source_result_name?: string | null;
  source_refs?: Array<Record<string, unknown>>;
  action_kind?: string | null;
  before_rows?: number | null;
  after_rows?: number | null;
  excluded_rows?: number | null;
  input_hash?: string | null;
  result_hash?: string | null;
  status: CorrectionApplicationStatus;
  summary?: string | null;
  checks?: string[] | null;
}

export interface Project {
  id: string;
  name: string;
  description?: string | null;
  status: string;
  extra_data: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SuggestedQuestion {
  label: string;
  prompt: string;
  reason: string;
}

export interface SuggestedQuestionsResponse {
  items: SuggestedQuestion[];
  generated_by: "ai" | "preflight";
  context_signature: string;
}

export type SemanticExecutionState =
  | "definition_only"
  | "needs_validation"
  | "verified"
  | "blocked";

export type SemanticSourceScope =
  | "project"
  | "local_database"
  | "remote_database"
  | "csv"
  | "excel"
  | "parquet"
  | "json"
  | "other_file"
  | "cross_source"
  | "unresolved";

export interface SemanticSourceRef {
  source_id: string;
  logical_name: string;
  name: string;
  kind: "file" | "connection";
  format?: string | null;
}

export interface SemanticEntry {
  id: string;
  project_id: string;
  key: string;
  value: string;
  entry_type:
    | "metric"
    | "dimension"
    | "relationship"
    | "business_rule"
    | "cleaning_rule"
    | "verified_query";
  state: "candidate" | "confirmed" | "locked";
  confidence: number;
  is_active?: boolean;
  revision_number?: number;
  active_revision_id?: string | null;
  definition?: Record<string, unknown> | null;
  execution_state?: SemanticExecutionState;
  execution_details?: {
    summary?: string | null;
    last_verified_run_id?: string | null;
    verified_at?: string | null;
    [key: string]: unknown;
  };
  allowed_actions: SemanticBatchAction[];
  validity: "active" | "unverified" | "stale";
  evidence: Record<string, unknown>[];
  source_refs?: SemanticSourceRef[];
  source_scope?: SemanticSourceScope;
  source: "inferred" | "user" | "verified_analysis" | "imported";
  created_at: string;
  updated_at: string;
}

export interface SemanticKnowledgePage {
  items: SemanticEntry[];
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
  next_offset: number | null;
}

export interface SemanticKnowledgeSummary {
  active_total: number;
  pending_total: number;
  relationship_total: number;
  confirmed_total: number;
  locked_total: number;
}

export type SemanticBatchAction =
  | "ignore"
  | "queue_validation"
  | "attest"
  | "remember"
  | "restore";

export interface SemanticBatchItem {
  entry_id: string;
  expected_active_revision_id: string;
}

export interface SemanticBatchResult {
  action: SemanticBatchAction;
  items: SemanticEntry[];
  validation_prompt?: string | null;
  queued_entry_ids: string[];
  validation_selection: SemanticBatchItem[];
}

export interface SemanticRevisionSnapshot {
  key: string;
  value: string;
  entry_type: SemanticEntry["entry_type"];
  state: SemanticEntry["state"];
  confidence: number;
  definition: Record<string, unknown> | null;
  validity: SemanticEntry["validity"];
  execution_state: SemanticExecutionState;
  execution_details: Record<string, unknown>;
  evidence: Record<string, unknown>[];
  source: SemanticEntry["source"];
  is_active: boolean;
}

export interface SemanticEntryRevision {
  id: string;
  project_id: string;
  semantic_entry_id: string;
  revision_number: number;
  parent_revision_id: string | null;
  restored_from_revision_id: string | null;
  mutation_kind: string;
  actor_source: string;
  reason: string | null;
  source_correction_id: string | null;
  snapshot: SemanticRevisionSnapshot;
  created_at: string;
}

export interface AnalysisCorrection {
  id: string;
  project_id: string;
  analysis_run_id: string;
  semantic_entry_id?: string | null;
  target_ref?: string | null;
  target_key?: string | null;
  selection?: AnalysisCorrectionSelection | null;
  correction_type:
    | "business_rule"
    | "metric_definition"
    | "filter_rule"
    | "relationship_rule"
    | "interpretation";
  text: string;
  scope: "run" | "project";
  state: "recorded" | "promoted";
  evidence: Record<string, unknown>[];
  created_at: string;
  updated_at: string;
}

export interface AnalysisCorrectionSelection {
  kind: "metric_column";
  field_ref: string;
}

export interface AnalysisCorrectionTarget {
  target_ref: string;
  label: string;
  description?: string | null;
  correction_type: AnalysisCorrection["correction_type"];
}

export interface AnalysisCorrectionTargetOption {
  kind: "metric_column";
  field_ref: string;
  label: string;
  description: string;
}

export interface ProjectDataSource {
  id: string;
  project_id: string;
  connection_id?: string | null;
  kind: "file" | "connection";
  name: string;
  format?: string | null;
  status: "attached" | "ready" | "needs_confirmation" | "error" | "superseded";
  fingerprint?: string | null;
  profile_data: {
    summary?: string;
    sample?: DataRow[];
    is_current?: boolean;
    replacement_of?: string;
    activation_state?: string;
    [key: string]: unknown;
  };
  created_at: string;
  updated_at: string;
}

export interface PreflightIssue {
  code: string;
  title: string;
  detail: string;
  severity: "info" | "warning" | "critical";
  automatic: boolean;
  count?: number | null;
}

export interface PreflightAmbiguity {
  key: string;
  question: string;
  reason: string;
  options: string[];
}

export interface PreflightReport {
  id: string;
  project_id: string;
  data_source_id: string;
  status: string;
  summary: string;
  issues: PreflightIssue[];
  ambiguities: PreflightAmbiguity[];
  inferred_schema?: Record<string, unknown>;
  source_snapshot?: {
    schema_drift?: {
      added_columns?: string[];
      removed_columns?: string[];
      type_changes?: Array<{
        column?: string;
        previous_type?: string;
        current_type?: string;
      }>;
      requires_confirmation?: boolean;
    };
    replacement?: {
      status?: string;
      replaces_source_id?: string | null;
      active_source_id?: string | null;
    };
    [key: string]: unknown;
  };
  fingerprint?: string | null;
  created_at: string;
  updated_at?: string;
}

export interface SanitationRecipe {
  id: string;
  project_id: string;
  data_source_id: string;
  name: string;
  status: "applied" | "needs_attention" | "candidate" | "reverted" | string;
  operations: Record<string, unknown>[];
  input_fingerprint?: string | null;
  output_fingerprint?: string | null;
  active_revision_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface SanitationRecipeRevision {
  id: string;
  recipe_id: string;
  revision_number: number;
  parent_revision_id?: string | null;
  state: "candidate" | "confirmed" | "reverted";
  operations: Record<string, unknown>[];
  input_contract: Record<string, unknown>;
  output_contract: Record<string, unknown>;
  actor_source: string;
  reason?: string | null;
  source_correction_id?: string | null;
  created_at: string;
}

export interface SanitationTemplateSummary {
  id: string;
  name: string;
  active_revision_id: string;
  revision_count: number;
  compatible_source_ids: string[];
}

export interface SanitationTemplatePreview {
  template_id: string;
  template_name: string;
  template_active_revision_id: string;
  template_operations_hash: string;
  source_id: string;
  source_fingerprint: string;
  preview_output_fingerprint: string;
  current_working_fingerprint?: string | null;
  current_recipe_active_revision_id?: string | null;
  before: { rows: number; columns: number };
  after: { rows: number; columns: number };
  summary: string;
  issues: PreflightIssue[];
  can_apply: boolean;
}

export type VisualCleaningOperation =
  | { operation: "trim_text"; column: string }
  | { operation: "fill_missing"; column: string; value: 0 }
  | { operation: "normalize_datetime"; column: string }
  | { operation: "normalize_currency"; column: string }
  | { operation: "drop_exact_duplicates" };

export interface VisualCleaningSnapshot {
  rows: number;
  columns: number;
  sample: DataRow[];
}

export interface VisualCleaningChange {
  column: string;
  changed_count: number;
}

export interface VisualCleaningPreview {
  source_id: string;
  operations_hash: string;
  source_fingerprint: string;
  preview_output_fingerprint: string;
  current_working_fingerprint?: string | null;
  current_recipe_active_revision_id?: string | null;
  before: VisualCleaningSnapshot;
  after: VisualCleaningSnapshot;
  changes: VisualCleaningChange[];
  can_apply: boolean;
}

export interface VisualCleaningApplyResult {
  recipe: SanitationRecipe;
  revision: SanitationRecipeRevision;
  preflight: PreflightReport;
}

export interface AnalysisRunSummary {
  id: string;
  project_id: string;
  conversation_id?: string | null;
  query: string;
  state: "understanding" | "waiting_confirmation" | "investigating" | "completed" | "needs_attention";
  stage: string;
  report: {
    title?: string;
    summary?: string;
    [key: string]: unknown;
  };
  checkpoint: Record<string, unknown>;
  error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AnalysisArtifact {
  id: string;
  project_id: string;
  analysis_run_id: string;
  kind:
    | "report"
    | "metric"
    | "table"
    | "chart"
    | "file"
    | "evidence"
    | "result_snapshot"
    | "change_brief";
  title: string;
  payload: Record<string, unknown>;
  technical_details: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface StandingMaterialityRule {
  id: string;
  metric: string;
  scope: "overall" | "by_key" | "either";
  direction: "any" | "increase" | "decrease";
  change_kind: "absolute" | "percent";
  threshold: number;
}

export interface StandingMaterialityPolicy {
  version: 1;
  match: "any";
  percent_unit: "ratio";
  top_driver_limit: number;
  rules: StandingMaterialityRule[];
}

export interface StandingBaseline {
  snapshot_id: string;
  analysis_run_id: string;
  artifact_id: string;
  input_token: string;
  shape_hash: string;
  validation_state: "validated";
  validation_evidence: string[];
  accepted_at: string;
}

export interface StandingInFlightClaim {
  input_token: string;
  idempotency_key: string;
  analysis_run_id: string;
  conversation_id: string;
  user_message_id: string;
  trigger: "manual" | "source_version" | "app_start_overdue";
  claimed_at: string;
  expires_at: string;
}

export interface StandingAnalysis {
  schema_version: 1;
  id: string;
  project_id: string;
  name: string;
  query: string;
  playbook_id: string;
  playbook_shape_hash: string;
  watched_source_roles: string[];
  state: "active" | "paused" | "needs_attention";
  trigger_policy: "app_open_and_source_change";
  overdue_after_seconds: number;
  materiality: StandingMaterialityPolicy;
  baseline?: StandingBaseline | null;
  in_flight?: StandingInFlightClaim | null;
  last_evaluated_token?: string | null;
  last_run_id?: string | null;
  last_brief_artifact_id?: string | null;
  attention_reason?: string | null;
  created_at: string;
  updated_at: string;
}

export interface StandingPrepareResponse {
  outcome:
    | "no_change"
    | "prepared"
    | "already_running"
    | "already_completed"
    | "needs_attention"
    | "paused";
  standing_analysis: StandingAnalysis;
  run_id?: string | null;
  conversation_id?: string | null;
  user_message_id?: string | null;
  input_token?: string | null;
  brief_artifact_id?: string | null;
  attention_reason?: string | null;
}

export interface AppSettings {
  default_model_id?: string | null;
  default_connection_id?: string | null;
  context_rounds: number;
  python_enabled: boolean;
  diagnostics_enabled: boolean;
  auto_repair_enabled: boolean;
}

export interface SystemCapabilities {
  install_profile: "core" | "analytics";
  python_enabled: boolean;
  diagnostics_enabled: boolean;
  auto_repair_enabled: boolean;
  analytics_installed: boolean;
  available_python_libraries: string[];
  missing_optional_libraries: string[];
}

// ===== SSE 事件类型 =====

/** SSE 进度事件数据 */
export interface SSEProgressData {
  step?: string;
  stage?: string;
  phase?: string;
  attempt?: number;
  message: string;
  conversation_id?: string;
  execution_context?: ExecutionContextSummary;
  diagnostic_entry?: AgentTraceEntry;
  analysis_run_id?: string;
  project_id?: string;
  analysis_state?: "understanding" | "waiting_confirmation" | "investigating" | "completed" | "needs_attention";
  resumable?: boolean;
}

/** SSE 结果事件数据 */
export interface SSEResultData {
  content: string;
  sql?: string;
  python?: string;
  data?: DataRow[];
  rows_count?: number;
  execution_time?: number;
  execution_context?: ExecutionContextSummary;
  diagnostics?: AgentTraceEntry[];
  report?: AnalysisReport;
  analysis_state?: "understanding" | "waiting_confirmation" | "investigating" | "completed" | "needs_attention";
  analysis_run_id?: string;
  project_id?: string;
  resumable?: boolean;
  tool_history?: Array<Record<string, unknown>>;
  semantic_engine?: string;
  correction_application?: CorrectionApplication;
}

/** SSE 可视化事件数据 */
export interface SSEVisualizationData {
  chart: Visualization;
}

/** SSE 错误事件数据 */
export interface SSEErrorData {
  code: string;
  message: string;
  error_category?: string;
  failed_stage?: string;
  attempt?: number;
  conversation_id?: string;
  execution_context?: ExecutionContextSummary;
  diagnostics?: AgentTraceEntry[];
  analysis_run_id?: string;
  project_id?: string;
  analysis_state?: "needs_attention";
  resumable?: boolean;
  correction_application?: CorrectionApplication;
}

/** SSE 完成事件数据 */
export interface SSEDoneData {
  conversation_id?: string;
  message_id?: string | null;
}

/** SSE 思考阶段事件数据 */
export interface SSEThinkingData {
  stage: string;
  detail?: string;
}

/** SSE Python 输出事件数据 */
export interface SSEPythonOutputData {
  output: string;
  stream: "stdout" | "stderr";
}

/** SSE Python 图表事件数据 */
export interface SSEPythonImageData {
  image: string; // base64 编码
  format: "png" | "jpeg";
}

/** SSE 事件联合类型 */
export type SSEEventData =
  | { type: "progress"; data: SSEProgressData }
  | { type: "thinking"; data: SSEThinkingData }
  | { type: "result"; data: SSEResultData }
  | { type: "visualization"; data: SSEVisualizationData }
  | { type: "python_output"; data: SSEPythonOutputData }
  | { type: "python_image"; data: SSEPythonImageData }
  | { type: "error"; data: SSEErrorData }
  | { type: "done"; data: SSEDoneData };

// ===== 消息类型 =====

/** Current ChartSpec v1 plus the one-way compatibility shape for saved chats. */
export type Visualization = ChartSpec | LegacyVisualization;

/** 消息元数据 */
export interface MessageMetadata {
  kind?: string;
  sql?: string;
  python?: string;
  execution_time?: number;
  rows_count?: number;
  visualization?: Visualization;
  data?: DataRow[];
  python_output?: string;
  python_images?: string[];
  error?: string;
  error_code?: string;
  error_category?: string;
  failed_stage?: string;
  original_query?: string;
  execution_context?: ExecutionContextSummary;
  diagnostics?: AgentTraceEntry[];
  report?: AnalysisReport;
  analysis_state?: string;
  analysis_run_id?: string;
  project_id?: string;
  resumable?: boolean;
  tool_history?: Array<Record<string, unknown>>;
  semantic_engine?: string;
  correction_application?: CorrectionApplication;
  confirmation_key?: string;
  selected_option?: string;
}

/** API 返回的消息 */
export interface APIMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  metadata?: MessageMetadata;
  created_at: string;
}

/** 对话 */
export interface Conversation {
  id: string;
  title: string;
  model?: string;
  model_id?: string;
  connection_id?: string;
  connection_name?: string;
  provider_summary?: string;
  context_rounds?: number;
  project_id?: string;
  status: string;
  messages: APIMessage[];
  created_at: string;
  updated_at: string;
}

// ===== 对话列表类型 =====

/** 对话列表项 */
export interface ConversationListItem {
  id: string;
  title?: string | null;
  model?: string;
  model_id?: string;
  connection_id?: string;
  connection_name?: string;
  provider_summary?: string;
  context_rounds?: number;
  project_id?: string;
  is_favorite: boolean;
  message_count: number;
  status: string;
  created_at: string;
  updated_at: string;
}

/** 分页响应 */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ===== 错误类型 =====

/** API 错误 */
export interface APIError {
  message: string;
  code?: string;
  detail?: string | Array<{ msg: string; loc: string[] }>;
}

/** 类型守卫：检查是否为 Error 对象 */
export function isError(error: unknown): error is Error {
  return error instanceof Error;
}

/** 获取错误消息 */
export function getErrorMessage(error: unknown): string {
  if (isError(error)) {
    return error.message;
  }
  if (typeof error === "string") {
    return error;
  }
  return "未知错误";
}
