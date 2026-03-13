import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { TabBar } from "../tab-bar";
import type { SqlTab } from "@/stores/sql-editor-store";

function makeTab(overrides: Partial<SqlTab> = {}): SqlTab {
  return {
    id: `tab-${Math.random().toString(36).slice(2)}`,
    title: "Query 1",
    content: "",
    cursorPosition: { line: 1, col: 1 },
    isExecuting: false,
    error: null,
    results: [],
    ...overrides,
  };
}

describe("TabBar", () => {
  const defaultProps = {
    onSelectTab: vi.fn(),
    onAddTab: vi.fn(),
    onCloseTab: vi.fn(),
    onRenameTab: vi.fn(),
  };

  it("renders tab bar with tabs", () => {
    const tabs = [
      makeTab({ id: "t1", title: "Query 1" }),
      makeTab({ id: "t2", title: "Query 2" }),
    ];

    render(
      <TabBar tabs={tabs} activeTabId="t1" {...defaultProps} />,
    );

    expect(screen.getByTestId("tab-bar")).toBeInTheDocument();
    expect(screen.getByTestId("tab-t1")).toBeInTheDocument();
    expect(screen.getByTestId("tab-t2")).toBeInTheDocument();
    expect(screen.getByText("Query 1")).toBeInTheDocument();
    expect(screen.getByText("Query 2")).toBeInTheDocument();
  });

  it("calls onSelectTab when clicking a tab", async () => {
    const user = userEvent.setup();
    const onSelectTab = vi.fn();
    const tabs = [
      makeTab({ id: "t1", title: "Query 1" }),
      makeTab({ id: "t2", title: "Query 2" }),
    ];

    render(
      <TabBar
        tabs={tabs}
        activeTabId="t1"
        {...defaultProps}
        onSelectTab={onSelectTab}
      />,
    );

    await user.click(screen.getByText("Query 2"));
    expect(onSelectTab).toHaveBeenCalledWith("t2");
  });

  it("calls onAddTab when clicking add button", async () => {
    const user = userEvent.setup();
    const onAddTab = vi.fn();
    const tabs = [makeTab({ id: "t1" })];

    render(
      <TabBar
        tabs={tabs}
        activeTabId="t1"
        {...defaultProps}
        onAddTab={onAddTab}
      />,
    );

    await user.click(screen.getByTestId("add-tab-button"));
    expect(onAddTab).toHaveBeenCalled();
  });

  it("calls onCloseTab when clicking close button", async () => {
    const user = userEvent.setup();
    const onCloseTab = vi.fn();
    const tabs = [makeTab({ id: "t1", title: "Query 1" })];

    render(
      <TabBar
        tabs={tabs}
        activeTabId="t1"
        {...defaultProps}
        onCloseTab={onCloseTab}
      />,
    );

    await user.click(screen.getByTestId("tab-close-t1"));
    expect(onCloseTab).toHaveBeenCalledWith("t1");
  });

  it("allows renaming a tab via double-click", async () => {
    const user = userEvent.setup();
    const onRenameTab = vi.fn();
    const tabs = [makeTab({ id: "t1", title: "Query 1" })];

    render(
      <TabBar
        tabs={tabs}
        activeTabId="t1"
        {...defaultProps}
        onRenameTab={onRenameTab}
      />,
    );

    // Double-click to start editing
    await user.dblClick(screen.getByTestId("tab-t1"));

    const input = screen.getByTestId("tab-rename-input-t1");
    expect(input).toBeInTheDocument();
    expect(input).toHaveValue("Query 1");

    // Type new name and press Enter
    await user.clear(input);
    await user.type(input, "Customers{Enter}");

    expect(onRenameTab).toHaveBeenCalledWith("t1", "Customers");
  });

  it("shows loading indicator for executing tab", () => {
    const tabs = [makeTab({ id: "t1", isExecuting: true })];

    render(
      <TabBar tabs={tabs} activeTabId="t1" {...defaultProps} />,
    );

    expect(screen.getByTestId("tab-loading-t1")).toBeInTheDocument();
  });

  it("renders many tabs with scroll container", () => {
    const tabs = Array.from({ length: 12 }, (_, i) =>
      makeTab({ id: `t${i}`, title: `Query ${i + 1}` }),
    );

    render(
      <TabBar tabs={tabs} activeTabId="t0" {...defaultProps} />,
    );

    const scrollContainer = screen.getByTestId("tab-scroll-container");
    expect(scrollContainer.className).toContain("overflow-x-auto");
    expect(screen.getAllByTestId(/^tab-t\d+$/)).toHaveLength(12);
  });

  it("highlights the active tab differently", () => {
    const tabs = [
      makeTab({ id: "t1", title: "Query 1" }),
      makeTab({ id: "t2", title: "Query 2" }),
    ];

    render(
      <TabBar tabs={tabs} activeTabId="t1" {...defaultProps} />,
    );

    const activeTab = screen.getByTestId("tab-t1");
    const inactiveTab = screen.getByTestId("tab-t2");

    expect(activeTab.className).toContain("border-primary");
    expect(inactiveTab.className).not.toContain("border-primary");
  });
});
