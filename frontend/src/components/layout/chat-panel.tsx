import { useEffect, useRef, useCallback, useState } from "react";
import {
  MessageSquare,
  Plus,
  ChevronDown,
  AlertCircle,
  Loader2,
  PanelLeftClose,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/stores/ui-store";
import { useChatStore } from "@/stores/chat-store";
import { useConversationList } from "@/hooks/use-conversations";
import { Button } from "@/components/ui/button";
import { ChatInput } from "@/components/chat/chat-input";
import { MessageBubble } from "@/components/chat/message-bubble";
import { StreamingText } from "@/components/chat/streaming-text";
import type { Conversation } from "@/types/api";

interface ChatPanelProps {
  fullWidth?: boolean;
}

function ConversationSelector({
  currentId,
  onSelect,
  onNew,
}: {
  currentId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const { data } = useConversationList("");

  const conversations: Conversation[] =
    data?.pages.flatMap((p) => p.conversations) ?? [];
  const current = conversations.find((c) => c.id === currentId);

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen]);

  return (
    <div ref={dropdownRef} className="relative flex-1 min-w-0">
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-sm font-semibold hover:bg-accent/50 transition-colors truncate"
        data-testid="conversation-selector-trigger"
        aria-label="Select conversation"
      >
        <span className="truncate">
          {current?.title ?? "New Conversation"}
        </span>
        <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
      </button>

      {isOpen && (
        <div
          className="absolute left-0 top-full z-50 mt-1 w-64 rounded-md border bg-popover shadow-md"
          data-testid="conversation-selector-dropdown"
        >
          <div className="p-1">
            <button
              type="button"
              onClick={() => {
                onNew();
                setIsOpen(false);
              }}
              className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-accent transition-colors"
              data-testid="new-conversation-button"
            >
              <Plus className="size-4" />
              New Conversation
            </button>
          </div>

          {conversations.length > 0 && (
            <>
              <div className="border-t" />
              <div className="max-h-48 overflow-y-auto p-1">
                {conversations.map((conv) => (
                  <button
                    key={conv.id}
                    type="button"
                    onClick={() => {
                      onSelect(conv.id);
                      setIsOpen(false);
                    }}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm transition-colors truncate",
                      conv.id === currentId
                        ? "bg-accent text-accent-foreground"
                        : "hover:bg-accent/50",
                    )}
                    data-testid="conversation-option"
                  >
                    <MessageSquare className="size-3.5 shrink-0 text-muted-foreground" />
                    <span className="truncate">{conv.title}</span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

export function ChatPanel({ fullWidth = false }: ChatPanelProps) {
  const { chatPanelOpen, chatPanelWidth, toggleChatPanel } = useUIStore();
  const {
    conversationId,
    messages,
    status,
    error,
    streamingContent,
    sendMessage,
    cancelStream,
    clearError,
    switchConversation,
    reset,
    restoreSession,
  } = useChatStore();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const isUserNearBottom = useRef(true);

  // Restore persisted conversation on first mount
  useEffect(() => {
    void restoreSession();
  }, [restoreSession]);

  // Auto-scroll to bottom when new messages appear or during streaming
  const scrollToBottom = useCallback(() => {
    if (isUserNearBottom.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages.length, streamingContent, scrollToBottom]);

  // Track if user is near bottom of scroll container
  const handleScroll = useCallback(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const { scrollTop, scrollHeight, clientHeight } = container;
    isUserNearBottom.current = scrollHeight - scrollTop - clientHeight < 100;
  }, []);

  const handleSend = useCallback(
    (content: string) => {
      void sendMessage(content);
    },
    [sendMessage],
  );

  const handleNewConversation = useCallback(() => {
    reset();
  }, [reset]);

  const handleSwitchConversation = useCallback(
    (id: string) => {
      void switchConversation(id);
    },
    [switchConversation],
  );

  if (!chatPanelOpen && !fullWidth) return null;

  const isStreaming = status === "streaming";
  const isLoading = status === "loading";

  return (
    <div
      data-testid="chat-panel"
      className={cn(
        "flex flex-col border-border bg-background",
        fullWidth ? "h-full w-full flex-1" : "h-full border-r",
      )}
      style={fullWidth ? undefined : { width: chatPanelWidth }}
    >
      {/* Chat header */}
      <div className="flex h-14 shrink-0 items-center gap-2 border-b border-border px-3">
        <MessageSquare className="size-4 shrink-0 text-muted-foreground" />
        <ConversationSelector
          currentId={conversationId}
          onSelect={handleSwitchConversation}
          onNew={handleNewConversation}
        />
        {!fullWidth && (
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={toggleChatPanel}
            aria-label="Collapse chat panel"
            data-testid="collapse-chat-button"
          >
            <PanelLeftClose className="size-4" />
          </Button>
        )}
      </div>

      {/* Messages area */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto"
        data-testid="message-list"
      >
        {messages.length === 0 && !isStreaming && !isLoading && (
          <div className="flex h-full flex-col items-center justify-center gap-3 p-6">
            <MessageSquare className="size-10 text-muted-foreground" />
            <p className="text-center text-sm text-muted-foreground">
              Ask a question about your data
            </p>
          </div>
        )}

        {isLoading && (
          <div className="flex h-full items-center justify-center" data-testid="chat-loading">
            <Loader2 className="size-6 animate-spin text-muted-foreground" />
          </div>
        )}

        <div className="space-y-4 p-4">
          {messages.map((message) => (
            <MessageBubble
              key={message.id}
              role={message.role}
              content={message.content}
            />
          ))}

          {/* Streaming assistant response */}
          {isStreaming && (
            <MessageBubble
              role="assistant"
              content=""
              isStreaming
            >
              <StreamingText
                content={streamingContent}
                isStreaming
              />
            </MessageBubble>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div
          className="flex items-center gap-2 border-t border-destructive/30 bg-destructive/10 px-3 py-2"
          data-testid="chat-error"
        >
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
      <ChatInput
        onSend={handleSend}
        onCancel={cancelStream}
        isStreaming={isStreaming}
        disabled={isLoading}
      />
    </div>
  );
}
