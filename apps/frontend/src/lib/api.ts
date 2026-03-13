/** API client for backend communication. */

import type {
  Dataset,
  DatasetDetail,
  DatasetPreview,
  DatasetUploadResponse,
  Connection,
  ConnectionDetail,
  ConnectionTestResult,
  ConnectionCreateRequest,
  ConnectionUpdateRequest,
  ConnectionTestParamsRequest,
  Conversation,
  ConversationListResponse,
  ConversationDetail,
  ProviderConfig,
  ProviderCreateRequest,
  ExecuteQueryRequest,
  ExecuteQueryResponse,
  ExplainRequest,
  ExplainResponse,
  SaveQueryRequest,
  SavedQuery,
  SavedQueryListResponse,
  HistoryResponse,
  SchemaResponse,
} from "@/types/api";

const API_BASE = "/api/v1";

async function apiFetch<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

async function apiMutate<T>(
  path: string,
  options: { method: string; body?: unknown },
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: options.method,
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(text || `API error: ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function fetchDatasets(): Promise<Dataset[]> {
  const data = await apiFetch<{ datasets: Dataset[] }>("/datasets");
  return data.datasets;
}

export function fetchDataset(id: string): Promise<DatasetDetail> {
  return apiFetch<DatasetDetail>(`/datasets/${id}`);
}

export function fetchDatasetPreview(
  id: string,
  params: { offset?: number; limit?: number; sort_by?: string; sort_order?: string } = {},
): Promise<DatasetPreview> {
  const search = new URLSearchParams();
  if (params.offset !== undefined) search.set("offset", String(params.offset));
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.sort_by) search.set("sort_by", params.sort_by);
  if (params.sort_order) search.set("sort_order", params.sort_order);
  const qs = search.toString();
  return apiFetch<DatasetPreview>(`/datasets/${id}/preview${qs ? `?${qs}` : ""}`);
}

export function deleteDataset(id: string): Promise<void> {
  return apiMutate<void>(`/datasets/${id}`, { method: "DELETE" });
}

export async function uploadDataset(
  file: File,
  name?: string,
): Promise<DatasetUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (name) formData.append("name", name);

  const response = await fetch(`${API_BASE}/datasets/upload`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(text || `API error: ${response.status}`);
  }
  return response.json() as Promise<DatasetUploadResponse>;
}

export async function fetchConnections(): Promise<Connection[]> {
  const data = await apiFetch<{ connections: Connection[] }>("/connections");
  return data.connections;
}

export function fetchConnection(id: string): Promise<ConnectionDetail> {
  return apiFetch<ConnectionDetail>(`/connections/${id}`);
}

export function fetchConnectionSchema(
  connectionId: string,
): Promise<ConnectionDetail> {
  return apiFetch<ConnectionDetail>(`/connections/${connectionId}`);
}

export function fetchConversations(): Promise<Conversation[]> {
  return apiFetch<Conversation[]>("/conversations");
}

export function fetchConversationsPaginated(params: {
  cursor?: string | null;
  limit?: number;
  search?: string;
}): Promise<ConversationListResponse> {
  const searchParams = new URLSearchParams();
  if (params.cursor) searchParams.set("cursor", params.cursor);
  if (params.limit !== undefined) searchParams.set("limit", String(params.limit));
  if (params.search) searchParams.set("search", params.search);
  const qs = searchParams.toString();
  return apiFetch<ConversationListResponse>(
    `/conversations${qs ? `?${qs}` : ""}`,
  );
}

export function deleteConversation(id: string): Promise<void> {
  return apiMutate<void>(`/conversations/${id}`, { method: "DELETE" });
}

export function updateConversationTitle(
  id: string,
  title: string,
): Promise<Conversation> {
  return apiMutate<Conversation>(`/conversations/${id}`, {
    method: "PATCH",
    body: { title },
  });
}

export function testConnection(connectionId: string): Promise<ConnectionTestResult> {
  return apiMutate<ConnectionTestResult>(`/connections/${connectionId}/test`, {
    method: "POST",
  });
}

export function refreshConnectionSchema(
  connectionId: string,
): Promise<Connection> {
  return apiMutate<Connection>(`/connections/${connectionId}/refresh-schema`, {
    method: "POST",
  });
}

export function createConnection(
  body: ConnectionCreateRequest,
): Promise<Connection> {
  return apiMutate<Connection>("/connections", {
    method: "POST",
    body,
  });
}

export function updateConnection(
  connectionId: string,
  body: ConnectionUpdateRequest,
): Promise<Connection> {
  return apiMutate<Connection>(`/connections/${connectionId}`, {
    method: "PUT",
    body,
  });
}

export function testConnectionParams(
  body: ConnectionTestParamsRequest,
): Promise<ConnectionTestResult> {
  return apiMutate<ConnectionTestResult>("/connections/test-params", {
    method: "POST",
    body,
  });
}

export function deleteConnection(connectionId: string): Promise<void> {
  return apiMutate<void>(`/connections/${connectionId}`, {
    method: "DELETE",
  });
}

export async function fetchProviders(): Promise<ProviderConfig[]> {
  const data = await apiFetch<{ providers: ProviderConfig[] }>(
    "/settings/providers",
  );
  return data.providers;
}

export function createProviderConfig(
  body: ProviderCreateRequest,
): Promise<ProviderConfig> {
  return apiMutate<ProviderConfig>("/settings/providers", {
    method: "POST",
    body,
  });
}

export function deleteProvider(id: string): Promise<void> {
  return apiMutate<void>(`/settings/providers/${id}`, {
    method: "DELETE",
  });
}

export function executeQuery(
  body: ExecuteQueryRequest,
  signal?: AbortSignal,
): Promise<ExecuteQueryResponse> {
  return fetch(`${API_BASE}/queries/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  }).then(async (response) => {
    if (!response.ok) {
      const text = await response.text().catch(() => response.statusText);
      throw new Error(text || `API error: ${response.status}`);
    }
    return response.json() as Promise<ExecuteQueryResponse>;
  });
}

export function explainQuery(
  body: ExplainRequest,
): Promise<ExplainResponse> {
  return apiMutate<ExplainResponse>("/queries/explain", {
    method: "POST",
    body,
  });
}

export function saveQuery(
  body: SaveQueryRequest,
): Promise<SavedQuery> {
  return apiMutate<SavedQuery>("/queries/save", {
    method: "POST",
    body,
  });
}

export function updateSavedQuery(
  id: string,
  body: SaveQueryRequest,
): Promise<SavedQuery> {
  return apiMutate<SavedQuery>(`/queries/saved/${id}`, {
    method: "PUT",
    body,
  });
}

export function deleteSavedQuery(id: string): Promise<void> {
  return apiMutate<void>(`/queries/saved/${id}`, {
    method: "DELETE",
  });
}

export function fetchSavedQueries(): Promise<SavedQuery[]> {
  return apiFetch<SavedQueryListResponse>("/queries/saved").then(
    (data) => data.queries,
  );
}

export function fetchSchema(): Promise<SchemaResponse> {
  return apiFetch<SchemaResponse>("/schema");
}

export function fetchQueryHistory(params?: {
  limit?: number;
  offset?: number;
}): Promise<HistoryResponse> {
  const search = new URLSearchParams();
  if (params?.limit !== undefined) search.set("limit", String(params.limit));
  if (params?.offset !== undefined) search.set("offset", String(params.offset));
  const qs = search.toString();
  return apiFetch<HistoryResponse>(`/queries/history${qs ? `?${qs}` : ""}`);
}

export function createConversation(): Promise<Conversation> {
  return apiMutate<Conversation>("/conversations", { method: "POST" });
}

export function fetchConversationDetail(
  id: string,
): Promise<ConversationDetail> {
  return apiFetch<ConversationDetail>(`/conversations/${id}`);
}

/** SSE event types emitted by the chat streaming endpoint. */
export type SSEEventType =
  | "message_start"
  | "token"
  | "sql_generated"
  | "query_result"
  | "chart_config"
  | "message_end"
  | "error";

export interface SSECallbacks {
  onToken?: (token: string) => void;
  onMessageStart?: (data: Record<string, unknown>) => void;
  onMessageEnd?: (data: Record<string, unknown>) => void;
  onSqlGenerated?: (sql: string) => void;
  onQueryResult?: (data: Record<string, unknown>) => void;
  onChartConfig?: (config: Record<string, unknown>) => void;
  onError?: (error: string) => void;
}

/**
 * Send a message to a conversation and stream the AI response via SSE.
 * Returns an AbortController for cancellation.
 */
export function sendMessageSSE(
  conversationId: string,
  content: string,
  callbacks: SSECallbacks,
): AbortController {
  const controller = new AbortController();

  const doStream = async () => {
    try {
      const response = await fetch(
        `${API_BASE}/conversations/${conversationId}/messages`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
          },
          body: JSON.stringify({ content }),
          signal: controller.signal,
        },
      );

      if (!response.ok) {
        const text = await response.text().catch(() => response.statusText);
        callbacks.onError?.(text || `API error: ${response.status}`);
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        callbacks.onError?.("No response body");
        return;
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        let eventType = "";
        let eventData = "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            eventData = line.slice(6);
          } else if (line === "" && eventType && eventData) {
            try {
              const parsed = JSON.parse(eventData) as Record<string, unknown>;
              switch (eventType as SSEEventType) {
                case "token":
                  callbacks.onToken?.(parsed.token as string);
                  break;
                case "message_start":
                  callbacks.onMessageStart?.(parsed);
                  break;
                case "message_end":
                  callbacks.onMessageEnd?.(parsed);
                  break;
                case "sql_generated":
                  callbacks.onSqlGenerated?.(parsed.sql as string);
                  break;
                case "query_result":
                  callbacks.onQueryResult?.(parsed);
                  break;
                case "chart_config":
                  callbacks.onChartConfig?.(parsed);
                  break;
                case "error":
                  callbacks.onError?.(parsed.message as string);
                  break;
              }
            } catch {
              // Skip malformed JSON lines
            }
            eventType = "";
            eventData = "";
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") {
        return;
      }
      callbacks.onError?.(
        err instanceof Error ? err.message : "Stream connection failed",
      );
    }
  };

  void doStream();
  return controller;
}
