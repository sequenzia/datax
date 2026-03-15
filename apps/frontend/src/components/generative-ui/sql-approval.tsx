import { useState, useEffect, useRef, useCallback } from "react";
import { EditorView, lineNumbers } from "@codemirror/view";
import { EditorState } from "@codemirror/state";
import { sql, PostgreSQL } from "@codemirror/lang-sql";
import {
  bracketMatching,
  syntaxHighlighting,
  defaultHighlightStyle,
} from "@codemirror/language";
import { oneDark } from "@codemirror/theme-one-dark";
import { Check, Pencil, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface SQLApprovalProps {
  /** The generated SQL to preview */
  sqlText: string;
  /** Current action status from CopilotKit */
  status: "inProgress" | "executing" | "complete";
  /** Callback to send the user's response back to the agent */
  respond?: (result: string) => void;
  /** The result after the action is complete */
  result?: string;
}

const editorTheme = EditorView.theme({
  "&": {
    fontSize: "13px",
    maxHeight: "400px",
  },
  ".cm-scroller": {
    overflow: "auto",
    fontFamily:
      "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace",
  },
  ".cm-gutters": {
    backgroundColor: "var(--color-muted)",
    color: "var(--color-muted-foreground)",
    border: "none",
  },
});

const darkEditorTheme = EditorView.theme({
  "&": {
    fontSize: "13px",
    maxHeight: "400px",
  },
  ".cm-scroller": {
    overflow: "auto",
    fontFamily:
      "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace",
  },
});

/**
 * SQL Approval component rendered inline in chat.
 *
 * Displays generated SQL with syntax highlighting and provides
 * Approve / Edit / Reject buttons. Uses CopilotKit's
 * renderAndWaitForResponse pattern so the agent waits for user input.
 */
export function SQLApproval({
  sqlText,
  status,
  respond,
  result,
}: SQLApprovalProps) {
  const [editing, setEditing] = useState(false);
  const [editedSql, setEditedSql] = useState(sqlText);
  const [responded, setResponded] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const editedSqlRef = useRef(editedSql);

  // Keep ref in sync
  editedSqlRef.current = editedSql;

  // Detect dark mode from the document
  const isDark =
    typeof document !== "undefined" &&
    document.documentElement.classList.contains("dark");

  // Create/destroy CodeMirror editor
  useEffect(() => {
    if (!containerRef.current) return;

    const isReadOnly = !editing;

    const themeExtension = isDark
      ? [oneDark, darkEditorTheme]
      : [editorTheme, syntaxHighlighting(defaultHighlightStyle, { fallback: true })];

    const updateListener = EditorView.updateListener.of((update) => {
      if (update.docChanged) {
        editedSqlRef.current = update.state.doc.toString();
        setEditedSql(update.state.doc.toString());
      }
    });

    const state = EditorState.create({
      doc: editedSql,
      extensions: [
        lineNumbers(),
        bracketMatching(),
        sql({ dialect: PostgreSQL }),
        ...themeExtension,
        EditorView.lineWrapping,
        EditorState.readOnly.of(isReadOnly),
        updateListener,
      ],
    });

    const view = new EditorView({
      state,
      parent: containerRef.current,
    });

    viewRef.current = view;

    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing, isDark]);

  const handleApprove = useCallback(() => {
    if (!respond) return;
    setResponded(true);
    respond("approved");
  }, [respond]);

  const handleEdit = useCallback(() => {
    setEditing(true);
  }, []);

  const handleExecuteEdited = useCallback(() => {
    if (!respond) return;
    setResponded(true);
    setEditing(false);
    const modified = editedSqlRef.current;
    respond(`modified: ${modified}`);
  }, [respond]);

  const handleReject = useCallback(() => {
    if (!respond) return;
    setResponded(true);
    respond("rejected");
  }, [respond]);

  // Determine which label to show after response
  const getStatusLabel = (): string | null => {
    if (status === "complete" && result) {
      if (result === "approved") return "Approved";
      if (result.startsWith("modified:")) return "Executed (edited)";
      if (result === "rejected") return "Rejected";
      return result;
    }
    if (responded) {
      return "Waiting for agent...";
    }
    return null;
  };

  const statusLabel = getStatusLabel();
  const isWaiting = status === "inProgress";
  const canRespond = status === "executing" && !responded;

  return (
    <div
      data-testid="sql-approval"
      className={cn(
        "my-2 rounded-lg border bg-card text-card-foreground shadow-sm",
        "dark:border-border",
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-2">
        <span className="text-sm font-medium">SQL Preview</span>
        {statusLabel && (
          <span
            data-testid="sql-approval-status"
            className={cn(
              "rounded-full px-2 py-0.5 text-xs font-medium",
              statusLabel === "Approved" &&
                "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300",
              statusLabel === "Rejected" &&
                "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
              statusLabel === "Executed (edited)" &&
                "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
              statusLabel === "Waiting for agent..." &&
                "bg-yellow-100 text-yellow-800 dark:bg-yellow-950 dark:text-yellow-300",
            )}
          >
            {statusLabel}
          </span>
        )}
      </div>

      {/* CodeMirror editor */}
      <div
        ref={containerRef}
        data-testid="sql-approval-editor"
        className="overflow-auto"
      />

      {/* Action buttons - only shown when agent is waiting for response */}
      {canRespond && !editing && (
        <div
          data-testid="sql-approval-actions"
          className="flex items-center gap-2 border-t px-4 py-2"
        >
          <Button
            size="sm"
            onClick={handleApprove}
            data-testid="sql-approve-button"
          >
            <Check className="mr-1 size-3.5" />
            Approve
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleEdit}
            data-testid="sql-edit-button"
          >
            <Pencil className="mr-1 size-3.5" />
            Edit
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleReject}
            data-testid="sql-reject-button"
          >
            <X className="mr-1 size-3.5" />
            Reject
          </Button>
        </div>
      )}

      {/* Edit mode actions */}
      {canRespond && editing && (
        <div
          data-testid="sql-approval-edit-actions"
          className="flex items-center gap-2 border-t px-4 py-2"
        >
          <Button
            size="sm"
            onClick={handleExecuteEdited}
            data-testid="sql-execute-edited-button"
          >
            <Check className="mr-1 size-3.5" />
            Execute
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setEditing(false);
              setEditedSql(sqlText);
            }}
            data-testid="sql-cancel-edit-button"
          >
            Cancel
          </Button>
        </div>
      )}

      {/* Loading state while waiting for args */}
      {isWaiting && (
        <div
          data-testid="sql-approval-loading"
          className="px-4 py-3 text-sm text-muted-foreground"
        >
          Generating SQL...
        </div>
      )}
    </div>
  );
}
