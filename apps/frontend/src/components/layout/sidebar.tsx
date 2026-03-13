import { useState, useCallback, useRef, useEffect } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  MessageSquare,
  Code2,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
  Database,
  Plus,
  Trash2,
  Loader2,
  AlertCircle,
  Search,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/stores/ui-store";
import { useChatStore } from "@/stores/chat-store";
import {
  useConversationList,
  useDeleteConversation,
} from "@/hooks/use-conversations";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";
import type { Conversation } from "@/types/api";

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard", end: true },
  { to: "/chat", icon: MessageSquare, label: "Chat", end: false },
  { to: "/sql", icon: Code2, label: "SQL Editor", end: false },
  { to: "/settings", icon: Settings, label: "Settings", end: false },
] as const;

function SidebarConversationList() {
  const navigate = useNavigate();
  const { conversationId } = useChatStore();
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
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

  const conversations: Conversation[] =
    data?.pages.flatMap((page) => page.conversations) ?? [];

  const handleSelect = useCallback(
    (id: string) => {
      void navigate(`/chat/${id}`);
    },
    [navigate],
  );

  const handleNewConversation = useCallback(() => {
    useChatStore.getState().reset();
    void navigate("/chat");
  }, [navigate]);

  const handleDeleteClick = useCallback(
    (e: React.MouseEvent, id: string) => {
      e.stopPropagation();
      setConfirmDeleteId(id);
    },
    [],
  );

  const handleDeleteConfirm = useCallback(() => {
    if (!confirmDeleteId) return;
    const idToDelete = confirmDeleteId;
    setDeletingId(idToDelete);
    setConfirmDeleteId(null);
    setDeleteError(null);
    deleteMutation.mutate(idToDelete, {
      onSuccess: () => {
        // If the deleted conversation was active, reset the chat
        if (useChatStore.getState().conversationId === idToDelete) {
          useChatStore.getState().reset();
        }
      },
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
    <div className="flex flex-col" data-testid="sidebar-conversation-list">
      {/* Section header with new button */}
      <div className="flex items-center justify-between px-3 py-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Conversations
        </span>
        <Button
          variant="ghost"
          size="icon-xs"
          onClick={handleNewConversation}
          className="text-sidebar-foreground hover:bg-sidebar-accent"
          aria-label="New conversation"
          data-testid="sidebar-new-conversation"
        >
          <Plus className="size-3.5" />
        </Button>
      </div>

      {/* Search bar */}
      <div className="relative px-2 pb-1">
        <Search className="absolute left-4 top-1/2 size-3 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-7 w-full rounded-md border border-input bg-background pl-7 pr-2 text-xs outline-none focus-visible:ring-1 focus-visible:ring-ring"
          data-testid="sidebar-search-input"
        />
      </div>

      {/* Delete error */}
      {deleteError && (
        <div
          className="mx-2 mb-1 flex items-center gap-1 rounded-md bg-destructive/10 px-2 py-1"
          data-testid="sidebar-delete-error"
        >
          <AlertCircle className="size-3 shrink-0 text-destructive" />
          <span className="text-xs text-destructive">Delete failed</span>
        </div>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="flex justify-center py-4" data-testid="sidebar-loading">
          <Loader2 className="size-4 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Error state */}
      {isError && (
        <div className="mx-2 flex flex-col items-center gap-1 py-4" data-testid="sidebar-error">
          <AlertCircle className="size-4 text-destructive" />
          <span className="text-xs text-destructive">Failed to load</span>
          <Button
            variant="ghost"
            size="xs"
            onClick={() => void refetch()}
            data-testid="sidebar-retry-button"
          >
            Retry
          </Button>
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !isError && conversations.length === 0 && (
        <div className="px-3 py-4 text-center" data-testid="sidebar-empty-state">
          <MessageSquare className="mx-auto size-6 text-muted-foreground" />
          <p className="mt-1 text-xs text-muted-foreground">
            {debouncedSearch ? "No results" : "No conversations yet"}
          </p>
        </div>
      )}

      {/* Conversation list */}
      {conversations.length > 0 && (
        <div
          ref={scrollRef}
          className="flex-1 space-y-0.5 overflow-y-auto px-2"
          data-testid="sidebar-conversations"
        >
          {conversations.map((conv) => (
            <div
              key={conv.id}
              role="button"
              tabIndex={0}
              onClick={() => handleSelect(conv.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  handleSelect(conv.id);
                }
              }}
              className={cn(
                "group flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors",
                conv.id === conversationId
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground hover:bg-sidebar-accent/50",
              )}
              data-testid="sidebar-conversation-item"
              title={conv.title}
            >
              <MessageSquare className="size-3.5 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate text-xs">
                {conv.title}
              </span>
              <button
                type="button"
                onClick={(e) => handleDeleteClick(e, conv.id)}
                className="invisible shrink-0 rounded p-0.5 text-muted-foreground hover:text-destructive group-hover:visible"
                disabled={deletingId === conv.id}
                aria-label={`Delete ${conv.title}`}
                data-testid="sidebar-delete-button"
              >
                {deletingId === conv.id ? (
                  <Loader2 className="size-3 animate-spin" />
                ) : (
                  <Trash2 className="size-3" />
                )}
              </button>
            </div>
          ))}

          {/* Infinite scroll sentinel */}
          <div ref={sentinelRef} className="h-1" />

          {isFetchingNextPage && (
            <div className="flex justify-center py-2" data-testid="sidebar-loading-more">
              <Loader2 className="size-3 animate-spin text-muted-foreground" />
            </div>
          )}
        </div>
      )}

      {/* Delete confirmation */}
      {confirmDeleteId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          data-testid="sidebar-delete-confirmation"
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
                data-testid="sidebar-confirm-delete"
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

export function Sidebar() {
  const { sidebarOpen, toggleSidebar } = useUIStore();

  return (
    <aside
      data-testid="sidebar"
      className={cn(
        "flex h-full flex-col border-r border-sidebar-border bg-sidebar transition-[width] duration-200 ease-in-out",
        sidebarOpen ? "w-56" : "w-14",
      )}
    >
      {/* Header / Brand */}
      <div className="flex h-14 items-center border-b border-sidebar-border px-3">
        {sidebarOpen && (
          <span className="text-lg font-bold tracking-tight text-sidebar-foreground">
            DataX
          </span>
        )}
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={toggleSidebar}
          className={cn(
            "text-sidebar-foreground hover:bg-sidebar-accent",
            sidebarOpen ? "ml-auto" : "mx-auto",
          )}
          aria-label={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
          data-testid="sidebar-toggle"
        >
          {sidebarOpen ? (
            <PanelLeftClose className="size-4" />
          ) : (
            <PanelLeftOpen className="size-4" />
          )}
        </Button>
      </div>

      {/* Navigation */}
      <nav className="flex flex-col gap-1 p-2" role="navigation">
        {navItems.map(({ to, icon: Icon, label, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground",
                !sidebarOpen && "justify-center px-0",
              )
            }
            title={!sidebarOpen ? label : undefined}
          >
            <Icon className="size-4 shrink-0" />
            {sidebarOpen && <span>{label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Conversation history - only when sidebar is expanded */}
      {sidebarOpen && (
        <div className="min-h-0 flex-1 overflow-hidden border-t border-sidebar-border">
          <SidebarConversationList />
        </div>
      )}

      {/* Footer */}
      <div className="border-t border-sidebar-border p-2">
        <div
          className={cn(
            "flex items-center gap-2 rounded-md px-3 py-2 text-xs text-muted-foreground",
            !sidebarOpen && "justify-center px-0",
          )}
        >
          <Database className="size-3.5 shrink-0 text-green-500" />
          {sidebarOpen && <span>Connected</span>}
        </div>
        <div
          className={cn(
            "flex items-center rounded-md",
            sidebarOpen ? "px-1" : "justify-center",
          )}
        >
          <ThemeToggle showLabel={sidebarOpen} />
        </div>
      </div>
    </aside>
  );
}
