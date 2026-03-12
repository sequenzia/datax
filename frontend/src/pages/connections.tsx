import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Database,
  AlertCircle,
  Plus,
  TestTube2,
  RefreshCw,
  Pencil,
  Trash2,
  Loader2,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  useConnectionList,
  useTestConnection,
  useRefreshConnectionSchema,
  useDeleteConnection,
} from "@/hooks/use-connections";
import type { Connection } from "@/types/api";

function statusColor(status: string): string {
  switch (status) {
    case "connected":
      return "bg-green-500";
    case "error":
      return "bg-red-500";
    case "disconnected":
    default:
      return "bg-gray-400";
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case "connected":
      return "Connected";
    case "error":
      return "Error";
    case "disconnected":
      return "Disconnected";
    default:
      return status;
  }
}

function formatDate(dateString: string | null): string {
  if (!dateString) return "Never";
  return new Date(dateString).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function ConnectionCard({
  connection,
  onTest,
  onRefreshSchema,
  onDelete,
  testingId,
  refreshingId,
  deletingId,
  testError,
}: {
  connection: Connection;
  onTest: (id: string) => void;
  onRefreshSchema: (id: string) => void;
  onDelete: (id: string) => void;
  testingId: string | null;
  refreshingId: string | null;
  deletingId: string | null;
  testError: { id: string; message: string } | null;
}) {
  const isTesting = testingId === connection.id;
  const isRefreshing = refreshingId === connection.id;
  const isDeleting = deletingId === connection.id;
  const isBusy = isTesting || isRefreshing || isDeleting;

  return (
    <Card data-testid="connection-card">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">{connection.name}</CardTitle>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">
              {statusLabel(connection.status)}
            </span>
            <span
              className={`inline-block size-2.5 rounded-full ${statusColor(connection.status)}`}
              title={connection.status}
              data-testid="connection-status"
            />
          </div>
        </div>
        <CardDescription>
          {connection.db_type} &middot; {connection.host}:{connection.port}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 pt-0">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Database: {connection.database_name}</span>
          <span>Tested: {formatDate(connection.last_tested_at)}</span>
        </div>

        {testError && testError.id === connection.id && (
          <div
            className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-2"
            data-testid="test-error"
          >
            <AlertCircle className="mt-0.5 size-3.5 shrink-0 text-destructive" />
            <p className="text-xs text-destructive">{testError.message}</p>
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="xs"
            onClick={() => onTest(connection.id)}
            disabled={isBusy}
            data-testid="test-button"
          >
            {isTesting ? (
              <Loader2 className="animate-spin" />
            ) : (
              <TestTube2 />
            )}
            Test
          </Button>
          <Button
            variant="outline"
            size="xs"
            onClick={() => onRefreshSchema(connection.id)}
            disabled={isBusy}
            data-testid="refresh-schema-button"
          >
            {isRefreshing ? (
              <Loader2 className="animate-spin" />
            ) : (
              <RefreshCw />
            )}
            Refresh Schema
          </Button>
          <Button
            variant="outline"
            size="xs"
            asChild
            disabled={isBusy}
          >
            <Link to={`/connections/${connection.id}/edit`}>
              <Pencil />
              Edit
            </Link>
          </Button>
          <Button
            variant="outline"
            size="xs"
            onClick={() => onDelete(connection.id)}
            disabled={isBusy}
            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
            data-testid="delete-button"
          >
            {isDeleting ? (
              <Loader2 className="animate-spin" />
            ) : (
              <Trash2 />
            )}
            Delete
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export function ConnectionsPage() {
  const { data: connections, isLoading, isError, refetch } = useConnectionList();
  const testMutation = useTestConnection();
  const refreshMutation = useRefreshConnectionSchema();
  const deleteMutation = useDeleteConnection();

  const [testingId, setTestingId] = useState<string | null>(null);
  const [refreshingId, setRefreshingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [testError, setTestError] = useState<{
    id: string;
    message: string;
  } | null>(null);

  function handleTest(connectionId: string) {
    setTestError(null);
    setTestingId(connectionId);
    testMutation.mutate(connectionId, {
      onError: (error) => {
        setTestError({ id: connectionId, message: error.message });
      },
      onSettled: () => setTestingId(null),
    });
  }

  function handleRefreshSchema(connectionId: string) {
    setRefreshingId(connectionId);
    refreshMutation.mutate(connectionId, {
      onSettled: () => setRefreshingId(null),
    });
  }

  function handleDeleteClick(connectionId: string) {
    setConfirmDeleteId(connectionId);
  }

  function handleDeleteConfirm() {
    if (!confirmDeleteId) return;
    setDeletingId(confirmDeleteId);
    setConfirmDeleteId(null);
    deleteMutation.mutate(confirmDeleteId, {
      onSettled: () => setDeletingId(null),
    });
  }

  function handleDeleteCancel() {
    setConfirmDeleteId(null);
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Connections</h1>
          <p className="mt-1 text-muted-foreground">
            Manage your database connections.
          </p>
        </div>
        <Button asChild>
          <Link to="/connections/new">
            <Plus />
            Add Connection
          </Link>
        </Button>
      </div>

      {isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="h-44 animate-pulse rounded-xl border bg-muted/50"
            />
          ))}
        </div>
      )}

      {isError && (
        <div className="flex items-center gap-3 rounded-lg border border-destructive/50 bg-destructive/10 p-4">
          <AlertCircle className="size-5 shrink-0 text-destructive" />
          <p className="text-sm text-destructive">
            Failed to load connections.
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void refetch()}
          >
            Retry
          </Button>
        </div>
      )}

      {connections && connections.length === 0 && (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center gap-3 py-12">
            <Database className="size-12 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              No database connections configured.
            </p>
            <Button variant="outline" size="sm" asChild>
              <Link to="/connections/new">Add Connection</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {connections && connections.length > 0 && (
        <div className="grid gap-4 overflow-y-auto sm:grid-cols-2 lg:grid-cols-3">
          {connections.map((connection) => (
            <ConnectionCard
              key={connection.id}
              connection={connection}
              onTest={handleTest}
              onRefreshSchema={handleRefreshSchema}
              onDelete={handleDeleteClick}
              testingId={testingId}
              refreshingId={refreshingId}
              deletingId={deletingId}
              testError={testError}
            />
          ))}
        </div>
      )}

      {confirmDeleteId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          data-testid="delete-confirmation"
        >
          <div className="mx-4 w-full max-w-sm rounded-lg border bg-background p-6 shadow-lg">
            <h2 className="text-lg font-semibold">Delete Connection</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Are you sure you want to delete this connection? This action
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
