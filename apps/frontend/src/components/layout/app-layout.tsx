import { Suspense } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "@/components/layout/sidebar";
import { ErrorBoundary } from "@/components/error-boundary";
import { OnboardingWizard } from "@/components/onboarding/onboarding-wizard";
import { AiStatusBanner } from "@/components/ai-status-banner";

function PageLoader() {
  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <p className="text-sm text-muted-foreground">Loading...</p>
    </div>
  );
}

export function AppLayout() {
  return (
    <div
      data-testid="app-layout"
      className="flex h-screen w-screen overflow-hidden bg-background"
    >
      <Sidebar />
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <AiStatusBanner />
        <div className="min-h-0 flex-1 overflow-y-auto">
          <ErrorBoundary>
            <Suspense fallback={<PageLoader />}>
              <Outlet />
            </Suspense>
          </ErrorBoundary>
        </div>
      </main>
      <OnboardingWizard />
    </div>
  );
}
