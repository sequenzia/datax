import { CopilotKit } from "@copilotkit/react-core";
import { Component, type ErrorInfo, type ReactNode } from "react";
import { CopilotActionsRegistrar } from "./copilot-actions-registrar";
import { useChatStore } from "@/stores/chat-store";

const RUNTIME_URL = "/api/agent";
const AGENT_NAME = "datax-analytics";

/** Silent error boundary — logs failures without breaking visible UI. */
class ActionsErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("CopilotActionsRegistrar failed:", error, info);
  }

  render() {
    return this.state.hasError ? null : this.props.children;
  }
}

export function CopilotKitProvider({ children }: { children: ReactNode }) {
  const selectedSources = useChatStore((s) => s.selectedSources);

  return (
    <CopilotKit
      runtimeUrl={RUNTIME_URL}
      agent={AGENT_NAME}
      properties={{
        selectedSources: selectedSources.map((s) => ({ id: s.id, type: s.type })),
      }}
    >
      <ActionsErrorBoundary>
        <CopilotActionsRegistrar />
      </ActionsErrorBoundary>
      {children}
    </CopilotKit>
  );
}
