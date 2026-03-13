import { useState, useCallback, useRef, useEffect } from "react";
import { NavLink, useNavigate, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  MessageSquare,
  Code2,
  Database,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
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
import { SchemaBrowser } from "@/components/schema-browser/schema-browser";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { ThemeToggle } from "@/components/theme-toggle";
import type { Conversation } from "@/types/api";

// Icon-only navigation items in the sidebar footer
const footerNavItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard", end: true },
  { to: "/chat", icon: MessageSquare, label: "Chat", end: false },
  { to: "/sql", icon: Code2, label: "SQL Editor", end: false },
  { to: "/data", icon: Database, label: "Data Sources", end: false },
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
    <div className="flex h-full flex-col" data-testid="sidebar-conversation-list">
      {/* New chat button */}
      <div className="px-3 pt-3 pb-2">
        <Button
          variant="outline"
          size="sm"
          onClick={handleNewConversation}
          className="w-full justify-start gap-2"
          data-testid="sidebar-new-conversation"
        >
          <Plus className="size-3.5" />
          New Chat
        </Button>
      </div>

      {/* Search bar */}
      <div className="relative px-3 pb-2">
        <Search className="absolute left-5 top-1/2 size-3 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search conversations..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-7 w-full rounded-md border border-input bg-background pl-7 pr-2 text-xs outline-none focus-visible:ring-1 focus-visible:ring-ring"
          data-testid="sidebar-search-input"
        />
      </div>

      {/* Delete error */}
      {deleteError && (
        <div className="mx-3 mb-1 flex items-center gap-1 rounded-md bg-destructive/10 px-2 py-1">
          <AlertCircle className="size-3 shrink-0 text-destructive" />
          <span className="text-xs text-destructive">Delete failed</span>
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="flex justify-center py-4">
          <Loader2 className="size-4 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Error */}
      {isError && (
        <div className="mx-3 flex flex-col items-center gap-1 py-4">
          <AlertCircle className="size-4 text-destructive" />
          <span className="text-xs text-destructive">Failed to load</span>
          <Button variant="ghost" size="xs" onClick={() => void refetch()}>
            Retry
          </Button>
        </div>
      )}

      {/* Empty */}
      {!isLoading && !isError && conversations.length === 0 && (
        <div className="px-3 py-4 text-center">
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

          <div ref={sentinelRef} className="h-1" />

          {isFetchingNextPage && (
            <div className="flex justify-center py-2">
              <Loader2 className="size-3 animate-spin text-muted-foreground" />
            </div>
          )}
        </div>
      )}

      {/* Delete confirmation */}
      {confirmDeleteId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="mx-4 w-full max-w-sm rounded-lg border bg-background p-6 shadow-lg">
            <h2 className="text-lg font-semibold">Delete Conversation</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Are you sure? This action cannot be undone.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={handleDeleteCancel}>
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

/** Draggable horizontal divider between conversation list and schema browser */
function SidebarDivider({ onResize }: { onResize: (deltaY: number) => void }) {
  const isDragging = useRef(false);
  const lastY = useRef(0);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      isDragging.current = true;
      lastY.current = e.clientY;

      const handleMouseMove = (ev: MouseEvent) => {
        if (!isDragging.current) return;
        const delta = ev.clientY - lastY.current;
        lastY.current = ev.clientY;
        onResize(delta);
      };

      const handleMouseUp = () => {
        isDragging.current = false;
        document.removeEventListener("mousemove", handleMouseMove);
        document.removeEventListener("mouseup", handleMouseUp);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      };

      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "row-resize";
      document.body.style.userSelect = "none";
    },
    [onResize],
  );

  return (
    <div
      className="group flex h-1.5 shrink-0 cursor-row-resize items-center justify-center border-y border-sidebar-border hover:bg-sidebar-accent/50"
      onMouseDown={handleMouseDown}
      role="separator"
      aria-orientation="horizontal"
      aria-label="Resize sidebar sections"
      data-testid="sidebar-divider"
    >
      <div className="h-px w-8 rounded-full bg-sidebar-border transition-colors group-hover:bg-primary/50" />
    </div>
  );
}

export function Sidebar() {
  const { sidebarOpen, toggleSidebar, sidebarConversationRatio, setSidebarConversationRatio } =
    useUIStore();
  const location = useLocation();
  const sidebarRef = useRef<HTMLDivElement>(null);

  const handleDividerResize = useCallback(
    (deltaY: number) => {
      const sidebar = sidebarRef.current;
      if (!sidebar) return;
      const sidebarHeight = sidebar.clientHeight;
      // Subtract header (~56px) + footer (~48px) + divider (~6px)
      const availableHeight = sidebarHeight - 110;
      if (availableHeight <= 0) return;
      const deltaRatio = deltaY / availableHeight;
      setSidebarConversationRatio(sidebarConversationRatio + deltaRatio);
    },
    [sidebarConversationRatio, setSidebarConversationRatio],
  );

  // Determine active nav item for footer icons
  const isActive = (path: string, end: boolean) => {
    if (end) return location.pathname === path;
    return location.pathname.startsWith(path);
  };

  return (
    <aside
      ref={sidebarRef}
      data-testid="sidebar"
      className={cn(
        "flex h-full flex-col border-r border-sidebar-border bg-sidebar transition-[width] duration-200 ease-in-out",
        sidebarOpen ? "w-64" : "w-14",
      )}
    >
      {/* Header */}
      <div className="flex h-14 shrink-0 items-center border-b border-sidebar-border px-3">
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

      {/* Expanded content: conversations + schema */}
      {sidebarOpen && (
        <>
          {/* Conversations section */}
          <div
            className="min-h-0 overflow-hidden"
            style={{ flex: `${sidebarConversationRatio} 1 0%` }}
          >
            <SidebarConversationList />
          </div>

          {/* Draggable divider */}
          <SidebarDivider onResize={handleDividerResize} />

          {/* Schema browser section */}
          <div
            className="min-h-0 overflow-hidden"
            style={{ flex: `${1 - sidebarConversationRatio} 1 0%` }}
          >
            <SchemaBrowser className="h-full" />
          </div>
        </>
      )}

      {/* Collapsed: just show icons centered */}
      {!sidebarOpen && <div className="flex-1" />}

      {/* Footer: icon-only navigation */}
      <div className="shrink-0 border-t border-sidebar-border p-1.5">
        <div
          className={cn(
            "flex items-center gap-0.5",
            sidebarOpen ? "justify-between px-1" : "flex-col gap-1",
          )}
        >
          {footerNavItems.map(({ to, icon: Icon, label, end }) => {
            const active = isActive(to, end);
            return (
              <Tooltip key={to}>
                <TooltipTrigger asChild>
                  <NavLink
                    to={to}
                    end={end}
                    className={cn(
                      "flex items-center justify-center rounded-md p-1.5 transition-colors",
                      active
                        ? "bg-sidebar-accent text-sidebar-accent-foreground"
                        : "text-sidebar-foreground hover:bg-sidebar-accent/50",
                    )}
                    aria-label={label}
                    data-testid={`nav-${label.toLowerCase().replace(/\s+/g, "-")}`}
                  >
                    <Icon className="size-4" />
                  </NavLink>
                </TooltipTrigger>
                <TooltipContent side={sidebarOpen ? "top" : "right"} sideOffset={8}>
                  {label}
                </TooltipContent>
              </Tooltip>
            );
          })}
          <ThemeToggle showLabel={false} />
        </div>
      </div>
    </aside>
  );
}
