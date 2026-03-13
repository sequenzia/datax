import { render, screen, within, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { AppLayout } from "../app-layout";
import { useUIStore } from "@/stores/ui-store";
import { ThemeProvider } from "@/providers/theme-provider";

// Mock hooks used by ChatPanel to avoid QueryClientProvider requirement
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
      streamingContent: "",
      sendMessage: vi.fn(),
      cancelStream: vi.fn(),
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

// Mock window.matchMedia for ThemeProvider (jsdom does not implement it)
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

function setViewportWidth(width: number) {
  Object.defineProperty(window, "innerWidth", {
    writable: true,
    configurable: true,
    value: width,
  });
}

function renderWithRouter(initialEntry = "/") {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<div>Dashboard Content</div>} />
            <Route path="chat" element={<div>Chat Content</div>} />
            <Route path="sql" element={<div>SQL Content</div>} />
            <Route path="settings" element={<div>Settings Content</div>} />
            <Route path="*" element={<div>Not Found Content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe("Desktop layout (1280px+)", () => {
  beforeEach(() => {
    setViewportWidth(1280);
    useUIStore.setState({
      sidebarOpen: true,
      chatPanelOpen: true,
      chatPanelWidth: 380,
      activeMobilePanel: "chat",
    });
  });

  afterEach(() => {
    setViewportWidth(1280);
  });

  it("renders full three-panel layout with sidebar, chat, and results", () => {
    renderWithRouter();

    expect(screen.getByTestId("sidebar")).toBeInTheDocument();
    expect(screen.getByTestId("chat-panel")).toBeInTheDocument();
    expect(screen.getByTestId("results-canvas")).toBeInTheDocument();
    expect(screen.getByTestId("resize-handle")).toBeInTheDocument();
  });

  it("does not render bottom navigation", () => {
    renderWithRouter();

    expect(screen.queryByTestId("bottom-navigation")).not.toBeInTheDocument();
  });

  it("renders sidebar expanded with labels visible", () => {
    renderWithRouter();

    const sidebar = screen.getByTestId("sidebar");
    expect(sidebar.className).toContain("w-56");

    const nav = within(sidebar);
    expect(nav.getByText("Dashboard")).toBeInTheDocument();
    expect(nav.getByText("Chat")).toBeInTheDocument();
    expect(nav.getByText("SQL Editor")).toBeInTheDocument();
    expect(nav.getByText("Settings")).toBeInTheDocument();
  });

  it("handles exactly 1280px without overflow", () => {
    setViewportWidth(1280);
    renderWithRouter();

    const layout = screen.getByTestId("app-layout");
    expect(layout.className).toContain("overflow-hidden");
    expect(layout.className).toContain("w-screen");
  });
});

describe("Tablet layout (768px - 1279px)", () => {
  beforeEach(() => {
    setViewportWidth(1024);
    useUIStore.setState({
      sidebarOpen: true,
      chatPanelOpen: true,
      chatPanelWidth: 380,
      activeMobilePanel: "chat",
    });
  });

  afterEach(() => {
    setViewportWidth(1280);
  });

  it("renders sidebar and stacked chat + results", () => {
    renderWithRouter();

    expect(screen.getByTestId("sidebar")).toBeInTheDocument();
    expect(screen.getByTestId("chat-panel")).toBeInTheDocument();
    expect(screen.getByTestId("results-canvas")).toBeInTheDocument();
  });

  it("does not render resize handle (panels stacked vertically)", () => {
    renderWithRouter();

    expect(screen.queryByTestId("resize-handle")).not.toBeInTheDocument();
  });

  it("does not render bottom navigation", () => {
    renderWithRouter();

    expect(screen.queryByTestId("bottom-navigation")).not.toBeInTheDocument();
  });

  it("auto-collapses sidebar to icon-only on breakpoint transition from desktop", () => {
    // Start at desktop width
    setViewportWidth(1280);
    useUIStore.setState({ sidebarOpen: true });
    renderWithRouter();

    // Sidebar should be expanded at desktop
    const sidebar = screen.getByTestId("sidebar");
    expect(sidebar.className).toContain("w-56");

    // Transition to tablet by resizing
    act(() => {
      setViewportWidth(1024);
      window.dispatchEvent(new Event("resize"));
    });

    // Sidebar should now be collapsed (icon-only)
    expect(sidebar.className).toContain("w-14");
  });

  it("works at 768px boundary", () => {
    setViewportWidth(768);
    renderWithRouter();

    expect(screen.getByTestId("sidebar")).toBeInTheDocument();
    expect(screen.queryByTestId("bottom-navigation")).not.toBeInTheDocument();
  });
});

describe("Mobile layout (< 768px)", () => {
  beforeEach(() => {
    setViewportWidth(375);
    useUIStore.setState({
      sidebarOpen: true,
      chatPanelOpen: true,
      chatPanelWidth: 380,
      activeMobilePanel: "chat",
    });
  });

  afterEach(() => {
    setViewportWidth(1280);
  });

  it("renders single panel with bottom navigation", () => {
    renderWithRouter();

    expect(screen.getByTestId("bottom-navigation")).toBeInTheDocument();
    expect(screen.getByTestId("chat-panel")).toBeInTheDocument();
  });

  it("does not render sidebar on mobile", () => {
    renderWithRouter();

    expect(screen.queryByTestId("sidebar")).not.toBeInTheDocument();
  });

  it("does not render resize handle on mobile", () => {
    renderWithRouter();

    expect(screen.queryByTestId("resize-handle")).not.toBeInTheDocument();
  });

  it("shows chat panel by default on mobile", () => {
    renderWithRouter();

    expect(screen.getByTestId("chat-panel")).toBeInTheDocument();
  });

  it("shows bottom navigation with all four tabs", () => {
    renderWithRouter();

    expect(screen.getByTestId("bottom-nav-dashboard")).toBeInTheDocument();
    expect(screen.getByTestId("bottom-nav-chat")).toBeInTheDocument();
    expect(screen.getByTestId("bottom-nav-sql")).toBeInTheDocument();
    expect(screen.getByTestId("bottom-nav-settings")).toBeInTheDocument();
  });

  it("switches panels via bottom navigation", async () => {
    const user = userEvent.setup();
    renderWithRouter();

    // Default is chat
    expect(screen.getByTestId("chat-panel")).toBeInTheDocument();
    expect(screen.queryByTestId("results-canvas")).not.toBeInTheDocument();

    // Switch to dashboard
    await user.click(screen.getByTestId("bottom-nav-dashboard"));
    expect(screen.queryByTestId("chat-panel")).not.toBeInTheDocument();
    expect(screen.getByTestId("results-canvas")).toBeInTheDocument();

    // Switch back to chat
    await user.click(screen.getByTestId("bottom-nav-chat"));
    expect(screen.getByTestId("chat-panel")).toBeInTheDocument();
  });

  it("highlights active tab in bottom navigation", () => {
    renderWithRouter();

    const chatTab = screen.getByTestId("bottom-nav-chat");
    expect(chatTab.className).toContain("text-primary");

    const dashboardTab = screen.getByTestId("bottom-nav-dashboard");
    expect(dashboardTab.className).toContain("text-muted-foreground");
  });

  it("sets aria-current on active tab", () => {
    renderWithRouter();

    const chatTab = screen.getByTestId("bottom-nav-chat");
    expect(chatTab).toHaveAttribute("aria-current", "page");

    const dashboardTab = screen.getByTestId("bottom-nav-dashboard");
    expect(dashboardTab).not.toHaveAttribute("aria-current");
  });

  it("works at 767px boundary (still mobile)", () => {
    setViewportWidth(767);
    renderWithRouter();

    expect(screen.getByTestId("bottom-navigation")).toBeInTheDocument();
    expect(screen.queryByTestId("sidebar")).not.toBeInTheDocument();
  });
});

describe("Breakpoint transitions", () => {
  afterEach(() => {
    setViewportWidth(1280);
    useUIStore.setState({
      sidebarOpen: true,
      chatPanelOpen: true,
      chatPanelWidth: 380,
      activeMobilePanel: "chat",
    });
  });

  it("transitions from desktop to tablet on resize", () => {
    setViewportWidth(1280);
    useUIStore.setState({ sidebarOpen: true });
    renderWithRouter();

    // Should start as desktop layout
    expect(screen.getByTestId("resize-handle")).toBeInTheDocument();

    // Resize to tablet
    act(() => {
      setViewportWidth(1024);
      window.dispatchEvent(new Event("resize"));
    });

    // Sidebar should auto-collapse
    const sidebar = screen.getByTestId("sidebar");
    expect(sidebar.className).toContain("w-14");
    // Resize handle should disappear (tablet layout)
    expect(screen.queryByTestId("resize-handle")).not.toBeInTheDocument();
  });

  it("transitions from tablet to mobile on resize", () => {
    setViewportWidth(1024);
    useUIStore.setState({ sidebarOpen: false });
    renderWithRouter();

    // Should start as tablet layout
    expect(screen.getByTestId("sidebar")).toBeInTheDocument();

    // Resize to mobile
    act(() => {
      setViewportWidth(375);
      window.dispatchEvent(new Event("resize"));
    });

    // Should show bottom navigation, no sidebar
    expect(screen.queryByTestId("sidebar")).not.toBeInTheDocument();
    expect(screen.getByTestId("bottom-navigation")).toBeInTheDocument();
  });

  it("responds to orientation change event", () => {
    setViewportWidth(1024);
    useUIStore.setState({ sidebarOpen: false });
    renderWithRouter();

    expect(screen.getByTestId("sidebar")).toBeInTheDocument();

    // Simulate orientation change to portrait (narrower)
    act(() => {
      setViewportWidth(600);
      window.dispatchEvent(new Event("orientationchange"));
    });

    // Should switch to mobile layout
    expect(screen.queryByTestId("sidebar")).not.toBeInTheDocument();
    expect(screen.getByTestId("bottom-navigation")).toBeInTheDocument();
  });
});
