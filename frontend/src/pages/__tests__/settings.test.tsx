import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { SettingsPage } from "../settings";
import type { ProviderConfig } from "@/types/api";

// Mock providers hooks
const mockUseProviders = vi.fn();
const mockCreateMutate = vi.fn();
const mockDeleteMutate = vi.fn();

vi.mock("@/hooks/use-providers", () => ({
  useProviders: () => mockUseProviders(),
  useCreateProvider: () => ({
    mutate: mockCreateMutate,
    isPending: false,
  }),
  useDeleteProvider: () => ({
    mutate: mockDeleteMutate,
    isPending: false,
  }),
}));

// Mock theme hook
const mockSetTheme = vi.fn();
vi.mock("@/hooks/use-theme", () => ({
  useTheme: () => ({
    theme: "system" as const,
    resolvedTheme: "light" as const,
    setTheme: mockSetTheme,
  }),
}));

// Mock onboarding store
const mockResetOnboarding = vi.fn();
vi.mock("@/stores/onboarding-store", () => ({
  useOnboardingStore: (selector: (s: { reset: () => void }) => unknown) =>
    selector({ reset: mockResetOnboarding }),
}));

const mockProviders: ProviderConfig[] = [
  {
    id: "550e8400-e29b-41d4-a716-446655440001",
    provider_name: "openai",
    model_name: "gpt-4o",
    base_url: null,
    is_default: true,
    is_active: true,
    has_api_key: true,
    source: "ui",
    created_at: "2026-03-01T10:00:00Z",
  },
  {
    id: "550e8400-e29b-41d4-a716-446655440002",
    provider_name: "anthropic",
    model_name: "claude-sonnet-4-20250514",
    base_url: null,
    is_default: false,
    is_active: true,
    has_api_key: true,
    source: "env_var",
    created_at: "2026-03-05T14:30:00Z",
  },
];

function successState<T>(data: T) {
  return { data, isLoading: false, isError: false, refetch: vi.fn() };
}

function loadingState() {
  return {
    data: undefined,
    isLoading: true,
    isError: false,
    refetch: vi.fn(),
  };
}

function errorState() {
  return {
    data: undefined,
    isLoading: false,
    isError: true,
    refetch: vi.fn(),
  };
}

function renderSettings() {
  return render(
    <MemoryRouter initialEntries={["/settings"]}>
      <SettingsPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseProviders.mockReturnValue(successState(mockProviders));
});

describe("SettingsPage", () => {
  describe("page header", () => {
    it("renders settings heading", () => {
      renderSettings();
      expect(
        screen.getByRole("heading", { name: "Settings", level: 1 }),
      ).toBeInTheDocument();
    });

    it("renders description text", () => {
      renderSettings();
      expect(
        screen.getByText(
          "Configure AI providers, preferences, and system settings.",
        ),
      ).toBeInTheDocument();
    });
  });

  describe("all sections render", () => {
    it("renders providers, preferences, and system sections", () => {
      renderSettings();
      expect(
        screen.getByRole("heading", { name: "AI Providers" }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("heading", { name: "Preferences" }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("heading", { name: "System" }),
      ).toBeInTheDocument();
    });
  });

  describe("provider list", () => {
    it("renders provider cards from API", () => {
      renderSettings();
      const cards = screen.getAllByTestId("provider-card");
      expect(cards).toHaveLength(2);
      expect(screen.getByText("OpenAI")).toBeInTheDocument();
      expect(screen.getByText("Anthropic")).toBeInTheDocument();
    });

    it("shows model name for each provider", () => {
      renderSettings();
      expect(screen.getByText("gpt-4o")).toBeInTheDocument();
      expect(
        screen.getByText("claude-sonnet-4-20250514"),
      ).toBeInTheDocument();
    });

    it("shows default badge on default provider", () => {
      renderSettings();
      const badges = screen.getAllByTestId("default-badge");
      expect(badges).toHaveLength(1);
      expect(badges[0]).toHaveTextContent("Default");
    });

    it("shows env var badge on env_var providers", () => {
      renderSettings();
      const badges = screen.getAllByTestId("env-var-badge");
      expect(badges).toHaveLength(1);
      expect(badges[0]).toHaveTextContent("Env var");
    });

    it("shows status indicator for each provider", () => {
      renderSettings();
      const statuses = screen.getAllByTestId("provider-status");
      expect(statuses).toHaveLength(2);
    });

    it("masks API key display", () => {
      renderSettings();
      const maskedKeys = screen.getAllByText(/API Key: \*{8}/);
      expect(maskedKeys).toHaveLength(2);
    });

    it("shows delete button only for UI-configured providers (not env var)", () => {
      renderSettings();
      const deleteButtons = screen.getAllByTestId("delete-provider-button");
      expect(deleteButtons).toHaveLength(1);
    });

    it("does not show delete button for env var providers", () => {
      renderSettings();
      const cards = screen.getAllByTestId("provider-card");
      const anthropicCard = cards.find((c) =>
        c.textContent?.includes("Anthropic"),
      )!;
      expect(
        within(anthropicCard).queryByTestId("delete-provider-button"),
      ).not.toBeInTheDocument();
    });
  });

  describe("add provider form", () => {
    it("shows add provider button initially", () => {
      renderSettings();
      expect(screen.getByTestId("add-provider-button")).toBeInTheDocument();
    });

    it("shows form when add button is clicked", async () => {
      const user = userEvent.setup();
      renderSettings();
      await user.click(screen.getByTestId("add-provider-button"));
      expect(screen.getByTestId("add-provider-form")).toBeInTheDocument();
      expect(screen.getByLabelText("Provider")).toBeInTheDocument();
      expect(screen.getByLabelText("Model")).toBeInTheDocument();
      expect(screen.getByLabelText("API Key")).toBeInTheDocument();
    });

    it("submits form to create provider", async () => {
      const user = userEvent.setup();
      renderSettings();
      await user.click(screen.getByTestId("add-provider-button"));

      const apiKeyInput = screen.getByLabelText("API Key");
      await user.type(apiKeyInput, "sk-test-key-1234567890");

      const submitButton = screen.getByRole("button", {
        name: "Add Provider",
      });
      await user.click(submitButton);

      expect(mockCreateMutate).toHaveBeenCalledTimes(1);
      const callArgs = mockCreateMutate.mock.calls[0];
      expect(callArgs[0]).toEqual(
        expect.objectContaining({
          provider_name: "openai",
          api_key: "sk-test-key-1234567890",
        }),
      );
    });

    it("masks API key input by default", async () => {
      const user = userEvent.setup();
      renderSettings();
      await user.click(screen.getByTestId("add-provider-button"));

      const apiKeyInput = screen.getByLabelText("API Key");
      expect(apiKeyInput).toHaveAttribute("type", "password");
    });

    it("toggles API key visibility", async () => {
      const user = userEvent.setup();
      renderSettings();
      await user.click(screen.getByTestId("add-provider-button"));

      const apiKeyInput = screen.getByLabelText("API Key");
      expect(apiKeyInput).toHaveAttribute("type", "password");

      const toggleBtn = screen.getByTestId("toggle-api-key-visibility");
      await user.click(toggleBtn);
      expect(apiKeyInput).toHaveAttribute("type", "text");

      await user.click(toggleBtn);
      expect(apiKeyInput).toHaveAttribute("type", "password");
    });

    it("validates empty API key", async () => {
      const user = userEvent.setup();
      renderSettings();
      await user.click(screen.getByTestId("add-provider-button"));

      const submitButton = screen.getByRole("button", {
        name: "Add Provider",
      });
      await user.click(submitButton);

      expect(screen.getByTestId("validation-error")).toHaveTextContent(
        "API key is required.",
      );
      expect(mockCreateMutate).not.toHaveBeenCalled();
    });

    it("validates short API key", async () => {
      const user = userEvent.setup();
      renderSettings();
      await user.click(screen.getByTestId("add-provider-button"));

      const apiKeyInput = screen.getByLabelText("API Key");
      await user.type(apiKeyInput, "short");

      const submitButton = screen.getByRole("button", {
        name: "Add Provider",
      });
      await user.click(submitButton);

      expect(screen.getByTestId("validation-error")).toHaveTextContent(
        "API key appears too short",
      );
      expect(mockCreateMutate).not.toHaveBeenCalled();
    });

    it("hides form when cancel button is clicked", async () => {
      const user = userEvent.setup();
      renderSettings();
      await user.click(screen.getByTestId("add-provider-button"));
      expect(screen.getByTestId("add-provider-form")).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Cancel" }));
      expect(
        screen.queryByTestId("add-provider-form"),
      ).not.toBeInTheDocument();
    });
  });

  describe("delete provider", () => {
    it("shows confirmation dialog when delete is clicked", async () => {
      const user = userEvent.setup();
      renderSettings();

      const deleteButton = screen.getByTestId("delete-provider-button");
      await user.click(deleteButton);

      expect(
        screen.getByTestId("delete-confirm-dialog"),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Are you sure you want to delete/),
      ).toBeInTheDocument();
    });

    it("calls delete mutation on confirm", async () => {
      const user = userEvent.setup();
      renderSettings();

      await user.click(screen.getByTestId("delete-provider-button"));
      await user.click(screen.getByTestId("confirm-delete"));

      expect(mockDeleteMutate).toHaveBeenCalledTimes(1);
      expect(mockDeleteMutate.mock.calls[0][0]).toBe(
        "550e8400-e29b-41d4-a716-446655440001",
      );
    });

    it("closes dialog on cancel", async () => {
      const user = userEvent.setup();
      renderSettings();

      await user.click(screen.getByTestId("delete-provider-button"));
      expect(
        screen.getByTestId("delete-confirm-dialog"),
      ).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Cancel" }));
      expect(
        screen.queryByTestId("delete-confirm-dialog"),
      ).not.toBeInTheDocument();
    });
  });

  describe("empty state", () => {
    it("shows empty state when no providers exist", () => {
      mockUseProviders.mockReturnValue(successState([]));
      renderSettings();
      expect(
        screen.getByTestId("providers-empty-state"),
      ).toBeInTheDocument();
      expect(
        screen.getByText("No AI providers configured yet."),
      ).toBeInTheDocument();
    });
  });

  describe("error handling", () => {
    it("shows error message when providers fail to load", () => {
      mockUseProviders.mockReturnValue(errorState());
      renderSettings();
      expect(
        screen.getByText("Failed to load providers."),
      ).toBeInTheDocument();
    });

    it("shows retry button on error", async () => {
      const mockRefetch = vi.fn();
      mockUseProviders.mockReturnValue({
        ...errorState(),
        refetch: mockRefetch,
      });
      renderSettings();

      const retryButton = screen.getByRole("button", { name: "Retry" });
      const user = userEvent.setup();
      await user.click(retryButton);

      expect(mockRefetch).toHaveBeenCalledTimes(1);
    });
  });

  describe("loading state", () => {
    it("shows loading skeletons while providers load", () => {
      mockUseProviders.mockReturnValue(loadingState());
      const { container } = renderSettings();
      const skeletons = container.querySelectorAll(".animate-pulse");
      expect(skeletons.length).toBeGreaterThan(0);
    });
  });

  describe("preferences section", () => {
    it("renders theme select with current value", () => {
      renderSettings();
      const select = screen.getByTestId("theme-select");
      expect(select).toBeInTheDocument();
      expect(select).toHaveValue("system");
    });

    it("calls setTheme when theme is changed", async () => {
      const user = userEvent.setup();
      renderSettings();
      const select = screen.getByTestId("theme-select");
      await user.selectOptions(select, "dark");
      expect(mockSetTheme).toHaveBeenCalledWith("dark");
    });
  });

  describe("system section", () => {
    it("renders storage path input", () => {
      renderSettings();
      expect(screen.getByTestId("storage-path-input")).toBeInTheDocument();
    });

    it("renders re-trigger onboarding button", () => {
      renderSettings();
      expect(
        screen.getByTestId("reset-onboarding-button"),
      ).toBeInTheDocument();
    });

    it("calls reset onboarding when button is clicked", async () => {
      const user = userEvent.setup();
      renderSettings();
      await user.click(screen.getByTestId("reset-onboarding-button"));
      expect(mockResetOnboarding).toHaveBeenCalledTimes(1);
    });
  });
});
