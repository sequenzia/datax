import { useState, useCallback, useRef } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  ChevronRight,
  Upload,
  Loader2,
  AlertCircle,
  FileUp,
  X,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useUploadDataset } from "@/hooks/use-datasets";

const ACCEPTED_EXTENSIONS = ".csv,.xlsx,.xls,.parquet,.json";
const ACCEPTED_FORMATS = ["CSV", "Excel (.xlsx, .xls)", "Parquet", "JSON"];

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DatasetUploadPage() {
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

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  }, []);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selected = e.target.files?.[0];
      if (selected) handleFile(selected);
    },
    [handleFile],
  );

  const handleUpload = useCallback(() => {
    if (!file) return;
    setError(null);
    const datasetName = name.trim() || undefined;
    uploadMutation.mutate(
      { file, name: datasetName },
      {
        onSuccess: (result) => {
          navigate(`/datasets/${result.id}`);
        },
        onError: (err) => {
          setError(
            err instanceof Error ? err.message : "Upload failed",
          );
        },
      },
    );
  }, [file, name, uploadMutation, navigate]);

  const clearFile = useCallback(() => {
    setFile(null);
    setError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, []);

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
            <Link to="/datasets" className="hover:text-foreground">
              Datasets
            </Link>
          </li>
          <li>
            <ChevronRight className="size-3.5" />
          </li>
          <li className="font-medium text-foreground">Upload Dataset</li>
        </ol>
      </nav>

      {/* Header */}
      <div className="flex items-center gap-3">
        <Upload className="size-8 text-muted-foreground" />
        <div>
          <h1 className="text-2xl font-bold">Upload Dataset</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Upload a file to create a new dataset for analysis.
          </p>
        </div>
      </div>

      {/* Upload Form */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">File</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Drop Zone */}
          <div
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onClick={() => fileInputRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-8 transition-colors ${
              dragOver
                ? "border-primary bg-primary/5"
                : "border-muted-foreground/25 hover:border-muted-foreground/50"
            }`}
            data-testid="drop-zone"
          >
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_EXTENSIONS}
              onChange={handleInputChange}
              className="hidden"
              data-testid="file-input"
            />
            {file ? (
              <div className="flex items-center gap-3">
                <FileUp className="size-6 text-primary" />
                <div className="text-sm">
                  <p className="font-medium">{file.name}</p>
                  <p className="text-muted-foreground">
                    {formatFileSize(file.size)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    clearFile();
                  }}
                  className="ml-2 rounded-full p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                  aria-label="Remove file"
                  data-testid="clear-file"
                >
                  <X className="size-4" />
                </button>
              </div>
            ) : (
              <>
                <FileUp className="size-8 text-muted-foreground" />
                <div className="text-center text-sm">
                  <p className="font-medium">
                    Drag and drop a file here, or click to select
                  </p>
                  <p className="mt-1 text-muted-foreground">
                    Accepted formats: {ACCEPTED_FORMATS.join(", ")}
                  </p>
                </div>
              </>
            )}
          </div>

          {/* Dataset Name */}
          <div>
            <label
              htmlFor="dataset-name"
              className="mb-1.5 block text-sm font-medium"
            >
              Dataset Name
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                (optional — defaults to filename)
              </span>
            </label>
            <input
              id="dataset-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={file?.name ?? "My Dataset"}
              className="h-9 w-full rounded-md border bg-background px-3 text-sm shadow-xs outline-none placeholder:text-muted-foreground focus:border-ring focus:ring-[3px] focus:ring-ring/50"
              data-testid="input-name"
            />
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <div
          className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3"
          data-testid="upload-error"
        >
          <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-3">
        <Button
          onClick={handleUpload}
          disabled={!file || uploadMutation.isPending}
          data-testid="upload-button"
        >
          {uploadMutation.isPending ? (
            <Loader2 className="animate-spin" />
          ) : (
            <Upload />
          )}
          Upload
        </Button>
        <Button variant="outline" asChild>
          <Link to="/datasets">Cancel</Link>
        </Button>
      </div>
    </div>
  );
}
