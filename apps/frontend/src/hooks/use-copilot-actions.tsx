/** Register CopilotKit actions for generative UI rendering in chat. */

import { useCopilotAction } from "@copilotkit/react-core";
import { DataProfile, DataTable, InteractiveChart, SQLApproval, DataExplorer, FollowUpSuggestions } from "@/components/generative-ui";
import type { DataTableColumn, PlotlyChartConfig, FollowUpSuggestion } from "@/components/generative-ui";
import { BookmarkCard } from "@/components/generative-ui/bookmark-card";
import { useCreateBookmark } from "@/hooks/use-bookmarks";

/**
 * Register the "showProfile" copilot action.
 *
 * When the AI agent invokes showProfile with a dataset_id (and optional
 * dataset_name), the DataProfile component is rendered inline in the chat.
 */
export function useCopilotProfileAction() {
  useCopilotAction({
    name: "showProfile",
    description: "Display data profiling statistics for a dataset",
    parameters: [
      {
        name: "dataset_id",
        type: "string",
        description: "The UUID of the dataset to profile",
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
        <DataProfile
          datasetId={datasetId}
          datasetName={args.dataset_name as string | undefined}
        />
      );
    },
  });
}

/**
 * Register the "showTable" copilot action.
 *
 * When the AI agent invokes showTable with column definitions and data rows,
 * the DataTable component is rendered inline in the chat with sorting,
 * filtering, virtual scrolling, and column management.
 */
export function useCopilotTableAction() {
  const createBookmarkMut = useCreateBookmark();

  useCopilotAction({
    name: "showTable",
    description: "Display query results as an interactive data table",
    parameters: [
      {
        name: "columns",
        type: "object[]",
        description: "Column definitions with name and optional type",
        required: true,
      },
      {
        name: "rows",
        type: "object[]",
        description: "Row data as arrays of values",
        required: true,
      },
      {
        name: "title",
        type: "string",
        description: "Optional title for the table",
        required: false,
      },
      {
        name: "message_id",
        type: "string",
        description: "UUID of the message containing this table",
        required: false,
      },
    ],
    render: ({ args }) => {
      const columns = args.columns as DataTableColumn[] | undefined;
      const rows = args.rows as unknown[][] | undefined;
      const messageId = args.message_id as string | undefined;
      if (!columns || !rows) return <></>;

      const handlePin = messageId
        ? () => {
            const title =
              (args.title as string) || "Data Table Bookmark";
            createBookmarkMut.mutate({
              message_id: messageId,
              title,
            });
          }
        : undefined;

      return (
        <DataTable
          columns={columns}
          rows={rows}
          title={args.title as string | undefined}
          onPin={handlePin}
          isPinned={createBookmarkMut.isSuccess}
        />
      );
    },
  });
}

/**
 * Register the "showChart" copilot action.
 *
 * When the AI agent invokes render_chart, the backend returns a PlotlyConfig
 * (data + layout + chart_type). This action receives that configuration along
 * with the raw column/row data and renders the InteractiveChart component
 * inline in the chat. The user can then switch chart types, swap axes, and
 * export -- all client-side without triggering another AI call.
 */
export function useCopilotChartAction() {
  const createBookmarkMut = useCreateBookmark();

  useCopilotAction({
    name: "showChart",
    description:
      "Display an interactive Plotly chart with editing controls for chart type switching and axis assignment",
    parameters: [
      {
        name: "chart_config",
        type: "object",
        description:
          "Plotly chart configuration with data traces, layout, chart_type, and is_fallback flag",
        required: true,
      },
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
        name: "reasoning",
        type: "string",
        description: "AI reasoning for the chart type selection",
        required: false,
      },
      {
        name: "message_id",
        type: "string",
        description: "UUID of the message containing this chart",
        required: false,
      },
    ],
    render: ({ args, status }) => {
      const chartConfig = args.chart_config as PlotlyChartConfig | undefined;
      const columns = args.columns as string[] | undefined;
      const rows = args.rows as unknown[][] | undefined;
      const messageId = args.message_id as string | undefined;

      if (!chartConfig || !columns || !rows) return <></>;

      const handlePin = messageId
        ? () => {
            const title =
              (args.title as string) || "Chart Bookmark";
            createBookmarkMut.mutate({
              message_id: messageId,
              title,
            });
          }
        : undefined;

      return (
        <InteractiveChart
          chartConfig={chartConfig}
          columns={columns}
          rows={rows}
          title={args.title as string | undefined}
          reasoning={args.reasoning as string | undefined}
          isLoading={status === "inProgress"}
          onPin={handlePin}
          isPinned={createBookmarkMut.isSuccess}
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
 * Register the "suggestFollowups" copilot action.
 *
 * When the AI agent invokes suggest_followups after detecting interesting
 * patterns in query results, the FollowUpSuggestions component is rendered
 * inline in the chat with 2-3 clickable suggestion chips. Each chip
 * includes the suggested question text and a brief rationale. Clicking a
 * chip sends it as a new message to the AI.
 */
export function useCopilotFollowupsAction() {
  useCopilotAction({
    name: "suggestFollowups",
    description:
      "Display contextual follow-up suggestion chips when interesting patterns are detected in query results",
    parameters: [
      {
        name: "suggestions",
        type: "object[]",
        description:
          "Array of 2-3 follow-up suggestions, each with question and reasoning fields",
        required: true,
      },
    ],
    render: ({ args }) => {
      const suggestions = args.suggestions as FollowUpSuggestion[] | undefined;
      if (!suggestions || suggestions.length === 0) return null;
      return <FollowUpSuggestions suggestions={suggestions} />;
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
