/** API response types matching backend ORM models. */

export interface Dataset {
  id: string;
  name: string;
  file_format: string;
  file_size_bytes: number;
  row_count: number | null;
  status: "uploading" | "processing" | "ready" | "error";
  created_at: string;
  updated_at: string;
}

export interface Connection {
  id: string;
  name: string;
  db_type: string;
  host: string;
  port: number;
  database_name: string;
  status: "connected" | "disconnected" | "error";
  last_tested_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface ConversationListResponse {
  conversations: Conversation[];
  next_cursor: string | null;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface ConversationDetail {
  id: string;
  title: string;
  created_at: string;
  messages: Message[];
}

export interface SchemaColumn {
  column_name: string;
  data_type: string;
  is_nullable: boolean;
  is_primary_key: boolean;
  table_name?: string;
  foreign_key_ref?: string | null;
}

export interface DatasetDetail extends Dataset {
  duckdb_table_name: string;
  schema: SchemaColumn[];
}

export interface ConnectionDetail extends Connection {
  username: string;
  schema?: SchemaColumn[];
}

export interface DatasetPreview {
  columns: string[];
  rows: (string | number | boolean | null)[][];
  total_rows: number;
  offset: number;
  limit: number;
}

export interface ConnectionTestResult {
  status: string;
  latency_ms: number | null;
  tables_found: number | null;
  error: string | null;
}

export interface DatasetUploadResponse {
  id: string;
  name: string;
  file_format: string;
  file_size_bytes: number;
  status: string;
  created_at: string;
}

export interface ConnectionCreateRequest {
  name: string;
  db_type: string;
  host: string;
  port: number;
  database_name: string;
  username: string;
  password: string;
}

export interface ConnectionUpdateRequest {
  name?: string;
  db_type?: string;
  host?: string;
  port?: number;
  database_name?: string;
  username?: string;
  password?: string;
}

export interface ConnectionTestParamsRequest {
  db_type: string;
  host: string;
  port: number;
  database_name: string;
  username: string;
  password: string;
}

export interface ProviderConfig {
  id: string;
  provider_name: string;
  model_name: string;
  base_url: string | null;
  is_default: boolean;
  is_active: boolean;
  has_api_key: boolean;
  source: "ui" | "env_var";
  created_at: string;
}

export interface ProviderCreateRequest {
  provider_name: string;
  model_name: string;
  api_key: string;
  base_url?: string | null;
  is_default?: boolean;
}

export interface ExecuteQueryRequest {
  sql: string;
  source_id: string;
  source_type: "dataset" | "connection";
}

export interface ExecuteQueryResponse {
  columns: string[];
  rows: unknown[][];
  row_count: number;
  execution_time_ms: number;
}

export interface ExplainRequest {
  sql: string;
  source_id: string;
  source_type: "dataset" | "connection";
}

export interface ExplainResponse {
  plan: string;
}

export interface SaveQueryRequest {
  name: string;
  sql_content: string;
  source_id?: string | null;
  source_type?: string | null;
}

export interface SavedQuery {
  id: string;
  name: string;
  sql_content: string;
  source_id: string | null;
  source_type: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface SavedQueryListResponse {
  queries: SavedQuery[];
}

export interface HistoryEntry {
  sql: string;
  source_id: string | null;
  source_type: string | null;
  row_count: number;
  execution_time_ms: number;
  status: string;
  executed_at: string;
}

export interface HistoryResponse {
  history: HistoryEntry[];
  total: number;
  offset: number;
  limit: number;
}

export interface SchemaColumnEntry {
  name: string;
  type: string;
  nullable: boolean;
  is_primary_key: boolean;
  foreign_key_ref?: string | null;
}

export interface SchemaTable {
  table_name: string;
  columns: SchemaColumnEntry[];
}

export interface SchemaSource {
  source_id: string;
  source_type: "dataset" | "connection";
  source_name: string;
  tables: SchemaTable[];
}

export interface SchemaResponse {
  sources: SchemaSource[];
}

export interface Bookmark {
  id: string;
  message_id: string;
  title: string;
  sql: string | null;
  chart_config: Record<string, unknown> | null;
  result_snapshot: Record<string, unknown> | null;
  source_id: string | null;
  source_type: string | null;
  created_at: string;
}

export interface BookmarkListResponse {
  bookmarks: Bookmark[];
}

export interface CreateBookmarkRequest {
  message_id: string;
  title: string;
}

export interface DashboardItem {
  id: string;
  dashboard_id: string;
  bookmark_id: string;
  position: number;
  bookmark: Bookmark | null;
  created_at: string;
}

export interface Dashboard {
  id: string;
  title: string;
  items: DashboardItem[];
  created_at: string;
  updated_at: string;
}

export interface DashboardListResponse {
  dashboards: Dashboard[];
}

export interface CreateDashboardRequest {
  title: string;
}

export interface UpdateDashboardRequest {
  title: string;
}

export interface AddDashboardItemRequest {
  bookmark_id: string;
  position: number;
}

/** Per-column statistics from DuckDB SUMMARIZE. */
export interface ColumnSummary {
  column_name: string;
  column_type: string;
  min: string | null;
  max: string | null;
  avg: string | null;
  std: string | null;
  approx_unique: number | null;
  null_percentage: string | null;
  q25: string | null;
  q50: string | null;
  q75: string | null;
  count: string | null;
}

/** Stored data profiling results for a dataset. */
export interface DatasetProfile {
  dataset_id: string;
  summarize_results: ColumnSummary[];
  sample_values: Record<string, unknown[]>;
  profiled_at: string | null;
}
