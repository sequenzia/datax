import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { OnboardingWizard } from "../onboarding-wizard";
import {
  useOnboardingStore,
  STORAGE_KEY,
} from "@/stores/onboarding-store";

// Create a mock localStorage since jsdom 28+ has issues with native localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
    }),
    clear: vi.fn(() => {
      store = {};
    }),
    get length() {
      return Object.keys(store).length;
    },
    key: vi.fn((index: number) => Object.keys(store)[index] ?? null),
  };
})();

function renderWizard() {
  return render(
    <MemoryRouter>
      <OnboardingWizard />
    </MemoryRouter>,
  );
}

describe("OnboardingWizard", () => {
  beforeEach(() => {
    // Install mock localStorage
    Object.defineProperty(window, "localStorage", {
      writable: true,
      value: localStorageMock,
    });
    localStorageMock.clear();
    vi.clearAllMocks();

    useOnboardingStore.setState({
      isOpen: true,
      currentStep: 0,
      completed: false,
      dismissed: false,
    });
  });

  describe("Rendering", () => {
    it("renders the wizard when isOpen is true", () => {
      renderWizard();
      expect(screen.getByTestId("onboarding-wizard")).toBeInTheDocument();
    });

    it("does not render when isOpen is false", () => {
      useOnboardingStore.setState({ isOpen: false });
      renderWizard();
      expect(screen.queryByTestId("onboarding-wizard")).not.toBeInTheDocument();
    });

    it("renders as a modal dialog", () => {
      renderWizard();
      const dialog = screen.getByRole("dialog");
      expect(dialog).toHaveAttribute("aria-modal", "true");
      expect(dialog).toHaveAttribute("aria-label", "Onboarding Wizard");
    });

    it("renders progress indicator with 3 steps", () => {
      renderWizard();
      const indicator = screen.getByTestId("progress-indicator");
      expect(indicator).toBeInTheDocument();
      expect(screen.getByTestId("step-indicator-0")).toBeInTheDocument();
      expect(screen.getByTestId("step-indicator-1")).toBeInTheDocument();
      expect(screen.getByTestId("step-indicator-2")).toBeInTheDocument();
    });
  });

  describe("Step 1 - Upload/Connect", () => {
    it("shows upload and connect options", () => {
      renderWizard();
      expect(screen.getByTestId("step-upload-connect")).toBeInTheDocument();
      expect(screen.getByTestId("upload-data-link")).toBeInTheDocument();
      expect(screen.getByTestId("connect-db-link")).toBeInTheDocument();
    });

    it("shows step title", () => {
      renderWizard();
      expect(screen.getByTestId("step-title")).toHaveTextContent(
        "Upload Data or Connect a Database",
      );
    });

    it("shows step counter as Step 1 of 3", () => {
      renderWizard();
      expect(screen.getByText("Step 1 of 3")).toBeInTheDocument();
    });

    it("shows skip button on first step", () => {
      renderWizard();
      expect(screen.getByTestId("skip-button")).toBeInTheDocument();
    });

    it("shows next button", () => {
      renderWizard();
      expect(screen.getByTestId("next-button")).toBeInTheDocument();
    });

    it("does not show back button on first step", () => {
      renderWizard();
      expect(screen.queryByTestId("prev-button")).not.toBeInTheDocument();
    });

    it("upload link navigates to /data", () => {
      renderWizard();
      const link = screen.getByTestId("upload-data-link");
      expect(link).toHaveAttribute("href", "/data");
    });

    it("connect link navigates to /data", () => {
      renderWizard();
      const link = screen.getByTestId("connect-db-link");
      expect(link).toHaveAttribute("href", "/data");
    });
  });

  describe("Step 2 - Ask Question", () => {
    beforeEach(() => {
      useOnboardingStore.setState({ currentStep: 1 });
    });

    it("shows sample questions", () => {
      renderWizard();
      expect(screen.getByTestId("step-ask-question")).toBeInTheDocument();
      const questions = screen.getAllByTestId("sample-question");
      expect(questions.length).toBeGreaterThanOrEqual(3);
    });

    it("shows step title for asking questions", () => {
      renderWizard();
      expect(screen.getByTestId("step-title")).toHaveTextContent(
        "Ask Your First Question",
      );
    });

    it("shows back button on second step", () => {
      renderWizard();
      expect(screen.getByTestId("prev-button")).toBeInTheDocument();
    });

    it("shows next button on second step", () => {
      renderWizard();
      expect(screen.getByTestId("next-button")).toBeInTheDocument();
    });
  });

  describe("Step 3 - View Results", () => {
    beforeEach(() => {
      useOnboardingStore.setState({ currentStep: 2 });
    });

    it("shows results explanation", () => {
      renderWizard();
      expect(screen.getByTestId("step-view-results")).toBeInTheDocument();
    });

    it("shows Get Started button on last step", () => {
      renderWizard();
      expect(screen.getByTestId("complete-button")).toBeInTheDocument();
    });

    it("does not show next button on last step", () => {
      renderWizard();
      expect(screen.queryByTestId("next-button")).not.toBeInTheDocument();
    });

    it("shows back button on last step", () => {
      renderWizard();
      expect(screen.getByTestId("prev-button")).toBeInTheDocument();
    });
  });

  describe("Navigation", () => {
    it("advances to step 2 when next is clicked", async () => {
      const user = userEvent.setup();
      renderWizard();

      await user.click(screen.getByTestId("next-button"));

      expect(screen.getByTestId("step-title")).toHaveTextContent(
        "Ask Your First Question",
      );
      expect(screen.getByText("Step 2 of 3")).toBeInTheDocument();
    });

    it("advances to step 3 when next is clicked from step 2", async () => {
      const user = userEvent.setup();
      useOnboardingStore.setState({ currentStep: 1 });
      renderWizard();

      await user.click(screen.getByTestId("next-button"));

      expect(screen.getByTestId("step-title")).toHaveTextContent(
        "View Your Results",
      );
      expect(screen.getByText("Step 3 of 3")).toBeInTheDocument();
    });

    it("goes back to step 1 when back is clicked from step 2", async () => {
      const user = userEvent.setup();
      useOnboardingStore.setState({ currentStep: 1 });
      renderWizard();

      await user.click(screen.getByTestId("prev-button"));

      expect(screen.getByTestId("step-title")).toHaveTextContent(
        "Upload Data or Connect a Database",
      );
    });

    it("navigates to a step when progress indicator dot is clicked", async () => {
      const user = userEvent.setup();
      renderWizard();

      await user.click(screen.getByTestId("step-indicator-2"));

      expect(screen.getByTestId("step-title")).toHaveTextContent(
        "View Your Results",
      );
    });

    it("completes onboarding when Get Started is clicked", async () => {
      const user = userEvent.setup();
      useOnboardingStore.setState({ currentStep: 2 });
      renderWizard();

      await user.click(screen.getByTestId("complete-button"));

      expect(
        screen.queryByTestId("onboarding-wizard"),
      ).not.toBeInTheDocument();
      expect(useOnboardingStore.getState().completed).toBe(true);
    });
  });

  describe("Dismiss", () => {
    it("closes wizard when dismiss button is clicked", async () => {
      const user = userEvent.setup();
      renderWizard();

      await user.click(screen.getByTestId("dismiss-button"));

      expect(
        screen.queryByTestId("onboarding-wizard"),
      ).not.toBeInTheDocument();
      expect(useOnboardingStore.getState().dismissed).toBe(true);
    });

    it("closes wizard when skip button is clicked", async () => {
      const user = userEvent.setup();
      renderWizard();

      await user.click(screen.getByTestId("skip-button"));

      expect(
        screen.queryByTestId("onboarding-wizard"),
      ).not.toBeInTheDocument();
    });

    it("closes wizard when backdrop is clicked", async () => {
      const user = userEvent.setup();
      renderWizard();

      const backdrop = screen.getByTestId("onboarding-wizard");
      await user.click(backdrop);

      expect(
        screen.queryByTestId("onboarding-wizard"),
      ).not.toBeInTheDocument();
    });
  });

  describe("localStorage persistence", () => {
    it("saves completion state to localStorage", async () => {
      const user = userEvent.setup();
      useOnboardingStore.setState({ currentStep: 2 });
      renderWizard();

      await user.click(screen.getByTestId("complete-button"));

      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        STORAGE_KEY,
        expect.stringContaining('"completed":true'),
      );
    });

    it("saves dismissed state to localStorage", async () => {
      const user = userEvent.setup();
      renderWizard();

      await user.click(screen.getByTestId("dismiss-button"));

      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        STORAGE_KEY,
        expect.stringContaining('"dismissed":true'),
      );
    });

    it("saves current step to localStorage on navigation", async () => {
      const user = userEvent.setup();
      renderWizard();

      await user.click(screen.getByTestId("next-button"));

      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        STORAGE_KEY,
        expect.stringContaining('"currentStep":1'),
      );
    });

    it("does not show wizard when completed in localStorage", () => {
      useOnboardingStore.setState({
        isOpen: false,
        completed: true,
        dismissed: false,
        currentStep: 2,
      });

      renderWizard();
      expect(
        screen.queryByTestId("onboarding-wizard"),
      ).not.toBeInTheDocument();
    });

    it("does not show wizard when dismissed in localStorage", () => {
      useOnboardingStore.setState({
        isOpen: false,
        completed: false,
        dismissed: true,
        currentStep: 1,
      });

      renderWizard();
      expect(
        screen.queryByTestId("onboarding-wizard"),
      ).not.toBeInTheDocument();
    });
  });

  describe("Resume from interrupted step", () => {
    it("resumes at the last step when store has currentStep set", () => {
      useOnboardingStore.setState({ currentStep: 1, isOpen: true });
      renderWizard();

      expect(screen.getByTestId("step-title")).toHaveTextContent(
        "Ask Your First Question",
      );
    });

    it("resumes at step 3 if interrupted there", () => {
      useOnboardingStore.setState({ currentStep: 2, isOpen: true });
      renderWizard();

      expect(screen.getByTestId("step-title")).toHaveTextContent(
        "View Your Results",
      );
    });
  });

  describe("Re-trigger from settings (reset)", () => {
    it("reopens the wizard and resets to step 1 after reset", () => {
      useOnboardingStore.setState({
        isOpen: false,
        completed: true,
        currentStep: 2,
      });

      useOnboardingStore.getState().reset();

      renderWizard();
      expect(screen.getByTestId("onboarding-wizard")).toBeInTheDocument();
      expect(screen.getByTestId("step-title")).toHaveTextContent(
        "Upload Data or Connect a Database",
      );
    });

    it("clears completed and dismissed flags on reset", () => {
      useOnboardingStore.setState({
        isOpen: false,
        completed: true,
        dismissed: true,
        currentStep: 2,
      });

      useOnboardingStore.getState().reset();

      const state = useOnboardingStore.getState();
      expect(state.isOpen).toBe(true);
      expect(state.completed).toBe(false);
      expect(state.dismissed).toBe(false);
      expect(state.currentStep).toBe(0);
    });
  });

  describe("Progress indicator state", () => {
    it("marks current step as active", () => {
      renderWizard();
      const step0 = screen.getByTestId("step-indicator-0");
      expect(step0).toHaveAttribute("aria-current", "step");
    });

    it("marks previous steps as completed after advancing", async () => {
      const user = userEvent.setup();
      renderWizard();

      await user.click(screen.getByTestId("next-button"));

      const step0 = screen.getByTestId("step-indicator-0");
      const step1 = screen.getByTestId("step-indicator-1");
      expect(step0).not.toHaveAttribute("aria-current", "step");
      expect(step1).toHaveAttribute("aria-current", "step");
    });
  });
});
