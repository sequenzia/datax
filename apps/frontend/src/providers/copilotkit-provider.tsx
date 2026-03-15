import { CopilotKit } from "@copilotkit/react-core";
import type { ReactNode } from "react";
import { CopilotActionsRegistrar } from "./copilot-actions-registrar";

const RUNTIME_URL = "/api/agent";

export function CopilotKitProvider({ children }: { children: ReactNode }) {
  return (
    <CopilotKit runtimeUrl={RUNTIME_URL}>
      <CopilotActionsRegistrar />
      {children}
    </CopilotKit>
  );
}
