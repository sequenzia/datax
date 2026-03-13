import { create } from "zustand";
import type { Message, ConversationDetail } from "@/types/api";
import {
  createConversation,
  fetchConversationDetail,
  sendMessageSSE,
  updateConversationTitle,
  type SSECallbacks,
} from "@/lib/api";

export type ChatStatus = "idle" | "loading" | "streaming" | "error";

const STORAGE_KEY = "datax-active-conversation";

function persistConversationId(id: string | null): void {
  if (id) {
    localStorage.setItem(STORAGE_KEY, id);
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
}

function loadPersistedConversationId(): string | null {
  return localStorage.getItem(STORAGE_KEY);
}

/** Metadata accumulated during streaming from SSE events */
export interface StreamingMetadata {
  sql: string | null;
  queryResult: Record<string, unknown> | null;
  chartConfig: Record<string, unknown> | null;
}

interface ChatState {
  conversationId: string | null;
  messages: Message[];
  status: ChatStatus;
  error: string | null;
  streamingContent: string;
  /** Metadata accumulated from SSE events during streaming */
  streamingMetadata: StreamingMetadata;
  abortController: AbortController | null;
  _restored: boolean;

  newConversation: () => Promise<string | null>;
  switchConversation: (conversationId: string) => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  cancelStream: () => void;
  clearError: () => void;
  reset: () => void;
  restoreSession: () => Promise<void>;
}

const EMPTY_STREAMING_METADATA: StreamingMetadata = {
  sql: null,
  queryResult: null,
  chartConfig: null,
};

export const useChatStore = create<ChatState>((set, get) => ({
  conversationId: null,
  messages: [],
  status: "idle",
  error: null,
  streamingContent: "",
  streamingMetadata: { ...EMPTY_STREAMING_METADATA },
  abortController: null,
  _restored: false,

  newConversation: async () => {
    set({ status: "loading", error: null });
    try {
      const conversation = await createConversation();
      persistConversationId(conversation.id);
      set({
        conversationId: conversation.id,
        messages: [],
        status: "idle",
        error: null,
        streamingContent: "",
        streamingMetadata: { ...EMPTY_STREAMING_METADATA },
      });
      return conversation.id;
    } catch (err: unknown) {
      set({
        status: "error",
        error:
          err instanceof Error ? err.message : "Failed to create conversation",
      });
      return null;
    }
  },

  switchConversation: async (conversationId: string) => {
    get().cancelStream();

    set({
      conversationId,
      messages: [],
      status: "loading",
      error: null,
      streamingContent: "",
      streamingMetadata: { ...EMPTY_STREAMING_METADATA },
    });

    try {
      const detail: ConversationDetail =
        await fetchConversationDetail(conversationId);
      persistConversationId(conversationId);
      set({
        messages: detail.messages,
        status: "idle",
      });
    } catch (err: unknown) {
      persistConversationId(null);
      set({
        conversationId: null,
        status: "error",
        error:
          err instanceof Error
            ? err.message
            : "Failed to load conversation",
      });
    }
  },

  sendMessage: async (content: string) => {
    const state = get();

    let convId = state.conversationId;
    const isFirstMessage = !convId || state.messages.length === 0;
    if (!convId) {
      const newId = await get().newConversation();
      if (!newId) return;
      convId = newId;
    }

    const userMessage: Message = {
      id: `temp-user-${Date.now()}`,
      role: "user",
      content,
      metadata: null,
      created_at: new Date().toISOString(),
    };

    set((s) => ({
      messages: [...s.messages, userMessage],
      status: "streaming",
      error: null,
      streamingContent: "",
      streamingMetadata: { ...EMPTY_STREAMING_METADATA },
    }));

    if (isFirstMessage) {
      const title =
        content.length > 100 ? content.slice(0, 100) + "..." : content;
      void updateConversationTitle(convId, title).catch(() => {});
    }

    const callbacks: SSECallbacks = {
      onToken: (token: string) => {
        set((s) => ({
          streamingContent: s.streamingContent + token,
        }));
      },
      onMessageStart: () => {
        set({
          streamingContent: "",
          streamingMetadata: { ...EMPTY_STREAMING_METADATA },
        });
      },
      onSqlGenerated: (sql: string) => {
        set((s) => ({
          streamingMetadata: { ...s.streamingMetadata, sql },
        }));
      },
      onQueryResult: (data: Record<string, unknown>) => {
        set((s) => ({
          streamingMetadata: { ...s.streamingMetadata, queryResult: data },
        }));
      },
      onChartConfig: (config: Record<string, unknown>) => {
        set((s) => ({
          streamingMetadata: { ...s.streamingMetadata, chartConfig: config },
        }));
      },
      onMessageEnd: (data: Record<string, unknown>) => {
        const currentState = get();

        // Merge streaming metadata into the message metadata
        const sseMetadata = currentState.streamingMetadata;
        const backendMetadata =
          (data.metadata as Record<string, unknown> | null) ?? {};

        const mergedMetadata: Record<string, unknown> = {
          ...backendMetadata,
        };
        if (sseMetadata.sql) mergedMetadata.sql = sseMetadata.sql;
        if (sseMetadata.queryResult)
          mergedMetadata.query_result = sseMetadata.queryResult;
        if (sseMetadata.chartConfig)
          mergedMetadata.chart_config = sseMetadata.chartConfig;

        const assistantMessage: Message = {
          id: (data.message_id as string) ?? `msg-${Date.now()}`,
          role: "assistant",
          content: currentState.streamingContent,
          metadata:
            Object.keys(mergedMetadata).length > 0 ? mergedMetadata : null,
          created_at: new Date().toISOString(),
        };

        set((s) => ({
          messages: [...s.messages, assistantMessage],
          status: "idle",
          streamingContent: "",
          streamingMetadata: { ...EMPTY_STREAMING_METADATA },
          abortController: null,
        }));
      },
      onError: (error: string) => {
        set({
          status: "error",
          error,
          abortController: null,
        });
      },
    };

    const controller = sendMessageSSE(convId, content, callbacks);
    set({ abortController: controller });
  },

  cancelStream: () => {
    const { abortController, streamingContent, streamingMetadata } = get();
    if (abortController) {
      abortController.abort();

      if (streamingContent) {
        // Merge any partial metadata
        const metadata: Record<string, unknown> = {};
        if (streamingMetadata.sql) metadata.sql = streamingMetadata.sql;
        if (streamingMetadata.queryResult)
          metadata.query_result = streamingMetadata.queryResult;
        if (streamingMetadata.chartConfig)
          metadata.chart_config = streamingMetadata.chartConfig;

        const partialMessage: Message = {
          id: `partial-${Date.now()}`,
          role: "assistant",
          content: streamingContent,
          metadata: Object.keys(metadata).length > 0 ? metadata : null,
          created_at: new Date().toISOString(),
        };
        set((s) => ({
          messages: [...s.messages, partialMessage],
        }));
      }

      set({
        status: "idle",
        streamingContent: "",
        streamingMetadata: { ...EMPTY_STREAMING_METADATA },
        abortController: null,
      });
    }
  },

  clearError: () => set({ error: null, status: "idle" }),

  reset: () => {
    get().cancelStream();
    persistConversationId(null);
    set({
      conversationId: null,
      messages: [],
      status: "idle",
      error: null,
      streamingContent: "",
      streamingMetadata: { ...EMPTY_STREAMING_METADATA },
      abortController: null,
    });
  },

  restoreSession: async () => {
    if (get()._restored) return;
    set({ _restored: true });

    const savedId = loadPersistedConversationId();
    if (savedId && !get().conversationId) {
      await get().switchConversation(savedId);
    }
  },
}));
