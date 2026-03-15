import { useEffect, useRef, useCallback, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { MessageSquare, AlertCircle, Loader2 } from "lucide-react";
import { useCopilotChatInternal } from "@copilotkit/react-core";
import { Button } from "@/components/ui/button";
import { ChatInput } from "@/components/chat/chat-input";
import { MessageBubble } from "@/components/chat/message-bubble";
import { useChatStore } from "@/stores/chat-store";
import { saveMessage } from "@/lib/api";
import { useAiStatus } from "@/hooks/use-ai-status";
import { useDatasetList } from "@/hooks/use-datasets";
import { useConnectionList } from "@/hooks/use-connections";

export function ChatPage() {
  const { conversationId: urlConversationId } = useParams<{
    conversationId: string;
  }>();
  const navigate = useNavigate();
  const {
    conversationId,
    messages,
    status,
    error,
    clearError,
    switchConversation,
    restoreSession,
    pendingMessage,
    selectedSources,
    toggleSource,
    clearSelectedSources,
  } = useChatStore();

  const { data: datasets = [] } = useDatasetList();
  const { data: connections = [] } = useConnectionList();

  const {
    messages: copilotMessages,
    sendMessage,
    isLoading: copilotIsLoading,
    stopGeneration,
    reset: resetCopilot,
  } = useCopilotChatInternal();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const isUserNearBottom = useRef(true);

  const isLoading = status === "loading" || copilotIsLoading;

  // Use CopilotKit messages (with generativeUI) when available, fall back to Zustand messages (history)
  const displayMessages = useMemo(() => {
    const filtered = copilotMessages.filter(
      (m) => m.role === "user" || m.role === "assistant",
    );
    return filtered.length > 0 ? filtered : messages;
  }, [copilotMessages, messages]);

  // Restore persisted conversation on first mount
  useEffect(() => {
    void restoreSession();
  }, [restoreSession]);

  // When URL has a conversationId, load it into the chat store
  useEffect(() => {
    if (urlConversationId && urlConversationId !== conversationId) {
      void switchConversation(urlConversationId);
    }
  }, [urlConversationId, conversationId, switchConversation]);

  // Reset CopilotKit state when conversation changes (new chat or switching conversations)
  const prevConversationIdRef = useRef(conversationId);
  useEffect(() => {
    if (prevConversationIdRef.current !== conversationId) {
      if (prevConversationIdRef.current != null) {
        resetCopilot();
      }
      prevConversationIdRef.current = conversationId;
    }
  }, [conversationId, resetCopilot]);

  // Persist assistant message when response completes (loading: true → false)
  const prevLoadingRef = useRef(false);
  useEffect(() => {
    if (prevLoadingRef.current && !copilotIsLoading) {
      const currentConvId = useChatStore.getState().conversationId;
      if (currentConvId) {
        const assistantMsgs = copilotMessages.filter(
          (m) => m.role === "assistant" && typeof m.content === "string" && m.content.length > 0,
        );
        const lastAssistant = assistantMsgs[assistantMsgs.length - 1];
        if (lastAssistant) {
          saveMessage(currentConvId, {
            role: "assistant",
            content: lastAssistant.content as string,
          }).catch(() => {});
        }
      }
    }
    prevLoadingRef.current = copilotIsLoading;
  }, [copilotIsLoading, copilotMessages]);

  // Auto-scroll to bottom when new messages appear
  const scrollToBottom = useCallback(() => {
    if (isUserNearBottom.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [displayMessages.length, scrollToBottom]);

  const handleScroll = useCallback(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const { scrollTop, scrollHeight, clientHeight } = container;
    isUserNearBottom.current = scrollHeight - scrollTop - clientHeight < 100;
  }, []);

  const handleSend = useCallback(async (text: string) => {
    useChatStore.getState().setPendingMessage(null);

    let activeConversationId = conversationId;
    if (!activeConversationId) {
      const newId = await useChatStore.getState().newConversation();
      if (newId) {
        activeConversationId = newId;
        navigate(`/chat/${newId}`, { replace: true });
      } else {
        return;
      }
    }

    // Persist user message (fire-and-forget)
    saveMessage(activeConversationId, { role: "user", content: text }).catch(() => {});

    await sendMessage({
      id: crypto.randomUUID(),
      role: "user" as const,
      content: text,
    });
  }, [conversationId, navigate, sendMessage]);

  const { chatDisabled: aiUnavailable, chatDisabledMessage } = useAiStatus();

  return (
    <div
      className="flex h-full flex-col"
      data-testid="chat-page"
    >
      {/* Messages area */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto"
        data-testid="message-list"
      >
        {/* Empty state */}
        {displayMessages.length === 0 && !isLoading && (
          <div className="flex h-full flex-col items-center justify-center gap-4 p-6">
            <div className="rounded-full bg-muted p-4">
              <MessageSquare className="size-8 text-muted-foreground" />
            </div>
            <div className="text-center">
              <h2 className="text-lg font-semibold tracking-tight">
                Ask a question about your data
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                I&apos;ll generate SQL, run queries, and create visualizations.
              </p>
            </div>
          </div>
        )}

        {/* Loading state */}
        {isLoading && (
          <div className="flex h-full items-center justify-center" data-testid="chat-loading">
            <Loader2 className="size-6 animate-spin text-muted-foreground" />
          </div>
        )}

        {/* Messages */}
        <div className="mx-auto max-w-3xl space-y-4 p-4">
          {displayMessages.map((message) => {
            const content =
              typeof message.content === "string"
                ? message.content
                : "";
            const role = message.role as "user" | "assistant";
            const metadata = "metadata" in message
              ? (message.metadata as Record<string, unknown> | null)
              : null;
            const generativeUI =
              "generativeUI" in message &&
              typeof message.generativeUI === "function"
                ? message.generativeUI
                : null;

            return (
              <MessageBubble
                key={message.id}
                role={role}
                content={content}
                metadata={metadata}
              >
                {generativeUI ? generativeUI() : undefined}
              </MessageBubble>
            );
          })}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-center gap-2 border-t border-destructive/30 bg-destructive/10 px-4 py-2">
          <AlertCircle className="size-4 shrink-0 text-destructive" />
          <p className="flex-1 text-xs text-destructive">{error}</p>
          <Button
            variant="ghost"
            size="xs"
            onClick={clearError}
            className="text-destructive hover:text-destructive"
          >
            Dismiss
          </Button>
        </div>
      )}

      {/* Input area */}
      <div className="mx-auto w-full max-w-3xl">
        <ChatInput
          onSend={handleSend}
          disabled={isLoading || aiUnavailable}
          disabledMessage={chatDisabledMessage}
          initialValue={pendingMessage}
          datasets={datasets}
          connections={connections}
          selectedSources={selectedSources}
          onToggleSource={toggleSource}
          onClearSources={clearSelectedSources}
        />
      </div>
    </div>
  );
}
