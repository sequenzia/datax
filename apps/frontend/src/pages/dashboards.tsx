import { useState, useCallback } from "react";
import {
  Plus,
  Pencil,
  Trash2,
  X,
  Check,
  Loader2,
  AlertCircle,
  LayoutDashboard,
  Bookmark,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  useDashboardList,
  useCreateDashboard,
  useUpdateDashboard,
  useDeleteDashboard,
  useRemoveDashboardItem,
  useAutoRefreshItem,
} from "@/hooks/use-dashboards";
import type { Dashboard, DashboardItem } from "@/types/api";

/** A single dashboard item card with auto-refresh of bookmark SQL. */
function DashboardItemCard({
  item,
  dashboardId,
  onRemove,
}: {
  item: DashboardItem;
  dashboardId: string;
  onRemove: (dashboardId: string, itemId: string) => void;
}) {
  const { data: refreshedData, isLoading, isError } = useAutoRefreshItem(item);
  const bookmark = item.bookmark;

  if (!bookmark) return null;

  // Use refreshed data if available, else fall back to snapshot
  const resultData = refreshedData ?? null;
  const snapshotData = bookmark.result_snapshot as {
    columns?: string[];
    rows?: unknown[][];
  } | null;

  const columns = resultData?.columns ?? snapshotData?.columns ?? [];
  const rows = resultData?.rows ?? snapshotData?.rows ?? [];
  const rowCount = resultData?.row_count ?? rows.length;

  return (
    <Card
      className="group relative transition-shadow hover:shadow-md"
      data-testid="dashboard-item-card"
    >
      <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0 pb-2">
        <div className="min-w-0 flex-1">
          <CardTitle className="truncate text-sm font-medium">
            {bookmark.title}
          </CardTitle>
          {bookmark.sql && (
            <p className="mt-1 truncate font-mono text-xs text-muted-foreground">
              {bookmark.sql}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {isLoading && (
            <Loader2
              className="size-3 animate-spin text-muted-foreground"
              data-testid="dashboard-item-loading"
            />
          )}
          {isError && (
            <span title="Failed to refresh data - showing cached results">
              <AlertCircle
                className="size-3 text-amber-500"
                data-testid="dashboard-item-error"
              />
            </span>
          )}
          <button
            type="button"
            onClick={() => onRemove(dashboardId, item.id)}
            className="invisible rounded p-0.5 text-muted-foreground hover:text-destructive group-hover:visible"
            aria-label={`Remove ${bookmark.title}`}
            data-testid="dashboard-item-remove"
          >
            <X className="size-3.5" />
          </button>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {columns.length > 0 && rows.length > 0 ? (
          <div className="max-h-48 overflow-auto rounded border">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b bg-muted/50">
                  {columns.map((col) => (
                    <th
                      key={col}
                      className="whitespace-nowrap px-2 py-1 text-left font-medium"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, 10).map((row, i) => (
                  <tr key={i} className="border-b last:border-0">
                    {(row as unknown[]).map((cell, j) => (
                      <td
                        key={j}
                        className="whitespace-nowrap px-2 py-1 text-muted-foreground"
                      >
                        {cell === null ? (
                          <span className="italic text-muted-foreground/50">
                            null
                          </span>
                        ) : (
                          String(cell)
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {rowCount > 10 && (
              <p className="border-t px-2 py-1 text-center text-xs text-muted-foreground">
                Showing 10 of {rowCount} rows
              </p>
            )}
          </div>
        ) : (
          <p className="py-4 text-center text-xs text-muted-foreground">
            No data available
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/** Grid display for a single dashboard's items. */
function DashboardGrid({
  dashboard,
  onRemoveItem,
}: {
  dashboard: Dashboard;
  onRemoveItem: (dashboardId: string, itemId: string) => void;
}) {
  if (dashboard.items.length === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center rounded-lg border border-dashed py-12"
        data-testid="dashboard-empty"
      >
        <Bookmark className="size-8 text-muted-foreground" />
        <p className="mt-3 text-sm text-muted-foreground">
          Pin bookmarks to get started
        </p>
      </div>
    );
  }

  return (
    <div
      className="grid gap-4 sm:grid-cols-1 md:grid-cols-2 xl:grid-cols-3"
      data-testid="dashboard-grid"
    >
      {dashboard.items.map((item) => (
        <DashboardItemCard
          key={item.id}
          item={item}
          dashboardId={dashboard.id}
          onRemove={onRemoveItem}
        />
      ))}
    </div>
  );
}

/** Inline title editor for dashboard rename. */
function DashboardTitleEditor({
  dashboard,
  onSave,
  onCancel,
}: {
  dashboard: Dashboard;
  onSave: (id: string, title: string) => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(dashboard.title);

  return (
    <div className="flex items-center gap-2">
      <input
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        className="h-8 rounded-md border border-input bg-background px-2 text-sm outline-none focus-visible:ring-1 focus-visible:ring-ring"
        autoFocus
        onKeyDown={(e) => {
          if (e.key === "Enter" && title.trim()) {
            onSave(dashboard.id, title.trim());
          }
          if (e.key === "Escape") {
            onCancel();
          }
        }}
        data-testid="dashboard-title-input"
      />
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={() => title.trim() && onSave(dashboard.id, title.trim())}
        aria-label="Save title"
      >
        <Check className="size-3.5" />
      </Button>
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={onCancel}
        aria-label="Cancel editing"
      >
        <X className="size-3.5" />
      </Button>
    </div>
  );
}

/** Header for a single dashboard with rename/delete actions. */
function DashboardHeader({
  dashboard,
  isEditing,
  onStartEdit,
  onSaveEdit,
  onCancelEdit,
  onDelete,
}: {
  dashboard: Dashboard;
  isEditing: boolean;
  onStartEdit: () => void;
  onSaveEdit: (id: string, title: string) => void;
  onCancelEdit: () => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="flex items-center justify-between">
      {isEditing ? (
        <DashboardTitleEditor
          dashboard={dashboard}
          onSave={onSaveEdit}
          onCancel={onCancelEdit}
        />
      ) : (
        <h2 className="text-lg font-semibold">{dashboard.title}</h2>
      )}
      {!isEditing && (
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onStartEdit}
            aria-label={`Rename ${dashboard.title}`}
            data-testid="dashboard-rename"
          >
            <Pencil className="size-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => onDelete(dashboard.id)}
            aria-label={`Delete ${dashboard.title}`}
            data-testid="dashboard-delete"
          >
            <Trash2 className="size-3.5 text-destructive" />
          </Button>
        </div>
      )}
    </div>
  );
}

export function DashboardsPage() {
  const { data: dashboards, isLoading, isError, refetch } = useDashboardList();
  const createMutation = useCreateDashboard();
  const updateMutation = useUpdateDashboard();
  const deleteMutation = useDeleteDashboard();
  const removeItemMutation = useRemoveDashboardItem();

  const [editingId, setEditingId] = useState<string | null>(null);

  const handleCreate = useCallback(() => {
    createMutation.mutate({ title: "Untitled Dashboard" });
  }, [createMutation]);

  const handleSaveEdit = useCallback(
    (id: string, title: string) => {
      updateMutation.mutate(
        { id, body: { title } },
        { onSuccess: () => setEditingId(null) },
      );
    },
    [updateMutation],
  );

  const handleDelete = useCallback(
    (id: string) => {
      deleteMutation.mutate(id);
    },
    [deleteMutation],
  );

  const handleRemoveItem = useCallback(
    (dashboardId: string, itemId: string) => {
      removeItemMutation.mutate({ dashboardId, itemId });
    },
    [removeItemMutation],
  );

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2">
        <AlertCircle className="size-6 text-destructive" />
        <p className="text-sm text-muted-foreground">Failed to load dashboards</p>
        <Button variant="outline" size="sm" onClick={() => void refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto" data-testid="dashboards-page">
      {/* Page header */}
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div className="flex items-center gap-2">
          <LayoutDashboard className="size-5" />
          <h1 className="text-xl font-bold">Dashboards</h1>
        </div>
        <Button
          size="sm"
          onClick={handleCreate}
          disabled={createMutation.isPending}
          data-testid="create-dashboard"
        >
          {createMutation.isPending ? (
            <Loader2 className="mr-1 size-3.5 animate-spin" />
          ) : (
            <Plus className="mr-1 size-3.5" />
          )}
          New Dashboard
        </Button>
      </div>

      {/* Dashboard list */}
      <div className="space-y-8 px-6 py-6">
        {(!dashboards || dashboards.length === 0) && (
          <div className="flex flex-col items-center justify-center py-16">
            <LayoutDashboard className="size-12 text-muted-foreground" />
            <p className="mt-4 text-lg font-medium text-muted-foreground">
              No dashboards yet
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              Create a dashboard and pin bookmarks to it.
            </p>
            <Button
              className="mt-4"
              onClick={handleCreate}
              disabled={createMutation.isPending}
            >
              <Plus className="mr-1 size-4" />
              Create Dashboard
            </Button>
          </div>
        )}

        {dashboards?.map((dashboard) => (
          <section key={dashboard.id} data-testid="dashboard-section">
            <DashboardHeader
              dashboard={dashboard}
              isEditing={editingId === dashboard.id}
              onStartEdit={() => setEditingId(dashboard.id)}
              onSaveEdit={handleSaveEdit}
              onCancelEdit={() => setEditingId(null)}
              onDelete={handleDelete}
            />
            <div className="mt-3">
              <DashboardGrid
                dashboard={dashboard}
                onRemoveItem={handleRemoveItem}
              />
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
