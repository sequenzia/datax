import { useState, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  ChevronRight,
  Database,
  Loader2,
  TestTube2,
  Save,
  AlertCircle,
  CheckCircle2,
  Eye,
  EyeOff,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  useConnectionDetail,
  useCreateConnection,
  useUpdateConnection,
  useTestConnectionParams,
  useTestConnection,
} from "@/hooks/use-connections";
import type { ConnectionDetail, ConnectionTestResult } from "@/types/api";

const DEFAULT_PORTS: Record<string, number> = {
  postgresql: 5432,
  mysql: 3306,
};

const DB_TYPES = [
  { value: "postgresql", label: "PostgreSQL" },
  { value: "mysql", label: "MySQL" },
];

const UUID_REGEX =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

interface FormState {
  name: string;
  db_type: string;
  host: string;
  port: string;
  database_name: string;
  username: string;
  password: string;
}

function validatePort(value: string): string | null {
  if (!value) return "Port is required";
  const num = Number(value);
  if (!Number.isInteger(num) || num < 1 || num > 65535) {
    return "Port must be between 1 and 65535";
  }
  return null;
}

function isFormValid(form: FormState, isEdit: boolean): boolean {
  if (!form.name.trim()) return false;
  if (!form.db_type) return false;
  if (!form.host.trim()) return false;
  if (validatePort(form.port) !== null) return false;
  if (!form.database_name.trim()) return false;
  if (!form.username.trim()) return false;
  if (!isEdit && !form.password) return false;
  return true;
}

function isTestable(form: FormState, isEdit: boolean): boolean {
  if (!form.db_type) return false;
  if (!form.host.trim()) return false;
  if (validatePort(form.port) !== null) return false;
  if (!form.database_name.trim()) return false;
  if (!form.username.trim()) return false;
  if (!isEdit && !form.password) return false;
  return true;
}

function buildInitialForm(connection?: ConnectionDetail): FormState {
  if (connection) {
    return {
      name: connection.name,
      db_type: connection.db_type,
      host: connection.host,
      port: String(connection.port),
      database_name: connection.database_name,
      username: connection.username || "",
      password: "",
    };
  }
  return {
    name: "",
    db_type: "postgresql",
    host: "",
    port: "5432",
    database_name: "",
    username: "",
    password: "",
  };
}

/** Inner form component. Receives initial values via props so state is
 *  initialized correctly on first render (no useEffect needed). The
 *  parent remounts this component via a key prop when edit data arrives. */
function ConnectionFormInner({
  isEdit,
  connectionId,
  initialData,
}: {
  isEdit: boolean;
  connectionId?: string;
  initialData?: ConnectionDetail;
}) {
  const navigate = useNavigate();

  const createMutation = useCreateConnection();
  const updateMutation = useUpdateConnection();
  const testParamsMutation = useTestConnectionParams();
  const testExistingMutation = useTestConnection();

  const [form, setForm] = useState<FormState>(() => buildInitialForm(initialData));
  const [showPassword, setShowPassword] = useState(false);
  const [portError, setPortError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const updateField = useCallback(
    (field: keyof FormState, value: string) => {
      setForm((prev) => {
        const next = { ...prev, [field]: value };

        // Auto-fill port when db_type changes
        if (field === "db_type" && DEFAULT_PORTS[value] !== undefined) {
          next.port = String(DEFAULT_PORTS[value]);
          setPortError(null);
        }

        // Validate port on change
        if (field === "port") {
          setPortError(validatePort(value));
        }

        return next;
      });
    },
    [],
  );

  const handleTest = useCallback(() => {
    setTestResult(null);

    if (isEdit && connectionId && !form.password) {
      // For edit mode without new password, test the existing connection
      testExistingMutation.mutate(connectionId, {
        onSuccess: (result) => {
          setTestResult(result);
        },
        onError: (err) => {
          setTestResult({
            status: "error",
            latency_ms: null,
            tables_found: null,
            error: err instanceof Error ? err.message : "Test failed",
          });
        },
      });
    } else {
      // Test with form parameters
      testParamsMutation.mutate(
        {
          db_type: form.db_type,
          host: form.host,
          port: Number(form.port),
          database_name: form.database_name,
          username: form.username,
          password: form.password,
        },
        {
          onSuccess: (result) => {
            setTestResult(result);
          },
          onError: (err) => {
            setTestResult({
              status: "error",
              latency_ms: null,
              tables_found: null,
              error: err instanceof Error ? err.message : "Test failed",
            });
          },
        },
      );
    }
  }, [form, isEdit, connectionId, testParamsMutation, testExistingMutation]);

  const handleSave = useCallback(() => {
    setSaveError(null);

    if (isEdit && connectionId) {
      const body: Record<string, string | number> = {};
      if (form.name.trim()) body.name = form.name.trim();
      if (form.db_type) body.db_type = form.db_type;
      if (form.host.trim()) body.host = form.host.trim();
      if (form.port) body.port = Number(form.port);
      if (form.database_name.trim()) body.database_name = form.database_name.trim();
      if (form.username.trim()) body.username = form.username.trim();
      if (form.password) body.password = form.password;

      updateMutation.mutate(
        { id: connectionId, body },
        {
          onSuccess: (result) => {
            navigate(`/data/connection/${result.id}`);
          },
          onError: (err) => {
            setSaveError(
              err instanceof Error ? err.message : "Failed to update connection",
            );
          },
        },
      );
    } else {
      createMutation.mutate(
        {
          name: form.name.trim(),
          db_type: form.db_type,
          host: form.host.trim(),
          port: Number(form.port),
          database_name: form.database_name.trim(),
          username: form.username.trim(),
          password: form.password,
        },
        {
          onSuccess: (result) => {
            navigate(`/data/connection/${result.id}`);
          },
          onError: (err) => {
            setSaveError(
              err instanceof Error ? err.message : "Failed to create connection",
            );
          },
        },
      );
    }
  }, [form, isEdit, connectionId, createMutation, updateMutation, navigate]);

  const isTesting =
    testParamsMutation.isPending || testExistingMutation.isPending;
  const isSaving = createMutation.isPending || updateMutation.isPending;
  const formValid = isFormValid(form, isEdit);
  const canTest = isTestable(form, isEdit);

  return (
    <div className="space-y-6 p-6">
      {/* Breadcrumbs */}
      <nav aria-label="Breadcrumb" data-testid="breadcrumbs">
        <ol className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <li>
            <Link to="/" className="hover:text-foreground">
              Dashboard
            </Link>
          </li>
          <li>
            <ChevronRight className="size-3.5" />
          </li>
          <li>
            <Link to="/data" className="hover:text-foreground">
              Connections
            </Link>
          </li>
          <li>
            <ChevronRight className="size-3.5" />
          </li>
          <li className="font-medium text-foreground">
            {isEdit ? "Edit Connection" : "New Connection"}
          </li>
        </ol>
      </nav>

      {/* Header */}
      <div className="flex items-center gap-3">
        <Database className="size-8 text-muted-foreground" />
        <div>
          <h1 className="text-2xl font-bold">
            {isEdit ? "Edit Connection" : "New Connection"}
          </h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {isEdit
              ? "Update your database connection settings."
              : "Configure a new database connection."}
          </p>
        </div>
      </div>

      {/* Form */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Connection Details</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2">
            {/* Name */}
            <div className="sm:col-span-2">
              <label
                htmlFor="conn-name"
                className="mb-1.5 block text-sm font-medium"
              >
                Connection Name
              </label>
              <input
                id="conn-name"
                type="text"
                value={form.name}
                onChange={(e) => updateField("name", e.target.value)}
                placeholder="My Database"
                className="h-9 w-full rounded-md border bg-background px-3 text-sm shadow-xs outline-none placeholder:text-muted-foreground focus:border-ring focus:ring-[3px] focus:ring-ring/50"
                data-testid="input-name"
              />
            </div>

            {/* DB Type */}
            <div>
              <label
                htmlFor="conn-db-type"
                className="mb-1.5 block text-sm font-medium"
              >
                Database Type
              </label>
              <select
                id="conn-db-type"
                value={form.db_type}
                onChange={(e) => updateField("db_type", e.target.value)}
                className="h-9 w-full rounded-md border bg-background px-3 text-sm shadow-xs outline-none focus:border-ring focus:ring-[3px] focus:ring-ring/50"
                data-testid="select-db-type"
              >
                {DB_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Host */}
            <div>
              <label
                htmlFor="conn-host"
                className="mb-1.5 block text-sm font-medium"
              >
                Host
              </label>
              <input
                id="conn-host"
                type="text"
                value={form.host}
                onChange={(e) => updateField("host", e.target.value)}
                placeholder="localhost"
                className="h-9 w-full rounded-md border bg-background px-3 text-sm shadow-xs outline-none placeholder:text-muted-foreground focus:border-ring focus:ring-[3px] focus:ring-ring/50"
                data-testid="input-host"
              />
            </div>

            {/* Port */}
            <div>
              <label
                htmlFor="conn-port"
                className="mb-1.5 block text-sm font-medium"
              >
                Port
              </label>
              <input
                id="conn-port"
                type="text"
                inputMode="numeric"
                value={form.port}
                onChange={(e) => updateField("port", e.target.value)}
                placeholder="5432"
                className={`h-9 w-full rounded-md border bg-background px-3 text-sm shadow-xs outline-none placeholder:text-muted-foreground focus:border-ring focus:ring-[3px] focus:ring-ring/50 ${
                  portError
                    ? "border-destructive focus:border-destructive focus:ring-destructive/50"
                    : ""
                }`}
                data-testid="input-port"
              />
              {portError && (
                <p
                  className="mt-1 text-xs text-destructive"
                  data-testid="port-error"
                >
                  {portError}
                </p>
              )}
            </div>

            {/* Database Name */}
            <div>
              <label
                htmlFor="conn-database"
                className="mb-1.5 block text-sm font-medium"
              >
                Database
              </label>
              <input
                id="conn-database"
                type="text"
                value={form.database_name}
                onChange={(e) => updateField("database_name", e.target.value)}
                placeholder="mydb"
                className="h-9 w-full rounded-md border bg-background px-3 text-sm shadow-xs outline-none placeholder:text-muted-foreground focus:border-ring focus:ring-[3px] focus:ring-ring/50"
                data-testid="input-database"
              />
            </div>

            {/* Username */}
            <div>
              <label
                htmlFor="conn-username"
                className="mb-1.5 block text-sm font-medium"
              >
                Username
              </label>
              <input
                id="conn-username"
                type="text"
                value={form.username}
                onChange={(e) => updateField("username", e.target.value)}
                placeholder="admin"
                className="h-9 w-full rounded-md border bg-background px-3 text-sm shadow-xs outline-none placeholder:text-muted-foreground focus:border-ring focus:ring-[3px] focus:ring-ring/50"
                data-testid="input-username"
              />
            </div>

            {/* Password */}
            <div>
              <label
                htmlFor="conn-password"
                className="mb-1.5 block text-sm font-medium"
              >
                Password
                {isEdit && (
                  <span className="ml-2 text-xs font-normal text-muted-foreground">
                    (leave blank to keep current)
                  </span>
                )}
              </label>
              <div className="relative">
                <input
                  id="conn-password"
                  type={showPassword ? "text" : "password"}
                  value={form.password}
                  onChange={(e) => updateField("password", e.target.value)}
                  placeholder={isEdit ? "Enter new password" : "Password"}
                  className="h-9 w-full rounded-md border bg-background px-3 pr-9 text-sm shadow-xs outline-none placeholder:text-muted-foreground focus:border-ring focus:ring-[3px] focus:ring-ring/50"
                  data-testid="input-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  data-testid="toggle-password"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? (
                    <EyeOff className="size-4" />
                  ) : (
                    <Eye className="size-4" />
                  )}
                </button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Test Result */}
      {testResult && (
        <div
          className={`flex items-start gap-2 rounded-md border p-3 ${
            testResult.status === "error" || testResult.error
              ? "border-destructive/50 bg-destructive/10"
              : "border-green-500/50 bg-green-500/10"
          }`}
          data-testid="test-result"
        >
          {testResult.status === "error" || testResult.error ? (
            <>
              <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
              <p className="text-sm text-destructive">
                Connection test failed: {testResult.error}
              </p>
            </>
          ) : (
            <>
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-green-600 dark:text-green-400" />
              <p className="text-sm text-green-700 dark:text-green-400">
                Connection successful
                {testResult.latency_ms != null &&
                  ` (${testResult.latency_ms.toFixed(0)}ms)`}
                {testResult.tables_found != null &&
                  ` - ${testResult.tables_found} tables found`}
              </p>
            </>
          )}
        </div>
      )}

      {/* Save Error */}
      {saveError && (
        <div
          className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3"
          data-testid="save-error"
        >
          <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
          <p className="text-sm text-destructive">{saveError}</p>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-3">
        <Button
          variant="outline"
          onClick={handleTest}
          disabled={!canTest || isTesting || isSaving}
          data-testid="test-button"
        >
          {isTesting ? (
            <Loader2 className="animate-spin" />
          ) : (
            <TestTube2 />
          )}
          Test Connection
        </Button>
        <Button
          onClick={handleSave}
          disabled={!formValid || isTesting || isSaving}
          data-testid="save-button"
        >
          {isSaving ? (
            <Loader2 className="animate-spin" />
          ) : (
            <Save />
          )}
          {isEdit ? "Update Connection" : "Save Connection"}
        </Button>
        <Button variant="outline" asChild>
          <Link to="/data">Cancel</Link>
        </Button>
      </div>
    </div>
  );
}

export function ConnectionFormPage() {
  const { id } = useParams<{ id: string }>();

  const isEdit = Boolean(id);
  const isValidId = id && UUID_REGEX.test(id);

  const {
    data: existingConnection,
    isLoading: isLoadingConnection,
  } = useConnectionDetail(isEdit && isValidId ? id : undefined);

  // Show invalid ID page for edit mode
  if (isEdit && id && !isValidId) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 p-6">
        <h1 className="text-2xl font-bold">Invalid Connection ID</h1>
        <p className="text-muted-foreground">
          The connection ID provided is not a valid identifier.
        </p>
        <Link
          to="/data"
          className="text-sm text-primary underline underline-offset-4 hover:text-primary/80"
        >
          Back to Connections
        </Link>
      </div>
    );
  }

  // Show loading state for edit mode
  if (isEdit && isLoadingConnection) {
    return (
      <div className="space-y-6 p-6">
        <div className="h-6 w-48 animate-pulse rounded bg-muted/50" />
        <div className="h-8 w-64 animate-pulse rounded bg-muted/50" />
        <div className="h-96 animate-pulse rounded-xl border bg-muted/50" />
      </div>
    );
  }

  // Use connection ID as key so the inner form remounts with fresh state
  // when the connection data loads (avoids useEffect + setState pattern).
  return (
    <ConnectionFormInner
      key={isEdit ? existingConnection?.id ?? "loading" : "new"}
      isEdit={isEdit}
      connectionId={id}
      initialData={existingConnection}
    />
  );
}
