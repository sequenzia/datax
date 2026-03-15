import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { SQLApproval } from "../sql-approval";

/* -------------------------------------------------------------------------- */
/*  Mocks                                                                      */
/* -------------------------------------------------------------------------- */

// Mock CodeMirror - jsdom cannot create real CM editors
vi.mock("@codemirror/view", () => {
  const lineNumbers = () => ({});

  class MockEditorView {
    _container: HTMLDivElement;
    state: { doc: { toString: () => string } };
    dispatch = vi.fn();

    constructor({ parent, state }: { parent?: HTMLElement; state?: { doc: string } }) {
      this._container = document.createElement("div");
      this._container.className = "cm-editor";
      this._container.setAttribute("data-testid", "cm-editor-mock");
      const content = document.createElement("div");
      content.className = "cm-content";
      content.textContent = state?.doc ?? "";
      this._container.appendChild(content);
      parent?.appendChild(this._container);
      const docStr = state?.doc ?? "";
      this.state = { doc: { toString: () => docStr } };
    }

    destroy() {
      this._container.remove();
    }

    static theme = () => ({});
    static lineWrapping = {};
    static updateListener = { of: () => ({}) };
  }

  return { EditorView: MockEditorView, lineNumbers };
});

vi.mock("@codemirror/state", () => {
  const EditorState = {
    create: ({ doc }: { doc: string }) => ({
      doc,
    }),
    readOnly: { of: () => ({}) },
  };
  return { EditorState };
});

vi.mock("@codemirror/lang-sql", () => ({
  sql: () => ({}),
  PostgreSQL: {},
}));

vi.mock("@codemirror/language", () => ({
  bracketMatching: () => ({}),
  syntaxHighlighting: () => ({}),
  defaultHighlightStyle: {},
}));

vi.mock("@codemirror/theme-one-dark", () => ({
  oneDark: {},
}));

/* -------------------------------------------------------------------------- */
/*  Tests                                                                      */
/* -------------------------------------------------------------------------- */

describe("SQLApproval", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders with the sql-approval test id", () => {
    render(
      <SQLApproval sqlText="SELECT 1" status="executing" respond={vi.fn()} />,
    );
    expect(screen.getByTestId("sql-approval")).toBeInTheDocument();
  });

  it("renders the SQL Preview header", () => {
    render(
      <SQLApproval sqlText="SELECT 1" status="executing" respond={vi.fn()} />,
    );
    expect(screen.getByText("SQL Preview")).toBeInTheDocument();
  });

  it("renders CodeMirror editor container", () => {
    render(
      <SQLApproval sqlText="SELECT 1" status="executing" respond={vi.fn()} />,
    );
    expect(screen.getByTestId("sql-approval-editor")).toBeInTheDocument();
  });

  it("renders Approve, Edit, and Reject buttons in executing status", () => {
    render(
      <SQLApproval
        sqlText="SELECT * FROM users"
        status="executing"
        respond={vi.fn()}
      />,
    );

    expect(screen.getByTestId("sql-approve-button")).toBeInTheDocument();
    expect(screen.getByTestId("sql-edit-button")).toBeInTheDocument();
    expect(screen.getByTestId("sql-reject-button")).toBeInTheDocument();
  });

  it("does not render action buttons in inProgress status", () => {
    render(
      <SQLApproval sqlText="" status="inProgress" />,
    );

    expect(screen.queryByTestId("sql-approve-button")).not.toBeInTheDocument();
    expect(screen.queryByTestId("sql-edit-button")).not.toBeInTheDocument();
    expect(screen.queryByTestId("sql-reject-button")).not.toBeInTheDocument();
    expect(screen.getByTestId("sql-approval-loading")).toBeInTheDocument();
  });

  it("does not render action buttons in complete status", () => {
    render(
      <SQLApproval
        sqlText="SELECT 1"
        status="complete"
        result="approved"
      />,
    );

    expect(screen.queryByTestId("sql-approve-button")).not.toBeInTheDocument();
    expect(screen.queryByTestId("sql-edit-button")).not.toBeInTheDocument();
    expect(screen.queryByTestId("sql-reject-button")).not.toBeInTheDocument();
  });

  it("Approve button calls respond with 'approved'", async () => {
    const respond = vi.fn();
    const user = userEvent.setup();
    render(
      <SQLApproval
        sqlText="SELECT * FROM users"
        status="executing"
        respond={respond}
      />,
    );

    await user.click(screen.getByTestId("sql-approve-button"));
    expect(respond).toHaveBeenCalledWith("approved");
    expect(respond).toHaveBeenCalledTimes(1);
  });

  it("Reject button calls respond with 'rejected'", async () => {
    const respond = vi.fn();
    const user = userEvent.setup();
    render(
      <SQLApproval
        sqlText="SELECT * FROM users"
        status="executing"
        respond={respond}
      />,
    );

    await user.click(screen.getByTestId("sql-reject-button"));
    expect(respond).toHaveBeenCalledWith("rejected");
    expect(respond).toHaveBeenCalledTimes(1);
  });

  it("Edit button switches to edit mode with Execute and Cancel buttons", async () => {
    const respond = vi.fn();
    const user = userEvent.setup();
    render(
      <SQLApproval
        sqlText="SELECT * FROM users"
        status="executing"
        respond={respond}
      />,
    );

    await user.click(screen.getByTestId("sql-edit-button"));

    // Original buttons should be gone
    expect(screen.queryByTestId("sql-approve-button")).not.toBeInTheDocument();
    // Edit mode buttons should be present
    expect(screen.getByTestId("sql-execute-edited-button")).toBeInTheDocument();
    expect(screen.getByTestId("sql-cancel-edit-button")).toBeInTheDocument();
  });

  it("Cancel edit returns to normal action buttons", async () => {
    const respond = vi.fn();
    const user = userEvent.setup();
    render(
      <SQLApproval
        sqlText="SELECT * FROM users"
        status="executing"
        respond={respond}
      />,
    );

    await user.click(screen.getByTestId("sql-edit-button"));
    await user.click(screen.getByTestId("sql-cancel-edit-button"));

    // Original buttons should be back
    expect(screen.getByTestId("sql-approve-button")).toBeInTheDocument();
    expect(screen.getByTestId("sql-edit-button")).toBeInTheDocument();
    expect(screen.getByTestId("sql-reject-button")).toBeInTheDocument();
  });

  it("Execute edited button calls respond with modified SQL", async () => {
    const respond = vi.fn();
    const user = userEvent.setup();
    render(
      <SQLApproval
        sqlText="SELECT * FROM users"
        status="executing"
        respond={respond}
      />,
    );

    await user.click(screen.getByTestId("sql-edit-button"));
    await user.click(screen.getByTestId("sql-execute-edited-button"));

    // Since we mock CM, the SQL stays the same
    expect(respond).toHaveBeenCalledWith("modified: SELECT * FROM users");
    expect(respond).toHaveBeenCalledTimes(1);
  });

  it("shows Approved status label when result is 'approved'", () => {
    render(
      <SQLApproval
        sqlText="SELECT 1"
        status="complete"
        result="approved"
      />,
    );

    expect(screen.getByTestId("sql-approval-status")).toHaveTextContent(
      "Approved",
    );
  });

  it("shows Rejected status label when result is 'rejected'", () => {
    render(
      <SQLApproval
        sqlText="SELECT 1"
        status="complete"
        result="rejected"
      />,
    );

    expect(screen.getByTestId("sql-approval-status")).toHaveTextContent(
      "Rejected",
    );
  });

  it("shows Executed (edited) status label when result starts with 'modified:'", () => {
    render(
      <SQLApproval
        sqlText="SELECT 1"
        status="complete"
        result="modified: SELECT 2"
      />,
    );

    expect(screen.getByTestId("sql-approval-status")).toHaveTextContent(
      "Executed (edited)",
    );
  });

  it("hides buttons after responding (approve)", async () => {
    const respond = vi.fn();
    const user = userEvent.setup();
    render(
      <SQLApproval
        sqlText="SELECT 1"
        status="executing"
        respond={respond}
      />,
    );

    await user.click(screen.getByTestId("sql-approve-button"));

    // Buttons should be hidden after responding
    expect(screen.queryByTestId("sql-approval-actions")).not.toBeInTheDocument();
  });

  it("shows Generating SQL message in inProgress status", () => {
    render(<SQLApproval sqlText="" status="inProgress" />);
    expect(screen.getByText("Generating SQL...")).toBeInTheDocument();
  });
});
