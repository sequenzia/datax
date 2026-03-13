import { Outlet } from "react-router-dom";
import { ResultsPanel } from "@/components/results";

export function ResultsCanvas() {
  return (
    <main
      data-testid="results-canvas"
      className="flex min-w-0 flex-1 flex-col bg-background"
    >
      {/* Results header */}
      <div className="flex h-14 items-center border-b border-border px-6">
        <h2 className="text-sm font-semibold">Results</h2>
      </div>

      {/* Stacked results panel */}
      <ResultsPanel />

      {/* Route content (hidden, used for page-level logic) */}
      <Outlet />
    </main>
  );
}
