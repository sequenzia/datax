import { Link } from "react-router-dom";
import { AlertTriangle, X, Settings } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAiStatus } from "@/hooks/use-ai-status";

/**
 * Dismissible banner shown when the AI assistant is unavailable.
 *
 * Displays different messages depending on whether:
 * - No provider is configured (includes Settings link)
 * - The provider is unreachable (network or API error)
 *
 * Auto-clears when connectivity is restored via the store.
 */
export function AiStatusBanner() {
  const { showBanner, bannerMessage, unavailableReason, hasProvider, dismissBanner } =
    useAiStatus();

  if (!showBanner) return null;

  const isNoProvider = unavailableReason === "no_provider" || !hasProvider;

  return (
    <div
      className="flex items-center gap-2 border-b border-amber-500/30 bg-amber-50 px-4 py-2 dark:border-amber-500/20 dark:bg-amber-950/30"
      role="alert"
      data-testid="ai-status-banner"
    >
      <AlertTriangle className="size-4 shrink-0 text-amber-600 dark:text-amber-400" />
      <p className="flex-1 text-sm text-amber-800 dark:text-amber-200" data-testid="ai-status-message">
        {bannerMessage}
      </p>
      {isNoProvider && (
        <Button
          variant="ghost"
          size="sm"
          asChild
          className="gap-1 text-amber-700 hover:text-amber-900 dark:text-amber-300 dark:hover:text-amber-100"
          data-testid="ai-status-settings-link"
        >
          <Link to="/settings">
            <Settings className="size-3.5" />
            Settings
          </Link>
        </Button>
      )}
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={dismissBanner}
        className="shrink-0 text-amber-600 hover:text-amber-800 dark:text-amber-400 dark:hover:text-amber-200"
        aria-label="Dismiss banner"
        data-testid="ai-status-dismiss"
      >
        <X className="size-4" />
      </Button>
    </div>
  );
}
