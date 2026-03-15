/**
 * Error classification utilities for query failures.
 *
 * Categorizes error messages into actionable types with user-facing
 * labels and improvement suggestions.
 */

/** Classified error info for final failure display */
export interface ErrorClassification {
  /** Category of the error */
  category: "syntax" | "schema" | "permission" | "timeout" | "connection" | "unknown";
  /** Human-readable label */
  label: string;
  /** Actionable suggestions for the user */
  suggestions: string[];
}

const ERROR_CATEGORIES: Array<{
  pattern: RegExp;
  category: ErrorClassification["category"];
  label: string;
  suggestions: string[];
}> = [
  {
    pattern: /syntax|parse|unexpected token|near "/i,
    category: "syntax",
    label: "SQL Syntax Error",
    suggestions: [
      "Rephrase your question with simpler language",
      "Specify exact column or table names if known",
    ],
  },
  {
    pattern: /permission|denied|unauthorized|forbidden/i,
    category: "permission",
    label: "Permission Denied",
    suggestions: [
      "Check database connection credentials",
      "Verify read access to the target tables",
    ],
  },
  {
    pattern: /timeout|timed out|deadline/i,
    category: "timeout",
    label: "Query Timeout",
    suggestions: [
      "Try a simpler query or reduce the data range",
      "Add filters to narrow the result set",
    ],
  },
  {
    pattern: /connection|connect|refused|unreachable|network/i,
    category: "connection",
    label: "Connection Error",
    suggestions: [
      "Verify the database connection is active",
      "Check network connectivity to the database server",
    ],
  },
  {
    pattern: /column|table|relation|not found|does not exist|no such/i,
    category: "schema",
    label: "Schema Mismatch",
    suggestions: [
      "Check that the referenced columns exist in your dataset",
      "Try asking about available columns first",
    ],
  },
];

/** Classify an error message into a category with suggestions. */
export function classifyError(message: string): ErrorClassification {
  for (const entry of ERROR_CATEGORIES) {
    if (entry.pattern.test(message)) {
      return {
        category: entry.category,
        label: entry.label,
        suggestions: entry.suggestions,
      };
    }
  }
  return {
    category: "unknown",
    label: "Query Error",
    suggestions: [
      "Try rephrasing your question",
      "Simplify the request or break it into smaller steps",
    ],
  };
}
