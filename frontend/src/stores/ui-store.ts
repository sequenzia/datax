import { create } from "zustand";

export type MobilePanel = "dashboard" | "chat" | "sql" | "settings";

interface UIState {
  sidebarOpen: boolean;
  chatPanelOpen: boolean;
  chatPanelWidth: number;
  activeMobilePanel: MobilePanel;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  toggleChatPanel: () => void;
  setChatPanelOpen: (open: boolean) => void;
  setChatPanelWidth: (width: number) => void;
  setActiveMobilePanel: (panel: MobilePanel) => void;
}

const MIN_CHAT_PANEL_WIDTH = 280;
const MAX_CHAT_PANEL_WIDTH = 600;
const DEFAULT_CHAT_PANEL_WIDTH = 380;

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: true,
  chatPanelOpen: true,
  chatPanelWidth: DEFAULT_CHAT_PANEL_WIDTH,
  activeMobilePanel: "chat",
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setSidebarOpen: (open: boolean) => set({ sidebarOpen: open }),
  toggleChatPanel: () =>
    set((state) => ({ chatPanelOpen: !state.chatPanelOpen })),
  setChatPanelOpen: (open: boolean) => set({ chatPanelOpen: open }),
  setChatPanelWidth: (width: number) =>
    set({
      chatPanelWidth: Math.min(
        MAX_CHAT_PANEL_WIDTH,
        Math.max(MIN_CHAT_PANEL_WIDTH, width),
      ),
    }),
  setActiveMobilePanel: (panel: MobilePanel) =>
    set({ activeMobilePanel: panel }),
}));

export { MIN_CHAT_PANEL_WIDTH, MAX_CHAT_PANEL_WIDTH, DEFAULT_CHAT_PANEL_WIDTH };
