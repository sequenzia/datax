import { create } from "zustand";

const STORAGE_KEY = "datax-settings";

/** Resolve the env-var default for verbose errors (VITE_DATAX_VERBOSE_ERRORS) */
function getEnvVerboseErrors(): boolean {
  try {
    const val = import.meta.env.VITE_DATAX_VERBOSE_ERRORS;
    if (typeof val === "string") return val === "true" || val === "1";
  } catch {
    // import.meta.env may not exist in tests
  }
  return false;
}

interface SettingsState {
  /** When true, show SQL preview before execution (default: off) */
  previewSqlBeforeExecution: boolean;
  setPreviewSqlBeforeExecution: (enabled: boolean) => void;

  /** When true, show detailed retry steps instead of a spinner (default: off or env var) */
  verboseErrors: boolean;
  setVerboseErrors: (enabled: boolean) => void;
}

function loadSettings(): Partial<SettingsState> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw) as Partial<SettingsState>;
  } catch {
    // Ignore parse errors
  }
  return {};
}

function persistSettings(state: Partial<SettingsState>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Ignore storage errors
  }
}

export const useSettingsStore = create<SettingsState>((set) => {
  const saved = loadSettings();

  return {
    previewSqlBeforeExecution: saved.previewSqlBeforeExecution ?? false,
    setPreviewSqlBeforeExecution: (enabled: boolean) => {
      set({ previewSqlBeforeExecution: enabled });
      persistSettings({ previewSqlBeforeExecution: enabled });
    },

    verboseErrors: saved.verboseErrors ?? getEnvVerboseErrors(),
    setVerboseErrors: (enabled: boolean) => {
      set({ verboseErrors: enabled });
      persistSettings({ verboseErrors: enabled });
    },
  };
});
