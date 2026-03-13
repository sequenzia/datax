import { useEffect, useRef, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { MessageSquare, AlertCircle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChatInput } from "@/components/chat/chat-input";
import { MessageBubble } from "@/components/chat/message-bubble";
import { StreamingText } from "@/components/chat/streaming-text";
import { useChatStore } from "@/stores/chat-store";

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
    streamingContent,
    streamingMetadata,
    sendMessage,
    cancelStream,
    clearError,
    switchConversation,
    restoreSession,
  } = useChatStore();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const isUserNearBottom = useRef(true);

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

  // Auto-scroll to bottom when new messages appear or during streaming
  const scrollToBottom = useCallback(() => {
    if (isUserNearBottom.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages.length, streamingContent, scrollToBottom]);

  const handleScroll = useCallback(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const { scrollTop, scrollHeight, clientHeight } = container;
    isUserNearBottom.current = scrollHeight - scrollTop - clientHeight < 100;
  }, []);

  const handleSend = useCallback(
    async (content: string) => {
      // Auto-create conversation if needed, then navigate to it
      if (!conversationId) {
        const newId = await useChatStore.getState().newConversation();
        if (newId) {
          navigate(`/chat/${newId}`, { replace: true });
          // Wait for state update, then send
          setTimeout(() => {
            void useChatStore.getState().sendMessage(content);
          }, 0);
        }
        return;
      }
      void sendMessage(content);
    },
    [conversationId, sendMessage, navigate],
  );

  const isStreaming = status === "streaming";
  const isLoading = status === "loading";

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
        {messages.length === 0 && !isStreaming && !isLoading && (
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
          {messages.map((message) => (
            <MessageBubble
              key={message.id}
              role={message.role}
              content={message.content}
              metadata={message.metadata}
            />
          ))}

          {/* Streaming assistant response */}
          {isStreaming && (
            <MessageBubble
              role="assistant"
              content=""
              isStreaming
              streamingMetadata={streamingMetadata}
            >
              <StreamingText content={streamingContent} isStreaming />
            </MessageBubble>
          )}

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
          onCancel={cancelStream}
          isStreaming={isStreaming}
          disabled={isLoading}
        />
      </div>
    </div>
  );
}
