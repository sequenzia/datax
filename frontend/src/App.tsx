import { lazy, Suspense } from "react";
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
const DatasetsPage = lazy(() =>
  import("@/pages/datasets").then((m) => ({
    default: m.DatasetsPage,
  })),
);
const DatasetDetailPage = lazy(() =>
  import("@/pages/dataset-detail").then((m) => ({
    default: m.DatasetDetailPage,
  })),
);
const DatasetUploadPage = lazy(() =>
  import("@/pages/dataset-upload").then((m) => ({
    default: m.DatasetUploadPage,
  })),
);
const ConnectionsPage = lazy(() =>
  import("@/pages/connections").then((m) => ({
    default: m.ConnectionsPage,
  })),
);
const ConnectionDetailPage = lazy(() =>
  import("@/pages/connection-detail").then((m) => ({
    default: m.ConnectionDetailPage,
  })),
);
const ConnectionFormPage = lazy(() =>
  import("@/pages/connection-form").then((m) => ({
    default: m.ConnectionFormPage,
  })),
);
const NotFoundPage = lazy(() =>
  import("@/pages/not-found").then((m) => ({ default: m.NotFoundPage })),
);

function PageLoader() {
  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <p className="text-sm text-muted-foreground">Loading...</p>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<DashboardPage />} />
            <Route path="chat" element={<ChatPage />} />
            <Route path="chat/:conversationId" element={<ChatPage />} />
            <Route path="sql" element={<SqlEditorPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="datasets" element={<DatasetsPage />} />
            <Route path="datasets/upload" element={<DatasetUploadPage />} />
            <Route path="datasets/:id" element={<DatasetDetailPage />} />
            <Route path="connections" element={<ConnectionsPage />} />
            <Route path="connections/new" element={<ConnectionFormPage />} />
            <Route
              path="connections/:id/edit"
              element={<ConnectionFormPage />}
            />
            <Route path="connections/:id" element={<ConnectionDetailPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

export default App;
