import "@testing-library/jest-dom/vitest";

// Mock window.matchMedia for jsdom (not natively supported)
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

// Default window.innerWidth to desktop breakpoint (1280px) for tests.
// Individual tests can override via Object.defineProperty.
Object.defineProperty(window, "innerWidth", {
  writable: true,
  configurable: true,
  value: 1280,
});

// Mock Element.scrollIntoView for jsdom (not natively supported)
Element.prototype.scrollIntoView = () => {};
