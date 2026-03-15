import { useState, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { Compass, ChevronDown } from "lucide-react";
import { DataExplorer } from "@/components/generative-ui";
import { useDatasetList } from "@/hooks/use-datasets";
import { Button } from "@/components/ui/button";

export function ExplorePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const datasetIdParam = searchParams.get("dataset");

  const { data: datasets, isLoading: loadingDatasets } = useDatasetList();

  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(
    datasetIdParam,
  );
  const [dropdownOpen, setDropdownOpen] = useState(false);

  // Resolve the selected dataset name
  const selectedDataset = useMemo(
    () => datasets?.find((d) => d.id === selectedDatasetId) ?? null,
    [datasets, selectedDatasetId],
  );

  function handleSelectDataset(id: string) {
    setSelectedDatasetId(id);
    setDropdownOpen(false);
    setSearchParams({ dataset: id });
  }

  return (
    <div className="flex h-full flex-col">
      {/* Page header with dataset selector */}
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div className="flex items-center gap-3">
          <Compass className="size-5 text-primary" />
          <div>
            <h1 className="text-lg font-semibold">Data Explorer</h1>
            <p className="text-xs text-muted-foreground">
              Browse columns, view distributions, and apply quick filters
            </p>
          </div>
        </div>

        {/* Dataset selector */}
        <div className="relative">
          <Button
            variant="outline"
            onClick={() => setDropdownOpen((prev) => !prev)}
            disabled={loadingDatasets}
            className="min-w-[200px] justify-between"
          >
            {selectedDataset?.name ?? "Select a dataset"}
            <ChevronDown className="size-4" />
          </Button>

          {dropdownOpen && datasets && datasets.length > 0 && (
            <div className="absolute right-0 z-50 mt-1 max-h-64 w-64 overflow-y-auto rounded-md border bg-popover p-1 shadow-md">
              {datasets
                .filter((d) => d.status === "ready")
                .map((dataset) => (
                  <button
                    key={dataset.id}
                    onClick={() => handleSelectDataset(dataset.id)}
                    className="flex w-full items-center gap-2 rounded-sm px-3 py-2 text-sm hover:bg-accent"
                  >
                    <span className="truncate">{dataset.name}</span>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {dataset.file_format.toUpperCase()}
                    </span>
                  </button>
                ))}
            </div>
          )}
        </div>
      </div>

      {/* Explorer content */}
      <div className="min-h-0 flex-1 p-4">
        {selectedDatasetId ? (
          <DataExplorer
            datasetId={selectedDatasetId}
            datasetName={selectedDataset?.name}
            fullScreen
            className="h-full"
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-muted-foreground">
            <Compass className="size-12 opacity-30" />
            <p className="text-sm">Select a dataset to start exploring</p>
          </div>
        )}
      </div>
    </div>
  );
}
