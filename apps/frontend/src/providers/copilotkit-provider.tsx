import { CopilotKit } from "@copilotkit/react-core";
import { Component, type ErrorInfo, type ReactNode } from "react";
import { CopilotActionsRegistrar } from "./copilot-actions-registrar";

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
  return (
    <CopilotKit runtimeUrl={RUNTIME_URL} agent={AGENT_NAME}>
      <ActionsErrorBoundary>
        <CopilotActionsRegistrar />
      </ActionsErrorBoundary>
      {children}
    </CopilotKit>
  );
}
