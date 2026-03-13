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
const DataPage = lazy(() =>
  import("@/pages/data").then((m) => ({ default: m.DataPage })),
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
            <Route path="data" element={<DataPage />} />
            <Route path="data/:type/:id" element={<DataPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

export default App;
