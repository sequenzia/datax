import { LayoutDashboard, MessageSquare, Code2, Settings } from "lucide-react";
import { cn } from "@/lib/utils";
import { useUIStore, type MobilePanel } from "@/stores/ui-store";

const navItems: { panel: MobilePanel; icon: typeof LayoutDashboard; label: string }[] = [
  { panel: "dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { panel: "chat", icon: MessageSquare, label: "Chat" },
  { panel: "sql", icon: Code2, label: "SQL" },
  { panel: "settings", icon: Settings, label: "Settings" },
];

export function BottomNavigation() {
  const { activeMobilePanel, setActiveMobilePanel } = useUIStore();

  return (
    <nav
      data-testid="bottom-navigation"
      className="flex h-14 shrink-0 items-center border-t border-border bg-background"
      role="navigation"
      aria-label="Mobile navigation"
    >
      {navItems.map(({ panel, icon: Icon, label }) => (
        <button
          key={panel}
          onClick={() => setActiveMobilePanel(panel)}
          className={cn(
            "flex flex-1 flex-col items-center justify-center gap-0.5 py-1 text-xs transition-colors",
            activeMobilePanel === panel
              ? "text-primary"
              : "text-muted-foreground hover:text-foreground",
          )}
          aria-label={label}
          aria-current={activeMobilePanel === panel ? "page" : undefined}
          data-testid={`bottom-nav-${panel}`}
        >
          <Icon className="size-5" />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  );
}
