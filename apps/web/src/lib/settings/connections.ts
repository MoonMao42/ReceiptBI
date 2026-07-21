import type {
  ConfiguredConnection,
  ConnectionExtraOptions,
  ConnectionSSLMode,
  ConnectionSummary,
} from "@/lib/types/api";

export interface ConnectionExtraOptionsForm {
  sslmode: ConnectionSSLMode;
  sslrootcert: string;
  sslcert: string;
  sslkey: string;
  schema: string;
}

export interface ConnectionFormData {
  name: string;
  driver: string;
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;
  extra_options: ConnectionExtraOptionsForm;
  is_default: boolean;
}

export interface ConnectionTestResult {
  id: string;
  success: boolean;
  message: string;
}

export const CONNECTION_DRIVERS = [
  { value: "mysql", label: "MySQL", defaultPort: 3306 },
  { value: "postgresql", label: "PostgreSQL", defaultPort: 5432 },
  { value: "sqlite", label: "SQLite", defaultPort: 0 },
] as const;

export const defaultConnectionFormData: ConnectionFormData = {
  name: "",
  driver: "mysql",
  host: "localhost",
  port: 3306,
  database: "",
  username: "",
  password: "",
  extra_options: {
    sslmode: "prefer",
    sslrootcert: "",
    sslcert: "",
    sslkey: "",
    schema: "",
  },
  is_default: false,
};

function buildExtraOptionsForm(
  options: ConnectionExtraOptions | undefined
): ConnectionExtraOptionsForm {
  return {
    sslmode: options?.sslmode ?? "prefer",
    sslrootcert: options?.sslrootcert ?? "",
    sslcert: options?.sslcert ?? "",
    sslkey: options?.sslkey ?? "",
    schema: options?.schema ?? "",
  };
}

export function getConnectionDatabase(
  connection: Pick<ConnectionSummary, "database" | "database_name">
): string {
  return connection.database ?? connection.database_name ?? "";
}

export function formatConnectionTarget(connection: ConfiguredConnection): string {
  const database = getConnectionDatabase(connection);
  if (connection.driver === "sqlite") {
    return database;
  }

  const host = connection.host?.trim() ?? "";
  const port = connection.port == null ? "" : `:${connection.port}`;
  const endpoint = host ? `${connection.driver}://${host}${port}` : connection.driver;
  return database ? `${endpoint}/${database}` : endpoint;
}

export function buildConnectionFormData(
  connection: ConfiguredConnection
): ConnectionFormData {
  const driverInfo = CONNECTION_DRIVERS.find((item) => item.value === connection.driver);
  return {
    name: connection.name,
    driver: connection.driver,
    host: connection.host ?? "",
    port: connection.port ?? driverInfo?.defaultPort ?? 0,
    database: getConnectionDatabase(connection),
    username: connection.username ?? "",
    password: "",
    extra_options: buildExtraOptionsForm(connection.extra_options),
    is_default: connection.is_default,
  };
}

export function applyDriverDefaults(
  formData: ConnectionFormData,
  driver: string
): ConnectionFormData {
  const driverInfo = CONNECTION_DRIVERS.find((item) => item.value === driver);
  const extraOptions =
    driver === "sqlite"
      ? { ...defaultConnectionFormData.extra_options }
      : {
          ...formData.extra_options,
          schema: driver === "postgresql" ? formData.extra_options.schema : "",
        };
  return {
    ...formData,
    driver,
    port: driverInfo?.defaultPort ?? 3306,
    extra_options: extraOptions,
  };
}
