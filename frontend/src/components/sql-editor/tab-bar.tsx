import { useRef, useState, useCallback, useEffect } from "react";
import { Plus, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import type { SqlTab } from "@/stores/sql-editor-store";

interface TabBarProps {
  tabs: SqlTab[];
  activeTabId: string;
  onSelectTab: (id: string) => void;
  onAddTab: () => void;
  onCloseTab: (id: string) => void;
  onRenameTab: (id: string, title: string) => void;
}

export function TabBar({
  tabs,
  activeTabId,
  onSelectTab,
  onAddTab,
  onCloseTab,
  onRenameTab,
}: TabBarProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [editingTabId, setEditingTabId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDoubleClick = useCallback(
    (tab: SqlTab) => {
      setEditingTabId(tab.id);
      setEditValue(tab.title);
    },
    [],
  );

  const commitRename = useCallback(() => {
    if (editingTabId && editValue.trim()) {
      onRenameTab(editingTabId, editValue.trim());
    }
    setEditingTabId(null);
  }, [editingTabId, editValue, onRenameTab]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") {
        commitRename();
      } else if (e.key === "Escape") {
        setEditingTabId(null);
      }
    },
    [commitRename],
  );

  useEffect(() => {
    if (editingTabId && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingTabId]);

  return (
    <div
      data-testid="tab-bar"
      className="flex items-center border-b border-border bg-muted/30"
    >
      <div
        ref={scrollRef}
        data-testid="tab-scroll-container"
        className="flex flex-1 items-center overflow-x-auto"
      >
        {tabs.map((tab) => (
          <div
            key={tab.id}
            data-testid={`tab-${tab.id}`}
            className={cn(
              "group flex min-w-0 shrink-0 cursor-pointer items-center gap-1.5 border-b-2 border-transparent px-3 py-2 text-xs transition-colors",
              tab.id === activeTabId
                ? "border-primary bg-background text-foreground"
                : "text-muted-foreground hover:bg-background/50 hover:text-foreground",
            )}
            onClick={() => onSelectTab(tab.id)}
            onDoubleClick={() => handleDoubleClick(tab)}
          >
            {editingTabId === tab.id ? (
              <input
                ref={inputRef}
                data-testid={`tab-rename-input-${tab.id}`}
                type="text"
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                onBlur={commitRename}
                onKeyDown={handleKeyDown}
                className="w-20 bg-transparent text-xs outline-none"
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <span className="max-w-[120px] truncate" title={tab.title}>
                {tab.title}
              </span>
            )}
            {tab.isExecuting && (
              <span
                data-testid={`tab-loading-${tab.id}`}
                className="size-2 animate-pulse rounded-full bg-primary"
              />
            )}
            <button
              data-testid={`tab-close-${tab.id}`}
              className="ml-1 rounded p-0.5 opacity-0 transition-opacity hover:bg-accent group-hover:opacity-100"
              onClick={(e) => {
                e.stopPropagation();
                onCloseTab(tab.id);
              }}
              aria-label={`Close ${tab.title}`}
            >
              <X className="size-3" />
            </button>
          </div>
        ))}
      </div>
      <Button
        variant="ghost"
        size="icon-xs"
        className="mx-1 shrink-0"
        onClick={onAddTab}
        aria-label="Add new tab"
        data-testid="add-tab-button"
      >
        <Plus className="size-3.5" />
      </Button>
    </div>
  );
}
