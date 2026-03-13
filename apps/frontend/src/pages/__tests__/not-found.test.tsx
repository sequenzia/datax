import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect } from "vitest";
import { NotFoundPage } from "../not-found";

function renderPage() {
  return render(
    <MemoryRouter>
      <NotFoundPage />
    </MemoryRouter>,
  );
}

describe("NotFoundPage", () => {
  it("renders 404 heading", () => {
    renderPage();
    expect(screen.getByText("404")).toBeInTheDocument();
  });

  it("renders page not found message", () => {
    renderPage();
    expect(screen.getByText("Page not found")).toBeInTheDocument();
  });

  it("renders a link back to dashboard", () => {
    renderPage();
    const link = screen.getByText("Back to Dashboard");
    expect(link).toBeInTheDocument();
    expect(link.closest("a")).toHaveAttribute("href", "/");
  });
});
