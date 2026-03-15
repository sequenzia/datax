/** Registers all CopilotKit generative UI actions and state renders.
 *
 * This component renders nothing visible — it only calls hooks that register
 * actions and state renders with the CopilotKit context. It must be rendered
 * inside <CopilotKit> so the context is available.
 */

import {
  useCopilotProfileAction,
  useCopilotTableAction,
  useCopilotChartAction,
  useCopilotConfirmQueryAction,
  useCopilotExploreAction,
  useCopilotFollowupsAction,
  useCopilotBookmarkAction,
} from "@/hooks/use-copilot-actions";
import { useQueryProgressRender } from "@/hooks/use-query-progress";
import { useCopilotSourceContext } from "@/hooks/use-copilot-source-context";

export function CopilotActionsRegistrar() {
  useCopilotSourceContext();
  useCopilotProfileAction();
  useCopilotTableAction();
  useCopilotChartAction();
  useCopilotConfirmQueryAction();
  useCopilotExploreAction();
  useCopilotFollowupsAction();
  useCopilotBookmarkAction();
  useQueryProgressRender();
  return null;
}
