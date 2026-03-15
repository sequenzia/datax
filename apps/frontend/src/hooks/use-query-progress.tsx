/**
 * Hook that subscribes to agent state via useCoAgentStateRender and
 * renders a QueryProgress component inline in the chat when the
 * datax-analytics agent is processing.
 *
 * Progress stages are derived from the agent's current state:
 * - Tool calls starting with "run_query" -> executing_query
 * - Tool calls starting with "render_chart" -> building_visualization
 * - Default in-progress state -> generating_sql
 * - Agent complete -> complete
 * - Agent error -> error
 *
 * Verbosity is controlled by the settings store's `verboseErrors` flag:
 * - Summary mode (default): spinner during retries, details on final failure only
 * - Verbose mode: each retry step visible in real-time, correction chain on success
 */

import { useCoAgentStateRender } from "@copilotkit/react-core";
import { useSettingsStore } from "@/stores/settings-store";
import {
  QueryProgress,
  type ProgressStage,
  type RetryStep,
} from "@/components/generative-ui/query-progress";

/** The name of the Pydantic AI agent (matches backend agent name) */
const AGENT_NAME = "datax-analytics";

/** Map of tool names to progress stages */
const TOOL_STAGE_MAP: Record<string, ProgressStage> = {
  run_query: "executing_query",
  get_schema: "generating_sql",
  summarize_table: "executing_query",
  render_chart: "building_visualization",
  render_table: "building_visualization",
  render_data_profile: "building_visualization",
  suggest_followups: "complete",
  create_bookmark: "complete",
  search_bookmarks: "executing_query",
};

/**
 * Derive the progress stage from agent state.
 *
 * The agent state object may contain tool call information, a `stage`
 * field from tool results, or other state indicators. This function
 * maps those to a user-facing ProgressStage.
 */
function deriveStage(state: Record<string, unknown>): ProgressStage {
  // Check for explicit stage field (set by tool return values)
  if (typeof state.stage === "string") {
    const stage = state.stage as string;
    if (stage === "query_error" || stage.endsWith("_error")) return "error";
    if (stage === "query_complete" || stage === "chart_ready" || stage === "table_ready") {
      return "complete";
    }
  }

  // Check for current tool name
  const toolName =
    (state.currentToolName as string) ??
    (state.tool_name as string) ??
    (state.toolName as string);

  if (toolName && toolName in TOOL_STAGE_MAP) {
    return TOOL_STAGE_MAP[toolName];
  }

  // Check for retry state
  if (state.retry === true || state.isRetrying === true) {
    return "retrying";
  }

  // Default: generating SQL (the first step in the workflow)
  return "generating_sql";
}

/**
 * Extract retry steps from agent state for verbose mode display.
 */
function extractRetrySteps(state: Record<string, unknown>): RetryStep[] {
  if (!Array.isArray(state.retrySteps)) return [];

  return (state.retrySteps as Array<Record<string, unknown>>).map((step) => ({
    attempt: typeof step.attempt === "number" ? step.attempt : 0,
    maxAttempts: typeof step.maxAttempts === "number" ? step.maxAttempts : 3,
    error: typeof step.error === "string" ? step.error : "Unknown error",
    correctedSql:
      typeof step.correctedSql === "string" ? step.correctedSql : undefined,
  }));
}

/**
 * Register the query progress state render for the datax-analytics agent.
 *
 * When the agent is running, this hook renders a QueryProgress component
 * in the chat showing the current step of the agent's workflow.
 */
export function useQueryProgressRender() {
  const verboseErrors = useSettingsStore((s) => s.verboseErrors);

  useCoAgentStateRender<Record<string, unknown>>({
    name: AGENT_NAME,
    render: ({ state, status }) => {
      const stage: ProgressStage =
        status === "complete" ? "complete" : deriveStage(state ?? {});

      // Skip rendering for complete state to avoid flash after results appear
      if (status === "complete" && stage === "complete") {
        return null;
      }

      const errorMessage =
        stage === "error" && typeof state?.error === "string"
          ? (state.error as string)
          : undefined;

      const retrySteps = state ? extractRetrySteps(state) : [];

      return (
        <QueryProgress
          stage={stage}
          summaryMode={!verboseErrors}
          errorMessage={errorMessage}
          retrySteps={retrySteps}
        />
      );
    },
  });
}
