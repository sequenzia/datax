import { useCallback } from "react";
import { Link } from "react-router-dom";
import {
  Upload,
  Database,
  MessageSquare,
  BarChart3,
  ChevronRight,
  ChevronLeft,
  X,
  Check,
  AlertCircle,
  Settings,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useOnboardingStore, TOTAL_STEPS } from "@/stores/onboarding-store";

const SAMPLE_QUESTIONS = [
  "Show me the top 10 rows from my data",
  "What are the column types and counts?",
  "Summarize the key statistics",
  "Find any duplicate records",
];

interface StepConfig {
  title: string;
  description: string;
  icon: React.ElementType;
}

const STEPS: StepConfig[] = [
  {
    title: "Upload Data or Connect a Database",
    description:
      "Start by uploading a CSV, Excel, Parquet, or JSON file. Or connect to an existing PostgreSQL or MySQL database.",
    icon: Upload,
  },
  {
    title: "Ask Your First Question",
    description:
      "Type a question in natural language and let the AI generate SQL queries to analyze your data.",
    icon: MessageSquare,
  },
  {
    title: "View Your Results",
    description:
      "See the query results as tables and interactive charts. Save queries and export results for later use.",
    icon: BarChart3,
  },
];

function ProgressIndicator({
  currentStep,
  onStepClick,
}: {
  currentStep: number;
  onStepClick: (step: number) => void;
}) {
  return (
    <div
      className="flex items-center justify-center gap-2"
      data-testid="progress-indicator"
    >
      {STEPS.map((step, index) => (
        <button
          key={index}
          type="button"
          onClick={() => onStepClick(index)}
          className={cn(
            "flex size-8 items-center justify-center rounded-full text-xs font-medium transition-colors",
            index === currentStep
              ? "bg-primary text-primary-foreground"
              : index < currentStep
                ? "bg-primary/20 text-primary"
                : "bg-muted text-muted-foreground",
          )}
          aria-label={`Step ${index + 1}: ${step.title}`}
          aria-current={index === currentStep ? "step" : undefined}
          data-testid={`step-indicator-${index}`}
        >
          {index < currentStep ? <Check className="size-3.5" /> : index + 1}
        </button>
      ))}
    </div>
  );
}

function StepUploadConnect({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div className="space-y-6" data-testid="step-upload-connect">
      <div className="grid gap-4 sm:grid-cols-2">
        <Link
          to="/data"
          onClick={onDismiss}
          className="group flex flex-col items-center gap-3 rounded-xl border-2 border-dashed p-6 transition-colors hover:border-primary hover:bg-accent"
          data-testid="upload-data-link"
        >
          <Upload className="size-10 text-muted-foreground transition-colors group-hover:text-primary" />
          <span className="text-sm font-medium">Upload a File</span>
          <span className="text-center text-xs text-muted-foreground">
            CSV, Excel, Parquet, JSON
          </span>
        </Link>
        <Link
          to="/data"
          onClick={onDismiss}
          className="group flex flex-col items-center gap-3 rounded-xl border-2 border-dashed p-6 transition-colors hover:border-primary hover:bg-accent"
          data-testid="connect-db-link"
        >
          <Database className="size-10 text-muted-foreground transition-colors group-hover:text-primary" />
          <span className="text-sm font-medium">Connect a Database</span>
          <span className="text-center text-xs text-muted-foreground">
            PostgreSQL, MySQL
          </span>
        </Link>
      </div>
      <p className="text-center text-xs text-muted-foreground">
        You can always add more data sources later from the Dashboard.
      </p>
    </div>
  );
}

function StepAskQuestion({
  hasProvider,
}: {
  hasProvider: boolean;
}) {
  return (
    <div className="space-y-6" data-testid="step-ask-question">
      {!hasProvider && (
        <div
          className="flex items-start gap-3 rounded-lg border border-yellow-500/50 bg-yellow-500/10 p-4"
          data-testid="provider-warning"
        >
          <AlertCircle className="mt-0.5 size-5 shrink-0 text-yellow-600 dark:text-yellow-400" />
          <div className="space-y-1">
            <p className="text-sm font-medium">AI Provider Not Configured</p>
            <p className="text-xs text-muted-foreground">
              You need to configure an AI provider before asking questions.
            </p>
            <Button variant="outline" size="sm" asChild className="mt-2">
              <Link to="/settings">
                <Settings className="size-3.5" />
                Configure Provider
              </Link>
            </Button>
          </div>
        </div>
      )}

      <div>
        <p className="mb-3 text-sm font-medium">Try one of these questions:</p>
        <div className="space-y-2">
          {SAMPLE_QUESTIONS.map((question) => (
            <div
              key={question}
              className="flex items-center gap-3 rounded-lg border px-4 py-3 text-sm transition-colors hover:bg-accent"
              data-testid="sample-question"
            >
              <MessageSquare className="size-4 shrink-0 text-muted-foreground" />
              <span>{question}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function StepViewResults() {
  return (
    <div className="space-y-6" data-testid="step-view-results">
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="flex flex-col items-center gap-2 rounded-lg border p-4 text-center">
          <div className="flex size-10 items-center justify-center rounded-full bg-primary/10">
            <BarChart3 className="size-5 text-primary" />
          </div>
          <span className="text-sm font-medium">Interactive Charts</span>
          <span className="text-xs text-muted-foreground">
            Auto-generated visualizations
          </span>
        </div>
        <div className="flex flex-col items-center gap-2 rounded-lg border p-4 text-center">
          <div className="flex size-10 items-center justify-center rounded-full bg-primary/10">
            <Database className="size-5 text-primary" />
          </div>
          <span className="text-sm font-medium">Data Tables</span>
          <span className="text-xs text-muted-foreground">
            Browse and explore results
          </span>
        </div>
        <div className="flex flex-col items-center gap-2 rounded-lg border p-4 text-center">
          <div className="flex size-10 items-center justify-center rounded-full bg-primary/10">
            <MessageSquare className="size-5 text-primary" />
          </div>
          <span className="text-sm font-medium">AI Explanations</span>
          <span className="text-xs text-muted-foreground">
            Understand your data insights
          </span>
        </div>
      </div>
      <p className="text-center text-sm text-muted-foreground">
        Results appear in the main canvas. You can save queries, export data, and
        continue the conversation for deeper analysis.
      </p>
    </div>
  );
}

export function OnboardingWizard() {
  const { isOpen, currentStep, dismiss, nextStep, prevStep, goToStep, complete } =
    useOnboardingStore();

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.target === e.currentTarget) {
        dismiss();
      }
    },
    [dismiss],
  );

  if (!isOpen) return null;

  const step = STEPS[currentStep];
  const StepIcon = step.icon;
  const isFirstStep = currentStep === 0;
  const isLastStep = currentStep === TOTAL_STEPS - 1;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      data-testid="onboarding-wizard"
      role="dialog"
      aria-modal="true"
      aria-label="Onboarding Wizard"
      onClick={handleBackdropClick}
    >
      <div className="w-full max-w-lg rounded-xl border bg-card shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between border-b p-6 pb-4">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-full bg-primary/10">
              <StepIcon className="size-5 text-primary" />
            </div>
            <div>
              <h2 className="text-lg font-semibold" data-testid="step-title">
                {step.title}
              </h2>
              <p className="text-sm text-muted-foreground">
                Step {currentStep + 1} of {TOTAL_STEPS}
              </p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={dismiss}
            aria-label="Dismiss onboarding"
            data-testid="dismiss-button"
          >
            <X className="size-4" />
          </Button>
        </div>

        {/* Body */}
        <div className="p-6">
          <p className="mb-6 text-sm text-muted-foreground">
            {step.description}
          </p>

          {currentStep === 0 && <StepUploadConnect onDismiss={dismiss} />}
          {currentStep === 1 && <StepAskQuestion hasProvider={true} />}
          {currentStep === 2 && <StepViewResults />}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t p-6 pt-4">
          <ProgressIndicator currentStep={currentStep} onStepClick={goToStep} />

          <div className="flex items-center gap-2">
            {!isFirstStep && (
              <Button
                variant="outline"
                size="sm"
                onClick={prevStep}
                data-testid="prev-button"
              >
                <ChevronLeft className="size-4" />
                Back
              </Button>
            )}
            {isFirstStep && (
              <Button
                variant="ghost"
                size="sm"
                onClick={dismiss}
                data-testid="skip-button"
              >
                Skip
              </Button>
            )}
            {isLastStep ? (
              <Button
                size="sm"
                onClick={complete}
                data-testid="complete-button"
              >
                Get Started
                <Check className="size-4" />
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={nextStep}
                data-testid="next-button"
              >
                Next
                <ChevronRight className="size-4" />
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
