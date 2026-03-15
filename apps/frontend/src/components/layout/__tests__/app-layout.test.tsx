import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { AppLayout } from "../app-layout";
import { useUIStore } from "@/stores/ui-store";
import { ThemeProvider } from "@/providers/theme-provider";
import { TooltipProvider } from "@/components/ui/tooltip";

// Mock hooks to avoid QueryClientProvider requirement
vi.mock("@/hooks/use-conversations", () => ({
  useConversationList: () => ({
    data: { pages: [{ conversations: [], next_cursor: null }], pageParams: [undefined] },
    isLoading: false,
    isError: false,
    fetchNextPage: vi.fn(),
    hasNextPage: false,
    isFetchingNextPage: false,
    refetch: vi.fn(),
  }),
  useDeleteConversation: () => ({ mutate: vi.fn() }),
}));

vi.mock("@/stores/chat-store", () => ({
  useChatStore: Object.assign(
    () => ({
      conversationId: null,
      messages: [],
      status: "idle",
      error: null,
      clearError: vi.fn(),
      newConversation: vi.fn(),
      switchConversation: vi.fn(),
      reset: vi.fn(),
      restoreSession: vi.fn(),
    }),
    {
      getState: () => ({
        conversationId: null,
        reset: vi.fn(),
      }),
    },
  ),
}));

vi.mock("@/hooks/use-schema", () => ({
  useSchema: () => ({
    data: { sources: [] },
    isLoading: false,
    isError: false,
    error: null,
  }),
}));

vi.mock("@/hooks/use-ai-status", () => ({
  useAiStatus: () => ({
    connectionStatus: "connected",
    unavailableReason: null,
    hasProvider: true,
    bannerDismissed: false,
    showBanner: false,
    bannerMessage: "",
    dismissBanner: vi.fn(),
    chatDisabled: false,
    chatDisabledMessage: null,
  }),
}));

vi.mock("@/stores/onboarding-store", () => ({
  useOnboardingStore: () => ({
    isOpen: false,
    currentStep: 0,
    dismiss: vi.fn(),
    nextStep: vi.fn(),
    prevStep: vi.fn(),
    goToStep: vi.fn(),
    complete: vi.fn(),
  }),
  TOTAL_STEPS: 3,
}));

beforeEach(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

function renderWithRouter(initialEntry = "/") {
  return render(
    <ThemeProvider>
      <TooltipProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes>
            <Route element={<AppLayout />}>
              <Route index element={<div>Dashboard Content</div>} />
              <Route path="chat" element={<div>Chat Content</div>} />
              <Route path="settings" element={<div>Settings Content</div>} />
              <Route path="*" element={<div>Not Found Content</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </ThemeProvider>,
  );
}

describe("AppLayout", () => {
  beforeEach(() => {
    useUIStore.setState({ sidebarOpen: true });
  });

  it("renders sidebar and main content area", () => {
    renderWithRouter();
    expect(screen.getByTestId("app-layout")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar")).toBeInTheDocument();
  });

  it("fills full viewport height", () => {
    renderWithRouter();
    const layout = screen.getByTestId("app-layout");
    expect(layout.className).toContain("h-screen");
  });

  it("renders route content via Outlet", () => {
    renderWithRouter("/settings");
    expect(screen.getByText("Settings Content")).toBeInTheDocument();
  });

  it("renders 404 content for unknown routes", () => {
    renderWithRouter("/some/unknown/route");
    expect(screen.getByText("Not Found Content")).toBeInTheDocument();
  });
});

describe("Sidebar", () => {
  beforeEach(() => {
    useUIStore.setState({ sidebarOpen: true });
  });

  it("collapses when toggle button is clicked", async () => {
    const user = userEvent.setup();
    renderWithRouter();

    const sidebar = screen.getByTestId("sidebar");
    expect(sidebar.className).toContain("w-64");

    const toggleButton = screen.getByTestId("sidebar-toggle");
    await user.click(toggleButton);

    expect(sidebar.className).toContain("w-14");
  });

  it("expands when toggle button is clicked while collapsed", async () => {
    useUIStore.setState({ sidebarOpen: false });
    const user = userEvent.setup();
    renderWithRouter();

    const sidebar = screen.getByTestId("sidebar");
    expect(sidebar.className).toContain("w-14");

    const toggleButton = screen.getByTestId("sidebar-toggle");
    await user.click(toggleButton);

    expect(sidebar.className).toContain("w-64");
  });

  it("has smooth animation class for collapse transition", () => {
    renderWithRouter();
    const sidebar = screen.getByTestId("sidebar");
    expect(sidebar.className).toContain("transition-[width]");
    expect(sidebar.className).toContain("duration-200");
  });
});
