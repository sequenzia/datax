import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { ThemeToggle } from "../theme-toggle";
import { ThemeProvider } from "@/providers/theme-provider";

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

function mockMatchMedia(prefersDark: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches:
        query === "(prefers-color-scheme: dark)" ? prefersDark : !prefersDark,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

function renderWithProvider() {
  return render(
    <ThemeProvider>
      <ThemeToggle showLabel />
    </ThemeProvider>,
  );
}

describe("ThemeToggle", () => {
  beforeEach(() => {
    // Install mock localStorage
    Object.defineProperty(window, "localStorage", {
      writable: true,
      value: localStorageMock,
    });
    localStorageMock.clear();
    vi.clearAllMocks();
    // Reset <html> classes
    document.documentElement.classList.remove("light", "dark");
    // Default to light system preference
    mockMatchMedia(false);
  });

  it("renders the toggle button", () => {
    renderWithProvider();
    expect(screen.getByTestId("theme-toggle")).toBeInTheDocument();
  });

  it("switches html class between dark and light when toggled", async () => {
    renderWithProvider();
    const user = userEvent.setup();
    const toggle = screen.getByTestId("theme-toggle");

    // Should start as light (system default mocked to light)
    expect(document.documentElement.classList.contains("light")).toBe(true);

    // Click to switch to dark
    await user.click(toggle);
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.classList.contains("light")).toBe(false);

    // Click again to switch back to light
    await user.click(toggle);
    expect(document.documentElement.classList.contains("light")).toBe(true);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("persists theme preference in localStorage", async () => {
    renderWithProvider();
    const user = userEvent.setup();
    const toggle = screen.getByTestId("theme-toggle");

    // Initially no explicit preference stored
    expect(localStorageMock.getItem("datax-theme")).toBeNull();

    // Toggle to dark
    await user.click(toggle);
    expect(localStorageMock.setItem).toHaveBeenCalledWith(
      "datax-theme",
      "dark",
    );

    // Toggle back to light
    await user.click(toggle);
    expect(localStorageMock.setItem).toHaveBeenCalledWith(
      "datax-theme",
      "light",
    );
  });

  it("reads stored theme from localStorage on mount", () => {
    localStorageMock.setItem("datax-theme", "dark");
    vi.clearAllMocks(); // Clear the setItem tracking from the line above

    renderWithProvider();

    // Should have read from localStorage
    expect(localStorageMock.getItem).toHaveBeenCalledWith("datax-theme");
    // Should apply dark class from localStorage even though system is light
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("defaults to system preference when no localStorage value", () => {
    // Mock system preference as dark
    mockMatchMedia(true);

    renderWithProvider();

    expect(document.documentElement.classList.contains("dark")).toBe(true);
    // Should have checked localStorage but found nothing
    expect(localStorageMock.getItem).toHaveBeenCalledWith("datax-theme");
    // setItem should NOT have been called (no explicit preference set)
    expect(localStorageMock.setItem).not.toHaveBeenCalled();
  });

  it("shows label text when showLabel is true", () => {
    renderWithProvider();

    // Default system theme is light, so label should show "System theme"
    expect(screen.getByText("System theme")).toBeInTheDocument();
  });
});
