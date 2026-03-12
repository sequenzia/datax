import { useEffect, useRef, useCallback } from "react";
import { EditorView, keymap, lineNumbers, highlightActiveLine, highlightActiveLineGutter } from "@codemirror/view";
import { EditorState } from "@codemirror/state";
import { sql, PostgreSQL } from "@codemirror/lang-sql";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { bracketMatching, foldGutter, indentOnInput, syntaxHighlighting, defaultHighlightStyle } from "@codemirror/language";
import { searchKeymap, highlightSelectionMatches } from "@codemirror/search";
import { autocompletion, completionKeymap } from "@codemirror/autocomplete";
import type { CompletionContext, CompletionResult } from "@codemirror/autocomplete";
import { oneDark } from "@codemirror/theme-one-dark";

interface CodeEditorProps {
  value: string;
  onChange: (value: string) => void;
  onCursorChange?: (position: { line: number; col: number }) => void;
  onExecute: () => void;
  onSave?: () => void;
  darkMode?: boolean;
  readOnly?: boolean;
  completionSource?: (context: CompletionContext) => CompletionResult | null;
}

const lightTheme = EditorView.theme({
  "&": {
    height: "100%",
    fontSize: "13px",
  },
  ".cm-scroller": {
    overflow: "auto",
    fontFamily: "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace",
  },
  ".cm-gutters": {
    backgroundColor: "var(--color-muted)",
    color: "var(--color-muted-foreground)",
    border: "none",
  },
  ".cm-activeLineGutter": {
    backgroundColor: "var(--color-accent)",
  },
  "&.cm-focused .cm-activeLine": {
    backgroundColor: "var(--color-accent)",
  },
  ".cm-matchingBracket": {
    backgroundColor: "var(--color-accent)",
    outline: "1px solid var(--color-border)",
  },
});

const darkThemeOverrides = EditorView.theme({
  "&": {
    height: "100%",
    fontSize: "13px",
  },
  ".cm-scroller": {
    overflow: "auto",
    fontFamily: "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace",
  },
});

export function CodeEditor({
  value,
  onChange,
  onCursorChange,
  onExecute,
  onSave,
  darkMode = false,
  readOnly = false,
  completionSource,
}: CodeEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  const onCursorChangeRef = useRef(onCursorChange);
  const onExecuteRef = useRef(onExecute);
  const onSaveRef = useRef(onSave);

  // Keep refs in sync with latest callbacks
  onChangeRef.current = onChange;
  onCursorChangeRef.current = onCursorChange;
  onExecuteRef.current = onExecute;
  onSaveRef.current = onSave;

  const createRunKeyBinding = useCallback(() => {
    return keymap.of([
      {
        key: "Mod-Enter",
        run: () => {
          onExecuteRef.current();
          return true;
        },
      },
      {
        key: "Mod-s",
        run: () => {
          onSaveRef.current?.();
          return true;
        },
        preventDefault: true,
      },
    ]);
  }, []);

  useEffect(() => {
    if (!containerRef.current) return;

    const updateListener = EditorView.updateListener.of((update) => {
      if (update.docChanged) {
        onChangeRef.current(update.state.doc.toString());
      }
      if (update.selectionSet || update.docChanged) {
        const pos = update.state.selection.main.head;
        const line = update.state.doc.lineAt(pos);
        onCursorChangeRef.current?.({
          line: line.number,
          col: pos - line.from + 1,
        });
      }
    });

    const themeExtension = darkMode
      ? [oneDark, darkThemeOverrides]
      : [lightTheme, syntaxHighlighting(defaultHighlightStyle, { fallback: true })];

    const state = EditorState.create({
      doc: value,
      extensions: [
        lineNumbers(),
        highlightActiveLineGutter(),
        highlightActiveLine(),
        history(),
        foldGutter(),
        indentOnInput(),
        bracketMatching(),
        autocompletion({
          override: completionSource ? [completionSource] : undefined,
          defaultKeymap: true,
        }),
        highlightSelectionMatches(),
        sql({ dialect: PostgreSQL }),
        ...themeExtension,
        EditorView.lineWrapping,
        EditorState.readOnly.of(readOnly),
        createRunKeyBinding(),
        keymap.of([
          ...defaultKeymap,
          ...historyKeymap,
          ...searchKeymap,
          ...completionKeymap,
        ]),
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
    // Re-create the editor when darkMode, readOnly, or completionSource changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [darkMode, readOnly, createRunKeyBinding, completionSource]);

  // Sync external value changes (e.g., tab switching) without recreating editor
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;

    const currentContent = view.state.doc.toString();
    if (currentContent !== value) {
      view.dispatch({
        changes: {
          from: 0,
          to: currentContent.length,
          insert: value,
        },
      });
    }
  }, [value]);

  return (
    <div
      ref={containerRef}
      data-testid="code-editor"
      className="h-full w-full overflow-hidden"
    />
  );
}
