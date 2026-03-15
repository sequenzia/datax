import { useState, useMemo, useCallback, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  FileSpreadsheet,
  Database,
  AlertCircle,
  Plus,
  Upload,
  Search,
  ArrowUpDown,
  Trash2,
  ChevronLeft,
  ChevronRight,
  TestTube2,
  RefreshCw,
  Pencil,
  Loader2,
  X,
  FileUp,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useDatasetList, useDeleteDataset, useUploadDataset } from "@/hooks/use-datasets";
import {
  useConnectionList,
  useTestConnection,
  useRefreshConnectionSchema,
  useDeleteConnection,
} from "@/hooks/use-connections";
import type { Connection } from "@/types/api";

// ─── Shared Utilities ──────────────────────────

const PAGE_SIZE = 20;

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
  return `${count}`;
}

function formatDate(dateString: string | null): string {
  if (!dateString) return "Never";
  return new Date(dateString).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function statusColor(status: string): string {
  switch (status) {
    case "ready":
    case "connected":
      return "bg-green-500";
    case "processing":
    case "uploading":
      return "bg-yellow-500";
    case "error":
    case "disconnected":
      return "bg-red-500";
    default:
      return "bg-gray-400";
  }
}

function statusLabel(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

// ─── Upload Dialog ──────────────────────────────

const ACCEPTED_EXTENSIONS = ".csv,.xlsx,.xls,.parquet,.json";

function UploadDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const navigate = useNavigate();
  const uploadMutation = useUploadDataset();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = useCallback((selected: File) => {
    setFile(selected);
    setError(null);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const dropped = e.dataTransfer.files[0];
      if (dropped) handleFile(dropped);
    },
    [handleFile],
  );

  const handleUpload = useCallback(() => {
    if (!file) return;
    setError(null);
    uploadMutation.mutate(
      { file, name: name.trim() || undefined },
      {
        onSuccess: (result) => {
          onOpenChange(false);
          setFile(null);
          setName("");
          navigate(`/data/dataset/${result.id}`);
        },
        onError: (err) => {
          setError(err instanceof Error ? err.message : "Upload failed");
        },
      },
    );
  }, [file, name, uploadMutation, navigate, onOpenChange]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Upload Dataset</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          {/* Drop Zone */}
          <div
            onDrop={handleDrop}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={(e) => {
              e.preventDefault();
              setDragOver(false);
            }}
            onClick={() => fileInputRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-6 transition-colors ${
              dragOver
                ? "border-primary bg-primary/5"
                : "border-muted-foreground/25 hover:border-muted-foreground/50"
            }`}
            data-testid="upload-drop-zone"
          >
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_EXTENSIONS}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleFile(f);
              }}
              className="hidden"
            />
            {file ? (
              <div className="flex items-center gap-3">
                <FileUp className="size-5 text-primary" />
                <div className="text-sm">
                  <p className="font-medium">{file.name}</p>
                  <p className="text-muted-foreground">{formatFileSize(file.size)}</p>
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setFile(null);
                    if (fileInputRef.current) fileInputRef.current.value = "";
                  }}
                  className="rounded-full p-1 text-muted-foreground hover:bg-muted"
                >
                  <X className="size-4" />
                </button>
              </div>
            ) : (
              <>
                <FileUp className="size-8 text-muted-foreground" />
                <p className="text-center text-sm">
                  <span className="font-medium">Drag & drop</span> or click to select
                </p>
                <p className="text-xs text-muted-foreground">CSV, Excel, Parquet, JSON</p>
              </>
            )}
          </div>

          <div>
            <label htmlFor="upload-name" className="mb-1.5 block text-sm font-medium">
              Name <span className="text-xs font-normal text-muted-foreground">(optional)</span>
            </label>
            <input
              id="upload-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={file?.name ?? "My Dataset"}
              className="h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          {error && (
            <div className="flex items-center gap-2 rounded-md bg-destructive/10 p-2">
              <AlertCircle className="size-4 text-destructive" />
              <span className="text-sm text-destructive">{error}</span>
            </div>
          )}

          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button onClick={handleUpload} disabled={!file || uploadMutation.isPending}>
              {uploadMutation.isPending ? (
                <Loader2 className="animate-spin" />
              ) : (
                <Upload />
              )}
              Upload
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Datasets Tab ──────────────────────────────

type SortField = "name" | "created_at" | "file_size_bytes" | "row_count";
type SortOrder = "asc" | "desc";

function SortButton({
  field,
  children,
  onSort,
}: {
  field: SortField;
  children: React.ReactNode;
  onSort: (field: SortField) => void;
}) {
  return (
    <button
      className="inline-flex items-center gap-1 font-medium hover:text-foreground"
      onClick={() => onSort(field)}
    >
      {children}
      <ArrowUpDown className="size-3 text-muted-foreground" />
    </button>
  );
}

function DatasetsTab({ onUpload }: { onUpload: () => void }) {
  const { data: datasets, isLoading, isError, refetch } = useDatasetList();
  const deleteMutation = useDeleteDataset();

  const [searchQuery, setSearchQuery] = useState("");
  const [sortField, setSortField] = useState<SortField>("created_at");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [page, setPage] = useState(0);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const filtered = useMemo(() => {
    if (!datasets) return [];
    let result = [...datasets];
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (d) => d.name.toLowerCase().includes(q) || d.file_format.toLowerCase().includes(q),
      );
    }
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
  }, [datasets, searchQuery, sortField, sortOrder]);

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

  function handleBulkDelete() {
    for (const id of selectedIds) {
      deleteMutation.mutate(id);
    }
    setSelectedIds(new Set());
  }

  if (isLoading) {
    return (
      <div className="space-y-3 pt-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-12 animate-pulse rounded-lg border bg-muted/50" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-destructive/50 bg-destructive/10 p-4">
        <AlertCircle className="size-5 shrink-0 text-destructive" />
        <p className="text-sm text-destructive">Failed to load datasets.</p>
        <Button variant="outline" size="sm" onClick={() => void refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  if (datasets && datasets.length === 0) {
    return (
      <Card className="mt-4 border-dashed">
        <CardContent className="flex flex-col items-center gap-3 py-12">
          <FileSpreadsheet className="size-12 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">No datasets uploaded yet.</p>
          <Button variant="outline" size="sm" onClick={onUpload}>
            Upload Dataset
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4 pt-4">
      {/* Search + bulk actions */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-xs">
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
          />
        </div>
        {selectedIds.size > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleBulkDelete}
            className="text-destructive"
          >
            <Trash2 />
            Delete ({selectedIds.size})
          </Button>
        )}
      </div>

      {filtered.length > 0 && (
        <>
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50 text-left text-muted-foreground">
                  <th className="py-2.5 pl-4 pr-2">
                    <input
                      type="checkbox"
                      checked={paginated.length > 0 && paginated.every((d) => selectedIds.has(d.id))}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedIds(new Set(paginated.map((d) => d.id)));
                        } else {
                          setSelectedIds(new Set());
                        }
                      }}
                    />
                  </th>
                  <th className="py-2.5 pr-4"><SortButton field="name" onSort={handleSort}>Name</SortButton></th>
                  <th className="py-2.5 pr-4 font-medium">Format</th>
                  <th className="py-2.5 pr-4"><SortButton field="file_size_bytes" onSort={handleSort}>Size</SortButton></th>
                  <th className="py-2.5 pr-4"><SortButton field="row_count" onSort={handleSort}>Rows</SortButton></th>
                  <th className="py-2.5 pr-4 font-medium">Status</th>
                  <th className="py-2.5 pr-4"><SortButton field="created_at" onSort={handleSort}>Created</SortButton></th>
                </tr>
              </thead>
              <tbody>
                {paginated.map((dataset) => (
                  <tr key={dataset.id} className="border-b last:border-0 hover:bg-accent/50">
                    <td className="py-3 pl-4 pr-2">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(dataset.id)}
                        onChange={(e) => {
                          setSelectedIds((prev) => {
                            const next = new Set(prev);
                            if (e.target.checked) next.add(dataset.id);
                            else next.delete(dataset.id);
                            return next;
                          });
                        }}
                      />
                    </td>
                    <td className="py-3 pr-4">
                      <Link to={`/data/dataset/${dataset.id}`} className="font-medium text-primary hover:underline">
                        {dataset.name}
                      </Link>
                    </td>
                    <td className="py-3 pr-4 text-muted-foreground">{dataset.file_format.toUpperCase()}</td>
                    <td className="py-3 pr-4 text-muted-foreground">{formatFileSize(dataset.file_size_bytes)}</td>
                    <td className="py-3 pr-4 text-muted-foreground">{formatRowCount(dataset.row_count)}</td>
                    <td className="py-3 pr-4">
                      <span className="inline-flex items-center gap-1.5">
                        <span className={`inline-block size-2 rounded-full ${statusColor(dataset.status)}`} />
                        <span className="text-sm">{statusLabel(dataset.status)}</span>
                      </span>
                    </td>
                    <td className="py-3 pr-4 text-muted-foreground">{formatDate(dataset.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">
                {page * PAGE_SIZE + 1}-{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of {filtered.length}
              </span>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => setPage((p) => p - 1)} disabled={page === 0}>
                  <ChevronLeft /> Previous
                </Button>
                <Button variant="outline" size="sm" onClick={() => setPage((p) => p + 1)} disabled={page >= totalPages - 1}>
                  Next <ChevronRight />
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      {datasets && datasets.length > 0 && filtered.length === 0 && (
        <div className="flex flex-col items-center gap-2 py-12 text-muted-foreground">
          <Search className="size-8" />
          <p className="text-sm">No datasets match your search.</p>
        </div>
      )}
    </div>
  );
}

// ─── Connections Tab ──────────────────────────────

function ConnectionCard({
  connection,
  onTest,
  onRefreshSchema,
  onDelete,
  isBusy,
}: {
  connection: Connection;
  onTest: (id: string) => void;
  onRefreshSchema: (id: string) => void;
  onDelete: (id: string) => void;
  isBusy: boolean;
}) {
  return (
    <Card data-testid="connection-card">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">{connection.name}</CardTitle>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">{statusLabel(connection.status)}</span>
            <span className={`inline-block size-2.5 rounded-full ${statusColor(connection.status)}`} />
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
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="xs" onClick={() => onTest(connection.id)} disabled={isBusy}>
            <TestTube2 /> Test
          </Button>
          <Button variant="outline" size="xs" onClick={() => onRefreshSchema(connection.id)} disabled={isBusy}>
            <RefreshCw /> Refresh
          </Button>
          <Button variant="outline" size="xs" asChild disabled={isBusy}>
            <Link to={`/data/connection/${connection.id}/edit`}>
              <Pencil /> Edit
            </Link>
          </Button>
          <Button
            variant="outline"
            size="xs"
            onClick={() => onDelete(connection.id)}
            disabled={isBusy}
            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
          >
            <Trash2 /> Delete
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ConnectionsTab({ onAddConnection }: { onAddConnection: () => void }) {
  const { data: connections, isLoading, isError, refetch } = useConnectionList();
  const testMutation = useTestConnection();
  const refreshMutation = useRefreshConnectionSchema();
  const deleteMutation = useDeleteConnection();

  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  function handleTest(id: string) {
    setBusyId(id);
    testMutation.mutate(id, { onSettled: () => setBusyId(null) });
  }

  function handleRefresh(id: string) {
    setBusyId(id);
    refreshMutation.mutate(id, { onSettled: () => setBusyId(null) });
  }

  function handleDelete(id: string) {
    setConfirmDeleteId(id);
  }

  function handleDeleteConfirm() {
    if (!confirmDeleteId) return;
    setBusyId(confirmDeleteId);
    setConfirmDeleteId(null);
    deleteMutation.mutate(confirmDeleteId, { onSettled: () => setBusyId(null) });
  }

  if (isLoading) {
    return (
      <div className="grid gap-4 pt-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-44 animate-pulse rounded-xl border bg-muted/50" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-destructive/50 bg-destructive/10 p-4">
        <AlertCircle className="size-5 shrink-0 text-destructive" />
        <p className="text-sm text-destructive">Failed to load connections.</p>
        <Button variant="outline" size="sm" onClick={() => void refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  if (connections && connections.length === 0) {
    return (
      <Card className="mt-4 border-dashed">
        <CardContent className="flex flex-col items-center gap-3 py-12">
          <Database className="size-12 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">No database connections configured.</p>
          <Button variant="outline" size="sm" onClick={onAddConnection}>
            Add Connection
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <div className="grid gap-4 pt-4 sm:grid-cols-2 lg:grid-cols-3">
        {connections?.map((connection) => (
          <ConnectionCard
            key={connection.id}
            connection={connection}
            onTest={handleTest}
            onRefreshSchema={handleRefresh}
            onDelete={handleDelete}
            isBusy={busyId === connection.id}
          />
        ))}
      </div>

      {confirmDeleteId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="mx-4 w-full max-w-sm rounded-lg border bg-background p-6 shadow-lg">
            <h2 className="text-lg font-semibold">Delete Connection</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Are you sure? This action cannot be undone.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setConfirmDeleteId(null)}>
                Cancel
              </Button>
              <Button variant="destructive" size="sm" onClick={handleDeleteConfirm}>
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ─── Data Page ──────────────────────────────────

export function DataPage() {
  const [uploadOpen, setUploadOpen] = useState(false);
  const { data: datasets } = useDatasetList();
  const { data: connections } = useConnectionList();

  const datasetCount = datasets?.length ?? 0;
  const connectionCount = connections?.length ?? 0;

  return (
    <div className="h-full overflow-y-auto">
      <div className="space-y-6 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Data Sources</h1>
            <p className="mt-1 text-muted-foreground">
              Manage your datasets and database connections.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => setUploadOpen(true)}>
              <Upload /> Upload
            </Button>
            <Button asChild>
              <Link to="/data/connection/new">
                <Plus /> Connect
              </Link>
            </Button>
          </div>
        </div>

        <Tabs defaultValue="datasets">
          <TabsList>
            <TabsTrigger value="datasets">
              Datasets {datasetCount > 0 && `(${datasetCount})`}
            </TabsTrigger>
            <TabsTrigger value="connections">
              Connections {connectionCount > 0 && `(${connectionCount})`}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="datasets">
            <DatasetsTab onUpload={() => setUploadOpen(true)} />
          </TabsContent>
          <TabsContent value="connections">
            <ConnectionsTab onAddConnection={() => void 0} />
          </TabsContent>
        </Tabs>
      </div>

      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
    </div>
  );
}
