import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, beforeEach, vi } from "vitest";
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

function hasClass(element: Element, className: string): boolean {
  return element.className.split(/\s+/).includes(className);
}

function renderWithRouter(initialEntry = "/") {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<div>Dashboard Content</div>} />
            <Route path="chat" element={<div>Chat Content</div>} />
            <Route
              path="chat/:conversationId"
              element={<div>Chat Conversation Content</div>}
            />
            <Route path="sql" element={<div>SQL Content</div>} />
            <Route path="settings" element={<div>Settings Content</div>} />
            <Route
              path="datasets/:id"
              element={<div>Dataset Detail Content</div>}
            />
            <Route
              path="connections/:id"
              element={<div>Connection Detail Content</div>}
            />
            <Route path="*" element={<div>Not Found Content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe("AppLayout", () => {
  beforeEach(() => {
    useUIStore.setState({
      sidebarOpen: true,
      chatPanelOpen: true,
      chatPanelWidth: 380,
    });
  });

  it("renders all three panels: sidebar, chat, and results", () => {
    renderWithRouter();

    expect(screen.getByTestId("sidebar")).toBeInTheDocument();
    expect(screen.getByTestId("chat-panel")).toBeInTheDocument();
    expect(screen.getByTestId("results-canvas")).toBeInTheDocument();
  });

  it("fills full viewport height", () => {
    renderWithRouter();

    const layout = screen.getByTestId("app-layout");
    expect(layout.className).toContain("h-screen");
  });

  it("renders results canvas on dashboard route", () => {
    renderWithRouter("/");

    expect(screen.getByTestId("results-canvas")).toBeInTheDocument();
  });

  it("renders results canvas on chat route", () => {
    renderWithRouter("/chat");

    expect(screen.getByTestId("results-canvas")).toBeInTheDocument();
  });

  it("renders resize handle between chat and results", () => {
    renderWithRouter();

    expect(screen.getByTestId("resize-handle")).toBeInTheDocument();
  });

  it("hides chat panel and resize handle when chat panel is closed", () => {
    useUIStore.setState({ chatPanelOpen: false });
    renderWithRouter();

    expect(screen.queryByTestId("chat-panel")).not.toBeInTheDocument();
    expect(screen.queryByTestId("resize-handle")).not.toBeInTheDocument();
  });
});

describe("Route rendering", () => {
  beforeEach(() => {
    useUIStore.setState({
      sidebarOpen: true,
      chatPanelOpen: true,
      chatPanelWidth: 380,
    });
  });

  it("handles the dashboard route at /", () => {
    renderWithRouter("/");
    expect(screen.getByTestId("results-canvas")).toBeInTheDocument();
  });

  it("handles the chat route at /chat", () => {
    renderWithRouter("/chat");
    expect(screen.getByTestId("results-canvas")).toBeInTheDocument();
  });

  it("handles chat with conversation ID at /chat/:conversationId", () => {
    renderWithRouter("/chat/550e8400-e29b-41d4-a716-446655440000");
    expect(screen.getByTestId("results-canvas")).toBeInTheDocument();
  });

  it("handles the SQL editor route at /sql", () => {
    renderWithRouter("/sql");
    expect(screen.getByTestId("results-canvas")).toBeInTheDocument();
  });

  it("renders settings content at /settings via Outlet", () => {
    renderWithRouter("/settings");
    expect(screen.getByText("Settings Content")).toBeInTheDocument();
  });

  it("renders dataset detail content at /datasets/:id via Outlet", () => {
    renderWithRouter("/datasets/550e8400-e29b-41d4-a716-446655440000");
    expect(screen.getByText("Dataset Detail Content")).toBeInTheDocument();
  });

  it("renders connection detail content at /connections/:id via Outlet", () => {
    renderWithRouter("/connections/550e8400-e29b-41d4-a716-446655440000");
    expect(screen.getByText("Connection Detail Content")).toBeInTheDocument();
  });

  it("renders 404 content for unknown routes via Outlet", () => {
    renderWithRouter("/some/unknown/route");
    expect(screen.getByText("Not Found Content")).toBeInTheDocument();
  });
});

describe("Sidebar", () => {
  beforeEach(() => {
    useUIStore.setState({
      sidebarOpen: true,
      chatPanelOpen: true,
      chatPanelWidth: 380,
    });
  });

  it("collapses when toggle button is clicked", async () => {
    const user = userEvent.setup();
    renderWithRouter();

    const sidebar = screen.getByTestId("sidebar");
    expect(sidebar.className).toContain("w-56");

    const toggleButton = screen.getByTestId("sidebar-toggle");
    await user.click(toggleButton);

    expect(sidebar.className).toContain("w-14");
    expect(sidebar.className).not.toContain("w-56");
  });

  it("expands when toggle button is clicked while collapsed", async () => {
    useUIStore.setState({ sidebarOpen: false });
    const user = userEvent.setup();
    renderWithRouter();

    const sidebar = screen.getByTestId("sidebar");
    expect(sidebar.className).toContain("w-14");

    const toggleButton = screen.getByTestId("sidebar-toggle");
    await user.click(toggleButton);

    expect(sidebar.className).toContain("w-56");
  });

  it("renders navigation links for all pages", () => {
    renderWithRouter();

    const sidebar = screen.getByTestId("sidebar");
    const nav = within(sidebar);

    expect(nav.getByText("Dashboard")).toBeInTheDocument();
    expect(nav.getByText("Chat")).toBeInTheDocument();
    expect(nav.getByText("SQL Editor")).toBeInTheDocument();
    expect(nav.getByText("Settings")).toBeInTheDocument();
  });

  it("navigation links route to correct pages", async () => {
    const user = userEvent.setup();
    renderWithRouter("/settings");

    const sidebar = screen.getByTestId("sidebar");
    const nav = within(sidebar);

    expect(screen.getByText("Settings Content")).toBeInTheDocument();

    await user.click(nav.getByText("Dashboard"));
    expect(screen.getByTestId("results-canvas")).toBeInTheDocument();

    await user.click(nav.getByText("Chat"));
    expect(screen.getByTestId("results-canvas")).toBeInTheDocument();

    await user.click(nav.getByText("Settings"));
    expect(screen.getByText("Settings Content")).toBeInTheDocument();
  });

  it("hides labels when collapsed but shows icons", () => {
    useUIStore.setState({ sidebarOpen: false });
    renderWithRouter();

    const sidebar = screen.getByTestId("sidebar");
    const nav = within(sidebar);

    expect(nav.queryByText("Dashboard")).not.toBeInTheDocument();
    expect(nav.queryByText("Chat")).not.toBeInTheDocument();
    expect(nav.queryByText("SQL Editor")).not.toBeInTheDocument();
    expect(nav.queryByText("Settings")).not.toBeInTheDocument();
  });

  it("has smooth animation class for collapse transition", () => {
    renderWithRouter();

    const sidebar = screen.getByTestId("sidebar");
    expect(sidebar.className).toContain("transition-[width]");
    expect(sidebar.className).toContain("duration-200");
  });

  it("highlights Dashboard link as active on /", () => {
    renderWithRouter("/");

    const sidebar = screen.getByTestId("sidebar");
    const dashboardLink = within(sidebar)
      .getByText("Dashboard")
      .closest("a")!;

    expect(hasClass(dashboardLink, "bg-sidebar-accent")).toBe(true);
  });

  it("highlights Chat link as active on /chat", () => {
    renderWithRouter("/chat");

    const sidebar = screen.getByTestId("sidebar");
    const chatLink = within(sidebar).getByText("Chat").closest("a")!;

    expect(hasClass(chatLink, "bg-sidebar-accent")).toBe(true);
  });

  it("highlights Chat link as active on /chat/:conversationId", () => {
    renderWithRouter("/chat/550e8400-e29b-41d4-a716-446655440000");

    const sidebar = screen.getByTestId("sidebar");
    const chatLink = within(sidebar).getByText("Chat").closest("a")!;

    expect(hasClass(chatLink, "bg-sidebar-accent")).toBe(true);
  });

  it("does not highlight Dashboard link on /chat", () => {
    renderWithRouter("/chat");

    const sidebar = screen.getByTestId("sidebar");
    const dashboardLink = within(sidebar)
      .getByText("Dashboard")
      .closest("a")!;

    expect(hasClass(dashboardLink, "bg-sidebar-accent")).toBe(false);
  });

  it("highlights SQL Editor link as active on /sql", () => {
    renderWithRouter("/sql");

    const sidebar = screen.getByTestId("sidebar");
    const sqlLink = within(sidebar).getByText("SQL Editor").closest("a")!;

    expect(hasClass(sqlLink, "bg-sidebar-accent")).toBe(true);
  });

  it("highlights Settings link as active on /settings", () => {
    renderWithRouter("/settings");

    const sidebar = screen.getByTestId("sidebar");
    const settingsLink = within(sidebar).getByText("Settings").closest("a")!;

    expect(hasClass(settingsLink, "bg-sidebar-accent")).toBe(true);
  });
});
