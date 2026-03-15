import { Database, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import type { Dataset, Connection, DataSource } from "@/types/api";

interface DatasourceSelectorProps {
  datasets: Dataset[];
  connections: Connection[];
  selectedSources: DataSource[];
  onToggle: (source: DataSource) => void;
  onClear: () => void;
  disabled?: boolean;
}

function isSelected(source: DataSource, selectedSources: DataSource[]): boolean {
  return selectedSources.some((s) => s.id === source.id && s.type === source.type);
}

export function DatasourceSelector({
  datasets,
  connections,
  selectedSources,
  onToggle,
  onClear,
  disabled = false,
}: DatasourceSelectorProps) {
  const readyDatasets = datasets.filter((d) => d.status === "ready");
  const hasAnySources = readyDatasets.length > 0 || connections.length > 0;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          disabled={disabled}
          className="shrink-0"
          aria-label="Select data sources"
          data-testid="datasource-selector-trigger"
        >
          <Database className="size-4" />
          {selectedSources.length > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex size-4 items-center justify-center rounded-full bg-primary text-[10px] text-primary-foreground">
              {selectedSources.length}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent
        side="top"
        align="start"
        className="w-72 p-0"
        data-testid="datasource-selector-popover"
      >
        <div className="flex items-center justify-between px-3 py-2">
          <h4 className="text-sm font-medium">Select Data Sources</h4>
          {selectedSources.length > 0 && (
            <Button
              variant="ghost"
              size="xs"
              onClick={onClear}
              className="h-auto px-1.5 py-0.5 text-xs text-muted-foreground"
            >
              Clear all
            </Button>
          )}
        </div>
        <Separator />
        {!hasAnySources ? (
          <div className="p-4 text-center text-sm text-muted-foreground">
            <p>No data sources available.</p>
            <p className="mt-1 text-xs">Upload a file or connect a database to get started.</p>
          </div>
        ) : (
          <ScrollArea className="max-h-64">
            <div className="p-2">
              {readyDatasets.length > 0 && (
                <>
                  <p className="mb-1 px-1 text-xs font-medium text-muted-foreground">Datasets</p>
                  {readyDatasets.map((ds) => {
                    const source: DataSource = { id: ds.id, name: ds.name, type: "dataset" };
                    const checked = isSelected(source, selectedSources);
                    return (
                      <label
                        key={ds.id}
                        className="flex cursor-pointer items-center gap-2 rounded-md px-1 py-1.5 hover:bg-accent"
                      >
                        <Checkbox
                          checked={checked}
                          onCheckedChange={() => onToggle(source)}
                          aria-label={`Select ${ds.name}`}
                        />
                        <span className="flex-1 truncate text-sm">{ds.name}</span>
                        <Badge variant="outline" className="text-[10px] px-1 py-0">
                          {ds.file_format}
                        </Badge>
                        {ds.row_count != null && (
                          <span className="text-[10px] text-muted-foreground">
                            {ds.row_count.toLocaleString()} rows
                          </span>
                        )}
                      </label>
                    );
                  })}
                </>
              )}
              {readyDatasets.length > 0 && connections.length > 0 && (
                <Separator className="my-1" />
              )}
              {connections.length > 0 && (
                <>
                  <p className="mb-1 px-1 text-xs font-medium text-muted-foreground">Connections</p>
                  {connections.map((conn) => {
                    const source: DataSource = { id: conn.id, name: conn.name, type: "connection" };
                    const checked = isSelected(source, selectedSources);
                    return (
                      <label
                        key={conn.id}
                        className="flex cursor-pointer items-center gap-2 rounded-md px-1 py-1.5 hover:bg-accent"
                      >
                        <Checkbox
                          checked={checked}
                          onCheckedChange={() => onToggle(source)}
                          aria-label={`Select ${conn.name}`}
                        />
                        <span className="flex-1 truncate text-sm">{conn.name}</span>
                        <Badge variant="outline" className="text-[10px] px-1 py-0">
                          {conn.db_type}
                        </Badge>
                      </label>
                    );
                  })}
                </>
              )}
            </div>
          </ScrollArea>
        )}
        <Separator />
        <div className="px-3 py-1.5 text-xs text-muted-foreground">
          {selectedSources.length > 0
            ? `${selectedSources.length} source${selectedSources.length > 1 ? "s" : ""} selected`
            : "All sources (auto-detect)"}
        </div>
      </PopoverContent>
    </Popover>
  );
}

interface SelectedSourceChipsProps {
  selectedSources: DataSource[];
  onRemove: (source: DataSource) => void;
}

export function SelectedSourceChips({ selectedSources, onRemove }: SelectedSourceChipsProps) {
  if (selectedSources.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap gap-1 px-3 pb-1" data-testid="selected-source-chips">
      {selectedSources.map((source) => (
        <Badge
          key={`${source.type}-${source.id}`}
          variant="secondary"
          className="gap-1 pl-2 pr-1 text-xs"
        >
          {source.name}
          <button
            onClick={() => onRemove(source)}
            className="rounded-full p-0.5 hover:bg-muted-foreground/20"
            aria-label={`Remove ${source.name}`}
          >
            <X className="size-3" />
          </button>
        </Badge>
      ))}
    </div>
  );
}
