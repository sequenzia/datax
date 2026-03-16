import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useDashboardList, useCreateDashboard, useAddDashboardItem } from "@/hooks/use-dashboards";
import { useCreateBookmark } from "@/hooks/use-bookmarks";
import { Check, Plus, LayoutDashboard, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export interface PinToDashboardDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  bookmarkData: {
    title?: string;
    sql?: string;
    chart_config?: Record<string, unknown>;
    result_snapshot?: Record<string, unknown>;
    source_id?: string;
    source_type?: string;
  };
}

type DialogStep = "select" | "success";

export function PinToDashboardDialog({
  open,
  onOpenChange,
  bookmarkData,
}: PinToDashboardDialogProps) {
  const [step, setStep] = useState<DialogStep>("select");
  const [title, setTitle] = useState(bookmarkData.title ?? "");
  const [selectedDashboardId, setSelectedDashboardId] = useState<string | null>(null);
  const [newDashboardName, setNewDashboardName] = useState("");
  const [showNewDashboard, setShowNewDashboard] = useState(false);
  const [isPinning, setIsPinning] = useState(false);

  const { data: dashboards, isLoading: dashboardsLoading } = useDashboardList();
  const createBookmark = useCreateBookmark();
  const createDashboard = useCreateDashboard();
  const addDashboardItem = useAddDashboardItem();

  const resetState = () => {
    setStep("select");
    setTitle(bookmarkData.title ?? "");
    setSelectedDashboardId(null);
    setNewDashboardName("");
    setShowNewDashboard(false);
    setIsPinning(false);
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) resetState();
    onOpenChange(nextOpen);
  };

  const handlePin = async () => {
    setIsPinning(true);

    try {
      // Resolve dashboard ID — create new one if needed
      let dashboardId = selectedDashboardId;
      if (showNewDashboard && newDashboardName.trim()) {
        const newDashboard = await createDashboard.mutateAsync({
          title: newDashboardName.trim(),
        });
        dashboardId = newDashboard.id;
      }

      if (!dashboardId) return;

      // Create the bookmark
      const bookmark = await createBookmark.mutateAsync({
        title: title.trim() || "Untitled",
        sql: bookmarkData.sql,
        chart_config: bookmarkData.chart_config,
        result_snapshot: bookmarkData.result_snapshot,
        source_id: bookmarkData.source_id,
        source_type: bookmarkData.source_type,
      });

      // Add bookmark to dashboard
      const itemCount = dashboards?.find((d) => d.id === dashboardId)?.items.length ?? 0;
      await addDashboardItem.mutateAsync({
        dashboardId,
        body: {
          bookmark_id: bookmark.id,
          position: itemCount,
        },
      });

      setStep("success");
      setTimeout(() => handleOpenChange(false), 1200);
    } catch {
      setIsPinning(false);
    }
  };

  const canPin =
    title.trim().length > 0 &&
    (selectedDashboardId || (showNewDashboard && newDashboardName.trim().length > 0));

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {step === "success" ? "Pinned!" : "Pin to Dashboard"}
          </DialogTitle>
        </DialogHeader>

        {step === "success" ? (
          <div className="flex flex-col items-center gap-3 py-6">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
              <Check className="h-6 w-6 text-green-600 dark:text-green-400" />
            </div>
            <p className="text-sm text-muted-foreground">
              Successfully pinned to dashboard
            </p>
          </div>
        ) : (
          <>
            <div className="space-y-4">
              {/* Title input */}
              <div className="space-y-2">
                <label className="text-sm font-medium" htmlFor="pin-title">
                  Title
                </label>
                <Input
                  id="pin-title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Enter a title for this pin"
                  maxLength={255}
                />
              </div>

              {/* Dashboard selection */}
              <div className="space-y-2">
                <label className="text-sm font-medium">Dashboard</label>
                {dashboardsLoading ? (
                  <div className="flex items-center justify-center py-4">
                    <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                  </div>
                ) : (
                  <ScrollArea className="max-h-48">
                    <div className="space-y-1">
                      {dashboards?.map((dashboard) => (
                        <button
                          key={dashboard.id}
                          onClick={() => {
                            setSelectedDashboardId(dashboard.id);
                            setShowNewDashboard(false);
                          }}
                          className={cn(
                            "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors",
                            selectedDashboardId === dashboard.id && !showNewDashboard
                              ? "bg-primary/10 text-primary"
                              : "hover:bg-muted",
                          )}
                        >
                          <LayoutDashboard className="h-4 w-4 shrink-0" />
                          <span className="truncate">{dashboard.title}</span>
                          <span className="ml-auto text-xs text-muted-foreground">
                            {dashboard.items.length} items
                          </span>
                          {selectedDashboardId === dashboard.id && !showNewDashboard && (
                            <Check className="h-4 w-4 shrink-0 text-primary" />
                          )}
                        </button>
                      ))}

                      {/* New dashboard option */}
                      <button
                        onClick={() => {
                          setShowNewDashboard(true);
                          setSelectedDashboardId(null);
                        }}
                        className={cn(
                          "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors",
                          showNewDashboard
                            ? "bg-primary/10 text-primary"
                            : "hover:bg-muted",
                        )}
                      >
                        <Plus className="h-4 w-4 shrink-0" />
                        <span>New dashboard</span>
                      </button>
                    </div>
                  </ScrollArea>
                )}

                {showNewDashboard && (
                  <Input
                    value={newDashboardName}
                    onChange={(e) => setNewDashboardName(e.target.value)}
                    placeholder="Dashboard name"
                    maxLength={255}
                    autoFocus
                  />
                )}
              </div>
            </div>

            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => handleOpenChange(false)}
                disabled={isPinning}
              >
                Cancel
              </Button>
              <Button onClick={handlePin} disabled={!canPin || isPinning}>
                {isPinning ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Pinning...
                  </>
                ) : (
                  "Pin"
                )}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
