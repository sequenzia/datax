import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import {
  FileSpreadsheet,
  AlertCircle,
  Plus,
  Search,
  ArrowUpDown,
  Trash2,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useDatasetList, useDeleteDataset } from "@/hooks/use-datasets";
import type { Dataset } from "@/types/api";

const PAGE_SIZE = 20;

type SortField = "name" | "created_at" | "file_size_bytes" | "row_count";
type SortOrder = "asc" | "desc";
type StatusFilter = "all" | "ready" | "processing" | "uploading" | "error";

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
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M rows`;
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}K rows`;
  return `${count} rows`;
}

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function DatasetRow({
  dataset,
  selected,
  onSelect,
}: {
  dataset: Dataset;
  selected: boolean;
  onSelect: (id: string, checked: boolean) => void;
}) {
  return (
    <tr className="border-b last:border-0 hover:bg-accent/50" data-testid="dataset-row">
      <td className="py-3 pl-4 pr-2">
        <input
          type="checkbox"
          checked={selected}
          onChange={(e) => onSelect(dataset.id, e.target.checked)}
          aria-label={`Select ${dataset.name}`}
        />
      </td>
      <td className="py-3 pr-4">
        <Link
          to={`/datasets/${dataset.id}`}
          className="font-medium text-primary hover:underline"
        >
          {dataset.name}
        </Link>
      </td>
      <td className="py-3 pr-4 text-muted-foreground">
        {dataset.file_format.toUpperCase()}
      </td>
      <td className="py-3 pr-4 text-muted-foreground">
        {formatFileSize(dataset.file_size_bytes)}
      </td>
      <td className="py-3 pr-4 text-muted-foreground">
        {formatRowCount(dataset.row_count)}
      </td>
      <td className="py-3 pr-4">
        <span className="inline-flex items-center gap-1.5">
          <span
            className={`inline-block size-2 rounded-full ${statusColor(dataset.status)}`}
          />
          <span className="text-sm">{statusLabel(dataset.status)}</span>
        </span>
      </td>
      <td className="py-3 pr-4 text-muted-foreground">
        {formatDate(dataset.created_at)}
      </td>
    </tr>
  );
}

export function DatasetsPage() {
  const { data: datasets, isLoading, isError, refetch } = useDatasetList();
  const deleteMutation = useDeleteDataset();

  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sortField, setSortField] = useState<SortField>("created_at");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [page, setPage] = useState(0);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const filtered = useMemo(() => {
    if (!datasets) return [];
    let result = [...datasets];

    // Search
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (d) =>
          d.name.toLowerCase().includes(q) ||
          d.file_format.toLowerCase().includes(q),
      );
    }

    // Status filter
    if (statusFilter !== "all") {
      result = result.filter((d) => d.status === statusFilter);
    }

    // Sort
    result.sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case "name":
          cmp = a.name.localeCompare(b.name);
          break;
        case "created_at":
          cmp = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
          break;
        case "file_size_bytes":
          cmp = a.file_size_bytes - b.file_size_bytes;
          break;
        case "row_count":
          cmp = (a.row_count ?? 0) - (b.row_count ?? 0);
          break;
      }
      return sortOrder === "asc" ? cmp : -cmp;
    });

    return result;
  }, [datasets, searchQuery, statusFilter, sortField, sortOrder]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  function handleSort(field: SortField) {
    if (sortField === field) {
      setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortOrder("asc");
    }
    setPage(0);
  }

  function handleSelectAll(checked: boolean) {
    if (checked) {
      setSelectedIds(new Set(paginated.map((d) => d.id)));
    } else {
      setSelectedIds(new Set());
    }
  }

  function handleSelect(id: string, checked: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  function handleBulkDelete() {
    setDeleteError(null);
    const ids = Array.from(selectedIds);
    let completed = 0;
    let failed = false;
    for (const id of ids) {
      deleteMutation.mutate(id, {
        onSuccess: () => {
          completed++;
          if (completed === ids.length && !failed) {
            setSelectedIds(new Set());
          }
        },
        onError: (err) => {
          failed = true;
          setDeleteError(err instanceof Error ? err.message : "Failed to delete some datasets.");
        },
      });
    }
  }

  const SortButton = ({ field, children }: { field: SortField; children: React.ReactNode }) => (
    <button
      className="inline-flex items-center gap-1 font-medium hover:text-foreground"
      onClick={() => handleSort(field)}
    >
      {children}
      <ArrowUpDown className="size-3 text-muted-foreground" />
    </button>
  );

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Datasets</h1>
          <p className="mt-1 text-muted-foreground">
            Manage your uploaded datasets.
          </p>
        </div>
        <Button asChild>
          <Link to="/datasets/upload">
            <Plus />
            Upload Dataset
          </Link>
        </Button>
      </div>

      {/* Search + Filter bar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 sm:max-w-xs">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search datasets..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(0);
            }}
            className="h-9 w-full rounded-md border bg-background pl-8 pr-3 text-sm outline-none focus:ring-2 focus:ring-ring"
            data-testid="search-input"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value as StatusFilter);
            setPage(0);
          }}
          className="h-9 rounded-md border bg-background px-3 text-sm"
          data-testid="status-filter"
        >
          <option value="all">All Statuses</option>
          <option value="ready">Ready</option>
          <option value="processing">Processing</option>
          <option value="uploading">Uploading</option>
          <option value="error">Error</option>
        </select>

        {selectedIds.size > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleBulkDelete}
            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
            data-testid="bulk-delete-button"
          >
            <Trash2 />
            Delete ({selectedIds.size})
          </Button>
        )}
      </div>

      {/* Delete error */}
      {deleteError && (
        <div className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3" data-testid="delete-error">
          <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
          <p className="text-sm text-destructive">{deleteError}</p>
        </div>
      )}

      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div
              key={i}
              className="h-12 animate-pulse rounded-lg border bg-muted/50"
            />
          ))}
        </div>
      )}

      {isError && (
        <div className="flex items-center gap-3 rounded-lg border border-destructive/50 bg-destructive/10 p-4">
          <AlertCircle className="size-5 shrink-0 text-destructive" />
          <p className="text-sm text-destructive">Failed to load datasets.</p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void refetch()}
          >
            Retry
          </Button>
        </div>
      )}

      {datasets && datasets.length === 0 && (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center gap-3 py-12">
            <FileSpreadsheet className="size-12 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              No datasets uploaded yet.
            </p>
            <Button variant="outline" size="sm" asChild>
              <Link to="/datasets/upload">Upload Dataset</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {filtered.length > 0 && (
        <>
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm" data-testid="datasets-table">
              <thead>
                <tr className="border-b bg-muted/50 text-left text-muted-foreground">
                  <th className="py-2.5 pl-4 pr-2">
                    <input
                      type="checkbox"
                      checked={
                        paginated.length > 0 &&
                        paginated.every((d) => selectedIds.has(d.id))
                      }
                      onChange={(e) => handleSelectAll(e.target.checked)}
                      aria-label="Select all"
                    />
                  </th>
                  <th className="py-2.5 pr-4">
                    <SortButton field="name">Name</SortButton>
                  </th>
                  <th className="py-2.5 pr-4 font-medium">Format</th>
                  <th className="py-2.5 pr-4">
                    <SortButton field="file_size_bytes">Size</SortButton>
                  </th>
                  <th className="py-2.5 pr-4">
                    <SortButton field="row_count">Rows</SortButton>
                  </th>
                  <th className="py-2.5 pr-4 font-medium">Status</th>
                  <th className="py-2.5 pr-4">
                    <SortButton field="created_at">Created</SortButton>
                  </th>
                </tr>
              </thead>
              <tbody>
                {paginated.map((dataset) => (
                  <DatasetRow
                    key={dataset.id}
                    dataset={dataset}
                    selected={selectedIds.has(dataset.id)}
                    onSelect={handleSelect}
                  />
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between" data-testid="pagination">
              <span className="text-sm text-muted-foreground">
                Showing {page * PAGE_SIZE + 1}-{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of{" "}
                {filtered.length} datasets
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  data-testid="page-prev"
                >
                  <ChevronLeft />
                  Previous
                </Button>
                <span className="text-sm">
                  Page {page + 1} of {totalPages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                  data-testid="page-next"
                >
                  Next
                  <ChevronRight />
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      {datasets && datasets.length > 0 && filtered.length === 0 && (
        <div className="flex flex-col items-center gap-2 py-12 text-muted-foreground">
          <Search className="size-8" />
          <p className="text-sm">No datasets match your search criteria.</p>
        </div>
      )}
    </div>
  );
}
