import { useCallback, useEffect, useRef } from "react";
import { Sidebar } from "@/components/layout/sidebar";
import { ChatPanel } from "@/components/layout/chat-panel";
import { ResultsCanvas } from "@/components/layout/results-canvas";
import { ResizeHandle } from "@/components/layout/resize-handle";
import { BottomNavigation } from "@/components/layout/bottom-navigation";
import { OnboardingWizard } from "@/components/onboarding/onboarding-wizard";
import { useUIStore } from "@/stores/ui-store";
import { useBreakpoint, type Breakpoint } from "@/hooks/use-breakpoint";

export function AppLayout() {
  const {
    chatPanelOpen,
    chatPanelWidth,
    setChatPanelWidth,
    setSidebarOpen,
    activeMobilePanel,
  } = useUIStore();

  const breakpoint = useBreakpoint();
  const prevBreakpoint = useRef<Breakpoint>(breakpoint);

  // Auto-collapse sidebar when transitioning to tablet, restore when returning to desktop
  useEffect(() => {
    const prev = prevBreakpoint.current;
    prevBreakpoint.current = breakpoint;

    if (prev === breakpoint) return;

    if (breakpoint === "tablet") {
      setSidebarOpen(false);
    } else if (breakpoint === "desktop" && prev === "tablet") {
      setSidebarOpen(true);
    }
  }, [breakpoint, setSidebarOpen]);

  const handleResize = useCallback(
    (delta: number) => {
      setChatPanelWidth(chatPanelWidth + delta);
    },
    [chatPanelWidth, setChatPanelWidth],
  );

  // Mobile layout: single panel with bottom navigation
  if (breakpoint === "mobile") {
    return (
      <div
        data-testid="app-layout"
        className="flex h-screen w-screen flex-col overflow-hidden bg-background"
      >
        <div className="flex-1 overflow-auto">
          {activeMobilePanel === "chat" && <ChatPanel fullWidth />}
          {activeMobilePanel === "dashboard" && <ResultsCanvas />}
          {activeMobilePanel === "sql" && <ResultsCanvas />}
          {activeMobilePanel === "settings" && <ResultsCanvas />}
        </div>
        <BottomNavigation />
        <OnboardingWizard />
      </div>
    );
  }

  // Tablet layout: collapsed sidebar + stacked chat/results
  if (breakpoint === "tablet") {
    return (
      <div
        data-testid="app-layout"
        className="flex h-screen w-screen overflow-hidden bg-background"
      >
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          {chatPanelOpen && <ChatPanel fullWidth />}
          <ResultsCanvas />
        </div>
        <OnboardingWizard />
      </div>
    );
  }

  // Desktop layout: full three-panel side by side
  return (
    <div
      data-testid="app-layout"
      className="flex h-screen w-screen overflow-hidden bg-background"
    >
      <Sidebar />

      {chatPanelOpen && (
        <>
          <ChatPanel />
          <ResizeHandle onResize={handleResize} />
        </>
      )}

      <ResultsCanvas />
      <OnboardingWizard />
    </div>
  );
}
