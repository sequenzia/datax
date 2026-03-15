import { useState, useRef, useEffect } from "react";
import {
  Pin,
  Maximize2,
  Download,
  X,
  MoreHorizontal,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useBreakpoint } from "@/hooks/use-breakpoint";
import { cn } from "@/lib/utils";

export interface ActionToolbarProps {
  /** Called when the pin/bookmark action is triggered */
  onPin?: () => void;
  /** Called when the expand/fullscreen action is triggered */
  onExpand?: () => void;
  /** Called when the export action is triggered */
  onExport?: () => void;
  /** Called when the close/dismiss action is triggered */
  onClose?: () => void;
  /** Whether the item is currently pinned */
  isPinned?: boolean;
  /** Additional CSS classes */
  className?: string;
}

interface ToolbarAction {
  key: string;
  icon: typeof Pin;
  label: string;
  onClick?: () => void;
  active?: boolean;
  testId: string;
}

/**
 * Shared action toolbar used by generative UI components.
 *
 * Desktop/tablet: renders all actions as icon buttons in a row.
 * Mobile: collapses into a "more" button that reveals actions in a dropdown.
 */
export function ActionToolbar({
  onPin,
  onExpand,
  onExport,
  onClose,
  isPinned = false,
  className,
}: ActionToolbarProps) {
  const breakpoint = useBreakpoint();
  const isMobile = breakpoint === "mobile";

  const actions: ToolbarAction[] = [];

  if (onPin) {
    actions.push({
      key: "pin",
      icon: Pin,
      label: isPinned ? "Unpin" : "Pin",
      onClick: onPin,
      active: isPinned,
      testId: "toolbar-pin",
    });
  }

  if (onExpand) {
    actions.push({
      key: "expand",
      icon: Maximize2,
      label: "Expand",
      onClick: onExpand,
      testId: "toolbar-expand",
    });
  }

  if (onExport) {
    actions.push({
      key: "export",
      icon: Download,
      label: "Export",
      onClick: onExport,
      testId: "toolbar-export",
    });
  }

  if (onClose) {
    actions.push({
      key: "close",
      icon: X,
      label: "Close",
      onClick: onClose,
      testId: "toolbar-close",
    });
  }

  if (actions.length === 0) return null;

  if (isMobile) {
    return (
      <MobileToolbar actions={actions} className={className} />
    );
  }

  return (
    <div
      data-testid="action-toolbar"
      className={cn(
        "flex items-center gap-1",
        className,
      )}
    >
      {actions.map((action) => (
        <Button
          key={action.key}
          variant="ghost"
          size="icon-xs"
          onClick={action.onClick}
          aria-label={action.label}
          data-testid={action.testId}
          className={cn(
            "text-muted-foreground hover:text-foreground",
            action.active &&
              "text-primary hover:text-primary",
          )}
        >
          <action.icon className="size-3.5" />
        </Button>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Mobile collapsed menu                                                     */
/* -------------------------------------------------------------------------- */

function MobileToolbar({
  actions,
  className,
}: {
  actions: ToolbarAction[];
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;

    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  return (
    <div ref={menuRef} className={cn("relative", className)}>
      <Button
        variant="ghost"
        size="icon-xs"
        onClick={() => setOpen((prev) => !prev)}
        aria-label="More actions"
        data-testid="toolbar-more"
      >
        <MoreHorizontal className="size-4" />
      </Button>

      {open && (
        <div
          data-testid="toolbar-mobile-menu"
          className="absolute right-0 top-full z-50 mt-1 min-w-[140px] rounded-md border bg-popover p-1 shadow-md dark:border-border"
        >
          {actions.map((action) => (
            <button
              key={action.key}
              onClick={() => {
                action.onClick?.();
                setOpen(false);
              }}
              data-testid={action.testId}
              className={cn(
                "flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm text-popover-foreground hover:bg-accent",
                action.active && "text-primary",
              )}
            >
              <action.icon className="size-3.5" />
              {action.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
