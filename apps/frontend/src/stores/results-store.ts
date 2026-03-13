import { create } from "zustand";

export type ResultSource = "chat" | "sql-editor";

export interface QueryResult {
  id: string;
  title: string;
  sql: string;
  data: Record<string, unknown>[] | null;
  columns: string[];
  rowCount: number;
  explanation: string | null;
  chartConfig: Record<string, unknown> | null;
  error: string | null;
  source: ResultSource;
  createdAt: number;
  isExpanded: boolean;
}

interface ResultsState {
  results: QueryResult[];
  sortNewestFirst: boolean;
  addResult: (result: Omit<QueryResult, "id" | "createdAt" | "isExpanded">) => void;
  removeResult: (id: string) => void;
  clearResults: () => void;
  toggleExpanded: (id: string) => void;
  setExpanded: (id: string, expanded: boolean) => void;
  toggleSortOrder: () => void;
}

let nextId = 1;

function generateResultId(): string {
  return `result-${nextId++}`;
}

export const useResultsStore = create<ResultsState>((set) => ({
  results: [],
  sortNewestFirst: true,

  addResult: (result) =>
    set((state) => ({
      results: [
        {
          ...result,
          id: generateResultId(),
          createdAt: Date.now(),
          isExpanded: true,
        },
        ...state.results,
      ],
    })),

  removeResult: (id) =>
    set((state) => ({
      results: state.results.filter((r) => r.id !== id),
    })),

  clearResults: () => set({ results: [] }),

  toggleExpanded: (id) =>
    set((state) => ({
      results: state.results.map((r) =>
        r.id === id ? { ...r, isExpanded: !r.isExpanded } : r,
      ),
    })),

  setExpanded: (id, expanded) =>
    set((state) => ({
      results: state.results.map((r) =>
        r.id === id ? { ...r, isExpanded: expanded } : r,
      ),
    })),

  toggleSortOrder: () =>
    set((state) => ({
      sortNewestFirst: !state.sortNewestFirst,
      results: [...state.results].reverse(),
    })),
}));
