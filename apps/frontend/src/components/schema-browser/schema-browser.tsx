/** Tree-view schema browser: Source -> Table -> Column.
 *
 * Displays all data sources (datasets and connections) with their tables
 * and columns in an expandable/collapsible tree view. Supports search
 * filtering, shows column types and constraints (PK, FK, nullable),
 * and uses distinct icons per source type.
 */

import { useState, useMemo, useCallback } from "react";
import {
  ChevronRight,
  ChevronDown,
  Database,
  FileSpreadsheet,
  Table2,
  Columns3,
  Search,
  X,
  Key,
  Link2,
  AlertCircle,
  Loader2,
  Copy,
  Check,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useSchema } from "@/hooks/use-schema";
import type { SchemaSource, SchemaTable, SchemaColumnEntry } from "@/types/api";

/** Tracks which tree nodes are expanded by a composite key. */
type ExpandedState = Record<string, boolean>;

function buildNodeKey(sourceId: string, tableName?: string): string {
  return tableName ? `${sourceId}::${tableName}` : sourceId;
}

function matchesSearch(text: string, query: string): boolean {
  return text.toLowerCase().includes(query.toLowerCase());
}

/** Filter sources, tables, and columns that match the search query. */
function filterSources(
  sources: SchemaSource[],
  query: string,
): SchemaSource[] {
  if (!query.trim()) return sources;

  return sources
    .map((source) => {
      const sourceMatch = matchesSearch(source.source_name, query);

      const filteredTables = source.tables
        .map((table) => {
          const tableMatch = matchesSearch(table.table_name, query);
          const filteredColumns = table.columns.filter(
            (col) =>
              matchesSearch(col.name, query) || matchesSearch(col.type, query),
          );

          if (sourceMatch || tableMatch || filteredColumns.length > 0) {
            return {
              ...table,
              columns:
                sourceMatch || tableMatch ? table.columns : filteredColumns,
            };
          }
          return null;
        })
        .filter((t): t is SchemaTable => t !== null);

      if (sourceMatch || filteredTables.length > 0) {
        return {
          ...source,
          tables: sourceMatch ? source.tables : filteredTables,
        };
      }
      return null;
    })
    .filter((s): s is SchemaSource => s !== null);
}

function SourceIcon({
  sourceType,
  className,
}: {
  sourceType: string;
  className?: string;
}) {
  if (sourceType === "dataset") {
    return (
      <FileSpreadsheet
        className={cn("size-4 shrink-0 text-blue-500", className)}
        data-testid="icon-dataset"
      />
    );
  }
  return (
    <Database
      className={cn("size-4 shrink-0 text-green-500", className)}
      data-testid="icon-connection"
    />
  );
}

function ColumnBadge({
  label,
  variant,
}: {
  label: string;
  variant: "pk" | "fk" | "nullable";
}) {
  const styles = {
    pk: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
    fk: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400",
    nullable:
      "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 rounded px-1 py-0.5 text-[10px] font-medium leading-none",
        styles[variant],
      )}
      data-testid={`badge-${variant}`}
    >
      {variant === "pk" && <Key className="size-2.5" />}
      {variant === "fk" && <Link2 className="size-2.5" />}
      {label}
    </span>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      void navigator.clipboard.writeText(text).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      });
    },
    [text],
  );
  return (
    <button
      onClick={handleCopy}
      className="invisible shrink-0 rounded p-0.5 text-muted-foreground hover:text-foreground group-hover:visible"
      aria-label={`Copy ${text}`}
      data-testid={`copy-${text}`}
    >
      {copied ? <Check className="size-2.5 text-green-500" /> : <Copy className="size-2.5" />}
    </button>
  );
}

function ColumnRow({ column }: { column: SchemaColumnEntry }) {
  return (
    <div
      className="group flex items-center gap-2 rounded-sm px-2 py-1 text-sm hover:bg-accent/50"
      data-testid={`column-${column.name}`}
    >
      <Columns3 className="size-3.5 shrink-0 text-muted-foreground" />
      <span className="truncate font-mono text-xs">{column.name}</span>
      <span className="shrink-0 text-[11px] text-muted-foreground">
        {column.type}
      </span>
      <CopyButton text={column.name} />
      <div className="ml-auto flex items-center gap-1">
        {column.is_primary_key && <ColumnBadge label="PK" variant="pk" />}
        {column.foreign_key_ref && (
          <ColumnBadge label="FK" variant="fk" />
        )}
        {column.nullable && !column.is_primary_key && (
          <ColumnBadge label="NULL" variant="nullable" />
        )}
      </div>
    </div>
  );
}

function TableNode({
  table,
  sourceId,
  expanded,
  onToggle,
}: {
  table: SchemaTable;
  sourceId: string;
  expanded: boolean;
  onToggle: (key: string) => void;
}) {
  const nodeKey = buildNodeKey(sourceId, table.table_name);

  return (
    <div data-testid={`table-${table.table_name}`}>
      <button
        className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-accent/50"
        onClick={() => onToggle(nodeKey)}
        aria-expanded={expanded}
        data-testid={`table-toggle-${table.table_name}`}
      >
        {expanded ? (
          <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />
        )}
        <Table2 className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="truncate font-medium">{table.table_name}</span>
        <span className="ml-auto text-xs text-muted-foreground">
          {table.columns.length} col{table.columns.length !== 1 ? "s" : ""}
        </span>
      </button>
      {expanded && (
        <div className="ml-6 border-l border-border pl-2">
          {table.columns.map((col) => (
            <ColumnRow key={col.name} column={col} />
          ))}
        </div>
      )}
    </div>
  );
}

function SourceNode({
  source,
  expanded,
  expandedTables,
  onToggleSource,
  onToggleTable,
}: {
  source: SchemaSource;
  expanded: boolean;
  expandedTables: ExpandedState;
  onToggleSource: (key: string) => void;
  onToggleTable: (key: string) => void;
}) {
  const nodeKey = buildNodeKey(source.source_id);

  return (
    <div data-testid={`source-${source.source_id}`}>
      <button
        className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm font-semibold hover:bg-accent/50"
        onClick={() => onToggleSource(nodeKey)}
        aria-expanded={expanded}
        data-testid={`source-toggle-${source.source_id}`}
      >
        {expanded ? (
          <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
        )}
        <SourceIcon sourceType={source.source_type} />
        <span className="truncate">{source.source_name}</span>
        <span className="ml-auto text-xs font-normal text-muted-foreground">
          {source.tables.length} table{source.tables.length !== 1 ? "s" : ""}
        </span>
      </button>
      {expanded && (
        <div className="ml-4">
          {source.tables.length === 0 ? (
            <p className="px-2 py-1.5 text-xs text-muted-foreground italic">
              No tables found
            </p>
          ) : (
            source.tables.map((table) => {
              const tableKey = buildNodeKey(
                source.source_id,
                table.table_name,
              );
              return (
                <TableNode
                  key={table.table_name}
                  table={table}
                  sourceId={source.source_id}
                  expanded={!!expandedTables[tableKey]}
                  onToggle={onToggleTable}
                />
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

export function SchemaBrowser({ className }: { className?: string }) {
  const { data, isLoading, isError, error } = useSchema();
  const [searchQuery, setSearchQuery] = useState("");
  const [expanded, setExpanded] = useState<ExpandedState>({});

  const toggleNode = useCallback((key: string) => {
    setExpanded((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const sources = useMemo(() => data?.sources ?? [], [data?.sources]);

  const filteredSources = useMemo(() => {
    return filterSources(sources, searchQuery);
  }, [sources, searchQuery]);

  // Auto-expand sources and tables when searching
  const effectiveExpanded = useMemo(() => {
    if (!searchQuery.trim()) return expanded;

    const autoExpanded: ExpandedState = { ...expanded };
    for (const source of filteredSources) {
      autoExpanded[buildNodeKey(source.source_id)] = true;
      for (const table of source.tables) {
        autoExpanded[buildNodeKey(source.source_id, table.table_name)] = true;
      }
    }
    return autoExpanded;
  }, [expanded, searchQuery, filteredSources]);

  if (isLoading) {
    return (
      <div
        className={cn("flex flex-col", className)}
        data-testid="schema-browser"
      >
        <div className="flex flex-1 items-center justify-center p-6">
          <Loader2 className="size-5 animate-spin text-muted-foreground" />
          <span className="ml-2 text-sm text-muted-foreground">
            Loading schema...
          </span>
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div
        className={cn("flex flex-col", className)}
        data-testid="schema-browser"
      >
        <div className="flex flex-1 items-center justify-center p-6">
          <AlertCircle className="size-5 text-destructive" />
          <span className="ml-2 text-sm text-destructive">
            {error instanceof Error
              ? error.message
              : "Failed to load schema"}
          </span>
        </div>
      </div>
    );
  }

  const isEmpty = sources.length === 0;

  return (
    <div
      className={cn("flex flex-col", className)}
      data-testid="schema-browser"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <h3 className="text-sm font-semibold">Schema Browser</h3>
        <span className="text-xs text-muted-foreground">
          {sources.length} source{sources.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Search */}
      <div className="border-b border-border px-3 py-2">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search tables, columns..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="h-8 w-full rounded-md border border-input bg-background pl-7 pr-7 text-sm outline-none placeholder:text-muted-foreground focus:border-ring focus:ring-1 focus:ring-ring"
            data-testid="schema-search-input"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              aria-label="Clear search"
              data-testid="schema-search-clear"
            >
              <X className="size-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Tree content */}
      <div
        className="flex-1 overflow-y-auto p-2"
        data-testid="schema-tree-container"
      >
        {isEmpty && (
          <div
            className="flex flex-col items-center justify-center p-6 text-center"
            data-testid="schema-empty-state"
          >
            <Database className="mb-2 size-8 text-muted-foreground/50" />
            <p className="text-sm font-medium text-muted-foreground">
              No data sources
            </p>
            <p className="mt-1 text-xs text-muted-foreground/70">
              Upload a dataset or add a database connection to see schema here.
            </p>
          </div>
        )}

        {!isEmpty && filteredSources.length === 0 && searchQuery && (
          <div
            className="flex flex-col items-center justify-center p-6 text-center"
            data-testid="schema-no-results"
          >
            <Search className="mb-2 size-6 text-muted-foreground/50" />
            <p className="text-sm text-muted-foreground">
              No results for &quot;{searchQuery}&quot;
            </p>
          </div>
        )}

        {filteredSources.map((source) => (
          <SourceNode
            key={source.source_id}
            source={source}
            expanded={!!effectiveExpanded[buildNodeKey(source.source_id)]}
            expandedTables={effectiveExpanded}
            onToggleSource={toggleNode}
            onToggleTable={toggleNode}
          />
        ))}
      </div>
    </div>
  );
}
