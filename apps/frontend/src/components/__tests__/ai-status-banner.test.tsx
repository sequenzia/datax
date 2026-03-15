import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AiStatusBanner } from "../ai-status-banner";

// Mock the useAiStatus hook
const mockDismiss = vi.fn();
const mockHookReturn = {
  connectionStatus: "disconnected" as const,
  unavailableReason: "network_error" as const,
  hasProvider: true,
  bannerDismissed: false,
  showBanner: true,
  bannerMessage:
    "AI assistant is unavailable. You can still browse data, view bookmarks, and use saved queries.",
  dismissBanner: mockDismiss,
  chatDisabled: true,
  chatDisabledMessage: "AI assistant is currently unavailable",
};

vi.mock("@/hooks/use-ai-status", () => ({
  useAiStatus: () => mockHookReturn,
}));

function renderBanner() {
  return render(
    <MemoryRouter>
      <AiStatusBanner />
    </MemoryRouter>,
  );
}

describe("AiStatusBanner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset to defaults
    mockHookReturn.showBanner = true;
    mockHookReturn.unavailableReason = "network_error";
    mockHookReturn.hasProvider = true;
    mockHookReturn.bannerMessage =
      "AI assistant is unavailable. You can still browse data, view bookmarks, and use saved queries.";
  });

  it("renders banner when AI connection fails", () => {
    renderBanner();
    expect(screen.getByTestId("ai-status-banner")).toBeInTheDocument();
  });

  it("shows correct banner text for connectivity failure", () => {
    renderBanner();
    expect(screen.getByTestId("ai-status-message")).toHaveTextContent(
      "AI assistant is unavailable. You can still browse data, view bookmarks, and use saved queries.",
    );
  });

  it("is dismissible", async () => {
    const user = userEvent.setup();
    renderBanner();

    const dismissButton = screen.getByTestId("ai-status-dismiss");
    expect(dismissButton).toBeInTheDocument();

    await user.click(dismissButton);
    expect(mockDismiss).toHaveBeenCalledTimes(1);
  });

  it("does not render when showBanner is false (auto-cleared on restore)", () => {
    mockHookReturn.showBanner = false;
    renderBanner();
    expect(screen.queryByTestId("ai-status-banner")).not.toBeInTheDocument();
  });

  it("shows Settings link when no provider configured", () => {
    mockHookReturn.unavailableReason = "no_provider";
    mockHookReturn.hasProvider = false;
    mockHookReturn.bannerMessage =
      "Configure an AI provider in Settings to start chatting.";
    renderBanner();

    expect(screen.getByTestId("ai-status-settings-link")).toBeInTheDocument();
    expect(screen.getByTestId("ai-status-settings-link")).toHaveAttribute(
      "href",
      "/settings",
    );
  });

  it("does not show Settings link for connectivity errors", () => {
    mockHookReturn.unavailableReason = "network_error";
    mockHookReturn.hasProvider = true;
    renderBanner();

    expect(screen.queryByTestId("ai-status-settings-link")).not.toBeInTheDocument();
  });

  it("does not show Settings link for provider unreachable errors", () => {
    mockHookReturn.unavailableReason = "provider_unreachable";
    mockHookReturn.hasProvider = true;
    renderBanner();

    expect(screen.queryByTestId("ai-status-settings-link")).not.toBeInTheDocument();
  });

  it("has role=alert for accessibility", () => {
    renderBanner();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
