import { create } from "zustand";

interface UIState {
  sidebarOpen: boolean;
  sidebarWidth: number;
  /** Ratio of conversation list height (0-1) vs schema browser */
  sidebarConversationRatio: number;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setSidebarConversationRatio: (ratio: number) => void;
}

const SIDEBAR_EXPANDED_WIDTH = 256; // w-64
const SIDEBAR_COLLAPSED_WIDTH = 56; // w-14

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: true,
  sidebarWidth: SIDEBAR_EXPANDED_WIDTH,
  sidebarConversationRatio: 0.6,
  toggleSidebar: () =>
    set((state) => ({
      sidebarOpen: !state.sidebarOpen,
      sidebarWidth: !state.sidebarOpen
        ? SIDEBAR_EXPANDED_WIDTH
        : SIDEBAR_COLLAPSED_WIDTH,
    })),
  setSidebarOpen: (open: boolean) =>
    set({
      sidebarOpen: open,
      sidebarWidth: open ? SIDEBAR_EXPANDED_WIDTH : SIDEBAR_COLLAPSED_WIDTH,
    }),
  setSidebarConversationRatio: (ratio: number) =>
    set({ sidebarConversationRatio: Math.min(0.85, Math.max(0.15, ratio)) }),
}));

export { SIDEBAR_EXPANDED_WIDTH, SIDEBAR_COLLAPSED_WIDTH };
