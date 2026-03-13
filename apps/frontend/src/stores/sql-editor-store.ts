import { create } from "zustand";
import type { QueryResult } from "@/stores/results-store";

export interface SqlTab {
  id: string;
  title: string;
  content: string;
  cursorPosition: { line: number; col: number };
  isExecuting: boolean;
  error: string | null;
  results: QueryResult[];
  executionTimeMs: number | null;
}

export interface DataSource {
  id: string;
  name: string;
  type: "dataset" | "connection";
}

interface SqlEditorState {
  tabs: SqlTab[];
  activeTabId: string;
  selectedSource: DataSource | null;
  abortControllers: Map<string, AbortController>;
  addTab: () => void;
  closeTab: (id: string) => void;
  renameTab: (id: string, title: string) => void;
  setActiveTab: (id: string) => void;
  updateTabContent: (id: string, content: string) => void;
  updateCursorPosition: (
    id: string,
    position: { line: number; col: number },
  ) => void;
  setTabExecuting: (id: string, isExecuting: boolean) => void;
  setTabError: (id: string, error: string | null) => void;
  addTabResult: (id: string, result: QueryResult) => void;
  setTabExecutionTime: (id: string, timeMs: number | null) => void;
  setSelectedSource: (source: DataSource | null) => void;
  setAbortController: (tabId: string, controller: AbortController) => void;
  cancelExecution: (tabId: string) => void;
  clearTabResults: (id: string) => void;
}

let nextTabId = 1;

function generateTabId(): string {
  return `tab-${nextTabId++}`;
}

function createDefaultTab(): SqlTab {
  return {
    id: generateTabId(),
    title: `Query ${nextTabId - 1}`,
    content: "",
    cursorPosition: { line: 1, col: 1 },
    isExecuting: false,
    error: null,
    results: [],
    executionTimeMs: null,
  };
}

const initialTab = createDefaultTab();

export const useSqlEditorStore = create<SqlEditorState>((set, get) => ({
  tabs: [initialTab],
  activeTabId: initialTab.id,
  selectedSource: null,
  abortControllers: new Map(),

  addTab: () => {
    const newTab = createDefaultTab();
    set((state) => ({
      tabs: [...state.tabs, newTab],
      activeTabId: newTab.id,
    }));
  },

  closeTab: (id) =>
    set((state) => {
      // Cancel any in-flight execution
      const controller = state.abortControllers.get(id);
      if (controller) controller.abort();
      const newControllers = new Map(state.abortControllers);
      newControllers.delete(id);

      if (state.tabs.length === 1) {
        const newTab = createDefaultTab();
        return {
          tabs: [newTab],
          activeTabId: newTab.id,
          abortControllers: newControllers,
        };
      }

      const closedIndex = state.tabs.findIndex((t) => t.id === id);
      const newTabs = state.tabs.filter((t) => t.id !== id);

      let newActiveId = state.activeTabId;
      if (state.activeTabId === id) {
        const newIndex = Math.min(closedIndex, newTabs.length - 1);
        newActiveId = newTabs[newIndex].id;
      }

      return {
        tabs: newTabs,
        activeTabId: newActiveId,
        abortControllers: newControllers,
      };
    }),

  renameTab: (id, title) =>
    set((state) => ({
      tabs: state.tabs.map((t) => (t.id === id ? { ...t, title } : t)),
    })),

  setActiveTab: (id) => set({ activeTabId: id }),

  updateTabContent: (id, content) =>
    set((state) => ({
      tabs: state.tabs.map((t) => (t.id === id ? { ...t, content } : t)),
    })),

  updateCursorPosition: (id, position) =>
    set((state) => ({
      tabs: state.tabs.map((t) =>
        t.id === id ? { ...t, cursorPosition: position } : t,
      ),
    })),

  setTabExecuting: (id, isExecuting) =>
    set((state) => ({
      tabs: state.tabs.map((t) => (t.id === id ? { ...t, isExecuting } : t)),
    })),

  setTabError: (id, error) =>
    set((state) => ({
      tabs: state.tabs.map((t) => (t.id === id ? { ...t, error } : t)),
    })),

  addTabResult: (id, result) =>
    set((state) => ({
      tabs: state.tabs.map((t) =>
        t.id === id ? { ...t, results: [result, ...t.results] } : t,
      ),
    })),

  setTabExecutionTime: (id, timeMs) =>
    set((state) => ({
      tabs: state.tabs.map((t) =>
        t.id === id ? { ...t, executionTimeMs: timeMs } : t,
      ),
    })),

  setSelectedSource: (source) => set({ selectedSource: source }),

  setAbortController: (tabId, controller) =>
    set((state) => {
      const newControllers = new Map(state.abortControllers);
      newControllers.set(tabId, controller);
      return { abortControllers: newControllers };
    }),

  cancelExecution: (tabId) => {
    const controller = get().abortControllers.get(tabId);
    if (controller) {
      controller.abort();
      const newControllers = new Map(get().abortControllers);
      newControllers.delete(tabId);
      set({ abortControllers: newControllers });
    }
  },

  clearTabResults: (id) =>
    set((state) => ({
      tabs: state.tabs.map((t) =>
        t.id === id
          ? { ...t, results: [], error: null, executionTimeMs: null }
          : t,
      ),
    })),
}));
