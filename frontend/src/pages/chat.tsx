import { useState, useCallback, useEffect, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  MessageSquare,
  Search,
  Trash2,
  Loader2,
  AlertCircle,
  Clock,
  MessagesSquare,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  useConversationList,
  useDeleteConversation,
} from "@/hooks/use-conversations";
import { useChatStore } from "@/stores/chat-store";
import type { Conversation } from "@/types/api";

function formatRelativeDate(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: date.getFullYear() !== now.getFullYear() ? "numeric" : undefined,
  });
}

function ConversationItem({
  conversation,
  onSelect,
  onDelete,
  isDeleting,
}: {
  conversation: Conversation;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  isDeleting: boolean;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      data-testid="conversation-item"
      className="flex w-full cursor-pointer items-center gap-3 rounded-lg border bg-card p-4 text-left transition-colors hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      onClick={() => onSelect(conversation.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(conversation.id);
        }
      }}
    >
      <MessageSquare className="size-5 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{conversation.title}</p>
        <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <Clock className="size-3" />
            {formatRelativeDate(conversation.updated_at)}
          </span>
          <span className="flex items-center gap-1">
            <MessagesSquare className="size-3" />
            {conversation.message_count} {conversation.message_count === 1 ? "message" : "messages"}
          </span>
        </div>
      </div>
      <Button
        variant="ghost"
        size="icon-xs"
        className="shrink-0 text-muted-foreground hover:text-destructive"
        onClick={(e) => {
          e.stopPropagation();
          onDelete(conversation.id);
        }}
        disabled={isDeleting}
        data-testid="delete-conversation-button"
        aria-label={`Delete ${conversation.title}`}
      >
        {isDeleting ? (
          <Loader2 className="animate-spin" />
        ) : (
          <Trash2 />
        )}
      </Button>
    </div>
  );
}

function ConversationHistoryBrowser() {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const navigate = useNavigate();
  const scrollRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const {
    data,
    isLoading,
    isError,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    refetch,
  } = useConversationList(debouncedSearch);

  const deleteMutation = useDeleteConversation();

  // Infinite scroll with IntersectionObserver
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) {
          void fetchNextPage();
        }
      },
      { root: scrollRef.current, threshold: 0.1 },
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const conversations =
    data?.pages.flatMap((page) => page.conversations) ?? [];

  const handleSelect = useCallback(
    (id: string) => {
      void navigate(`/chat/${id}`);
    },
    [navigate],
  );

  const handleDeleteClick = useCallback((id: string) => {
    setConfirmDeleteId(id);
  }, []);

  const handleDeleteConfirm = useCallback(() => {
    if (!confirmDeleteId) return;
    setDeletingId(confirmDeleteId);
    setConfirmDeleteId(null);
    setDeleteError(null);
    deleteMutation.mutate(confirmDeleteId, {
      onError: (error) => {
        setDeleteError(error.message);
        setTimeout(() => setDeleteError(null), 5000);
      },
      onSettled: () => setDeletingId(null),
    });
  }, [confirmDeleteId, deleteMutation]);

  const handleDeleteCancel = useCallback(() => {
    setConfirmDeleteId(null);
  }, []);

  return (
    <div className="flex h-full flex-col space-y-4 p-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">Conversations</h1>
        <p className="mt-1 text-muted-foreground">
          Browse and search your conversation history.
        </p>
      </div>

      {/* Search bar */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search conversations..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-9 w-full rounded-md border border-input bg-background pl-9 pr-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          data-testid="search-input"
        />
      </div>

      {/* Delete error toast */}
      {deleteError && (
        <div
          className="flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3"
          data-testid="delete-error-toast"
        >
          <AlertCircle className="size-4 shrink-0 text-destructive" />
          <p className="text-sm text-destructive">
            Failed to delete conversation. Please try again.
          </p>
        </div>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="space-y-3" data-testid="loading-skeleton">
          {Array.from({ length: 5 }).map((_, i) => (
            <div
              key={i}
              className="h-[72px] animate-pulse rounded-lg border bg-muted/50"
            />
          ))}
        </div>
      )}

      {/* Error state */}
      {isError && (
        <div
          className="flex items-center gap-3 rounded-lg border border-destructive/50 bg-destructive/10 p-4"
          data-testid="error-state"
        >
          <AlertCircle className="size-5 shrink-0 text-destructive" />
          <p className="text-sm text-destructive">
            Failed to load conversations.
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void refetch()}
            data-testid="retry-button"
          >
            Retry
          </Button>
        </div>
      )}

      {/* Empty state - no conversations at all */}
      {!isLoading && !isError && conversations.length === 0 && !debouncedSearch && (
        <Card className="border-dashed" data-testid="empty-state">
          <CardContent className="flex flex-col items-center gap-3 py-12">
            <MessageSquare className="size-12 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              No conversations yet. Start a new chat to analyze your data.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Empty state - no search results */}
      {!isLoading && !isError && conversations.length === 0 && debouncedSearch && (
        <div
          className="flex flex-col items-center gap-2 py-12 text-center"
          data-testid="no-search-results"
        >
          <Search className="size-10 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            No conversations matching &ldquo;{debouncedSearch}&rdquo;
          </p>
        </div>
      )}

      {/* Conversation list */}
      {conversations.length > 0 && (
        <div
          ref={scrollRef}
          className="flex-1 space-y-2 overflow-y-auto"
          data-testid="conversation-list"
        >
          {conversations.map((conversation) => (
            <ConversationItem
              key={conversation.id}
              conversation={conversation}
              onSelect={handleSelect}
              onDelete={handleDeleteClick}
              isDeleting={deletingId === conversation.id}
            />
          ))}

          {/* Infinite scroll sentinel */}
          <div ref={sentinelRef} className="h-1" />

          {isFetchingNextPage && (
            <div className="flex justify-center py-4" data-testid="loading-more">
              <Loader2 className="size-5 animate-spin text-muted-foreground" />
            </div>
          )}
        </div>
      )}

      {/* Delete confirmation dialog */}
      {confirmDeleteId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          data-testid="delete-confirmation"
        >
          <div className="mx-4 w-full max-w-sm rounded-lg border bg-background p-6 shadow-lg">
            <h2 className="text-lg font-semibold">Delete Conversation</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Are you sure you want to delete this conversation? This action
              cannot be undone.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleDeleteCancel}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={handleDeleteConfirm}
                data-testid="confirm-delete-button"
              >
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function ChatPage() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const { switchConversation, conversationId: activeId } = useChatStore();

  // When URL has a conversationId, load it into the chat store
  useEffect(() => {
    if (conversationId && conversationId !== activeId) {
      void switchConversation(conversationId);
    }
  }, [conversationId, activeId, switchConversation]);

  if (conversationId) {
    // The actual chat UI is rendered by ChatPanel in the layout.
    // This page component just triggers the store load.
    return null;
  }

  return <ConversationHistoryBrowser />;
}
