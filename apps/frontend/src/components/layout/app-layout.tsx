import { Outlet } from "react-router-dom";
import { Sidebar } from "@/components/layout/sidebar";
import { OnboardingWizard } from "@/components/onboarding/onboarding-wizard";

export function AppLayout() {
  return (
    <div
      data-testid="app-layout"
      className="flex h-screen w-screen overflow-hidden bg-background"
    >
      <Sidebar />
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Outlet />
      </main>
      <OnboardingWizard />
    </div>
  );
}
