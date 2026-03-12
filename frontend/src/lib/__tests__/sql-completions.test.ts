import { describe, it, expect } from "vitest";
import {
  typeLabel,
  getPrecedingKeyword,
  isTableContext,
  isColumnContext,
  getDotPrefix,
  extractReferencedTables,
  buildKeywordCompletions,
  buildTableCompletions,
  buildColumnCompletions,
  SQL_KEYWORDS,
  createSchemaCompletionSource,
  createKeywordsOnlyCompletionSource,
} from "../sql-completions";
import type { TableSchema } from "../sql-completions";
import type { SchemaColumn } from "@/types/api";

const mockColumns: SchemaColumn[] = [
  {
    column_name: "id",
    data_type: "integer",
    is_nullable: false,
    is_primary_key: true,
  },
  {
    column_name: "name",
    data_type: "varchar(255)",
    is_nullable: false,
    is_primary_key: false,
  },
  {
    column_name: "created_at",
    data_type: "timestamp",
    is_nullable: true,
    is_primary_key: false,
  },
  {
    column_name: "is_active",
    data_type: "boolean",
    is_nullable: false,
    is_primary_key: false,
  },
  {
    column_name: "score",
    data_type: "double precision",
    is_nullable: true,
    is_primary_key: false,
  },
];

const mockTables: TableSchema[] = [
  { tableName: "users", columns: mockColumns },
  {
    tableName: "orders",
    columns: [
      {
        column_name: "id",
        data_type: "integer",
        is_nullable: false,
        is_primary_key: true,
      },
      {
        column_name: "user_id",
        data_type: "integer",
        is_nullable: false,
        is_primary_key: false,
      },
      {
        column_name: "total",
        data_type: "numeric(10,2)",
        is_nullable: false,
        is_primary_key: false,
      },
      {
        column_name: "order_date",
        data_type: "date",
        is_nullable: false,
        is_primary_key: false,
      },
    ],
  },
];

describe("typeLabel", () => {
  it("maps integer types to 'int'", () => {
    expect(typeLabel("integer")).toBe("int");
    expect(typeLabel("bigint")).toBe("int");
    expect(typeLabel("smallint")).toBe("int");
  });

  it("maps float/numeric types to 'num'", () => {
    expect(typeLabel("double precision")).toBe("num");
    expect(typeLabel("float")).toBe("num");
    expect(typeLabel("numeric(10,2)")).toBe("num");
    expect(typeLabel("decimal")).toBe("num");
    expect(typeLabel("real")).toBe("num");
  });

  it("maps text types to 'text'", () => {
    expect(typeLabel("varchar(255)")).toBe("text");
    expect(typeLabel("text")).toBe("text");
    expect(typeLabel("character varying")).toBe("text");
  });

  it("maps boolean to 'bool'", () => {
    expect(typeLabel("boolean")).toBe("bool");
  });

  it("maps timestamp/datetime types", () => {
    expect(typeLabel("timestamp")).toBe("datetime");
    expect(typeLabel("timestamp with time zone")).toBe("datetime");
    expect(typeLabel("datetime")).toBe("datetime");
  });

  it("maps date to 'date'", () => {
    expect(typeLabel("date")).toBe("date");
  });

  it("maps json types", () => {
    expect(typeLabel("json")).toBe("json");
    expect(typeLabel("jsonb")).toBe("json");
  });

  it("maps uuid types", () => {
    expect(typeLabel("uuid")).toBe("uuid");
  });

  it("maps serial types", () => {
    expect(typeLabel("serial")).toBe("serial");
    expect(typeLabel("bigserial")).toBe("serial");
  });

  it("returns original type for unknown types", () => {
    expect(typeLabel("geometry")).toBe("geometry");
    expect(typeLabel("custom_type")).toBe("custom_type");
  });
});

describe("getPrecedingKeyword", () => {
  it("extracts the keyword before the current word", () => {
    expect(getPrecedingKeyword("SELECT name FROM ")).toBe("FROM");
    expect(getPrecedingKeyword("SELECT ")).toBe("SELECT");
    expect(getPrecedingKeyword("WHERE x = 1 AND ")).toBe("AND");
  });

  it("returns null when no preceding keyword", () => {
    expect(getPrecedingKeyword("")).toBe(null);
    expect(getPrecedingKeyword("S")).toBe(null);
  });

  it("handles case insensitivity", () => {
    expect(getPrecedingKeyword("select name from ")).toBe("FROM");
    expect(getPrecedingKeyword("Select ")).toBe("SELECT");
  });
});

describe("isTableContext", () => {
  it("returns true after FROM", () => {
    expect(isTableContext("SELECT * FROM ")).toBe(true);
  });

  it("returns true after JOIN", () => {
    expect(isTableContext("SELECT * FROM users JOIN ")).toBe(true);
  });

  it("returns true after LEFT", () => {
    expect(isTableContext("SELECT * FROM users LEFT ")).toBe(true);
  });

  it("returns false after SELECT", () => {
    expect(isTableContext("SELECT ")).toBe(false);
  });

  it("returns false after WHERE", () => {
    expect(isTableContext("SELECT * FROM users WHERE ")).toBe(false);
  });
});

describe("isColumnContext", () => {
  it("returns true after SELECT", () => {
    expect(isColumnContext("SELECT ")).toBe(true);
  });

  it("returns true after WHERE", () => {
    expect(isColumnContext("SELECT * FROM users WHERE ")).toBe(true);
  });

  it("returns true after ON", () => {
    expect(isColumnContext("JOIN orders ON ")).toBe(true);
  });

  it("returns true after AND", () => {
    expect(isColumnContext("WHERE x = 1 AND ")).toBe(true);
  });

  it("returns true after BY (ORDER BY, GROUP BY)", () => {
    expect(isColumnContext("ORDER BY ")).toBe(true);
    expect(isColumnContext("GROUP BY ")).toBe(true);
  });

  it("returns false after FROM", () => {
    expect(isColumnContext("SELECT * FROM ")).toBe(false);
  });
});

describe("getDotPrefix", () => {
  it("extracts table name before dot", () => {
    expect(getDotPrefix("u.")).toBe("u");
    expect(getDotPrefix("users.")).toBe("users");
    expect(getDotPrefix("SELECT u.")).toBe("u");
  });

  it("returns null when no dot notation", () => {
    expect(getDotPrefix("SELECT ")).toBe(null);
    expect(getDotPrefix("FROM users")).toBe(null);
  });
});

describe("extractReferencedTables", () => {
  it("extracts table from FROM clause", () => {
    const result = extractReferencedTables("SELECT * FROM users");
    expect(result.get("users")).toBe("users");
  });

  it("extracts table with alias", () => {
    const result = extractReferencedTables("SELECT * FROM users u");
    expect(result.get("users")).toBe("users");
    expect(result.get("u")).toBe("users");
  });

  it("extracts table with AS alias", () => {
    const result = extractReferencedTables("SELECT * FROM users AS u");
    expect(result.get("users")).toBe("users");
    expect(result.get("u")).toBe("users");
  });

  it("extracts multiple tables from JOIN", () => {
    const result = extractReferencedTables(
      "SELECT * FROM users u JOIN orders o ON u.id = o.user_id",
    );
    expect(result.get("users")).toBe("users");
    expect(result.get("u")).toBe("users");
    expect(result.get("orders")).toBe("orders");
    expect(result.get("o")).toBe("orders");
  });

  it("returns empty map for no FROM/JOIN", () => {
    const result = extractReferencedTables("SELECT 1");
    expect(result.size).toBe(0);
  });

  it("is case-insensitive on keys", () => {
    const result = extractReferencedTables("SELECT * FROM Users");
    expect(result.get("users")).toBe("Users");
  });
});

describe("buildKeywordCompletions", () => {
  it("returns completions for all SQL keywords", () => {
    const completions = buildKeywordCompletions();
    expect(completions.length).toBe(SQL_KEYWORDS.length);
    expect(completions[0].type).toBe("keyword");
  });

  it("sets keyword type on all completions", () => {
    const completions = buildKeywordCompletions();
    for (const c of completions) {
      expect(c.type).toBe("keyword");
    }
  });
});

describe("buildTableCompletions", () => {
  it("creates completions for each table", () => {
    const completions = buildTableCompletions(mockTables);
    expect(completions.length).toBe(2);
    expect(completions[0].label).toBe("users");
    expect(completions[0].detail).toContain("5 cols");
    expect(completions[1].label).toBe("orders");
    expect(completions[1].detail).toContain("4 cols");
  });

  it("sets type to 'type' for table icon", () => {
    const completions = buildTableCompletions(mockTables);
    for (const c of completions) {
      expect(c.type).toBe("type");
    }
  });
});

describe("buildColumnCompletions", () => {
  it("returns columns from all tables when no filter", () => {
    const completions = buildColumnCompletions(mockTables);
    const labels = completions.map((c) => c.label);
    expect(labels).toContain("id");
    expect(labels).toContain("name");
    expect(labels).toContain("user_id");
    expect(labels).toContain("total");
  });

  it("deduplicates columns with same name and type", () => {
    const completions = buildColumnCompletions(mockTables);
    // "id" appears in both tables with same type
    const idCount = completions.filter((c) => c.label === "id").length;
    expect(idCount).toBe(1);
  });

  it("filters columns by table names when provided", () => {
    const completions = buildColumnCompletions(
      mockTables,
      new Set(["users"]),
    );
    const labels = completions.map((c) => c.label);
    expect(labels).toContain("name");
    expect(labels).toContain("is_active");
    expect(labels).not.toContain("user_id");
    expect(labels).not.toContain("total");
  });

  it("sets type to 'property' for column icon", () => {
    const completions = buildColumnCompletions(mockTables);
    for (const c of completions) {
      expect(c.type).toBe("property");
    }
  });

  it("includes type indicator detail", () => {
    const completions = buildColumnCompletions(mockTables);
    const nameCompletion = completions.find((c) => c.label === "name");
    expect(nameCompletion?.detail).toBe("text");
  });
});

describe("createSchemaCompletionSource", () => {
  it("is a function", () => {
    const source = createSchemaCompletionSource(mockTables);
    expect(typeof source).toBe("function");
  });
});

describe("createKeywordsOnlyCompletionSource", () => {
  it("is a function", () => {
    const source = createKeywordsOnlyCompletionSource();
    expect(typeof source).toBe("function");
  });
});

describe("edge cases", () => {
  it("handles empty tables array", () => {
    const completions = buildTableCompletions([]);
    expect(completions).toEqual([]);
  });

  it("handles empty columns in table", () => {
    const completions = buildColumnCompletions([
      { tableName: "empty_table", columns: [] },
    ]);
    expect(completions).toEqual([]);
  });

  it("handles filter with no matching tables", () => {
    const completions = buildColumnCompletions(
      mockTables,
      new Set(["nonexistent"]),
    );
    expect(completions).toEqual([]);
  });
});
