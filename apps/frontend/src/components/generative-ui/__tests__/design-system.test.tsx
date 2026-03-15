import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  ChartSkeleton,
  TableSkeleton,
  ProfileSkeleton,
  ComponentErrorBoundary,
  ActionToolbar,
} from "../index";

/* ========================================================================== */
/*  Skeleton States                                                           */
/* ========================================================================== */

describe("Skeleton States", () => {
  describe("ChartSkeleton", () => {
    it("renders with correct test id", () => {
      render(<ChartSkeleton />);
      expect(screen.getByTestId("skeleton-chart")).toBeInTheDocument();
    });

    it("renders bar-shaped placeholders for chart area", () => {
      render(<ChartSkeleton />);
      const skeleton = screen.getByTestId("skeleton-chart");
      // Should have shimmer bars (items-end container with multiple children)
      const barContainer = skeleton.querySelector(".items-end");
      expect(barContainer).not.toBeNull();
      expect(barContainer!.children.length).toBeGreaterThanOrEqual(4);
    });

    it("applies custom className", () => {
      render(<ChartSkeleton className="custom-class" />);
      expect(screen.getByTestId("skeleton-chart").className).toContain(
        "custom-class",
      );
    });

    it("uses animate-pulse for shimmer effect", () => {
      render(<ChartSkeleton />);
      const skeleton = screen.getByTestId("skeleton-chart");
      const shimmerElements = skeleton.querySelectorAll(".animate-pulse");
      expect(shimmerElements.length).toBeGreaterThan(0);
    });
  });

  describe("TableSkeleton", () => {
    it("renders with correct test id", () => {
      render(<TableSkeleton />);
      expect(screen.getByTestId("skeleton-table")).toBeInTheDocument();
    });

    it("renders default 5 rows and 4 columns", () => {
      render(<TableSkeleton />);
      const skeleton = screen.getByTestId("skeleton-table");
      // Header row + separator + 5 data rows = at minimum 5 row containers
      const rows = skeleton.querySelectorAll(".flex.gap-3");
      // 1 header row + 5 data rows = 6
      expect(rows.length).toBe(6);
    });

    it("renders custom row and column counts", () => {
      render(<TableSkeleton rows={3} columns={6} />);
      const skeleton = screen.getByTestId("skeleton-table");
      const rows = skeleton.querySelectorAll(".flex.gap-3");
      // 1 header + 3 data rows = 4
      expect(rows.length).toBe(4);
      // Header should have 6 columns
      const headerCols = rows[0].children;
      expect(headerCols.length).toBe(6);
    });

    it("applies custom className", () => {
      render(<TableSkeleton className="my-table" />);
      expect(screen.getByTestId("skeleton-table").className).toContain(
        "my-table",
      );
    });
  });

  describe("ProfileSkeleton", () => {
    it("renders with correct test id", () => {
      render(<ProfileSkeleton />);
      expect(screen.getByTestId("skeleton-profile")).toBeInTheDocument();
    });

    it("renders summary stats grid with 3 columns", () => {
      render(<ProfileSkeleton />);
      const skeleton = screen.getByTestId("skeleton-profile");
      const grid = skeleton.querySelector(".grid-cols-3");
      expect(grid).not.toBeNull();
      expect(grid!.children.length).toBe(3);
    });

    it("renders column stat rows", () => {
      render(<ProfileSkeleton />);
      const skeleton = screen.getByTestId("skeleton-profile");
      // Column stats list has items with flex items-center
      const statRows = skeleton.querySelectorAll(".flex.items-center.gap-3");
      expect(statRows.length).toBe(4);
    });

    it("applies custom className", () => {
      render(<ProfileSkeleton className="my-profile" />);
      expect(screen.getByTestId("skeleton-profile").className).toContain(
        "my-profile",
      );
    });
  });
});

/* ========================================================================== */
/*  Component Error Boundary                                                  */
/* ========================================================================== */

describe("ComponentErrorBoundary", () => {
  // Suppress console.error from React and our boundary during error tests
  const originalConsoleError = console.error;
  beforeEach(() => {
    console.error = vi.fn();
  });

  afterEach(() => {
    console.error = originalConsoleError;
  });

  function ThrowingComponent({ message }: { message: string }) {
    throw new Error(message);
  }

  it("renders children when no error occurs", () => {
    render(
      <ComponentErrorBoundary>
        <div data-testid="child">OK</div>
      </ComponentErrorBoundary>,
    );

    expect(screen.getByTestId("child")).toBeInTheDocument();
    expect(screen.getByText("OK")).toBeInTheDocument();
  });

  it("catches errors and displays error UI instead of crashing", () => {
    render(
      <ComponentErrorBoundary componentName="Chart">
        <ThrowingComponent message="render failed" />
      </ComponentErrorBoundary>,
    );

    const errorBoundary = screen.getByTestId("component-error-boundary");
    expect(errorBoundary).toBeInTheDocument();
    expect(screen.getByText("Chart failed to render")).toBeInTheDocument();
    expect(screen.getByText("render failed")).toBeInTheDocument();
  });

  it("shows default label when componentName is not provided", () => {
    render(
      <ComponentErrorBoundary>
        <ThrowingComponent message="oops" />
      </ComponentErrorBoundary>,
    );

    expect(
      screen.getByText("Component failed to render"),
    ).toBeInTheDocument();
  });

  it("provides retry button for recoverable errors", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();

    render(
      <ComponentErrorBoundary onRetry={onRetry}>
        <ThrowingComponent message="temporary failure" />
      </ComponentErrorBoundary>,
    );

    const retryButton = screen.getByTestId("error-boundary-retry");
    expect(retryButton).toBeInTheDocument();
    expect(retryButton).toHaveTextContent("Retry");

    await user.click(retryButton);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("renders custom fallback when provided", () => {
    render(
      <ComponentErrorBoundary
        fallback={<div data-testid="custom-fallback">Custom error</div>}
      >
        <ThrowingComponent message="failed" />
      </ComponentErrorBoundary>,
    );

    expect(screen.getByTestId("custom-fallback")).toBeInTheDocument();
    expect(screen.getByText("Custom error")).toBeInTheDocument();
    expect(
      screen.queryByTestId("component-error-boundary"),
    ).not.toBeInTheDocument();
  });

  it("does not crash the outer tree when child fails", () => {
    render(
      <div data-testid="outer">
        <ComponentErrorBoundary componentName="Inner">
          <ThrowingComponent message="kaboom" />
        </ComponentErrorBoundary>
        <div data-testid="sibling">Still here</div>
      </div>,
    );

    expect(screen.getByTestId("outer")).toBeInTheDocument();
    expect(screen.getByTestId("sibling")).toBeInTheDocument();
    expect(screen.getByText("Still here")).toBeInTheDocument();
    expect(
      screen.getByText("Inner failed to render"),
    ).toBeInTheDocument();
  });

  it("applies custom className to error card", () => {
    render(
      <ComponentErrorBoundary className="my-error">
        <ThrowingComponent message="err" />
      </ComponentErrorBoundary>,
    );

    expect(
      screen.getByTestId("component-error-boundary").className,
    ).toContain("my-error");
  });
});

/* ========================================================================== */
/*  Action Toolbar                                                            */
/* ========================================================================== */

describe("ActionToolbar", () => {
  describe("Desktop rendering", () => {
    beforeEach(() => {
      // Default window.innerWidth is 1280 (desktop) from test setup
      Object.defineProperty(window, "innerWidth", {
        writable: true,
        configurable: true,
        value: 1280,
      });
    });

    it("renders all action buttons when callbacks provided", () => {
      render(
        <ActionToolbar
          onPin={vi.fn()}
          onExpand={vi.fn()}
          onExport={vi.fn()}
          onClose={vi.fn()}
        />,
      );

      expect(screen.getByTestId("action-toolbar")).toBeInTheDocument();
      expect(screen.getByTestId("toolbar-pin")).toBeInTheDocument();
      expect(screen.getByTestId("toolbar-expand")).toBeInTheDocument();
      expect(screen.getByTestId("toolbar-export")).toBeInTheDocument();
      expect(screen.getByTestId("toolbar-close")).toBeInTheDocument();
    });

    it("only renders actions that have callbacks", () => {
      render(<ActionToolbar onPin={vi.fn()} onClose={vi.fn()} />);

      expect(screen.getByTestId("toolbar-pin")).toBeInTheDocument();
      expect(screen.getByTestId("toolbar-close")).toBeInTheDocument();
      expect(screen.queryByTestId("toolbar-expand")).not.toBeInTheDocument();
      expect(screen.queryByTestId("toolbar-export")).not.toBeInTheDocument();
    });

    it("renders nothing when no callbacks provided", () => {
      const { container } = render(<ActionToolbar />);
      expect(container.innerHTML).toBe("");
    });

    it("fires onPin callback when pin button clicked", async () => {
      const onPin = vi.fn();
      const user = userEvent.setup();
      render(<ActionToolbar onPin={onPin} />);

      await user.click(screen.getByTestId("toolbar-pin"));
      expect(onPin).toHaveBeenCalledTimes(1);
    });

    it("fires onExpand callback when expand button clicked", async () => {
      const onExpand = vi.fn();
      const user = userEvent.setup();
      render(<ActionToolbar onExpand={onExpand} />);

      await user.click(screen.getByTestId("toolbar-expand"));
      expect(onExpand).toHaveBeenCalledTimes(1);
    });

    it("fires onExport callback when export button clicked", async () => {
      const onExport = vi.fn();
      const user = userEvent.setup();
      render(<ActionToolbar onExport={onExport} />);

      await user.click(screen.getByTestId("toolbar-export"));
      expect(onExport).toHaveBeenCalledTimes(1);
    });

    it("fires onClose callback when close button clicked", async () => {
      const onClose = vi.fn();
      const user = userEvent.setup();
      render(<ActionToolbar onClose={onClose} />);

      await user.click(screen.getByTestId("toolbar-close"));
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("highlights pin button when isPinned is true", () => {
      render(<ActionToolbar onPin={vi.fn()} isPinned />);

      const pinBtn = screen.getByTestId("toolbar-pin");
      expect(pinBtn.className).toContain("text-primary");
    });

    it("shows 'Unpin' label when isPinned is true", () => {
      render(<ActionToolbar onPin={vi.fn()} isPinned />);

      const pinBtn = screen.getByTestId("toolbar-pin");
      expect(pinBtn).toHaveAttribute("aria-label", "Unpin");
    });

    it("shows 'Pin' label when isPinned is false", () => {
      render(<ActionToolbar onPin={vi.fn()} isPinned={false} />);

      const pinBtn = screen.getByTestId("toolbar-pin");
      expect(pinBtn).toHaveAttribute("aria-label", "Pin");
    });
  });

  describe("Mobile rendering", () => {
    beforeEach(() => {
      Object.defineProperty(window, "innerWidth", {
        writable: true,
        configurable: true,
        value: 600,
      });
      // Trigger resize so useBreakpoint picks up the width
      window.dispatchEvent(new Event("resize"));
    });

    afterEach(() => {
      // Reset to desktop
      Object.defineProperty(window, "innerWidth", {
        writable: true,
        configurable: true,
        value: 1280,
      });
      window.dispatchEvent(new Event("resize"));
    });

    it("renders collapsed 'more' button on mobile", () => {
      render(
        <ActionToolbar
          onPin={vi.fn()}
          onExpand={vi.fn()}
          onClose={vi.fn()}
        />,
      );

      expect(screen.getByTestId("toolbar-more")).toBeInTheDocument();
      expect(screen.queryByTestId("action-toolbar")).not.toBeInTheDocument();
    });

    it("opens mobile menu on click and shows actions", async () => {
      const user = userEvent.setup();
      render(
        <ActionToolbar
          onPin={vi.fn()}
          onExpand={vi.fn()}
          onClose={vi.fn()}
        />,
      );

      await user.click(screen.getByTestId("toolbar-more"));

      const menu = screen.getByTestId("toolbar-mobile-menu");
      expect(menu).toBeInTheDocument();

      expect(
        within(menu).getByTestId("toolbar-pin"),
      ).toBeInTheDocument();
      expect(
        within(menu).getByTestId("toolbar-expand"),
      ).toBeInTheDocument();
      expect(
        within(menu).getByTestId("toolbar-close"),
      ).toBeInTheDocument();
    });

    it("fires callback and closes menu when mobile action clicked", async () => {
      const onPin = vi.fn();
      const user = userEvent.setup();
      render(<ActionToolbar onPin={onPin} onClose={vi.fn()} />);

      await user.click(screen.getByTestId("toolbar-more"));
      await user.click(screen.getByTestId("toolbar-pin"));

      expect(onPin).toHaveBeenCalledTimes(1);
      // Menu should close after action
      expect(
        screen.queryByTestId("toolbar-mobile-menu"),
      ).not.toBeInTheDocument();
    });
  });
});

/* ========================================================================== */
/*  Theme Awareness                                                           */
/* ========================================================================== */

describe("Theme Awareness", () => {
  it("skeleton components use bg-muted which adapts to theme", () => {
    render(<ChartSkeleton />);
    const skeleton = screen.getByTestId("skeleton-chart");
    const shimmerElements = skeleton.querySelectorAll(".bg-muted");
    expect(shimmerElements.length).toBeGreaterThan(0);
  });

  it("error boundary uses dark-mode-aware classes", () => {
    // Suppress error boundary console output
    const originalError = console.error;
    console.error = vi.fn();

    function Thrower() {
      throw new Error("test");
    }

    render(
      <ComponentErrorBoundary>
        <Thrower />
      </ComponentErrorBoundary>,
    );

    const errorCard = screen.getByTestId("component-error-boundary");
    // Check for dark: variant classes
    expect(errorCard.className).toContain("dark:");

    console.error = originalError;
  });

  it("action toolbar uses theme-aware text colors", () => {
    render(<ActionToolbar onPin={vi.fn()} />);

    const pinBtn = screen.getByTestId("toolbar-pin");
    // text-muted-foreground is theme-aware via CSS custom properties
    expect(pinBtn.className).toContain("text-muted-foreground");
  });
});
