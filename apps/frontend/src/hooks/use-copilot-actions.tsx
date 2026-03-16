/** Register CopilotKit actions for generative UI rendering in chat. */

import { useCallback } from "react";
import { useCopilotAction, useCopilotChatInternal } from "@copilotkit/react-core";
import { DataProfile, SQLApproval, DataExplorer, FollowUpSuggestions, ChartSkeleton, ProfileSkeleton } from "@/components/generative-ui";
import type { DataTableColumn, PlotlyChartConfig, FollowUpSuggestion } from "@/components/generative-ui";
import { PinnableChart } from "@/components/generative-ui/pinnable-chart";
import { PinnableTable } from "@/components/generative-ui/pinnable-table";
import { BookmarkCard } from "@/components/generative-ui/bookmark-card";

/** Accumulates structured tool results during the current agent turn. */
let pendingToolData: Record<string, unknown> = {};

/** Retrieve and clear the accumulated tool data for persistence. */
export function getPendingToolData(): Record<string, unknown> {
  const data = { ...pendingToolData };
  pendingToolData = {};
  return data;
}

/** Clear accumulated tool data without retrieving it. */
export function clearPendingToolData(): void {
  pendingToolData = {};
}

/**
 * Register the "render_data_profile" copilot action.
 *
 * Matches the backend `render_data_profile` tool. The tool receives
 * `table_name` as input; the result contains `dataset_id` for the
 * DataProfile component.
 */
export function useCopilotProfileAction() {
  useCopilotAction({
    name: "render_data_profile",
    description: "Display data profiling statistics for a dataset",
    available: "disabled",
    parameters: [
      {
        name: "table_name",
        type: "string",
        description: "The DuckDB table name to profile",
        required: true,
      },
    ],
    render: ({ status, result }) => {
      if (status !== "complete") return <ProfileSkeleton />;
      const parsed = typeof result === "string" ? JSON.parse(result) : result;
      const datasetId = parsed?.dataset_id as string | undefined;
      if (!datasetId) return null;
      return <DataProfile datasetId={datasetId} />;
    },
  });
}

/**
 * Register the "render_table" copilot action.
 *
 * Matches the backend `render_table` tool. The tool receives `columns`
 * (string[]) and `rows` (list of lists) as inputs. We convert the
 * string column names into DataTableColumn objects for the component.
 * Renders PinnableTable to support the Pin-to-Dashboard flow.
 */
export function useCopilotTableAction() {
  useCopilotAction({
    name: "render_table",
    description: "Display query results as an interactive data table",
    available: "disabled",
    parameters: [
      {
        name: "columns",
        type: "string[]",
        description: "Column names from the query result",
        required: true,
      },
      {
        name: "rows",
        type: "object[]",
        description: "Row data as arrays of values",
        required: true,
      },
      {
        name: "sql",
        type: "string",
        description: "The SQL query that produced the data",
        required: false,
      },
      {
        name: "source_id",
        type: "string",
        description: "UUID of the data source",
        required: false,
      },
      {
        name: "source_type",
        type: "string",
        description: "Source type: dataset or connection",
        required: false,
      },
    ],
    render: ({ args, status, result }) => {
      const columnNames = args.columns as string[] | undefined;
      const rows = args.rows as unknown[][] | undefined;
      if (!columnNames || !rows) return <></>;

      // Extract source info from tool result (backend includes them)
      let sql = args.sql as string | undefined;
      let sourceId = args.source_id as string | undefined;
      let sourceType = args.source_type as string | undefined;

      if (status === "complete") {
        const parsed = typeof result === "string" ? JSON.parse(result) : result;
        sql = sql ?? (parsed?.sql as string | undefined);
        sourceId = sourceId ?? (parsed?.source_id as string | undefined);
        sourceType = sourceType ?? (parsed?.source_type as string | undefined);

        pendingToolData.query_result_summary = {
          columns: columnNames,
          rows: rows.slice(0, 50),
          row_count: rows.length,
        };
      }

      const columns: DataTableColumn[] = columnNames.map((name) => ({ name }));

      return (
        <PinnableTable
          columns={columns}
          rows={rows}
          sql={sql}
          sourceId={sourceId}
          sourceType={sourceType}
        />
      );
    },
  });
}

/**
 * Register the "render_chart" copilot action.
 *
 * Matches the backend `render_chart` tool. The tool receives `columns`,
 * `rows`, `title`, `chart_type_override`, and `query_context` as inputs.
 * The chart_config and reasoning are in the tool's RESULT, not inputs.
 * Renders PinnableChart to support the Pin-to-Dashboard flow.
 */
export function useCopilotChartAction() {
  useCopilotAction({
    name: "render_chart",
    description:
      "Display an interactive Plotly chart with editing controls for chart type switching and axis assignment",
    available: "disabled",
    parameters: [
      {
        name: "columns",
        type: "string[]",
        description: "Column names from the query result",
        required: true,
      },
      {
        name: "rows",
        type: "object[]",
        description: "Row data from the query result (list of lists)",
        required: true,
      },
      {
        name: "title",
        type: "string",
        description: "Chart title",
        required: false,
      },
      {
        name: "chart_type_override",
        type: "string",
        description: "Optional chart type to force",
        required: false,
      },
      {
        name: "query_context",
        type: "string",
        description: "Optional description of what the data represents",
        required: false,
      },
      {
        name: "sql",
        type: "string",
        description: "The SQL query that produced the data",
        required: false,
      },
      {
        name: "source_id",
        type: "string",
        description: "UUID of the data source",
        required: false,
      },
      {
        name: "source_type",
        type: "string",
        description: "Source type: dataset or connection",
        required: false,
      },
    ],
    render: ({ args, status, result }) => {
      const columns = args.columns as string[] | undefined;
      const rows = args.rows as unknown[][] | undefined;

      if (!columns || !rows) return <></>;
      if (status !== "complete") return <ChartSkeleton />;

      const parsed = typeof result === "string" ? JSON.parse(result) : result;
      const chartConfig = parsed?.chart_config as PlotlyChartConfig | undefined;
      if (!chartConfig) return <></>;

      // Resolve source info: prefer args (tool params), fall back to result
      const sql = (args.sql as string | undefined) ?? (parsed?.sql as string | undefined);
      const sourceId = (args.source_id as string | undefined) ?? (parsed?.source_id as string | undefined);
      const sourceType = (args.source_type as string | undefined) ?? (parsed?.source_type as string | undefined);

      pendingToolData.chart_config = {
        ...chartConfig,
        type: chartConfig.chart_type,
      };

      return (
        <PinnableChart
          chartConfig={chartConfig}
          columns={columns}
          rows={rows}
          title={args.title as string | undefined}
          reasoning={parsed?.reasoning as string | undefined}
          isLoading={false}
          sql={sql}
          sourceId={sourceId}
          sourceType={sourceType}
        />
      );
    },
  });
}

/**
 * Register the "confirmQuery" copilot action.
 *
 * Uses the renderAndWaitForResponse pattern so the agent pauses
 * until the user approves, edits, or rejects the generated SQL.
 * The agent receives one of: "approved", "modified: <new SQL>", or "rejected".
 */
export function useCopilotConfirmQueryAction() {
  useCopilotAction({
    name: "confirmQuery",
    description:
      "Show generated SQL to the user for approval before execution. The user can approve, edit, or reject the query.",
    parameters: [
      {
        name: "sql",
        type: "string",
        description: "The generated SQL query to preview",
        required: true,
      },
    ],
    renderAndWaitForResponse: ({ args, status, respond }) => {
      const sqlText = (args.sql as string) ?? "";
      return (
        <SQLApproval
          sqlText={sqlText}
          status={status}
          respond={respond}
          result={undefined}
        />
      );
    },
  });
}

/**
 * Register the "exploreDataset" copilot action.
 *
 * When the AI agent invokes exploreDataset with a dataset_id (and optional
 * dataset_name), the DataExplorer component is rendered inline in the chat
 * for visual column browsing with stats, distributions, and quick filters.
 */
export function useCopilotExploreAction() {
  useCopilotAction({
    name: "exploreDataset",
    description:
      "Display an interactive data explorer for browsing dataset columns, viewing distributions, and filtering",
    available: "disabled",
    parameters: [
      {
        name: "dataset_id",
        type: "string",
        description: "The UUID of the dataset to explore",
        required: true,
      },
      {
        name: "dataset_name",
        type: "string",
        description: "The display name of the dataset",
        required: false,
      },
    ],
    render: ({ args }) => {
      const datasetId = args.dataset_id as string | undefined;
      if (!datasetId) return null;
      return (
        <DataExplorer
          datasetId={datasetId}
          datasetName={args.dataset_name as string | undefined}
        />
      );
    },
  });
}

/**
 * Register the "suggest_followups" copilot action.
 *
 * Matches the backend `suggest_followups` tool. The tool receives query
 * context as inputs; the actual suggestions array is in the tool's RESULT.
 * We return null until the tool completes and the result is available.
 */
export function useCopilotFollowupsAction() {
  const { sendMessage } = useCopilotChatInternal();

  const handleFollowUpSend = useCallback(
    (question: string) => {
      void sendMessage({
        id: crypto.randomUUID(),
        role: "user" as const,
        content: question,
      });
    },
    [sendMessage],
  );

  useCopilotAction({
    name: "suggest_followups",
    description:
      "Display contextual follow-up suggestion chips when interesting patterns are detected in query results",
    available: "disabled",
    parameters: [
      {
        name: "current_query",
        type: "string",
        description: "The SQL query that produced the current results",
        required: true,
      },
      {
        name: "columns",
        type: "string[]",
        description: "Column names from the current result",
        required: true,
      },
      {
        name: "row_count",
        type: "number",
        description: "Number of rows in the current result",
        required: true,
      },
      {
        name: "chart_type",
        type: "string",
        description: "The chart type used to visualize the current result",
        required: false,
      },
    ],
    render: ({ status, result }) => {
      if (status !== "complete") return null;
      const parsed = typeof result === "string" ? JSON.parse(result) : result;
      const suggestions = parsed?.suggestions as FollowUpSuggestion[] | undefined;
      if (!suggestions || suggestions.length === 0) return null;
      return (
        <FollowUpSuggestions
          suggestions={suggestions}
          onSend={handleFollowUpSend}
        />
      );
    },
  });
}

/**
 * Register the "showBookmark" copilot action.
 *
 * When the AI agent presents a saved bookmark, it renders a BookmarkCard
 * inline in the chat showing the bookmark's title, SQL, and chart config.
 */
export function useCopilotBookmarkAction() {
  useCopilotAction({
    name: "showBookmark",
    description:
      "Display a saved bookmark with its SQL query and chart configuration",
    available: "disabled",
    parameters: [
      {
        name: "bookmark_id",
        type: "string",
        description: "The UUID of the bookmark to display",
        required: true,
      },
      {
        name: "title",
        type: "string",
        description: "The bookmark title",
        required: true,
      },
      {
        name: "sql",
        type: "string",
        description: "The SQL query associated with the bookmark",
        required: false,
      },
      {
        name: "source_id",
        type: "string",
        description: "The UUID of the data source",
        required: false,
      },
      {
        name: "source_type",
        type: "string",
        description: "The type of data source (dataset or connection)",
        required: false,
      },
    ],
    render: ({ args }) => {
      const bookmarkId = args.bookmark_id as string | undefined;
      const title = args.title as string | undefined;
      if (!bookmarkId || !title) return <></>;
      return (
        <BookmarkCard
          bookmarkId={bookmarkId}
          title={title}
          sql={args.sql as string | undefined}
          sourceId={args.source_id as string | undefined}
          sourceType={args.source_type as string | undefined}
        />
      );
    },
  });
}
