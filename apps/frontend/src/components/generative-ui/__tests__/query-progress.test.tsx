import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import {
  QueryProgress,
  type ProgressStage,
  type RetryStep,
} from "../query-progress";
import { classifyError } from "../error-classification";

/* ========================================================================== */
/*  QueryProgress - State Labels                                              */
/* ========================================================================== */

describe("QueryProgress", () => {
  describe("renders correct state labels", () => {
    const stages: Array<{ stage: ProgressStage; label: string }> = [
      { stage: "generating_sql", label: "Generating SQL..." },
      { stage: "executing_query", label: "Executing query..." },
      { stage: "building_visualization", label: "Building visualization..." },
      { stage: "complete", label: "Results ready" },
      { stage: "error", label: "Query failed" },
    ];

    stages.forEach(({ stage, label }) => {
      it(`shows "${label}" for stage "${stage}"`, () => {
        render(<QueryProgress stage={stage} summaryMode={false} />);
        expect(screen.getByTestId("progress-label")).toHaveTextContent(label);
      });
    });

    it('shows "Retrying..." for retrying stage when summaryMode is off', () => {
      render(<QueryProgress stage="retrying" summaryMode={false} />);
      expect(screen.getByTestId("progress-label")).toHaveTextContent(
        "Retrying...",
      );
    });
  });

  /* ======================================================================== */
  /*  Data attributes                                                         */
  /* ======================================================================== */

  describe("data-stage attribute", () => {
    it("sets data-stage to the current stage", () => {
      render(<QueryProgress stage="executing_query" />);
      const el = screen.getByTestId("query-progress");
      expect(el).toHaveAttribute("data-stage", "executing_query");
    });

    it("maps retrying to executing_query in summary mode", () => {
      render(<QueryProgress stage="retrying" summaryMode />);
      const el = screen.getByTestId("query-progress");
      expect(el).toHaveAttribute("data-stage", "executing_query");
    });

    it("keeps retrying as retrying when summary mode is off", () => {
      render(<QueryProgress stage="retrying" summaryMode={false} />);
      const el = screen.getByTestId("query-progress");
      expect(el).toHaveAttribute("data-stage", "retrying");
    });
  });

  /* ======================================================================== */
  /*  State transitions                                                       */
  /* ======================================================================== */

  describe("state transitions update UI correctly", () => {
    it("transitions from generating_sql to executing_query", () => {
      const { rerender } = render(<QueryProgress stage="generating_sql" />);
      expect(screen.getByTestId("progress-label")).toHaveTextContent(
        "Generating SQL...",
      );

      rerender(<QueryProgress stage="executing_query" />);
      expect(screen.getByTestId("progress-label")).toHaveTextContent(
        "Executing query...",
      );
    });

    it("transitions from executing_query to building_visualization", () => {
      const { rerender } = render(<QueryProgress stage="executing_query" />);
      expect(screen.getByTestId("progress-label")).toHaveTextContent(
        "Executing query...",
      );

      rerender(<QueryProgress stage="building_visualization" />);
      expect(screen.getByTestId("progress-label")).toHaveTextContent(
        "Building visualization...",
      );
    });

    it("transitions from building_visualization to complete", () => {
      const { rerender } = render(
        <QueryProgress stage="building_visualization" />,
      );
      expect(screen.getByTestId("progress-label")).toHaveTextContent(
        "Building visualization...",
      );

      rerender(<QueryProgress stage="complete" />);
      expect(screen.getByTestId("progress-label")).toHaveTextContent(
        "Results ready",
      );
    });

    it("transitions from executing_query to error", () => {
      const { rerender } = render(<QueryProgress stage="executing_query" />);
      rerender(
        <QueryProgress stage="error" errorMessage="Query timed out" />,
      );

      expect(screen.getByTestId("progress-label")).toHaveTextContent(
        "Query failed",
      );
      expect(screen.getByTestId("progress-error-message")).toHaveTextContent(
        "Query timed out",
      );
    });
  });

  /* ======================================================================== */
  /*  Spinner                                                                 */
  /* ======================================================================== */

  describe("spinner behavior", () => {
    it("shows spinner for in-progress stages", () => {
      render(<QueryProgress stage="generating_sql" />);
      expect(screen.getByTestId("progress-spinner")).toBeInTheDocument();
    });

    it("does not show spinner for complete stage", () => {
      render(<QueryProgress stage="complete" />);
      expect(screen.queryByTestId("progress-spinner")).not.toBeInTheDocument();
    });

    it("does not show spinner for error stage", () => {
      render(<QueryProgress stage="error" />);
      expect(screen.queryByTestId("progress-spinner")).not.toBeInTheDocument();
    });
  });

  /* ======================================================================== */
  /*  Progress steps indicator                                                */
  /* ======================================================================== */

  describe("progress step indicators", () => {
    it("renders step indicators for in-progress stages", () => {
      render(<QueryProgress stage="executing_query" />);
      expect(screen.getByTestId("progress-steps")).toBeInTheDocument();
    });

    it("does not render step indicators for complete stage", () => {
      render(<QueryProgress stage="complete" />);
      expect(
        screen.queryByTestId("progress-steps"),
      ).not.toBeInTheDocument();
    });

    it("renders three step bars (generating, executing, building)", () => {
      render(<QueryProgress stage="generating_sql" />);
      expect(
        screen.getByTestId("progress-step-generating_sql"),
      ).toBeInTheDocument();
      expect(
        screen.getByTestId("progress-step-executing_query"),
      ).toBeInTheDocument();
      expect(
        screen.getByTestId("progress-step-building_visualization"),
      ).toBeInTheDocument();
    });
  });

  /* ======================================================================== */
  /*  Summary mode                                                            */
  /* ======================================================================== */

  describe("summary mode", () => {
    it("defaults to summary mode enabled", () => {
      render(<QueryProgress stage="retrying" />);
      // In summary mode, retrying should show as executing_query
      expect(screen.getByTestId("query-progress")).toHaveAttribute(
        "data-stage",
        "executing_query",
      );
      expect(screen.getByTestId("progress-label")).toHaveTextContent(
        "Executing query...",
      );
    });

    it("hides retry details in summary mode", () => {
      const retrySteps: RetryStep[] = [
        { attempt: 1, maxAttempts: 3, error: "column not found" },
      ];
      render(
        <QueryProgress
          stage="retrying"
          summaryMode
          retrySteps={retrySteps}
        />,
      );
      // Should NOT show "Retrying..." label
      expect(screen.getByTestId("progress-label")).not.toHaveTextContent(
        "Retrying",
      );
      // Should show spinner (mapped to executing_query)
      expect(screen.getByTestId("progress-spinner")).toBeInTheDocument();
      // Should NOT show retry chain
      expect(screen.queryByTestId("retry-chain")).not.toBeInTheDocument();
    });

    it("shows retry details when summary mode is off", () => {
      render(<QueryProgress stage="retrying" summaryMode={false} />);
      expect(screen.getByTestId("progress-label")).toHaveTextContent(
        "Retrying...",
      );
    });

    it("summary mode shows details only on final failure", () => {
      render(
        <QueryProgress
          stage="error"
          summaryMode
          errorMessage="column users.age does not exist"
        />,
      );
      // Error message should be shown (final failure)
      expect(screen.getByTestId("progress-error-message")).toHaveTextContent(
        "column users.age does not exist",
      );
      // Error classification should be shown
      expect(screen.getByTestId("error-classification")).toBeInTheDocument();
    });
  });

  /* ======================================================================== */
  /*  Verbose mode (retry chain)                                              */
  /* ======================================================================== */

  describe("verbose mode - retry chain", () => {
    const retrySteps: RetryStep[] = [
      {
        attempt: 1,
        maxAttempts: 3,
        error: "column not found: age",
        correctedSql: "SELECT name FROM users",
      },
      {
        attempt: 2,
        maxAttempts: 3,
        error: "ambiguous column: name",
        correctedSql: "SELECT users.name FROM users",
      },
    ];

    it("shows retry chain in verbose mode during retrying", () => {
      render(
        <QueryProgress
          stage="retrying"
          summaryMode={false}
          retrySteps={retrySteps}
        />,
      );
      expect(screen.getByTestId("retry-chain")).toBeInTheDocument();
      expect(screen.getByTestId("retry-step-1")).toBeInTheDocument();
      expect(screen.getByTestId("retry-step-2")).toBeInTheDocument();
    });

    it("displays error and corrected SQL for each retry step", () => {
      render(
        <QueryProgress
          stage="retrying"
          summaryMode={false}
          retrySteps={retrySteps}
        />,
      );
      expect(screen.getByTestId("retry-step-1")).toHaveTextContent(
        "column not found: age",
      );
      expect(screen.getByTestId("retry-step-1")).toHaveTextContent(
        "SELECT name FROM users",
      );
    });

    it("shows retry attempt numbers", () => {
      render(
        <QueryProgress
          stage="retrying"
          summaryMode={false}
          retrySteps={retrySteps}
        />,
      );
      expect(screen.getByTestId("retry-step-1")).toHaveTextContent(
        "Retry 1/3",
      );
      expect(screen.getByTestId("retry-step-2")).toHaveTextContent(
        "Retry 2/3",
      );
    });

    it("does not show retry chain when no retry steps provided", () => {
      render(
        <QueryProgress stage="retrying" summaryMode={false} />,
      );
      expect(screen.queryByTestId("retry-chain")).not.toBeInTheDocument();
    });
  });

  /* ======================================================================== */
  /*  Verbose mode - correction chain on success                              */
  /* ======================================================================== */

  describe("verbose mode - correction chain on success", () => {
    const retrySteps: RetryStep[] = [
      {
        attempt: 1,
        maxAttempts: 3,
        error: "column not found",
        correctedSql: "SELECT name FROM users",
      },
    ];

    it("shows correction chain on successful completion in verbose mode", () => {
      render(
        <QueryProgress
          stage="complete"
          summaryMode={false}
          retrySteps={retrySteps}
        />,
      );
      expect(screen.getByTestId("correction-chain")).toBeInTheDocument();
      expect(screen.getByTestId("correction-chain")).toHaveTextContent(
        "Self-corrected after 1 retry",
      );
    });

    it("does not show correction chain in summary mode on success", () => {
      render(
        <QueryProgress
          stage="complete"
          summaryMode
          retrySteps={retrySteps}
        />,
      );
      expect(
        screen.queryByTestId("correction-chain"),
      ).not.toBeInTheDocument();
    });

    it("does not show correction chain when no retries occurred", () => {
      render(
        <QueryProgress stage="complete" summaryMode={false} />,
      );
      expect(
        screen.queryByTestId("correction-chain"),
      ).not.toBeInTheDocument();
    });

    it("pluralizes retries correctly", () => {
      const multipleSteps: RetryStep[] = [
        { attempt: 1, maxAttempts: 3, error: "err1" },
        { attempt: 2, maxAttempts: 3, error: "err2" },
      ];
      render(
        <QueryProgress
          stage="complete"
          summaryMode={false}
          retrySteps={multipleSteps}
        />,
      );
      expect(screen.getByTestId("correction-chain")).toHaveTextContent(
        "Self-corrected after 2 retries",
      );
    });
  });

  /* ======================================================================== */
  /*  Error classification                                                    */
  /* ======================================================================== */

  describe("error classification on final failure", () => {
    it("shows classified error with suggestions on error stage", () => {
      render(
        <QueryProgress
          stage="error"
          errorMessage="column users.age does not exist"
        />,
      );
      expect(screen.getByTestId("error-classification")).toBeInTheDocument();
      expect(screen.getByTestId("error-category-label")).toHaveTextContent(
        "Schema Mismatch",
      );
      expect(screen.getByTestId("error-suggestions")).toBeInTheDocument();
    });

    it("classifies syntax errors", () => {
      render(
        <QueryProgress
          stage="error"
          errorMessage='syntax error near "FROM"'
        />,
      );
      expect(screen.getByTestId("error-category-label")).toHaveTextContent(
        "SQL Syntax Error",
      );
    });

    it("classifies timeout errors", () => {
      render(
        <QueryProgress
          stage="error"
          errorMessage="query timed out after 30s"
        />,
      );
      expect(screen.getByTestId("error-category-label")).toHaveTextContent(
        "Query Timeout",
      );
    });

    it("classifies connection errors", () => {
      render(
        <QueryProgress
          stage="error"
          errorMessage="connection refused to host"
        />,
      );
      expect(screen.getByTestId("error-category-label")).toHaveTextContent(
        "Connection Error",
      );
    });

    it("classifies permission errors", () => {
      render(
        <QueryProgress
          stage="error"
          errorMessage="permission denied for table users"
        />,
      );
      expect(screen.getByTestId("error-category-label")).toHaveTextContent(
        "Permission Denied",
      );
    });

    it("falls back to generic classification for unknown errors", () => {
      render(
        <QueryProgress
          stage="error"
          errorMessage="something went wrong"
        />,
      );
      expect(screen.getByTestId("error-category-label")).toHaveTextContent(
        "Query Error",
      );
    });

    it("uses provided errorClassification over auto-detection", () => {
      render(
        <QueryProgress
          stage="error"
          errorMessage="something weird"
          errorClassification={{
            category: "syntax",
            label: "Custom Error Label",
            suggestions: ["Custom suggestion"],
          }}
        />,
      );
      expect(screen.getByTestId("error-category-label")).toHaveTextContent(
        "Custom Error Label",
      );
      expect(screen.getByTestId("error-suggestions")).toHaveTextContent(
        "Custom suggestion",
      );
    });
  });

  /* ======================================================================== */
  /*  No retries needed                                                       */
  /* ======================================================================== */

  describe("no retries needed", () => {
    it("completes normally without any error UX", () => {
      const { rerender } = render(<QueryProgress stage="generating_sql" />);
      rerender(<QueryProgress stage="executing_query" />);
      rerender(<QueryProgress stage="building_visualization" />);
      rerender(<QueryProgress stage="complete" />);

      expect(screen.getByTestId("progress-label")).toHaveTextContent(
        "Results ready",
      );
      expect(screen.queryByTestId("retry-chain")).not.toBeInTheDocument();
      expect(
        screen.queryByTestId("correction-chain"),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByTestId("error-classification"),
      ).not.toBeInTheDocument();
    });
  });

  /* ======================================================================== */
  /*  Error message                                                           */
  /* ======================================================================== */

  describe("error message", () => {
    it("displays error message when stage is error", () => {
      render(
        <QueryProgress stage="error" errorMessage="Connection refused" />,
      );
      expect(screen.getByTestId("progress-error-message")).toHaveTextContent(
        "Connection refused",
      );
    });

    it("does not render error message element when no message provided", () => {
      render(<QueryProgress stage="error" />);
      expect(
        screen.queryByTestId("progress-error-message"),
      ).not.toBeInTheDocument();
    });

    it("does not render error message for non-error stages", () => {
      render(
        <QueryProgress
          stage="generating_sql"
          errorMessage="should not show"
        />,
      );
      expect(
        screen.queryByTestId("progress-error-message"),
      ).not.toBeInTheDocument();
    });
  });

  /* ======================================================================== */
  /*  Styling and design system                                               */
  /* ======================================================================== */

  describe("design system patterns", () => {
    it("applies custom className", () => {
      render(<QueryProgress stage="generating_sql" className="my-custom" />);
      expect(screen.getByTestId("query-progress").className).toContain(
        "my-custom",
      );
    });

    it("uses transition classes for smooth state changes", () => {
      render(<QueryProgress stage="generating_sql" />);
      const el = screen.getByTestId("query-progress");
      expect(el.className).toContain("transition-all");
      expect(el.className).toContain("duration-300");
    });

    it("uses rounded-lg border for card appearance", () => {
      render(<QueryProgress stage="generating_sql" />);
      const el = screen.getByTestId("query-progress");
      expect(el.className).toContain("rounded-lg");
      expect(el.className).toContain("border");
    });

    it("uses destructive colors for error state", () => {
      render(<QueryProgress stage="error" />);
      const el = screen.getByTestId("query-progress");
      expect(el.className).toContain("border-destructive");
    });

    it("uses green colors for complete state", () => {
      render(<QueryProgress stage="complete" />);
      const el = screen.getByTestId("query-progress");
      expect(el.className).toContain("border-green-500");
    });

    it("uses dark mode variants", () => {
      render(<QueryProgress stage="generating_sql" />);
      const el = screen.getByTestId("query-progress");
      expect(el.className).toContain("dark:");
    });
  });
});

/* ========================================================================== */
/*  classifyError utility                                                     */
/* ========================================================================== */

describe("classifyError", () => {
  it("classifies syntax errors", () => {
    const result = classifyError('syntax error near "SELECT"');
    expect(result.category).toBe("syntax");
    expect(result.label).toBe("SQL Syntax Error");
    expect(result.suggestions.length).toBeGreaterThan(0);
  });

  it("classifies schema errors", () => {
    const result = classifyError("column age does not exist");
    expect(result.category).toBe("schema");
    expect(result.label).toBe("Schema Mismatch");
  });

  it("classifies permission errors", () => {
    const result = classifyError("permission denied for table");
    expect(result.category).toBe("permission");
    expect(result.label).toBe("Permission Denied");
  });

  it("classifies timeout errors", () => {
    const result = classifyError("query timed out");
    expect(result.category).toBe("timeout");
    expect(result.label).toBe("Query Timeout");
  });

  it("classifies connection errors", () => {
    const result = classifyError("connection refused");
    expect(result.category).toBe("connection");
    expect(result.label).toBe("Connection Error");
  });

  it("returns unknown for unrecognized errors", () => {
    const result = classifyError("something unexpected happened");
    expect(result.category).toBe("unknown");
    expect(result.label).toBe("Query Error");
    expect(result.suggestions.length).toBeGreaterThan(0);
  });
});
