import { lazy } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppLayout } from "@/components/layout";

const DashboardPage = lazy(() =>
  import("@/pages/dashboard").then((m) => ({ default: m.DashboardPage })),
);
const ChatPage = lazy(() =>
  import("@/pages/chat").then((m) => ({ default: m.ChatPage })),
);
const SqlEditorPage = lazy(() =>
  import("@/pages/sql-editor").then((m) => ({ default: m.SqlEditorPage })),
);
const SettingsPage = lazy(() =>
  import("@/pages/settings").then((m) => ({ default: m.SettingsPage })),
);
const DataPage = lazy(() =>
  import("@/pages/data").then((m) => ({ default: m.DataPage })),
);
const DatasetDetailPage = lazy(() =>
  import("@/pages/dataset-detail").then((m) => ({ default: m.DatasetDetailPage })),
);
const ConnectionDetailPage = lazy(() =>
  import("@/pages/connection-detail").then((m) => ({ default: m.ConnectionDetailPage })),
);
const ConnectionFormPage = lazy(() =>
  import("@/pages/connection-form").then((m) => ({ default: m.ConnectionFormPage })),
);
const DashboardsPage = lazy(() =>
  import("@/pages/dashboards").then((m) => ({ default: m.DashboardsPage })),
);
const ExplorePage = lazy(() =>
  import("@/pages/explore").then((m) => ({ default: m.ExplorePage })),
);
const NotFoundPage = lazy(() =>
  import("@/pages/not-found").then((m) => ({ default: m.NotFoundPage })),
);

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<DashboardPage />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="chat/:conversationId" element={<ChatPage />} />
          <Route path="sql" element={<SqlEditorPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="data" element={<DataPage />} />
          <Route path="data/dataset/:id" element={<DatasetDetailPage />} />
          <Route path="data/connection/new" element={<ConnectionFormPage />} />
          <Route path="data/connection/:id/edit" element={<ConnectionFormPage />} />
          <Route path="data/connection/:id" element={<ConnectionDetailPage />} />
          <Route path="dashboards" element={<DashboardsPage />} />
          <Route path="dashboards/:dashboardId" element={<DashboardsPage />} />
          <Route path="explore" element={<ExplorePage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
