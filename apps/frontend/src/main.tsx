import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryProvider } from "@/providers/query-provider";
import { ThemeProvider } from "@/providers/theme-provider";
import { CopilotKitProvider } from "@/providers/copilotkit-provider";
import { TooltipProvider } from "@/components/ui/tooltip";
import App from "@/App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryProvider>
        <CopilotKitProvider>
          <TooltipProvider delayDuration={300}>
            <App />
          </TooltipProvider>
        </CopilotKitProvider>
      </QueryProvider>
    </ThemeProvider>
  </StrictMode>,
);
