import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ConnectionFormPage } from "../connection-form";
import type { ConnectionDetail } from "@/types/api";

// Mock hooks
const mockUseConnectionDetail = vi.fn();
const mockCreateMutate = vi.fn();
const mockUpdateMutate = vi.fn();
const mockTestParamsMutate = vi.fn();
const mockTestExistingMutate = vi.fn();
const mockNavigate = vi.fn();

vi.mock("@/hooks/use-connections", () => ({
  useConnectionDetail: (id: string | undefined) =>
    mockUseConnectionDetail(id),
  useCreateConnection: () => ({
    mutate: mockCreateMutate,
    isPending: false,
  }),
  useUpdateConnection: () => ({
    mutate: mockUpdateMutate,
    isPending: false,
  }),
  useTestConnectionParams: () => ({
    mutate: mockTestParamsMutate,
    isPending: false,
  }),
  useTestConnection: () => ({
    mutate: mockTestExistingMutate,
    isPending: false,
  }),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const mockConnection: ConnectionDetail = {
  id: "660e8400-e29b-41d4-a716-446655440001",
  name: "Production DB",
  db_type: "postgresql",
  host: "db.example.com",
  port: 5432,
  database_name: "production",
  username: "admin",
  status: "connected",
  last_tested_at: "2026-03-10T08:00:00Z",
  created_at: "2026-02-15T09:00:00Z",
  updated_at: "2026-03-10T08:00:00Z",
};

function successState<T>(data: T) {
  return { data, isLoading: false, isError: false, error: null };
}

function loadingState() {
  return { data: undefined, isLoading: true, isError: false, error: null };
}

function renderNewForm() {
  return render(
    <MemoryRouter initialEntries={["/connections/new"]}>
      <Routes>
        <Route path="connections/new" element={<ConnectionFormPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderEditForm(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/connections/${id}/edit`]}>
      <Routes>
        <Route
          path="connections/:id/edit"
          element={<ConnectionFormPage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseConnectionDetail.mockReturnValue(successState(mockConnection));
});

describe("ConnectionFormPage", () => {
  describe("new connection mode", () => {
    it("renders new connection heading", () => {
      mockUseConnectionDetail.mockReturnValue(
        successState(undefined),
      );
      renderNewForm();
      expect(
        screen.getByRole("heading", { name: "New Connection", level: 1 }),
      ).toBeInTheDocument();
    });

    it("renders all form fields", () => {
      mockUseConnectionDetail.mockReturnValue(
        successState(undefined),
      );
      renderNewForm();
      expect(screen.getByTestId("input-name")).toBeInTheDocument();
      expect(screen.getByTestId("select-db-type")).toBeInTheDocument();
      expect(screen.getByTestId("input-host")).toBeInTheDocument();
      expect(screen.getByTestId("input-port")).toBeInTheDocument();
      expect(screen.getByTestId("input-database")).toBeInTheDocument();
      expect(screen.getByTestId("input-username")).toBeInTheDocument();
      expect(screen.getByTestId("input-password")).toBeInTheDocument();
    });

    it("has save button disabled when required fields are empty", () => {
      mockUseConnectionDetail.mockReturnValue(
        successState(undefined),
      );
      renderNewForm();
      const saveButton = screen.getByTestId("save-button");
      expect(saveButton).toBeDisabled();
    });

    it("enables save button when all required fields are filled", async () => {
      mockUseConnectionDetail.mockReturnValue(
        successState(undefined),
      );
      renderNewForm();
      const user = userEvent.setup();

      await user.type(screen.getByTestId("input-name"), "Test DB");
      await user.type(screen.getByTestId("input-host"), "localhost");
      await user.type(screen.getByTestId("input-database"), "testdb");
      await user.type(screen.getByTestId("input-username"), "user");
      await user.type(screen.getByTestId("input-password"), "pass");

      const saveButton = screen.getByTestId("save-button");
      expect(saveButton).not.toBeDisabled();
    });

    it("defaults port to 5432 for PostgreSQL", () => {
      mockUseConnectionDetail.mockReturnValue(
        successState(undefined),
      );
      renderNewForm();
      const portInput = screen.getByTestId("input-port") as HTMLInputElement;
      expect(portInput.value).toBe("5432");
    });

    it("auto-fills port when db_type changes to MySQL", async () => {
      mockUseConnectionDetail.mockReturnValue(
        successState(undefined),
      );
      renderNewForm();
      const user = userEvent.setup();
      const dbTypeSelect = screen.getByTestId(
        "select-db-type",
      ) as HTMLSelectElement;

      await user.selectOptions(dbTypeSelect, "mysql");

      const portInput = screen.getByTestId("input-port") as HTMLInputElement;
      expect(portInput.value).toBe("3306");
    });

    it("auto-fills port when db_type changes back to PostgreSQL", async () => {
      mockUseConnectionDetail.mockReturnValue(
        successState(undefined),
      );
      renderNewForm();
      const user = userEvent.setup();
      const dbTypeSelect = screen.getByTestId(
        "select-db-type",
      ) as HTMLSelectElement;

      await user.selectOptions(dbTypeSelect, "mysql");
      await user.selectOptions(dbTypeSelect, "postgresql");

      const portInput = screen.getByTestId("input-port") as HTMLInputElement;
      expect(portInput.value).toBe("5432");
    });

    it("password is masked by default", () => {
      mockUseConnectionDetail.mockReturnValue(
        successState(undefined),
      );
      renderNewForm();
      const passwordInput = screen.getByTestId(
        "input-password",
      ) as HTMLInputElement;
      expect(passwordInput.type).toBe("password");
    });

    it("toggles password visibility", async () => {
      mockUseConnectionDetail.mockReturnValue(
        successState(undefined),
      );
      renderNewForm();
      const user = userEvent.setup();
      const passwordInput = screen.getByTestId(
        "input-password",
      ) as HTMLInputElement;
      const toggleButton = screen.getByTestId("toggle-password");

      expect(passwordInput.type).toBe("password");
      await user.click(toggleButton);
      expect(passwordInput.type).toBe("text");
      await user.click(toggleButton);
      expect(passwordInput.type).toBe("password");
    });

    it("submits create API when save is clicked", async () => {
      mockUseConnectionDetail.mockReturnValue(
        successState(undefined),
      );
      renderNewForm();
      const user = userEvent.setup();

      await user.type(screen.getByTestId("input-name"), "Test DB");
      await user.type(screen.getByTestId("input-host"), "localhost");
      await user.type(screen.getByTestId("input-database"), "testdb");
      await user.type(screen.getByTestId("input-username"), "user");
      await user.type(screen.getByTestId("input-password"), "pass");

      await user.click(screen.getByTestId("save-button"));

      expect(mockCreateMutate).toHaveBeenCalledWith(
        {
          name: "Test DB",
          db_type: "postgresql",
          host: "localhost",
          port: 5432,
          database_name: "testdb",
          username: "user",
          password: "pass",
        },
        expect.objectContaining({
          onSuccess: expect.any(Function),
          onError: expect.any(Function),
        }),
      );
    });

    it("calls test-params API when test button is clicked", async () => {
      mockUseConnectionDetail.mockReturnValue(
        successState(undefined),
      );
      renderNewForm();
      const user = userEvent.setup();

      await user.type(screen.getByTestId("input-host"), "localhost");
      await user.type(screen.getByTestId("input-database"), "testdb");
      await user.type(screen.getByTestId("input-username"), "user");
      await user.type(screen.getByTestId("input-password"), "pass");

      await user.click(screen.getByTestId("test-button"));

      expect(mockTestParamsMutate).toHaveBeenCalledWith(
        {
          db_type: "postgresql",
          host: "localhost",
          port: 5432,
          database_name: "testdb",
          username: "user",
          password: "pass",
        },
        expect.objectContaining({
          onSuccess: expect.any(Function),
          onError: expect.any(Function),
        }),
      );
    });

    it("renders breadcrumbs with Dashboard, Connections, New Connection", () => {
      mockUseConnectionDetail.mockReturnValue(
        successState(undefined),
      );
      renderNewForm();
      const breadcrumbs = screen.getByTestId("breadcrumbs");
      expect(breadcrumbs).toBeInTheDocument();
      const items = breadcrumbs.querySelectorAll("li");
      const lastItem = items[items.length - 1];
      expect(lastItem?.textContent).toBe("New Connection");
    });
  });

  describe("edit connection mode", () => {
    it("renders edit connection heading", () => {
      renderEditForm("660e8400-e29b-41d4-a716-446655440001");
      expect(
        screen.getByRole("heading", { name: /Edit Connection/i, level: 1 }),
      ).toBeInTheDocument();
    });

    it("pre-fills form with existing connection data", () => {
      renderEditForm("660e8400-e29b-41d4-a716-446655440001");

      expect(
        (screen.getByTestId("input-name") as HTMLInputElement).value,
      ).toBe("Production DB");
      expect(
        (screen.getByTestId("select-db-type") as HTMLSelectElement).value,
      ).toBe("postgresql");
      expect(
        (screen.getByTestId("input-host") as HTMLInputElement).value,
      ).toBe("db.example.com");
      expect(
        (screen.getByTestId("input-port") as HTMLInputElement).value,
      ).toBe("5432");
      expect(
        (screen.getByTestId("input-database") as HTMLInputElement).value,
      ).toBe("production");
      expect(
        (screen.getByTestId("input-username") as HTMLInputElement).value,
      ).toBe("admin");
    });

    it("password field is empty in edit mode", () => {
      renderEditForm("660e8400-e29b-41d4-a716-446655440001");
      const passwordInput = screen.getByTestId(
        "input-password",
      ) as HTMLInputElement;
      expect(passwordInput.value).toBe("");
    });

    it("shows hint about keeping current password", () => {
      renderEditForm("660e8400-e29b-41d4-a716-446655440001");
      expect(
        screen.getByText("(leave blank to keep current)"),
      ).toBeInTheDocument();
    });

    it("save button is enabled in edit mode with pre-filled fields (no password required)", () => {
      renderEditForm("660e8400-e29b-41d4-a716-446655440001");
      const saveButton = screen.getByTestId("save-button");
      expect(saveButton).not.toBeDisabled();
    });

    it("submits update API when save is clicked", async () => {
      renderEditForm("660e8400-e29b-41d4-a716-446655440001");
      const user = userEvent.setup();

      await user.click(screen.getByTestId("save-button"));

      expect(mockUpdateMutate).toHaveBeenCalledWith(
        {
          id: "660e8400-e29b-41d4-a716-446655440001",
          body: expect.objectContaining({
            name: "Production DB",
            host: "db.example.com",
          }),
        },
        expect.objectContaining({
          onSuccess: expect.any(Function),
          onError: expect.any(Function),
        }),
      );
    });

    it("shows invalid ID page for non-UUID edit route", () => {
      renderEditForm("not-a-valid-uuid");
      expect(
        screen.getByText("Invalid Connection ID"),
      ).toBeInTheDocument();
    });

    it("shows loading skeleton when connection data is loading", () => {
      mockUseConnectionDetail.mockReturnValue(loadingState());
      const { container } = renderEditForm(
        "660e8400-e29b-41d4-a716-446655440001",
      );
      const skeletons = container.querySelectorAll(".animate-pulse");
      expect(skeletons.length).toBeGreaterThan(0);
    });

    it("renders breadcrumbs with Edit Connection label", () => {
      renderEditForm("660e8400-e29b-41d4-a716-446655440001");
      const breadcrumbs = screen.getByTestId("breadcrumbs");
      expect(breadcrumbs).toBeInTheDocument();
      // The breadcrumb contains "Edit Connection" as a list item
      const items = breadcrumbs.querySelectorAll("li");
      const lastItem = items[items.length - 1];
      expect(lastItem?.textContent).toBe("Edit Connection");
    });
  });

  describe("port validation", () => {
    it("shows error for invalid port value", async () => {
      mockUseConnectionDetail.mockReturnValue(
        successState(undefined),
      );
      renderNewForm();
      const user = userEvent.setup();
      const portInput = screen.getByTestId("input-port");

      await user.clear(portInput);
      await user.type(portInput, "99999");

      expect(screen.getByTestId("port-error")).toBeInTheDocument();
      expect(screen.getByText("Port must be between 1 and 65535")).toBeInTheDocument();
    });

    it("shows error for non-numeric port", async () => {
      mockUseConnectionDetail.mockReturnValue(
        successState(undefined),
      );
      renderNewForm();
      const user = userEvent.setup();
      const portInput = screen.getByTestId("input-port");

      await user.clear(portInput);
      await user.type(portInput, "abc");

      expect(screen.getByTestId("port-error")).toBeInTheDocument();
    });

    it("shows error for empty port", async () => {
      mockUseConnectionDetail.mockReturnValue(
        successState(undefined),
      );
      renderNewForm();
      const user = userEvent.setup();
      const portInput = screen.getByTestId("input-port");

      await user.clear(portInput);

      expect(screen.getByTestId("port-error")).toBeInTheDocument();
      expect(screen.getByText("Port is required")).toBeInTheDocument();
    });
  });

  describe("long hostname", () => {
    it("accepts a long hostname", async () => {
      mockUseConnectionDetail.mockReturnValue(
        successState(undefined),
      );
      renderNewForm();
      const user = userEvent.setup();
      const longHost =
        "very-long-hostname.subdomain.another-subdomain.example.com";

      await user.type(screen.getByTestId("input-host"), longHost);

      const hostInput = screen.getByTestId("input-host") as HTMLInputElement;
      expect(hostInput.value).toBe(longHost);
    });
  });

  describe("test result display", () => {
    it("shows success test result inline", async () => {
      mockUseConnectionDetail.mockReturnValue(
        successState(undefined),
      );
      mockTestParamsMutate.mockImplementation(
        (
          _body: unknown,
          opts: {
            onSuccess: (r: {
              status: string;
              latency_ms: number;
              tables_found: number;
            }) => void;
          },
        ) => {
          opts.onSuccess({
            status: "connected",
            latency_ms: 42,
            tables_found: 10,
          });
        },
      );
      renderNewForm();
      const user = userEvent.setup();

      await user.type(screen.getByTestId("input-host"), "localhost");
      await user.type(screen.getByTestId("input-database"), "testdb");
      await user.type(screen.getByTestId("input-username"), "user");
      await user.type(screen.getByTestId("input-password"), "pass");
      await user.click(screen.getByTestId("test-button"));

      expect(screen.getByTestId("test-result")).toBeInTheDocument();
      expect(screen.getByText(/Connection successful/)).toBeInTheDocument();
      expect(screen.getByText(/42ms/)).toBeInTheDocument();
      expect(screen.getByText(/10 tables found/)).toBeInTheDocument();
    });

    it("shows test failure details inline", async () => {
      mockUseConnectionDetail.mockReturnValue(
        successState(undefined),
      );
      mockTestParamsMutate.mockImplementation(
        (
          _body: unknown,
          opts: {
            onSuccess: (r: {
              status: string;
              error: string;
              latency_ms: null;
              tables_found: null;
            }) => void;
          },
        ) => {
          opts.onSuccess({
            status: "error",
            error: "Connection refused",
            latency_ms: null,
            tables_found: null,
          });
        },
      );
      renderNewForm();
      const user = userEvent.setup();

      await user.type(screen.getByTestId("input-host"), "localhost");
      await user.type(screen.getByTestId("input-database"), "testdb");
      await user.type(screen.getByTestId("input-username"), "user");
      await user.type(screen.getByTestId("input-password"), "pass");
      await user.click(screen.getByTestId("test-button"));

      expect(screen.getByTestId("test-result")).toBeInTheDocument();
      expect(
        screen.getByText(/Connection test failed: Connection refused/),
      ).toBeInTheDocument();
    });

    it("test result preserved when save fails", async () => {
      mockUseConnectionDetail.mockReturnValue(
        successState(undefined),
      );

      // Set up test success
      mockTestParamsMutate.mockImplementation(
        (
          _body: unknown,
          opts: {
            onSuccess: (r: {
              status: string;
              latency_ms: number;
              tables_found: number;
            }) => void;
          },
        ) => {
          opts.onSuccess({
            status: "connected",
            latency_ms: 42,
            tables_found: 10,
          });
        },
      );

      // Set up save failure
      mockCreateMutate.mockImplementation(
        (
          _body: unknown,
          opts: { onError: (e: Error) => void },
        ) => {
          opts.onError(new Error("Save failed: server error"));
        },
      );

      renderNewForm();
      const user = userEvent.setup();

      await user.type(screen.getByTestId("input-name"), "Test DB");
      await user.type(screen.getByTestId("input-host"), "localhost");
      await user.type(screen.getByTestId("input-database"), "testdb");
      await user.type(screen.getByTestId("input-username"), "user");
      await user.type(screen.getByTestId("input-password"), "pass");

      // Test first
      await user.click(screen.getByTestId("test-button"));
      expect(screen.getByTestId("test-result")).toBeInTheDocument();

      // Then save (fails)
      await user.click(screen.getByTestId("save-button"));

      // Test result should still be visible
      expect(screen.getByTestId("test-result")).toBeInTheDocument();
      expect(screen.getByText(/Connection successful/)).toBeInTheDocument();

      // Save error should be shown
      expect(screen.getByTestId("save-error")).toBeInTheDocument();
      expect(
        screen.getByText("Save failed: server error"),
      ).toBeInTheDocument();
    });
  });

  describe("error handling", () => {
    it("shows save failure as inline error with form preserved", async () => {
      mockUseConnectionDetail.mockReturnValue(
        successState(undefined),
      );
      mockCreateMutate.mockImplementation(
        (
          _body: unknown,
          opts: { onError: (e: Error) => void },
        ) => {
          opts.onError(new Error("Server error"));
        },
      );
      renderNewForm();
      const user = userEvent.setup();

      await user.type(screen.getByTestId("input-name"), "Test DB");
      await user.type(screen.getByTestId("input-host"), "localhost");
      await user.type(screen.getByTestId("input-database"), "testdb");
      await user.type(screen.getByTestId("input-username"), "user");
      await user.type(screen.getByTestId("input-password"), "pass");

      await user.click(screen.getByTestId("save-button"));

      // Error shown
      expect(screen.getByTestId("save-error")).toBeInTheDocument();
      expect(screen.getByText("Server error")).toBeInTheDocument();

      // Form still has values
      expect(
        (screen.getByTestId("input-name") as HTMLInputElement).value,
      ).toBe("Test DB");
    });
  });
});
