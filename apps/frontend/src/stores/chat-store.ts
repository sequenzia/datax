import { create } from "zustand";
import type { Message, ConversationDetail } from "@/types/api";
import {
  createConversation,
  fetchConversationDetail,
  updateConversationTitle,
} from "@/lib/api";

export type ChatStatus = "idle" | "loading" | "error";

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
  conversationId: string | null;
  messages: Message[];
  status: ChatStatus;
  error: string | null;
  _restored: boolean;
  pendingMessage: string | null;

  newConversation: () => Promise<string | null>;
  switchConversation: (conversationId: string) => Promise<void>;
  setTitle: (conversationId: string, title: string) => void;
  clearError: () => void;
  reset: () => void;
  restoreSession: () => Promise<void>;
  setPendingMessage: (message: string | null) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversationId: null,
  messages: [],
  status: "idle",
  error: null,
  _restored: false,
  pendingMessage: null,

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
    set({
      conversationId,
      messages: [],
      status: "loading",
      error: null,
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

  setTitle: (conversationId: string, title: string) => {
    void updateConversationTitle(conversationId, title).catch(() => {});
  },

  clearError: () => set({ error: null, status: "idle" }),

  reset: () => {
    persistConversationId(null);
    set({
      conversationId: null,
      messages: [],
      status: "idle",
      error: null,
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

  setPendingMessage: (message: string | null) => set({ pendingMessage: message }),
}));
