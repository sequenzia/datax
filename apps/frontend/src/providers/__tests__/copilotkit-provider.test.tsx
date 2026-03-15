import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { CopilotKitProvider } from "../copilotkit-provider";

// Capture props passed to CopilotKit
let lastCopilotKitProps: Record<string, unknown> = {};

vi.mock("@copilotkit/react-core", () => ({
  CopilotKit: (props: Record<string, unknown>) => {
    lastCopilotKitProps = props;
    return (
      <div data-testid="copilotkit-provider">
        {props.children as React.ReactNode}
      </div>
    );
  },
  useCopilotAction: vi.fn(),
  useCoAgentStateRender: vi.fn(),
}));

describe("CopilotKitProvider", () => {
  it("renders children without errors", () => {
    render(
      <CopilotKitProvider>
        <div>Test Child</div>
      </CopilotKitProvider>,
    );
    expect(screen.getByText("Test Child")).toBeInTheDocument();
  });

  it("wraps children in CopilotKit component", () => {
    render(
      <CopilotKitProvider>
        <div>Wrapped Content</div>
      </CopilotKitProvider>,
    );
    expect(screen.getByTestId("copilotkit-provider")).toBeInTheDocument();
    expect(
      screen.getByTestId("copilotkit-provider"),
    ).toContainElement(screen.getByText("Wrapped Content"));
  });

  it("configures runtimeUrl to /api/agent", () => {
    render(
      <CopilotKitProvider>
        <div>Check Props</div>
      </CopilotKitProvider>,
    );
    expect(lastCopilotKitProps.runtimeUrl).toBe("/api/agent");
  });
});
