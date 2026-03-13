import { create } from "zustand";

const STORAGE_KEY = "datax-onboarding";

interface OnboardingState {
  /** Whether the wizard is currently visible */
  isOpen: boolean;
  /** Current step index (0-based) */
  currentStep: number;
  /** Whether onboarding has been completed at least once */
  completed: boolean;
  /** Whether the wizard was explicitly dismissed (skipped) */
  dismissed: boolean;

  /** Open the wizard (from settings re-trigger or first visit) */
  open: () => void;
  /** Close/dismiss the wizard without completing */
  dismiss: () => void;
  /** Move to the next step */
  nextStep: () => void;
  /** Move to the previous step */
  prevStep: () => void;
  /** Go to a specific step */
  goToStep: (step: number) => void;
  /** Mark onboarding as complete */
  complete: () => void;
  /** Reset onboarding state (re-trigger from settings) */
  reset: () => void;
}

const TOTAL_STEPS = 3;

function loadPersistedState(): {
  currentStep: number;
  completed: boolean;
  dismissed: boolean;
} {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as {
        currentStep?: number;
        completed?: boolean;
        dismissed?: boolean;
      };
      return {
        currentStep:
          typeof parsed.currentStep === "number" ? parsed.currentStep : 0,
        completed: parsed.completed === true,
        dismissed: parsed.dismissed === true,
      };
    }
  } catch {
    // Ignore parse errors, fall through to defaults
  }
  return { currentStep: 0, completed: false, dismissed: false };
}

function persistState(state: {
  currentStep: number;
  completed: boolean;
  dismissed: boolean;
}): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Ignore storage errors (e.g. quota exceeded)
  }
}

const persisted = loadPersistedState();

export const useOnboardingStore = create<OnboardingState>((set) => ({
  // Show wizard on first visit (not completed and not dismissed)
  isOpen: !persisted.completed && !persisted.dismissed,
  currentStep: persisted.currentStep,
  completed: persisted.completed,
  dismissed: persisted.dismissed,

  open: () =>
    set((state) => {
      const newState = { ...state, isOpen: true };
      return newState;
    }),

  dismiss: () =>
    set((state) => {
      const updates = {
        isOpen: false,
        dismissed: true,
      };
      persistState({
        currentStep: state.currentStep,
        completed: state.completed,
        dismissed: true,
      });
      return updates;
    }),

  nextStep: () =>
    set((state) => {
      const nextStep = Math.min(state.currentStep + 1, TOTAL_STEPS - 1);
      persistState({
        currentStep: nextStep,
        completed: state.completed,
        dismissed: state.dismissed,
      });
      return { currentStep: nextStep };
    }),

  prevStep: () =>
    set((state) => {
      const prevStep = Math.max(state.currentStep - 1, 0);
      persistState({
        currentStep: prevStep,
        completed: state.completed,
        dismissed: state.dismissed,
      });
      return { currentStep: prevStep };
    }),

  goToStep: (step: number) =>
    set((state) => {
      const clampedStep = Math.max(0, Math.min(step, TOTAL_STEPS - 1));
      persistState({
        currentStep: clampedStep,
        completed: state.completed,
        dismissed: state.dismissed,
      });
      return { currentStep: clampedStep };
    }),

  complete: () =>
    set(() => {
      const updates = {
        isOpen: false,
        completed: true,
        currentStep: TOTAL_STEPS - 1,
      };
      persistState({
        currentStep: TOTAL_STEPS - 1,
        completed: true,
        dismissed: false,
      });
      return updates;
    }),

  reset: () =>
    set(() => {
      const updates = {
        isOpen: true,
        currentStep: 0,
        completed: false,
        dismissed: false,
      };
      persistState({
        currentStep: 0,
        completed: false,
        dismissed: false,
      });
      return updates;
    }),
}));

export { TOTAL_STEPS, STORAGE_KEY };
