/** Context-aware SQL autocomplete completions from schema registry. */

import type {
  Completion,
  CompletionContext,
  CompletionResult,
} from "@codemirror/autocomplete";
import type { SchemaColumn } from "@/types/api";

/** Represents a table (or dataset virtual table) with its columns. */
export interface TableSchema {
  tableName: string;
  columns: SchemaColumn[];
}

/** SQL keywords for autocomplete. */
const SQL_KEYWORDS: string[] = [
  "SELECT",
  "FROM",
  "WHERE",
  "JOIN",
  "LEFT",
  "RIGHT",
  "INNER",
  "OUTER",
  "FULL",
  "CROSS",
  "ON",
  "AND",
  "OR",
  "NOT",
  "IN",
  "EXISTS",
  "BETWEEN",
  "LIKE",
  "ILIKE",
  "IS",
  "NULL",
  "AS",
  "ORDER",
  "BY",
  "GROUP",
  "HAVING",
  "LIMIT",
  "OFFSET",
  "UNION",
  "ALL",
  "DISTINCT",
  "INSERT",
  "INTO",
  "VALUES",
  "UPDATE",
  "SET",
  "DELETE",
  "CREATE",
  "TABLE",
  "ALTER",
  "DROP",
  "INDEX",
  "VIEW",
  "CASE",
  "WHEN",
  "THEN",
  "ELSE",
  "END",
  "ASC",
  "DESC",
  "COUNT",
  "SUM",
  "AVG",
  "MIN",
  "MAX",
  "CAST",
  "COALESCE",
  "NULLIF",
  "TRUE",
  "FALSE",
  "WITH",
  "RECURSIVE",
  "EXCEPT",
  "INTERSECT",
  "FETCH",
  "NEXT",
  "ROWS",
  "ONLY",
  "FIRST",
  "OVER",
  "PARTITION",
  "WINDOW",
  "ROW_NUMBER",
  "RANK",
  "DENSE_RANK",
  "LAG",
  "LEAD",
  "NTILE",
];

/** Keywords after which table names are expected. */
const TABLE_CONTEXT_KEYWORDS = new Set([
  "FROM",
  "JOIN",
  "INNER",
  "LEFT",
  "RIGHT",
  "FULL",
  "CROSS",
  "INTO",
  "UPDATE",
  "TABLE",
]);

/** Keywords after which column names are expected. */
const COLUMN_CONTEXT_KEYWORDS = new Set([
  "SELECT",
  "WHERE",
  "ON",
  "AND",
  "OR",
  "BY",
  "HAVING",
  "SET",
  "BETWEEN",
]);

/** Maps SQL data types to short display labels for the completion UI. */
function typeLabel(dataType: string): string {
  const t = dataType.toLowerCase();
  if (t.includes("int")) return "int";
  if (t.includes("serial")) return "serial";
  if (t.includes("float") || t.includes("double") || t.includes("real") || t.includes("numeric") || t.includes("decimal"))
    return "num";
  if (t.includes("bool")) return "bool";
  if (t.includes("timestamp") || t.includes("datetime")) return "datetime";
  if (t.includes("date")) return "date";
  if (t.includes("time")) return "time";
  if (t.includes("text") || t.includes("char") || t.includes("varchar") || t.includes("string"))
    return "text";
  if (t.includes("json")) return "json";
  if (t.includes("uuid")) return "uuid";
  if (t.includes("blob") || t.includes("bytea")) return "binary";
  return dataType;
}

/**
 * Extract the preceding keyword context by walking backwards from
 * the cursor to find the nearest SQL keyword before the current word.
 *
 * When `text` ends with whitespace, the "current word" is empty and
 * the preceding keyword is the last word in the text.
 *
 * When `text` ends with word characters, those are the partial word
 * being typed and the preceding keyword is the word before it.
 */
function getPrecedingKeyword(text: string): string | null {
  // Strip the partial word currently being typed (trailing word chars)
  const withoutPartial = text.replace(/\w*$/, "").trimEnd();
  if (!withoutPartial) return null;

  // Extract the last word from the remaining text
  const match = withoutPartial.match(/(\w+)\s*$/);
  if (!match) return null;
  return match[1].toUpperCase();
}

/**
 * Check if the cursor is in a "table name" context by looking at
 * preceding text for FROM, JOIN, etc.
 */
function isTableContext(textBefore: string): boolean {
  const keyword = getPrecedingKeyword(textBefore);
  if (!keyword) return false;
  return TABLE_CONTEXT_KEYWORDS.has(keyword);
}

/**
 * Check if the cursor is in a "column name" context (after SELECT, WHERE, etc.)
 */
function isColumnContext(textBefore: string): boolean {
  const keyword = getPrecedingKeyword(textBefore);
  if (!keyword) return false;
  return COLUMN_CONTEXT_KEYWORDS.has(keyword);
}

/**
 * Try to extract the table alias or name before a dot (e.g., "t." or "users.").
 * Returns the part before the dot, or null if no dot notation.
 */
function getDotPrefix(textBefore: string): string | null {
  const match = textBefore.match(/(\w+)\.\s*$/);
  return match ? match[1] : null;
}

/**
 * Extract table names referenced in the query (from FROM and JOIN clauses)
 * to scope column completions. Returns a mapping of alias -> tableName.
 */
function extractReferencedTables(
  fullText: string,
): Map<string, string> {
  const result = new Map<string, string>();
  // Match FROM/JOIN followed by table name with optional alias
  // Pattern: FROM/JOIN tableName (AS)? alias
  const regex =
    /(?:FROM|JOIN)\s+(\w+)(?:\s+(?:AS\s+)?(\w+))?/gi;
  let match;
  while ((match = regex.exec(fullText)) !== null) {
    const tableName = match[1];
    const alias = match[2];
    // Map both the alias and the real name to the table name
    result.set(tableName.toLowerCase(), tableName);
    if (alias) {
      result.set(alias.toLowerCase(), tableName);
    }
  }
  return result;
}

/**
 * Build keyword completions.
 */
function buildKeywordCompletions(): Completion[] {
  return SQL_KEYWORDS.map((kw) => ({
    label: kw,
    type: "keyword",
    boost: -1, // lower priority than schema items
  }));
}

/**
 * Build table name completions with type indicators.
 */
function buildTableCompletions(tables: TableSchema[]): Completion[] {
  return tables.map((t) => ({
    label: t.tableName,
    type: "type", // CodeMirror type "type" renders as a type icon
    detail: `table (${t.columns.length} cols)`,
    boost: 1,
  }));
}

/**
 * Build column completions for specific tables, with type indicators.
 */
function buildColumnCompletions(
  tables: TableSchema[],
  filterTableNames?: Set<string>,
): Completion[] {
  const completions: Completion[] = [];
  const seen = new Set<string>();

  for (const table of tables) {
    if (filterTableNames && !filterTableNames.has(table.tableName.toLowerCase())) {
      continue;
    }
    for (const col of table.columns) {
      const key = `${col.column_name}:${col.data_type}`;
      if (seen.has(key)) continue;
      seen.add(key);

      completions.push({
        label: col.column_name,
        type: "property",
        detail: typeLabel(col.data_type),
        boost: 2,
      });
    }
  }

  return completions;
}

/**
 * Build column completions scoped to a specific table (for dot notation).
 */
function buildDotColumnCompletions(
  table: TableSchema,
): Completion[] {
  return table.columns.map((col) => ({
    label: col.column_name,
    type: "property",
    detail: typeLabel(col.data_type),
    boost: 3,
  }));
}

/**
 * Creates a CodeMirror CompletionSource function from schema data.
 *
 * Provides context-aware completions:
 * - After FROM/JOIN: table names
 * - After SELECT/WHERE/ON etc.: column names scoped to referenced tables
 * - After "table.": columns for that specific table
 * - Otherwise: SQL keywords + all available completions
 *
 * Falls back to keywords only if no schema data is available.
 */
export function createSchemaCompletionSource(
  tables: TableSchema[],
): (context: CompletionContext) => CompletionResult | null {
  const keywordCompletions = buildKeywordCompletions();
  const tableCompletions = buildTableCompletions(tables);

  return (context: CompletionContext): CompletionResult | null => {
    // Get the text from start of document to cursor
    const line = context.state.doc.lineAt(context.pos);
    const textBefore = context.state.doc.sliceString(0, context.pos);
    const lineTextBefore = line.text.slice(0, context.pos - line.from);

    // Check for dot notation (table.column)
    const dotPrefix = getDotPrefix(lineTextBefore);
    if (dotPrefix) {
      // Find the table matching this dot prefix
      const referencedTables = extractReferencedTables(
        context.state.doc.toString(),
      );
      const realTableName = referencedTables.get(dotPrefix.toLowerCase());

      const matchedTable = tables.find(
        (t) =>
          t.tableName.toLowerCase() === dotPrefix.toLowerCase() ||
          (realTableName &&
            t.tableName.toLowerCase() === realTableName.toLowerCase()),
      );

      if (matchedTable) {
        // Find the position right after the dot
        const dotPos = lineTextBefore.lastIndexOf(".");
        const from = line.from + dotPos + 1;

        return {
          from,
          options: buildDotColumnCompletions(matchedTable),
          validFor: /^\w*$/i,
        };
      }
    }

    // Match a word being typed (for partial word matching)
    const word = context.matchBefore(/\w*/);
    if (!word) return null;

    // Only trigger autocomplete if there is at least one character typed
    // or the completion was explicitly invoked
    if (word.from === word.to && !context.explicit) return null;

    if (isTableContext(textBefore)) {
      // After FROM/JOIN: show table names + keywords
      return {
        from: word.from,
        options: [...tableCompletions, ...keywordCompletions],
        validFor: /^\w*$/i,
      };
    }

    if (isColumnContext(textBefore) && tables.length > 0) {
      // After SELECT/WHERE etc.: show columns scoped to referenced tables
      const referencedTables = extractReferencedTables(
        context.state.doc.toString(),
      );

      let columnCompletions: Completion[];
      if (referencedTables.size > 0) {
        // Scope columns to referenced tables
        const tableNames = new Set(
          Array.from(referencedTables.values()).map((n) => n.toLowerCase()),
        );
        columnCompletions = buildColumnCompletions(tables, tableNames);
      } else {
        // No referenced tables yet, show all columns
        columnCompletions = buildColumnCompletions(tables);
      }

      return {
        from: word.from,
        options: [
          ...columnCompletions,
          ...tableCompletions,
          ...keywordCompletions,
        ],
        validFor: /^\w*$/i,
      };
    }

    // Default: show all completions
    const allColumnCompletions = buildColumnCompletions(tables);
    return {
      from: word.from,
      options: [
        ...allColumnCompletions,
        ...tableCompletions,
        ...keywordCompletions,
      ],
      validFor: /^\w*$/i,
    };
  };
}

/**
 * Creates a keywords-only completion source (fallback when no schema is available).
 */
export function createKeywordsOnlyCompletionSource(): (
  context: CompletionContext,
) => CompletionResult | null {
  const keywordCompletions = buildKeywordCompletions();

  return (context: CompletionContext): CompletionResult | null => {
    const word = context.matchBefore(/\w*/);
    if (!word) return null;
    if (word.from === word.to && !context.explicit) return null;

    return {
      from: word.from,
      options: keywordCompletions,
      validFor: /^\w*$/i,
    };
  };
}

// Re-export for testing
export { SQL_KEYWORDS, TABLE_CONTEXT_KEYWORDS, COLUMN_CONTEXT_KEYWORDS };
export {
  typeLabel,
  getPrecedingKeyword,
  isTableContext,
  isColumnContext,
  getDotPrefix,
  extractReferencedTables,
  buildKeywordCompletions,
  buildTableCompletions,
  buildColumnCompletions,
};
