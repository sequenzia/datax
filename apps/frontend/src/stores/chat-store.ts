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

interface ChatState {
  /** Current conversation ID (null = no conversation selected) */
  conversationId: string | null;
  /** Messages in the current conversation */
  messages: Message[];
  /** Current streaming status */
  status: ChatStatus;
  /** Error message if any */
  error: string | null;
  /** Accumulated streaming text for the current assistant response */
  streamingContent: string;
  /** AbortController for the current SSE stream */
  abortController: AbortController | null;
  /** Whether the persisted conversation has been restored */
  _restored: boolean;

  /** Start a new conversation */
  newConversation: () => Promise<string | null>;
  /** Switch to an existing conversation (loads messages) */
  switchConversation: (conversationId: string) => Promise<void>;
  /** Send a user message and stream the AI response */
  sendMessage: (content: string) => Promise<void>;
  /** Cancel the current streaming response */
  cancelStream: () => void;
  /** Clear the error state */
  clearError: () => void;
  /** Reset to initial state */
  reset: () => void;
  /** Restore persisted conversation on app load */
  restoreSession: () => Promise<void>;
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversationId: null,
  messages: [],
  status: "idle",
  error: null,
  streamingContent: "",
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
    // Cancel any existing stream
    get().cancelStream();

    set({
      conversationId,
      messages: [],
      status: "loading",
      error: null,
      streamingContent: "",
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

    // Auto-create conversation if none selected
    let convId = state.conversationId;
    const isFirstMessage = !convId || state.messages.length === 0;
    if (!convId) {
      const newId = await get().newConversation();
      if (!newId) return;
      convId = newId;
    }

    // Add user message optimistically
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
    }));

    // Auto-update title from first user message
    if (isFirstMessage) {
      const title =
        content.length > 100 ? content.slice(0, 100) + "..." : content;
      void updateConversationTitle(convId, title).catch(() => {
        // Title update is best-effort; don't block the message flow
      });
    }

    const callbacks: SSECallbacks = {
      onToken: (token: string) => {
        set((s) => ({
          streamingContent: s.streamingContent + token,
        }));
      },
      onMessageStart: () => {
        set({ streamingContent: "" });
      },
      onMessageEnd: (data: Record<string, unknown>) => {
        const assistantMessage: Message = {
          id: (data.message_id as string) ?? `msg-${Date.now()}`,
          role: "assistant",
          content: get().streamingContent,
          metadata: data.metadata as Record<string, unknown> | null ?? null,
          created_at: new Date().toISOString(),
        };

        set((s) => ({
          messages: [...s.messages, assistantMessage],
          status: "idle",
          streamingContent: "",
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
    const { abortController, streamingContent } = get();
    if (abortController) {
      abortController.abort();

      // If there was partial content, keep it as a message
      if (streamingContent) {
        const partialMessage: Message = {
          id: `partial-${Date.now()}`,
          role: "assistant",
          content: streamingContent,
          metadata: null,
          created_at: new Date().toISOString(),
        };
        set((s) => ({
          messages: [...s.messages, partialMessage],
        }));
      }

      set({
        status: "idle",
        streamingContent: "",
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
