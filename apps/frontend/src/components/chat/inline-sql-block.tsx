import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Copy, Check, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useSqlEditorStore } from "@/stores/sql-editor-store";

const SQL_KEYWORDS = new Set([
  "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "IN", "IS", "NULL",
  "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "FULL", "CROSS", "ON",
  "GROUP", "BY", "ORDER", "ASC", "DESC", "LIMIT", "OFFSET", "HAVING",
  "INSERT", "INTO", "VALUES", "UPDATE", "SET", "DELETE", "CREATE",
  "TABLE", "ALTER", "DROP", "INDEX", "VIEW", "AS", "DISTINCT",
  "COUNT", "SUM", "AVG", "MIN", "MAX", "CASE", "WHEN", "THEN",
  "ELSE", "END", "BETWEEN", "LIKE", "EXISTS", "UNION", "ALL",
  "WITH", "RECURSIVE", "OVER", "PARTITION", "WINDOW", "ROWS",
  "RANGE", "UNBOUNDED", "PRECEDING", "FOLLOWING", "CURRENT", "ROW",
  "CAST", "COALESCE", "NULLIF", "TRUE", "FALSE",
]);

function highlightSql(sql: string): Array<{ text: string; isKeyword: boolean }> {
  const tokens: Array<{ text: string; isKeyword: boolean }> = [];
  const regex = /(\b[A-Za-z_]+\b|[^A-Za-z_]+)/g;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(sql)) !== null) {
    tokens.push({
      text: match[0],
      isKeyword: SQL_KEYWORDS.has(match[0].toUpperCase()),
    });
  }
  return tokens;
}

interface InlineSqlBlockProps {
  sql: string;
  className?: string;
}

export function InlineSqlBlock({ sql, className }: InlineSqlBlockProps) {
  const [copied, setCopied] = useState(false);
  const navigate = useNavigate();

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [sql]);

  const handleOpenInEditor = useCallback(() => {
    useSqlEditorStore.getState().addTabWithContent(sql, "Chat Query");
    navigate("/sql");
  }, [sql, navigate]);

  return (
    <div
      className={cn("rounded-lg border bg-muted/50 overflow-hidden", className)}
      data-testid="inline-sql-block"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b bg-muted/30 px-3 py-1.5">
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          SQL
        </span>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={() => void handleCopy()}
            aria-label="Copy SQL"
            data-testid="copy-sql-button"
          >
            {copied ? (
              <Check className="size-3 text-green-500" />
            ) : (
              <Copy className="size-3" />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={handleOpenInEditor}
            aria-label="Open in SQL Editor"
            data-testid="open-in-editor-button"
          >
            <ExternalLink className="size-3" />
          </Button>
        </div>
      </div>

      {/* SQL code */}
      <pre className="overflow-x-auto p-3 text-xs leading-relaxed">
        <code>
          {highlightSql(sql).map((token, i) =>
            token.isKeyword ? (
              <span key={i} className="font-semibold text-primary">
                {token.text}
              </span>
            ) : (
              <span key={i}>{token.text}</span>
            ),
          )}
        </code>
      </pre>
    </div>
  );
}
