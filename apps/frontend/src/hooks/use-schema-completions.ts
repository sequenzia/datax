/** Hook to fetch schema metadata and build CodeMirror autocomplete extensions. */

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchDataset, fetchConnection } from "@/lib/api";
import type { DataSource } from "@/stores/sql-editor-store";
import type { TableSchema } from "@/lib/sql-completions";
import type { SchemaColumn, DatasetDetail, ConnectionDetail } from "@/types/api";

/**
 * Fetches schema for the selected data source and returns TableSchema[].
 * Falls back to empty array on fetch failure.
 */
export function useSchemaCompletions(
  selectedSource: DataSource | null,
): {
  tables: TableSchema[];
  isLoading: boolean;
  error: Error | null;
} {
  const { data, isLoading, error } = useQuery({
    queryKey: ["schema-completions", selectedSource?.type, selectedSource?.id],
    queryFn: async (): Promise<TableSchema[]> => {
      if (!selectedSource) return [];

      if (selectedSource.type === "dataset") {
        const detail: DatasetDetail = await fetchDataset(selectedSource.id);
        if (!detail.schema || detail.schema.length === 0) return [];
        return [
          {
            tableName: detail.duckdb_table_name,
            columns: detail.schema,
          },
        ];
      }

      if (selectedSource.type === "connection") {
        const detail: ConnectionDetail = await fetchConnection(
          selectedSource.id,
        );
        if (!detail.schema || detail.schema.length === 0) return [];

        // Group columns by table_name for connections (which may have multiple tables)
        const tableMap = new Map<string, SchemaColumn[]>();
        for (const col of detail.schema) {
          const tName = col.table_name ?? "unknown";
          if (!tableMap.has(tName)) {
            tableMap.set(tName, []);
          }
          tableMap.get(tName)!.push(col);
        }

        return Array.from(tableMap.entries()).map(
          ([tableName, columns]) => ({
            tableName,
            columns,
          }),
        );
      }

      return [];
    },
    enabled: !!selectedSource,
    staleTime: 60_000, // Cache schema for 1 minute
    retry: 1,
  });

  const tables = useMemo(() => data ?? [], [data]);

  return {
    tables,
    isLoading,
    error: error as Error | null,
  };
}
