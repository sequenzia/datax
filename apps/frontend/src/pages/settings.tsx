import { useState, useCallback } from "react";
import {
  Settings,
  Plus,
  Trash2,
  Eye,
  EyeOff,
  AlertCircle,
  CheckCircle,
  Star,
  Shield,
  RotateCcw,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/hooks/use-theme";
import { useOnboardingStore } from "@/stores/onboarding-store";
import { useSettingsStore } from "@/stores/settings-store";
import {
  useProviders,
  useCreateProvider,
  useDeleteProvider,
} from "@/hooks/use-providers";
import type { ProviderConfig, ProviderCreateRequest } from "@/types/api";
import type { Theme } from "@/contexts/theme-context";

const PROVIDER_OPTIONS = [
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "gemini", label: "Gemini" },
  { value: "openai_compatible", label: "OpenAI Compatible" },
] as const;

const DEFAULT_MODELS: Record<string, string> = {
  openai: "gpt-4o",
  anthropic: "claude-sonnet-4-20250514",
  gemini: "gemini-2.0-flash",
  openai_compatible: "",
};

function providerDisplayName(name: string): string {
  const option = PROVIDER_OPTIONS.find((o) => o.value === name);
  return option?.label ?? name;
}

function SectionError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-destructive/50 bg-destructive/10 p-4">
      <AlertCircle className="size-5 shrink-0 text-destructive" />
      <p className="text-sm text-destructive">{message}</p>
      <Button
        variant="outline"
        size="sm"
        onClick={onRetry}
        className="ml-auto"
      >
        Retry
      </Button>
    </div>
  );
}

function Toast({
  message,
  type,
  onClose,
}: {
  message: string;
  type: "success" | "error";
  onClose: () => void;
}) {
  return (
    <div
      data-testid="toast"
      className={`fixed right-4 top-4 z-50 flex items-center gap-2 rounded-lg border px-4 py-3 shadow-lg ${
        type === "error"
          ? "border-destructive/50 bg-destructive/10 text-destructive"
          : "border-green-500/50 bg-green-50 text-green-800 dark:bg-green-950 dark:text-green-200"
      }`}
    >
      {type === "error" ? (
        <AlertCircle className="size-4" />
      ) : (
        <CheckCircle className="size-4" />
      )}
      <p className="text-sm">{message}</p>
      <button
        onClick={onClose}
        className="ml-2 text-xs opacity-60 hover:opacity-100"
        aria-label="Dismiss"
      >
        x
      </button>
    </div>
  );
}

function useToast() {
  const [toast, setToast] = useState<{
    message: string;
    type: "success" | "error";
  } | null>(null);

  const showToast = useCallback(
    (message: string, type: "success" | "error") => {
      setToast({ message, type });
      setTimeout(() => setToast(null), 5000);
    },
    [],
  );

  const dismissToast = useCallback(() => setToast(null), []);

  return { toast, showToast, dismissToast };
}

function DeleteConfirmDialog({
  providerName,
  onConfirm,
  onCancel,
}: {
  providerName: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div
      data-testid="delete-confirm-dialog"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
    >
      <div className="mx-4 w-full max-w-md rounded-lg border bg-card p-6 shadow-xl">
        <h3 className="text-lg font-semibold">Delete Provider</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          Are you sure you want to delete the{" "}
          <strong>{providerDisplayName(providerName)}</strong> provider? This
          action cannot be undone.
        </p>
        <div className="mt-4 flex justify-end gap-3">
          <Button variant="outline" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={onConfirm}
            data-testid="confirm-delete"
          >
            Delete
          </Button>
        </div>
      </div>
    </div>
  );
}

function AddProviderForm({
  onSuccess,
  onError,
}: {
  onSuccess: (msg: string) => void;
  onError: (msg: string) => void;
}) {
  const createMutation = useCreateProvider();
  const [isOpen, setIsOpen] = useState(false);
  const [providerName, setProviderName] = useState("openai");
  const [modelName, setModelName] = useState(DEFAULT_MODELS["openai"]);
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  const resetForm = () => {
    setProviderName("openai");
    setModelName(DEFAULT_MODELS["openai"]);
    setApiKey("");
    setBaseUrl("");
    setIsDefault(false);
    setShowApiKey(false);
    setValidationError(null);
  };

  const handleProviderChange = (value: string) => {
    setProviderName(value);
    setModelName(DEFAULT_MODELS[value] ?? "");
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setValidationError(null);

    if (!apiKey.trim()) {
      setValidationError("API key is required.");
      return;
    }

    if (apiKey.trim().length < 8) {
      setValidationError(
        "API key appears too short. Please check and try again.",
      );
      return;
    }

    if (providerName === "openai_compatible" && !baseUrl.trim()) {
      setValidationError("Base URL is required for OpenAI Compatible provider.");
      return;
    }

    const body: ProviderCreateRequest = {
      provider_name: providerName,
      model_name: modelName.trim() || DEFAULT_MODELS[providerName] || "default",
      api_key: apiKey.trim(),
      is_default: isDefault,
    };
    if (providerName === "openai_compatible" && baseUrl.trim()) {
      body.base_url = baseUrl.trim();
    }

    createMutation.mutate(body, {
      onSuccess: () => {
        onSuccess(
          `${providerDisplayName(providerName)} provider added successfully.`,
        );
        resetForm();
        setIsOpen(false);
      },
      onError: (err) => {
        onError(err instanceof Error ? err.message : "Failed to add provider.");
      },
    });
  };

  if (!isOpen) {
    return (
      <Button
        variant="outline"
        size="sm"
        onClick={() => setIsOpen(true)}
        data-testid="add-provider-button"
      >
        <Plus className="size-4" />
        Add Provider
      </Button>
    );
  }

  return (
    <Card data-testid="add-provider-form">
      <CardHeader className="pb-4">
        <CardTitle className="text-sm">Add AI Provider</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="provider-name"
              className="mb-1 block text-sm font-medium"
            >
              Provider
            </label>
            <select
              id="provider-name"
              value={providerName}
              onChange={(e) => handleProviderChange(e.target.value)}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            >
              {PROVIDER_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label
              htmlFor="model-name"
              className="mb-1 block text-sm font-medium"
            >
              Model
            </label>
            <input
              id="model-name"
              type="text"
              value={modelName}
              onChange={(e) => setModelName(e.target.value)}
              placeholder="e.g. gpt-4o"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            />
          </div>

          <div>
            <label
              htmlFor="api-key"
              className="mb-1 block text-sm font-medium"
            >
              API Key
            </label>
            <div className="relative">
              <input
                id="api-key"
                type={showApiKey ? "text" : "password"}
                value={apiKey}
                onChange={(e) => {
                  setApiKey(e.target.value);
                  if (validationError) setValidationError(null);
                }}
                placeholder="sk-..."
                className="w-full rounded-md border bg-background px-3 py-2 pr-10 text-sm"
                autoComplete="off"
              />
              <button
                type="button"
                onClick={() => setShowApiKey(!showApiKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                aria-label={showApiKey ? "Hide API key" : "Show API key"}
                data-testid="toggle-api-key-visibility"
              >
                {showApiKey ? (
                  <EyeOff className="size-4" />
                ) : (
                  <Eye className="size-4" />
                )}
              </button>
            </div>
          </div>

          {providerName === "openai_compatible" && (
            <div>
              <label
                htmlFor="base-url"
                className="mb-1 block text-sm font-medium"
              >
                Base URL
              </label>
              <input
                id="base-url"
                type="url"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://api.example.com/v1"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              />
            </div>
          )}

          <div className="flex items-center gap-2">
            <input
              id="is-default"
              type="checkbox"
              checked={isDefault}
              onChange={(e) => setIsDefault(e.target.checked)}
              className="rounded border"
            />
            <label htmlFor="is-default" className="text-sm">
              Set as default provider
            </label>
          </div>

          {validationError && (
            <p
              className="text-sm text-destructive"
              data-testid="validation-error"
            >
              {validationError}
            </p>
          )}

          <div className="flex gap-2">
            <Button
              type="submit"
              size="sm"
              disabled={createMutation.isPending}
            >
              {createMutation.isPending ? "Adding..." : "Add Provider"}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                resetForm();
                setIsOpen(false);
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function ProviderCard({
  provider,
  onDelete,
}: {
  provider: ProviderConfig;
  onDelete: (id: string, name: string) => void;
}) {
  const isEnvVar = provider.source === "env_var";

  return (
    <Card data-testid="provider-card">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle className="text-sm">
              {providerDisplayName(provider.provider_name)}
            </CardTitle>
            {provider.is_default && (
              <span
                className="flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary"
                data-testid="default-badge"
              >
                <Star className="size-3" />
                Default
              </span>
            )}
            {isEnvVar && (
              <span
                className="flex items-center gap-1 rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700 dark:bg-blue-950 dark:text-blue-300"
                data-testid="env-var-badge"
              >
                <Shield className="size-3" />
                Env var
              </span>
            )}
          </div>
          <span
            className={`inline-block size-2.5 rounded-full ${provider.is_active ? "bg-green-500" : "bg-gray-400"}`}
            title={provider.is_active ? "Active" : "Inactive"}
            data-testid="provider-status"
          />
        </div>
        <CardDescription>{provider.model_name}</CardDescription>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">
            API Key: {provider.has_api_key ? "********" : "Not set"}
          </span>
          {!isEnvVar && (
            <Button
              variant="ghost"
              size="icon-xs"
              onClick={() =>
                onDelete(provider.id, provider.provider_name)
              }
              aria-label={`Delete ${providerDisplayName(provider.provider_name)} provider`}
              data-testid="delete-provider-button"
            >
              <Trash2 className="size-3.5 text-destructive" />
            </Button>
          )}
        </div>
        {provider.base_url && (
          <p className="mt-1 truncate text-xs text-muted-foreground">
            {provider.base_url}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function ProvidersSection() {
  const { data: providers, isLoading, isError, refetch } = useProviders();
  const deleteMutation = useDeleteProvider();
  const { toast, showToast, dismissToast } = useToast();
  const [deleteTarget, setDeleteTarget] = useState<{
    id: string;
    name: string;
  } | null>(null);

  const handleDeleteRequest = (id: string, name: string) => {
    setDeleteTarget({ id, name });
  };

  const handleDeleteConfirm = () => {
    if (!deleteTarget) return;
    deleteMutation.mutate(deleteTarget.id, {
      onSuccess: () => {
        showToast(
          `${providerDisplayName(deleteTarget.name)} provider deleted.`,
          "success",
        );
        setDeleteTarget(null);
      },
      onError: (err) => {
        showToast(
          err instanceof Error ? err.message : "Failed to delete provider.",
          "error",
        );
        setDeleteTarget(null);
      },
    });
  };

  return (
    <section aria-labelledby="providers-heading">
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={dismissToast}
        />
      )}
      {deleteTarget && (
        <DeleteConfirmDialog
          providerName={deleteTarget.name}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      <div className="mb-4 flex items-center justify-between">
        <h2 id="providers-heading" className="text-lg font-semibold">
          AI Providers
        </h2>
      </div>

      {isLoading && (
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 2 }).map((_, i) => (
            <div
              key={i}
              className="h-32 animate-pulse rounded-xl border bg-muted/50"
            />
          ))}
        </div>
      )}

      {isError && (
        <SectionError
          message="Failed to load providers."
          onRetry={() => void refetch()}
        />
      )}

      {providers && providers.length === 0 && (
        <Card className="border-dashed" data-testid="providers-empty-state">
          <CardContent className="flex flex-col items-center gap-3 py-8">
            <Settings className="size-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              No AI providers configured yet.
            </p>
            <p className="text-xs text-muted-foreground">
              Add a provider to start using AI features.
            </p>
          </CardContent>
        </Card>
      )}

      {providers && providers.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2">
          {providers.map((provider) => (
            <ProviderCard
              key={provider.id}
              provider={provider}
              onDelete={handleDeleteRequest}
            />
          ))}
        </div>
      )}

      <div className="mt-4">
        <AddProviderForm
          onSuccess={(msg) => showToast(msg, "success")}
          onError={(msg) => showToast(msg, "error")}
        />
      </div>
    </section>
  );
}

function PreferencesSection() {
  const { theme, setTheme } = useTheme();
  const previewSql = useSettingsStore((s) => s.previewSqlBeforeExecution);
  const setPreviewSql = useSettingsStore((s) => s.setPreviewSqlBeforeExecution);
  const verboseErrors = useSettingsStore((s) => s.verboseErrors);
  const setVerboseErrors = useSettingsStore((s) => s.setVerboseErrors);

  return (
    <section aria-labelledby="preferences-heading">
      <h2 id="preferences-heading" className="mb-4 text-lg font-semibold">
        Preferences
      </h2>
      <Card>
        <CardContent className="space-y-4 pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Theme</p>
              <p className="text-xs text-muted-foreground">
                Choose your preferred color scheme.
              </p>
            </div>
            <select
              value={theme}
              onChange={(e) => setTheme(e.target.value as Theme)}
              className="rounded-md border bg-background px-3 py-1.5 text-sm"
              aria-label="Theme selection"
              data-testid="theme-select"
            >
              <option value="system">System</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
          </div>

          <div className="flex items-center justify-between border-t pt-4">
            <div>
              <p className="text-sm font-medium">Preview SQL before execution</p>
              <p className="text-xs text-muted-foreground">
                Review and approve generated SQL queries before they run.
              </p>
            </div>
            <input
              type="checkbox"
              checked={previewSql}
              onChange={(e) => setPreviewSql(e.target.checked)}
              className="rounded border"
              aria-label="Preview SQL before execution"
              data-testid="preview-sql-toggle"
            />
          </div>

          <div className="flex items-center justify-between border-t pt-4">
            <div>
              <p className="text-sm font-medium">Verbose error details</p>
              <p className="text-xs text-muted-foreground">
                Show AI self-correction steps during query retries.
              </p>
            </div>
            <input
              type="checkbox"
              checked={verboseErrors}
              onChange={(e) => setVerboseErrors(e.target.checked)}
              className="rounded border"
              aria-label="Verbose error details"
              data-testid="verbose-errors-toggle"
            />
          </div>
        </CardContent>
      </Card>
    </section>
  );
}

function SystemSection() {
  const resetOnboarding = useOnboardingStore((s) => s.reset);
  const [storagePath, setStoragePath] = useState("./data");

  return (
    <section aria-labelledby="system-heading">
      <h2 id="system-heading" className="mb-4 text-lg font-semibold">
        System
      </h2>
      <Card>
        <CardContent className="space-y-4 pt-6">
          <div>
            <label
              htmlFor="storage-path"
              className="mb-1 block text-sm font-medium"
            >
              Data Storage Path
            </label>
            <p className="mb-2 text-xs text-muted-foreground">
              Directory where uploaded files are stored locally.
            </p>
            <input
              id="storage-path"
              type="text"
              value={storagePath}
              onChange={(e) => setStoragePath(e.target.value)}
              className="w-full max-w-md rounded-md border bg-background px-3 py-2 text-sm"
              data-testid="storage-path-input"
            />
          </div>

          <div className="flex items-center justify-between border-t pt-4">
            <div>
              <p className="text-sm font-medium">Onboarding Wizard</p>
              <p className="text-xs text-muted-foreground">
                Re-run the setup wizard to reconfigure your environment.
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={resetOnboarding}
              data-testid="reset-onboarding-button"
            >
              <RotateCcw className="size-4" />
              Re-trigger
            </Button>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}

export function SettingsPage() {
  return (
    <div className="space-y-8 p-6">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="mt-1 text-muted-foreground">
          Configure AI providers, preferences, and system settings.
        </p>
      </div>

      <ProvidersSection />
      <PreferencesSection />
      <SystemSection />
    </div>
  );
}
