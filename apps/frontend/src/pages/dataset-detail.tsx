import { useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import {
  ChevronRight,
  FileSpreadsheet,
  Trash2,
  AlertCircle,
  Loader2,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight as ChevronRightIcon,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  useDatasetDetail,
  useDatasetPreview,
  useDeleteDataset,
} from "@/hooks/use-datasets";

const UUID_REGEX =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const PREVIEW_PAGE_SIZE = 50;

function statusColor(status: string): string {
  switch (status) {
    case "ready":
      return "bg-green-500";
    case "processing":
    case "uploading":
      return "bg-yellow-500";
    case "error":
      return "bg-red-500";
    default:
      return "bg-gray-400";
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case "ready":
      return "Ready";
    case "processing":
      return "Processing";
    case "uploading":
      return "Uploading";
    case "error":
      return "Error";
    default:
      return status;
  }
}

function formatFileSize(bytes: number): string {
  if (bytes >= 1_073_741_824) return `${(bytes / 1_073_741_824).toFixed(1)} GB`;
  if (bytes >= 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} MB`;
  if (bytes >= 1_024) return `${(bytes / 1_024).toFixed(1)} KB`;
  return `${bytes} B`;
}

function formatRowCount(count: number | null): string {
  if (count === null) return "--";
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`;
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}K`;
  return String(count);
}

function formatDate(dateString: string | null): string {
  if (!dateString) return "--";
  return new Date(dateString).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function DatasetDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [previewOffset, setPreviewOffset] = useState(0);
  const [sortBy, setSortBy] = useState<string | undefined>(undefined);
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");

  const isValidId = id && UUID_REGEX.test(id);

  const {
    data: dataset,
    isLoading,
    isError,
    error,
  } = useDatasetDetail(isValidId ? id : undefined);

  const {
    data: preview,
    isLoading: isPreviewLoading,
    isError: isPreviewError,
  } = useDatasetPreview(
    dataset?.status === "ready" ? id : undefined,
    { offset: previewOffset, limit: PREVIEW_PAGE_SIZE, sort_by: sortBy, sort_order: sortOrder },
  );

  const deleteMutation = useDeleteDataset();

  if (!id || !isValidId) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 p-6">
        <h1 className="text-2xl font-bold">Invalid Dataset ID</h1>
        <p className="text-muted-foreground">
          The dataset ID provided is not a valid identifier.
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
        <h1 className="text-2xl font-bold">Dataset Not Found</h1>
        <p className="text-muted-foreground">
          The dataset you are looking for does not exist or has been deleted.
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

  if (isError) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 p-6">
        <AlertCircle className="size-10 text-destructive" />
        <h1 className="text-2xl font-bold">Error Loading Dataset</h1>
        <p className="text-muted-foreground">
          {error instanceof Error ? error.message : "An unexpected error occurred."}
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

  if (!dataset) return null;

  function handleDelete() {
    setDeleteError(null);
    deleteMutation.mutate(id!, {
      onSuccess: () => {
        navigate("/");
      },
      onError: (err) => {
        setDeleteError(err instanceof Error ? err.message : "Failed to delete dataset.");
        setConfirmDelete(false);
      },
    });
  }

  function handleSort(column: string) {
    if (sortBy === column) {
      setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(column);
      setSortOrder("asc");
    }
    setPreviewOffset(0);
  }

  const totalPreviewPages = preview
    ? Math.ceil(preview.total_rows / PREVIEW_PAGE_SIZE)
    : 0;
  const currentPage = Math.floor(previewOffset / PREVIEW_PAGE_SIZE) + 1;

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
              Datasets
            </Link>
          </li>
          <li>
            <ChevronRight className="size-3.5" />
          </li>
          <li className="font-medium text-foreground">{dataset.name}</li>
        </ol>
      </nav>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <FileSpreadsheet className="size-8 text-muted-foreground" />
          <div>
            <h1 className="text-2xl font-bold">{dataset.name}</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {dataset.file_format.toUpperCase()} dataset
            </p>
          </div>
        </div>
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
          <CardTitle className="text-sm">Metadata</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3 lg:grid-cols-4" data-testid="metadata">
            <div>
              <dt className="text-muted-foreground">Status</dt>
              <dd className="mt-0.5 flex items-center gap-2 font-medium">
                <span
                  className={`inline-block size-2.5 rounded-full ${statusColor(dataset.status)}`}
                />
                {statusLabel(dataset.status)}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Format</dt>
              <dd className="mt-0.5 font-medium">{dataset.file_format.toUpperCase()}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">File Size</dt>
              <dd className="mt-0.5 font-medium">{formatFileSize(dataset.file_size_bytes)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Row Count</dt>
              <dd className="mt-0.5 font-medium">{formatRowCount(dataset.row_count)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Table Name</dt>
              <dd className="mt-0.5 font-mono text-xs">{dataset.duckdb_table_name}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Created</dt>
              <dd className="mt-0.5 font-medium">{formatDate(dataset.created_at)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Updated</dt>
              <dd className="mt-0.5 font-medium">{formatDate(dataset.updated_at)}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {/* Schema Table */}
      {dataset.schema && dataset.schema.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">
              Schema ({dataset.schema.length} columns)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="schema-table">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="pb-2 pr-4 font-medium">Column</th>
                    <th className="pb-2 pr-4 font-medium">Type</th>
                    <th className="pb-2 pr-4 font-medium">Nullable</th>
                    <th className="pb-2 font-medium">Primary Key</th>
                  </tr>
                </thead>
                <tbody>
                  {dataset.schema.map((col) => (
                    <tr key={col.column_name} className="border-b last:border-0">
                      <td className="py-2 pr-4 font-mono text-xs">{col.column_name}</td>
                      <td className="py-2 pr-4 text-muted-foreground">{col.data_type}</td>
                      <td className="py-2 pr-4">{col.is_nullable ? "Yes" : "No"}</td>
                      <td className="py-2">{col.is_primary_key ? "Yes" : "No"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Data Preview */}
      {dataset.status === "ready" && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">
                Data Preview
                {preview && (
                  <span className="ml-2 font-normal text-muted-foreground">
                    ({preview.total_rows.toLocaleString()} total rows)
                  </span>
                )}
              </CardTitle>
              {preview && totalPreviewPages > 1 && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">
                    Page {currentPage} of {totalPreviewPages}
                  </span>
                  <Button
                    variant="outline"
                    size="icon-xs"
                    onClick={() => setPreviewOffset(Math.max(0, previewOffset - PREVIEW_PAGE_SIZE))}
                    disabled={previewOffset === 0}
                    data-testid="preview-prev"
                  >
                    <ChevronLeft className="size-3" />
                  </Button>
                  <Button
                    variant="outline"
                    size="icon-xs"
                    onClick={() => setPreviewOffset(previewOffset + PREVIEW_PAGE_SIZE)}
                    disabled={currentPage >= totalPreviewPages}
                    data-testid="preview-next"
                  >
                    <ChevronRightIcon className="size-3" />
                  </Button>
                </div>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {isPreviewLoading && (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="size-6 animate-spin text-muted-foreground" />
              </div>
            )}
            {isPreviewError && (
              <div className="flex items-center gap-2 py-4 text-sm text-destructive">
                <AlertCircle className="size-4" />
                Failed to load data preview.
              </div>
            )}
            {preview && (
              <div className="overflow-x-auto" data-testid="preview-table">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left">
                      {preview.columns.map((col) => (
                        <th key={col} className="pb-2 pr-4 font-medium">
                          <button
                            className="inline-flex items-center gap-1 hover:text-foreground"
                            onClick={() => handleSort(col)}
                          >
                            {col}
                            <ArrowUpDown className="size-3 text-muted-foreground" />
                          </button>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((row, rowIdx) => (
                      <tr key={rowIdx} className="border-b last:border-0">
                        {row.map((cell, cellIdx) => (
                          <td
                            key={cellIdx}
                            className="max-w-[200px] truncate py-1.5 pr-4 text-xs"
                            title={cell != null ? String(cell) : "null"}
                          >
                            {cell != null ? String(cell) : (
                              <span className="italic text-muted-foreground">null</span>
                            )}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
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
            <h2 className="text-lg font-semibold">Delete Dataset</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Are you sure you want to delete &quot;{dataset.name}&quot;? This
              action cannot be undone and will remove the file and all associated
              data.
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
