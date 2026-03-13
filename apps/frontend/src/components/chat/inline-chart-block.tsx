import { useState } from "react";
import { Maximize2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ChartRenderer, type ChartConfig } from "@/components/charts";
import { useTheme } from "@/hooks/use-theme";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface InlineChartBlockProps {
  chartConfig: ChartConfig;
  className?: string;
}

export function InlineChartBlock({ chartConfig, className }: InlineChartBlockProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const { resolvedTheme } = useTheme();

  return (
    <>
      <div
        className={cn("rounded-lg border overflow-hidden", className)}
        data-testid="inline-chart-block"
      >
        {/* Header */}
        <div className="flex items-center justify-between bg-muted/30 px-3 py-1.5">
          <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Chart
          </span>
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={() => setModalOpen(true)}
            aria-label="Expand chart"
            data-testid="expand-chart-button"
          >
            <Maximize2 className="size-3" />
          </Button>
        </div>

        {/* Compact chart */}
        <div className="h-[250px]">
          <ChartRenderer
            chartConfig={chartConfig}
            resolvedTheme={resolvedTheme}
            className="h-full border-0 rounded-none"
          />
        </div>
      </div>

      {/* Full-size modal */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-4xl max-h-[85vh]">
          <DialogHeader>
            <DialogTitle>
              {(chartConfig.layout?.title as string) ?? "Chart"}
            </DialogTitle>
          </DialogHeader>
          <div className="h-[500px]">
            <ChartRenderer
              chartConfig={chartConfig}
              resolvedTheme={resolvedTheme}
              className="h-full"
            />
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
