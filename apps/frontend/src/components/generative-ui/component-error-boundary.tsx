import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ComponentErrorBoundaryProps {
  children: ReactNode;
  /** Label shown in the error UI to identify which component failed */
  componentName?: string;
  /** Optional fallback to render instead of the default error card */
  fallback?: ReactNode;
  /** Called when the user clicks "Retry" */
  onRetry?: () => void;
  className?: string;
}

interface ComponentErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

/**
 * Error boundary designed for individual CopilotKit-rendered components.
 * A failed chart/table/profile does not crash the entire chat.
 * Provides a "Retry" action for recoverable errors.
 */
export class ComponentErrorBoundary extends Component<
  ComponentErrorBoundaryProps,
  ComponentErrorBoundaryState
> {
  constructor(props: ComponentErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(
    error: Error,
  ): ComponentErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error(
      `[ComponentErrorBoundary] ${this.props.componentName ?? "Unknown"} failed:`,
      error,
      errorInfo,
    );
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
    this.props.onRetry?.();
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      const label = this.props.componentName ?? "Component";

      return (
        <div
          data-testid="component-error-boundary"
          className={cn(
            "flex flex-col items-center justify-center gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-6 dark:border-destructive/20 dark:bg-destructive/10",
            this.props.className,
          )}
        >
          <div className="rounded-full bg-destructive/10 p-2 dark:bg-destructive/20">
            <AlertCircle className="size-5 text-destructive" />
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-foreground">
              {label} failed to render
            </p>
            <p className="mt-1 max-w-sm text-xs text-muted-foreground">
              {this.state.error?.message ?? "An unexpected error occurred."}
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={this.handleRetry}
            data-testid="error-boundary-retry"
          >
            <RefreshCw className="size-3.5" />
            Retry
          </Button>
        </div>
      );
    }

    return this.props.children;
  }
}
