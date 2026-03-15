/**
 * QueryProgress - Real-time progress indicator for agent operations.
 *
 * Displays the current step of the AI agent's workflow (generating SQL,
 * executing query, building visualization, etc.) with appropriate icons
 * and smooth transitions. Supports two verbosity modes:
 *
 * - Summary mode (default): spinner during retries, details only on final failure.
 * - Verbose mode: each retry step shown in real-time, correction chain on success.
 */

import { cn } from "@/lib/utils";
import {
  Loader2,
  Code2,
  Database,
  BarChart3,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Lightbulb,
} from "lucide-react";
import {
  classifyError,
  type ErrorClassification,
} from "./error-classification";

/* -------------------------------------------------------------------------- */
/*  Progress state types                                                      */
/* -------------------------------------------------------------------------- */

export type ProgressStage =
  | "generating_sql"
  | "executing_query"
  | "building_visualization"
  | "retrying"
  | "complete"
  | "error";

/** A single retry step for the verbose retry chain */
export interface RetryStep {
  /** 1-based attempt number */
  attempt: number;
  /** Maximum retries allowed */
  maxAttempts: number;
  /** Error message from the failed attempt */
  error: string;
  /** Corrected SQL (if available) */
  correctedSql?: string;
}

export type { ErrorClassification };

export interface QueryProgressProps {
  /** Current progress stage */
  stage: ProgressStage;
  /** Hide retry details, show a single spinner instead (default: true) */
  summaryMode?: boolean;
  /** Optional error message to display when stage is "error" */
  errorMessage?: string;
  /** Retry steps for verbose mode display */
  retrySteps?: RetryStep[];
  /** Error classification for final failure */
  errorClassification?: ErrorClassification;
  /** Additional CSS classes */
  className?: string;
}

/* -------------------------------------------------------------------------- */
/*  Stage configuration                                                       */
/* -------------------------------------------------------------------------- */

interface StageConfig {
  label: string;
  icon: typeof Loader2;
  /** Whether the icon should animate (spin) */
  animate: boolean;
}

const STAGE_CONFIGS: Record<ProgressStage, StageConfig> = {
  generating_sql: {
    label: "Generating SQL...",
    icon: Code2,
    animate: false,
  },
  executing_query: {
    label: "Executing query...",
    icon: Database,
    animate: false,
  },
  building_visualization: {
    label: "Building visualization...",
    icon: BarChart3,
    animate: false,
  },
  retrying: {
    label: "Retrying...",
    icon: RefreshCw,
    animate: true,
  },
  complete: {
    label: "Results ready",
    icon: CheckCircle2,
    animate: false,
  },
  error: {
    label: "Query failed",
    icon: AlertCircle,
    animate: false,
  },
};

/** Ordered list of stages for showing completed steps */
const STAGE_ORDER: ProgressStage[] = [
  "generating_sql",
  "executing_query",
  "building_visualization",
  "complete",
];

/* -------------------------------------------------------------------------- */
/*  Sub-components                                                            */
/* -------------------------------------------------------------------------- */

function RetryChain({ steps }: { steps: RetryStep[] }) {
  return (
    <div className="mt-2 space-y-1.5" data-testid="retry-chain">
      {steps.map((step) => (
        <div
          key={step.attempt}
          className="rounded border border-amber-500/20 bg-amber-500/5 px-2.5 py-1.5 text-xs dark:border-amber-500/15 dark:bg-amber-500/10"
          data-testid={`retry-step-${step.attempt}`}
        >
          <p className="font-medium text-amber-700 dark:text-amber-400">
            <RefreshCw className="mr-1 inline-block size-3" />
            Retry {step.attempt}/{step.maxAttempts}
          </p>
          <p className="mt-0.5 text-muted-foreground">
            Error: {step.error}
          </p>
          {step.correctedSql && (
            <p className="mt-0.5 font-mono text-muted-foreground">
              Corrected: {step.correctedSql}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

function ErrorWithSuggestions({
  message,
  classification,
}: {
  message: string;
  classification: ErrorClassification;
}) {
  return (
    <div data-testid="error-classification">
      <p className="text-xs font-medium text-destructive" data-testid="error-category-label">
        {classification.label}
      </p>
      <p className="mt-0.5 text-xs text-muted-foreground" data-testid="progress-error-message">
        {message}
      </p>
      {classification.suggestions.length > 0 && (
        <div className="mt-1.5" data-testid="error-suggestions">
          {classification.suggestions.map((suggestion, i) => (
            <p
              key={i}
              className="flex items-start gap-1 text-xs text-muted-foreground"
            >
              <Lightbulb className="mt-0.5 size-3 shrink-0 text-amber-500" />
              {suggestion}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Component                                                                  */
/* -------------------------------------------------------------------------- */

export function QueryProgress({
  stage,
  summaryMode = true,
  errorMessage,
  retrySteps,
  errorClassification,
  className,
}: QueryProgressProps) {
  // In summary mode, retrying shows as a spinner with no retry details
  const effectiveStage =
    summaryMode && stage === "retrying" ? "executing_query" : stage;

  const config = STAGE_CONFIGS[effectiveStage];
  const Icon = config.icon;

  const isInProgress =
    effectiveStage !== "complete" && effectiveStage !== "error";
  const isError = effectiveStage === "error";
  const isComplete = effectiveStage === "complete";

  const currentStageIndex = STAGE_ORDER.indexOf(effectiveStage);

  // Determine if we should show the retry chain
  const showRetryChain = !summaryMode && retrySteps && retrySteps.length > 0;

  // Show correction chain on success in verbose mode
  const showCorrectionChain =
    !summaryMode && isComplete && retrySteps && retrySteps.length > 0;

  // Determine error classification for final failure
  const resolvedClassification =
    isError && errorMessage
      ? errorClassification ?? classifyError(errorMessage)
      : undefined;

  return (
    <div
      data-testid="query-progress"
      data-stage={effectiveStage}
      className={cn(
        "flex items-start gap-3 rounded-lg border px-4 py-3 transition-all duration-300",
        isError
          ? "border-destructive/30 bg-destructive/5 dark:border-destructive/20 dark:bg-destructive/10"
          : isComplete
            ? "border-green-500/30 bg-green-500/5 dark:border-green-500/20 dark:bg-green-500/10"
            : "border-border bg-muted/50 dark:bg-muted/30",
        className,
      )}
    >
      {/* Icon area */}
      <div
        className={cn(
          "mt-0.5 shrink-0",
          isError && "text-destructive",
          isComplete && "text-green-600 dark:text-green-500",
          isInProgress && "text-primary",
        )}
      >
        {isInProgress ? (
          <Loader2
            className="size-4 animate-spin"
            data-testid="progress-spinner"
          />
        ) : (
          <Icon className={cn("size-4", config.animate && "animate-spin")} />
        )}
      </div>

      {/* Content area */}
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        {/* Current step label */}
        <p
          className={cn(
            "text-sm font-medium",
            isError && "text-destructive",
            isComplete && "text-green-700 dark:text-green-400",
            isInProgress && "text-foreground",
          )}
          data-testid="progress-label"
        >
          {config.label}
        </p>

        {/* Step indicators for in-progress states */}
        {isInProgress && currentStageIndex >= 0 && (
          <div
            className="flex items-center gap-1.5"
            data-testid="progress-steps"
          >
            {STAGE_ORDER.slice(0, -1).map((s, i) => (
              <div
                key={s}
                className={cn(
                  "h-1 flex-1 rounded-full transition-colors duration-500",
                  i < currentStageIndex
                    ? "bg-primary"
                    : i === currentStageIndex
                      ? "bg-primary/60 animate-pulse"
                      : "bg-muted-foreground/20",
                )}
                data-testid={`progress-step-${s}`}
              />
            ))}
          </div>
        )}

        {/* Verbose mode: retry chain during retries */}
        {showRetryChain && !isComplete && retrySteps && (
          <RetryChain steps={retrySteps} />
        )}

        {/* Verbose mode: correction chain on success */}
        {showCorrectionChain && retrySteps && (
          <div className="mt-1" data-testid="correction-chain">
            <p className="text-xs text-muted-foreground">
              Self-corrected after {retrySteps.length}{" "}
              {retrySteps.length === 1 ? "retry" : "retries"}
            </p>
            <RetryChain steps={retrySteps} />
          </div>
        )}

        {/* Error message with classification */}
        {isError && errorMessage && resolvedClassification && (
          <ErrorWithSuggestions
            message={errorMessage}
            classification={resolvedClassification}
          />
        )}

        {/* Error message without classification (fallback) */}
        {isError && errorMessage && !resolvedClassification && (
          <p
            className="text-xs text-muted-foreground"
            data-testid="progress-error-message"
          >
            {errorMessage}
          </p>
        )}
      </div>
    </div>
  );
}
