import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { FollowUpSuggestions, type FollowUpSuggestion } from "../follow-up-suggestions";

// Mock the chat store's sendMessage
const mockSendMessage = vi.fn().mockResolvedValue(undefined);

vi.mock("@/stores/chat-store", () => ({
  useChatStore: {
    getState: () => ({
      sendMessage: mockSendMessage,
    }),
  },
}));

/* ========================================================================== */
/*  Test data                                                                  */
/* ========================================================================== */

const mockSuggestions: FollowUpSuggestion[] = [
  {
    question: "Can you break this down by region?",
    reasoning: "3 outliers detected in the data",
  },
  {
    question: "How does this trend over time?",
    reasoning: "Date columns present — time series analysis recommended",
  },
  {
    question: "Which categories have the highest concentration?",
    reasoning: "Skewed distribution — 85% in one category",
  },
];

/* ========================================================================== */
/*  Rendering tests                                                            */
/* ========================================================================== */

describe("FollowUpSuggestions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("renders chips with text and rationale", () => {
    it("renders all suggestion chips", () => {
      render(<FollowUpSuggestions suggestions={mockSuggestions} />);

      expect(screen.getByTestId("follow-up-suggestions")).toBeInTheDocument();
      expect(screen.getByTestId("suggestion-chip-0")).toBeInTheDocument();
      expect(screen.getByTestId("suggestion-chip-1")).toBeInTheDocument();
      expect(screen.getByTestId("suggestion-chip-2")).toBeInTheDocument();
    });

    it("displays question text on each chip", () => {
      render(<FollowUpSuggestions suggestions={mockSuggestions} />);

      expect(screen.getByTestId("suggestion-text-0")).toHaveTextContent(
        "Can you break this down by region?",
      );
      expect(screen.getByTestId("suggestion-text-1")).toHaveTextContent(
        "How does this trend over time?",
      );
      expect(screen.getByTestId("suggestion-text-2")).toHaveTextContent(
        "Which categories have the highest concentration?",
      );
    });

    it("displays rationale on each chip", () => {
      render(<FollowUpSuggestions suggestions={mockSuggestions} />);

      expect(screen.getByTestId("suggestion-rationale-0")).toHaveTextContent(
        "3 outliers detected in the data",
      );
      expect(screen.getByTestId("suggestion-rationale-1")).toHaveTextContent(
        "Date columns present",
      );
      expect(screen.getByTestId("suggestion-rationale-2")).toHaveTextContent(
        "Skewed distribution",
      );
    });

    it("shows the 'Suggested follow-ups' heading", () => {
      render(<FollowUpSuggestions suggestions={mockSuggestions} />);

      expect(screen.getByText("Suggested follow-ups")).toBeInTheDocument();
    });

    it("renders with 2 suggestions", () => {
      render(
        <FollowUpSuggestions suggestions={mockSuggestions.slice(0, 2)} />,
      );

      expect(screen.getByTestId("suggestion-chip-0")).toBeInTheDocument();
      expect(screen.getByTestId("suggestion-chip-1")).toBeInTheDocument();
      expect(screen.queryByTestId("suggestion-chip-2")).not.toBeInTheDocument();
    });

    it("applies custom className", () => {
      render(
        <FollowUpSuggestions
          suggestions={mockSuggestions}
          className="custom-class"
        />,
      );

      expect(
        screen.getByTestId("follow-up-suggestions").className,
      ).toContain("custom-class");
    });
  });

  /* ======================================================================== */
  /*  Click handling                                                           */
  /* ======================================================================== */

  describe("clicking chip fires message send", () => {
    it("sends the suggestion question as a message when clicked", async () => {
      const user = userEvent.setup();
      render(<FollowUpSuggestions suggestions={mockSuggestions} />);

      await user.click(screen.getByTestId("suggestion-chip-0"));

      expect(mockSendMessage).toHaveBeenCalledTimes(1);
      expect(mockSendMessage).toHaveBeenCalledWith(
        "Can you break this down by region?",
      );
    });

    it("sends the correct question for each chip", async () => {
      const user = userEvent.setup();
      render(<FollowUpSuggestions suggestions={mockSuggestions} />);

      await user.click(screen.getByTestId("suggestion-chip-1"));

      expect(mockSendMessage).toHaveBeenCalledWith(
        "How does this trend over time?",
      );
    });

    it("sends different question when second chip is clicked", async () => {
      const user = userEvent.setup();
      render(<FollowUpSuggestions suggestions={mockSuggestions} />);

      await user.click(screen.getByTestId("suggestion-chip-2"));

      expect(mockSendMessage).toHaveBeenCalledWith(
        "Which categories have the highest concentration?",
      );
    });
  });

  /* ======================================================================== */
  /*  Empty / no patterns state                                                */
  /* ======================================================================== */

  describe("no patterns detected — nothing rendered", () => {
    it("returns null for empty suggestions array", () => {
      const { container } = render(<FollowUpSuggestions suggestions={[]} />);

      expect(container.innerHTML).toBe("");
      expect(
        screen.queryByTestId("follow-up-suggestions"),
      ).not.toBeInTheDocument();
    });

    it("returns null for undefined suggestions", () => {
      const { container } = render(
        <FollowUpSuggestions
          suggestions={undefined as unknown as FollowUpSuggestion[]}
        />,
      );

      expect(container.innerHTML).toBe("");
    });
  });
});
