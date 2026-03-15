import { useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import {
  ChevronRight,
  Database,
  Trash2,
  AlertCircle,
  Loader2,
  TestTube2,
  Pencil,
  RefreshCw,
  Table2,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  useConnectionDetail,
  useTestConnection,
  useRefreshConnectionSchema,
  useDeleteConnection,
} from "@/hooks/use-connections";
import type { SchemaColumn } from "@/types/api";

const UUID_REGEX =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

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

function groupSchemaByTable(
  schema: SchemaColumn[],
): Map<string, SchemaColumn[]> {
  const grouped = new Map<string, SchemaColumn[]>();
  for (const col of schema) {
    const tableName = col.table_name ?? "unknown";
    const existing = grouped.get(tableName) ?? [];
    existing.push(col);
    grouped.set(tableName, existing);
  }
  return grouped;
}

export function ConnectionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{
    status: string;
    latency_ms?: number | null;
    tables_found?: number | null;
    error?: string | null;
  } | null>(null);
  const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set());

  const isValidId = id && UUID_REGEX.test(id);

  const {
    data: connection,
    isLoading,
    isError,
    error,
  } = useConnectionDetail(isValidId ? id : undefined);

  const testMutation = useTestConnection();
  const refreshMutation = useRefreshConnectionSchema();
  const deleteMutation = useDeleteConnection();

  if (!id || !isValidId) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 p-6">
        <h1 className="text-2xl font-bold">Invalid Connection ID</h1>
        <p className="text-muted-foreground">
          The connection ID provided is not a valid identifier.
        </p>
        <Link
          to="/"
          className="text-sm text-primary underline underline-offset-4 hover:text-primary/80"
        >
          Back to Dashboard
        </Link>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-6 p-6">
        <div className="h-6 w-48 animate-pulse rounded bg-muted/50" />
        <div className="h-8 w-64 animate-pulse rounded bg-muted/50" />
        <div className="h-48 animate-pulse rounded-xl border bg-muted/50" />
      </div>
    );
  }

  const is404 =
    isError && error instanceof Error && error.message.includes("404");

  if (is404) {
    return (
      <div
        className="flex flex-1 flex-col items-center justify-center gap-4 p-6"
        data-testid="not-found"
      >
        <h1 className="text-2xl font-bold">Connection Not Found</h1>
        <p className="text-muted-foreground">
          The connection you are looking for does not exist or has been deleted.
        </p>
        <Link
          to="/data"
          className="text-sm text-primary underline underline-offset-4 hover:text-primary/80"
        >
          Back to Connections
        </Link>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 p-6">
        <AlertCircle className="size-10 text-destructive" />
        <h1 className="text-2xl font-bold">Error Loading Connection</h1>
        <p className="text-muted-foreground">
          {error instanceof Error
            ? error.message
            : "An unexpected error occurred."}
        </p>
        <Link
          to="/data"
          className="text-sm text-primary underline underline-offset-4 hover:text-primary/80"
        >
          Back to Connections
        </Link>
      </div>
    );
  }

  if (!connection) return null;

  function handleTest() {
    setTestResult(null);
    testMutation.mutate(id!, {
      onSuccess: (result) => {
        setTestResult(result);
      },
      onError: (err) => {
        setTestResult({
          status: "error",
          error: err instanceof Error ? err.message : "Test failed",
        });
      },
    });
  }

  function handleRefreshSchema() {
    refreshMutation.mutate(id!);
  }

  function handleDelete() {
    setDeleteError(null);
    deleteMutation.mutate(id!, {
      onSuccess: () => {
        navigate("/data");
      },
      onError: (err) => {
        setDeleteError(
          err instanceof Error ? err.message : "Failed to delete connection.",
        );
        setConfirmDelete(false);
      },
    });
  }

  function toggleTable(tableName: string) {
    setExpandedTables((prev) => {
      const next = new Set(prev);
      if (next.has(tableName)) next.delete(tableName);
      else next.add(tableName);
      return next;
    });
  }

  const schemaByTable = connection.schema
    ? groupSchemaByTable(connection.schema)
    : new Map();
  const isBusy =
    testMutation.isPending ||
    refreshMutation.isPending ||
    deleteMutation.isPending;

  return (
    <div className="space-y-6 p-6">
      {/* Breadcrumbs */}
      <nav aria-label="Breadcrumb" data-testid="breadcrumbs">
        <ol className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <li>
            <Link to="/" className="hover:text-foreground">
              Dashboard
            </Link>
          </li>
          <li>
            <ChevronRight className="size-3.5" />
          </li>
          <li>
            <Link to="/data" className="hover:text-foreground">
              Connections
            </Link>
          </li>
          <li>
            <ChevronRight className="size-3.5" />
          </li>
          <li className="font-medium text-foreground">{connection.name}</li>
        </ol>
      </nav>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <Database className="size-8 text-muted-foreground" />
          <div>
            <h1 className="text-2xl font-bold">{connection.name}</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {connection.db_type} database
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleTest}
            disabled={isBusy}
            data-testid="test-button"
          >
            {testMutation.isPending ? (
              <Loader2 className="animate-spin" />
            ) : (
              <TestTube2 />
            )}
            Test
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefreshSchema}
            disabled={isBusy}
            data-testid="refresh-schema-button"
          >
            {refreshMutation.isPending ? (
              <Loader2 className="animate-spin" />
            ) : (
              <RefreshCw />
            )}
            Refresh Schema
          </Button>
          <Button variant="outline" size="sm" asChild>
            <Link to={`/data/connection/${id}/edit`}>
              <Pencil />
              Edit
            </Link>
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setConfirmDelete(true)}
            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
            data-testid="delete-button"
          >
            <Trash2 />
            Delete
          </Button>
        </div>
      </div>

      {/* Test result */}
      {testResult && (
        <div
          className={`flex items-start gap-2 rounded-md border p-3 ${
            testResult.status === "error" || testResult.error
              ? "border-destructive/50 bg-destructive/10"
              : "border-green-500/50 bg-green-500/10"
          }`}
          data-testid="test-result"
        >
          {testResult.status === "error" || testResult.error ? (
            <>
              <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
              <p className="text-sm text-destructive">
                Connection test failed: {testResult.error}
              </p>
            </>
          ) : (
            <p className="text-sm text-green-700 dark:text-green-400">
              Connection successful
              {testResult.latency_ms != null && ` (${testResult.latency_ms.toFixed(0)}ms)`}
              {testResult.tables_found != null &&
                ` - ${testResult.tables_found} tables found`}
            </p>
          )}
        </div>
      )}

      {/* Delete error */}
      {deleteError && (
        <div
          className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3"
          data-testid="delete-error"
        >
          <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
          <p className="text-sm text-destructive">{deleteError}</p>
        </div>
      )}

      {/* Metadata */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Connection Details</CardTitle>
        </CardHeader>
        <CardContent>
          <dl
            className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3 lg:grid-cols-4"
            data-testid="metadata"
          >
            <div>
              <dt className="text-muted-foreground">Status</dt>
              <dd className="mt-0.5 flex items-center gap-2 font-medium">
                <span
                  className={`inline-block size-2.5 rounded-full ${statusColor(connection.status)}`}
                />
                {statusLabel(connection.status)}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Type</dt>
              <dd className="mt-0.5 font-medium">{connection.db_type}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Host</dt>
              <dd className="mt-0.5 font-mono text-xs">
                {connection.host}:{connection.port}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Database</dt>
              <dd className="mt-0.5 font-medium">{connection.database_name}</dd>
            </div>
            {connection.username && (
              <div>
                <dt className="text-muted-foreground">Username</dt>
                <dd className="mt-0.5 font-medium">{connection.username}</dd>
              </div>
            )}
            <div>
              <dt className="text-muted-foreground">Last Tested</dt>
              <dd className="mt-0.5 font-medium">
                {formatDate(connection.last_tested_at)}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Created</dt>
              <dd className="mt-0.5 font-medium">
                {formatDate(connection.created_at)}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Updated</dt>
              <dd className="mt-0.5 font-medium">
                {formatDate(connection.updated_at)}
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {/* Schema Browser */}
      {connection.schema && connection.schema.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">
              Schema Browser ({schemaByTable.size}{" "}
              {schemaByTable.size === 1 ? "table" : "tables"},{" "}
              {connection.schema.length} columns)
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2" data-testid="schema-browser">
            {Array.from(schemaByTable.entries()).map(([tableName, columns]) => (
              <div key={tableName} className="rounded-md border">
                <button
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-medium hover:bg-accent/50"
                  onClick={() => toggleTable(tableName)}
                  data-testid={`table-toggle-${tableName}`}
                >
                  <Table2 className="size-4 text-muted-foreground" />
                  <span>{tableName}</span>
                  <span className="text-xs text-muted-foreground">
                    ({columns.length} columns)
                  </span>
                  <ChevronRight
                    className={`ml-auto size-4 transition-transform ${
                      expandedTables.has(tableName) ? "rotate-90" : ""
                    }`}
                  />
                </button>
                {expandedTables.has(tableName) && (
                  <div className="border-t px-3 py-2">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-xs text-muted-foreground">
                          <th className="pb-1 pr-4 font-medium">Column</th>
                          <th className="pb-1 pr-4 font-medium">Type</th>
                          <th className="pb-1 pr-4 font-medium">Nullable</th>
                          <th className="pb-1 pr-4 font-medium">PK</th>
                          <th className="pb-1 font-medium">FK</th>
                        </tr>
                      </thead>
                      <tbody>
                        {columns.map((col) => (
                          <tr key={col.column_name} className="border-t">
                            <td className="py-1 pr-4 font-mono text-xs">
                              {col.column_name}
                            </td>
                            <td className="py-1 pr-4 text-muted-foreground">
                              {col.data_type}
                            </td>
                            <td className="py-1 pr-4">
                              {col.is_nullable ? "Yes" : "No"}
                            </td>
                            <td className="py-1 pr-4">
                              {col.is_primary_key ? "Yes" : "No"}
                            </td>
                            <td className="py-1 text-xs text-muted-foreground">
                              {col.foreign_key_ref ?? "--"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {connection.schema && connection.schema.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-8">
            <Table2 className="size-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              No schema information available.
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={handleRefreshSchema}
              disabled={isBusy}
            >
              <RefreshCw />
              Refresh Schema
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Delete Confirmation */}
      {confirmDelete && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          data-testid="delete-confirmation"
        >
          <div className="mx-4 w-full max-w-sm rounded-lg border bg-background p-6 shadow-lg">
            <h2 className="text-lg font-semibold">Delete Connection</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Are you sure you want to delete &quot;{connection.name}&quot;? This
              action cannot be undone.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setConfirmDelete(false)}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={handleDelete}
                disabled={deleteMutation.isPending}
                data-testid="confirm-delete-button"
              >
                {deleteMutation.isPending ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <Trash2 />
                )}
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
