//! Capability-limited, read-only SQLite execution for the local desktop host.
//!
//! This crate owns no renderer or IPC types. Callers must register a validated
//! query before moving it to a worker thread. Cancellation is linearized in the
//! registry and reaches SQLite through both `sqlite3_interrupt` and a progress
//! handler, while termination of the outer sidecar process remains the
//! hard-kill boundary.

use std::collections::{HashMap, HashSet};
use std::error::Error;
use std::fmt::{self, Display, Formatter};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, MutexGuard};
use std::time::{Duration, Instant};

use rusqlite::config::DbConfig;
use rusqlite::hooks::{AuthAction, AuthContext, Authorization};
use rusqlite::limits::Limit;
use rusqlite::types::{ToSql, ToSqlOutput, ValueRef};
use rusqlite::{
    Connection, Error as SqliteError, ErrorCode as SqliteErrorCode, InterruptHandle, OpenFlags,
    PrepFlags, params_from_iter,
};

const MAX_QUERY_ID_BYTES: usize = 128;
const MAX_ACTIVE_QUERIES: usize = 1;
const MAX_SQL_BYTES: usize = 64 * 1024;
const MAX_PARAMETERS: usize = 256;
const MAX_PARAMETER_TEXT_BYTES: usize = 1024 * 1024;
const MAX_PARAMETER_BYTES: usize = 8 * 1024 * 1024;
const MAX_RELATIONS: usize = 128;
const MAX_COLUMNS: usize = 256;
const MAX_IDENTIFIER_BYTES: usize = 1024;
const MAX_PLAN_STEPS: u32 = 64;
const MAX_PLAN_FULL_SCANS: u32 = 8;
const MAX_PLAN_TEMP_BTREES: u32 = 4;
const MAX_ROWS: u32 = 50_000;
const MIN_RESULT_BYTES: u32 = 1024;
const MAX_RESULT_BYTES: u32 = 32 * 1024 * 1024;
pub const MAX_SQLITE_VALUE_BYTES: u32 = 16 * 1024 * 1024;
const MIN_TIMEOUT: Duration = Duration::from_millis(10);
const MAX_TIMEOUT: Duration = Duration::from_secs(60);
const BUSY_TIMEOUT: Duration = Duration::from_millis(250);
const PROGRESS_INTERVAL_OPS: i32 = 1_000;
const PINNED_SQLITE_EQP_VERSION: &str = "3.53.2";

const SAFE_FUNCTIONS: &[&str] = &[
    "abs",
    "avg",
    "coalesce",
    "count",
    "date",
    "datetime",
    "dense_rank",
    "first_value",
    "ifnull",
    "instr",
    "julianday",
    "lag",
    "last_value",
    "lead",
    "length",
    "like",
    "lower",
    "max",
    "min",
    "nullif",
    "ntile",
    "rank",
    "round",
    "row_number",
    "strftime",
    "substr",
    "substring",
    "sum",
    "time",
    "total",
    "unixepoch",
    "upper",
];

#[derive(Clone, Debug, PartialEq)]
pub enum QueryParameter {
    Null,
    Integer(i64),
    Real(f64),
    Text(String),
}

impl ToSql for QueryParameter {
    fn to_sql(&self) -> rusqlite::Result<ToSqlOutput<'_>> {
        Ok(ToSqlOutput::Borrowed(match self {
            Self::Null => ValueRef::Null,
            Self::Integer(value) => ValueRef::Integer(*value),
            Self::Real(value) => ValueRef::Real(*value),
            Self::Text(value) => ValueRef::Text(value.as_bytes()),
        }))
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct QueryLimits {
    pub max_rows: u32,
    pub max_bytes: u32,
    pub timeout: Duration,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ExpectedLogicalType {
    Integer,
    Real,
    Number,
    Text,
    Boolean,
    /// Accept any non-BLOB SQLite scalar while preserving its concrete value
    /// kind in `QueryCell`. This is reserved for the compatibility boundary
    /// that executes legacy SQL without a precompiled result schema.
    Scalar,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ExpectedColumn {
    pub name: String,
    pub logical_type: ExpectedLogicalType,
    pub nullable: bool,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct QueryPlanBudget {
    pub max_steps: u32,
    pub max_full_scans: u32,
    pub max_temp_btrees: u32,
}

/// The path capability identity captured at the host/sidecar boundary before execution.
///
/// These fields provide the platform-neutral process contract used to detect
/// accidental replacement and ordinary local source churn, but they are not a
/// cryptographic or atomic defense against a hostile process running as the
/// same user and swapping a path between checks.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ExpectedSourceIdentity {
    pub dev: u64,
    pub ino: u64,
    pub ctime_ns: u64,
    pub mtime_ns: u64,
    pub size: u64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct QueryRequest {
    pub query_id: String,
    pub database_path: PathBuf,
    pub expected_source_identity: ExpectedSourceIdentity,
    pub sql: String,
    pub parameters: Vec<QueryParameter>,
    pub allowed_relations: Vec<String>,
    pub expected_columns: Vec<ExpectedColumn>,
    /// Legacy callers may ask the executor to bind the result column names at
    /// prepare time. Explicit-schema callers keep this disabled and retain the
    /// stronger compiled-output contract.
    pub allow_dynamic_result_schema: bool,
    pub plan_budget: QueryPlanBudget,
    pub limits: QueryLimits,
}

#[derive(Clone, Debug, PartialEq)]
pub enum QueryCell {
    Null,
    Integer(i64),
    Real(f64),
    Text(String),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TruncationReason {
    RowLimit,
    ByteLimit,
}

#[derive(Clone, Debug, PartialEq)]
pub struct QueryResult {
    pub columns: Vec<String>,
    pub rows: Vec<Vec<QueryCell>>,
    pub row_count: u32,
    pub byte_count: u32,
    pub truncated_by: Option<TruncationReason>,
    pub duration: Duration,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ExecutorErrorCode {
    InvalidRequest,
    DuplicateQuery,
    SourceUnavailable,
    SourceChanged,
    SourceActiveJournal,
    QueryDenied,
    QueryBudgetExceeded,
    QueryPlanUnverified,
    ResourceExhausted,
    QueryCellLimitExceeded,
    QueryBusy,
    QueryCancelled,
    QueryTimedOut,
    QueryResultInvalid,
    QueryExecutionFailed,
    Internal,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ExecutorError {
    code: ExecutorErrorCode,
    message: &'static str,
    retryable: bool,
}

impl ExecutorError {
    pub fn code(&self) -> ExecutorErrorCode {
        self.code
    }

    pub fn safe_message(&self) -> &'static str {
        self.message
    }

    pub fn retryable(&self) -> bool {
        self.retryable
    }
}

impl Display for ExecutorError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.message)
    }
}

impl Error for ExecutorError {}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CancelDisposition {
    Requested,
    AlreadyRequested,
    TooLate,
    NotFound,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum RunPhase {
    Registered,
    Running,
    Finished,
}

struct RunState {
    phase: RunPhase,
    cancel_requested: bool,
    interrupt: Option<Arc<InterruptHandle>>,
}

struct RunControl {
    cancelled: AtomicBool,
    state: Mutex<RunState>,
}

impl RunControl {
    fn new() -> Self {
        Self {
            cancelled: AtomicBool::new(false),
            state: Mutex::new(RunState {
                phase: RunPhase::Registered,
                cancel_requested: false,
                interrupt: None,
            }),
        }
    }

    fn begin(&self) -> Result<(), ExecutorError> {
        let cancel_requested = {
            let mut state = lock(&self.state)?;
            if state.phase != RunPhase::Registered {
                return Err(internal_error());
            }
            state.phase = RunPhase::Running;
            state.cancel_requested
        };
        if cancel_requested {
            return Err(cancelled_error());
        }
        Ok(())
    }

    fn arm(&self, interrupt: Arc<InterruptHandle>) -> Result<(), ExecutorError> {
        let cancel_requested = {
            let mut state = lock(&self.state)?;
            if state.phase != RunPhase::Running || state.interrupt.is_some() {
                return Err(internal_error());
            }
            state.interrupt = Some(Arc::clone(&interrupt));
            state.cancel_requested
        };

        if cancel_requested {
            interrupt.interrupt();
            return Err(cancelled_error());
        }
        Ok(())
    }

    fn request_cancel(&self) -> Result<CancelDisposition, ExecutorError> {
        let (disposition, interrupt) = {
            let mut state = lock(&self.state)?;
            if state.phase == RunPhase::Finished {
                return Ok(CancelDisposition::TooLate);
            }

            let disposition = if state.cancel_requested {
                CancelDisposition::AlreadyRequested
            } else {
                state.cancel_requested = true;
                self.cancelled.store(true, Ordering::SeqCst);
                CancelDisposition::Requested
            };
            (disposition, state.interrupt.as_ref().map(Arc::clone))
        };

        if let Some(interrupt) = interrupt {
            interrupt.interrupt();
        }
        Ok(disposition)
    }

    fn finish(&self) -> Result<bool, ExecutorError> {
        let mut state = lock(&self.state)?;
        let cancel_requested = state.cancel_requested;
        state.phase = RunPhase::Finished;
        state.interrupt = None;
        Ok(cancel_requested)
    }

    fn abandon_before_start(&self) -> Result<bool, ExecutorError> {
        let mut state = lock(&self.state)?;
        if state.phase != RunPhase::Registered {
            return Ok(false);
        }
        state.phase = RunPhase::Finished;
        Ok(true)
    }
}

type Registry = Arc<Mutex<HashMap<String, Arc<RunControl>>>>;

#[derive(Clone)]
pub struct QueryExecutor {
    registry: Registry,
}

impl Default for QueryExecutor {
    fn default() -> Self {
        Self::new()
    }
}

pub fn sqlite_version() -> &'static str {
    rusqlite::version()
}

/// Capture the filesystem identity used to bind a query to one SQLite source.
///
/// Execution checks this identity again before opening the database and after
/// reading the result. Symlinks and databases with active journal sidecars are
/// rejected here as well as during execution.
pub fn capture_source_identity(
    database_path: &Path,
) -> Result<ExpectedSourceIdentity, ExecutorError> {
    let metadata = fs::symlink_metadata(database_path).map_err(|_| source_error())?;
    if !metadata.is_file() || metadata.file_type().is_symlink() {
        return Err(source_error());
    }
    reject_active_journals(database_path)?;
    source_identity(database_path, &metadata)
}

impl QueryExecutor {
    pub fn new() -> Self {
        Self {
            registry: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    pub fn register(&self, request: QueryRequest) -> Result<RegisteredQuery, ExecutorError> {
        validate_request(&request)?;
        let control = Arc::new(RunControl::new());
        {
            let mut registry = lock(&self.registry)?;
            if registry.contains_key(&request.query_id) {
                return Err(executor_error(
                    ExecutorErrorCode::DuplicateQuery,
                    "The query identifier is already active.",
                    false,
                ));
            }
            if registry.len() >= MAX_ACTIVE_QUERIES {
                return Err(executor_error(
                    ExecutorErrorCode::QueryBusy,
                    "The local SQLite executor is already running a query.",
                    true,
                ));
            }
            registry.insert(request.query_id.clone(), Arc::clone(&control));
        }

        Ok(RegisteredQuery {
            registry: Arc::clone(&self.registry),
            query_id: request.query_id.clone(),
            request: Some(request),
            control,
        })
    }

    pub fn cancel(&self, query_id: &str) -> Result<CancelDisposition, ExecutorError> {
        let control = {
            let registry = lock(&self.registry)?;
            registry.get(query_id).map(Arc::clone)
        };
        match control {
            Some(control) => control.request_cancel(),
            None => Ok(CancelDisposition::NotFound),
        }
    }
}

pub struct RegisteredQuery {
    registry: Registry,
    query_id: String,
    request: Option<QueryRequest>,
    control: Arc<RunControl>,
}

#[derive(Clone)]
pub struct RegistrationHandle {
    registry: Registry,
    query_id: String,
    control: Arc<RunControl>,
}

impl RegistrationHandle {
    /// Removes this exact registration only if worker execution has not begun.
    /// This is used when a host fails to queue a task after synchronous
    /// registration.
    pub fn unregister_before_start(&self) -> Result<bool, ExecutorError> {
        if !self.control.abandon_before_start()? {
            return Ok(false);
        }
        unregister_if_same(&self.registry, &self.query_id, &self.control);
        Ok(true)
    }
}

impl RegisteredQuery {
    /// Executes the registered request once on the current thread.
    ///
    /// The caller is expected to move this value onto a dedicated worker
    /// thread. The SQLite connection never crosses threads.
    pub fn execute(&mut self) -> Result<QueryResult, ExecutorError> {
        let request = self.request.take().ok_or_else(internal_error)?;
        let result = self
            .control
            .begin()
            .and_then(|()| execute_request(&request, &self.control));
        let cancel_won = self.control.finish()?;
        if cancel_won {
            return Err(cancelled_error());
        }
        result
    }

    pub fn query_id(&self) -> &str {
        &self.query_id
    }

    pub fn registration_handle(&self) -> RegistrationHandle {
        RegistrationHandle {
            registry: Arc::clone(&self.registry),
            query_id: self.query_id.clone(),
            control: Arc::clone(&self.control),
        }
    }
}

impl Drop for RegisteredQuery {
    fn drop(&mut self) {
        unregister_if_same(&self.registry, &self.query_id, &self.control);
    }
}

fn unregister_if_same(registry: &Registry, query_id: &str, control: &Arc<RunControl>) {
    let Ok(mut registry) = registry.lock() else {
        return;
    };
    let should_remove = registry
        .get(query_id)
        .is_some_and(|current| Arc::ptr_eq(current, control));
    if should_remove {
        registry.remove(query_id);
    }
}

fn validate_request(request: &QueryRequest) -> Result<(), ExecutorError> {
    if request.query_id.is_empty()
        || request.query_id.len() > MAX_QUERY_ID_BYTES
        || !request
            .query_id
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_')
    {
        return Err(invalid_request());
    }
    if !request.database_path.is_absolute()
        || request.database_path.as_os_str().is_empty()
        || request
            .database_path
            .as_os_str()
            .to_string_lossy()
            .contains('\0')
    {
        return Err(invalid_request());
    }
    if request.sql.trim().is_empty()
        || request.sql.len() > MAX_SQL_BYTES
        || request.sql.as_bytes().contains(&0)
    {
        return Err(invalid_request());
    }
    if request.parameters.len() > MAX_PARAMETERS
        || request.allowed_relations.is_empty()
        || request.allowed_relations.len() > MAX_RELATIONS
        || request.expected_columns.len() > MAX_COLUMNS
        || request.allow_dynamic_result_schema != request.expected_columns.is_empty()
        || request.plan_budget.max_steps == 0
        || request.plan_budget.max_steps > MAX_PLAN_STEPS
        || request.plan_budget.max_full_scans > MAX_PLAN_FULL_SCANS
        || request.plan_budget.max_temp_btrees > MAX_PLAN_TEMP_BTREES
        || request.limits.max_rows == 0
        || request.limits.max_rows > MAX_ROWS
        || request.limits.max_bytes < MIN_RESULT_BYTES
        || request.limits.max_bytes > MAX_RESULT_BYTES
        || request.limits.timeout < MIN_TIMEOUT
        || request.limits.timeout > MAX_TIMEOUT
    {
        return Err(invalid_request());
    }

    let mut parameter_bytes = 0_usize;
    for parameter in &request.parameters {
        match parameter {
            QueryParameter::Real(value) if !value.is_finite() => return Err(invalid_request()),
            QueryParameter::Text(value)
                if value.len() > MAX_PARAMETER_TEXT_BYTES || value.as_bytes().contains(&0) =>
            {
                return Err(invalid_request());
            }
            _ => {}
        }
        parameter_bytes = parameter_bytes
            .checked_add(match parameter {
                QueryParameter::Null => 1,
                QueryParameter::Integer(_) | QueryParameter::Real(_) => 8,
                QueryParameter::Text(value) => value.len(),
            })
            .and_then(|value| value.checked_add(16))
            .ok_or_else(invalid_request)?;
        if parameter_bytes > MAX_PARAMETER_BYTES {
            return Err(invalid_request());
        }
    }

    validate_unique_names(&request.allowed_relations, true)?;
    if !request.allow_dynamic_result_schema {
        let expected_names: Vec<String> = request
            .expected_columns
            .iter()
            .map(|column| column.name.clone())
            .collect();
        validate_unique_names(&expected_names, false)?;
    }
    Ok(())
}

fn validate_unique_names(
    values: &[String],
    ascii_case_insensitive: bool,
) -> Result<(), ExecutorError> {
    let mut names = HashSet::with_capacity(values.len());
    for value in values {
        let key = if ascii_case_insensitive {
            value.to_ascii_lowercase()
        } else {
            value.clone()
        };
        if value.is_empty()
            || value.len() > MAX_IDENTIFIER_BYTES
            || value.chars().any(char::is_control)
            || (ascii_case_insensitive && key.starts_with("sqlite_"))
            || !names.insert(key)
        {
            return Err(invalid_request());
        }
    }
    Ok(())
}

fn execute_request(
    request: &QueryRequest,
    control: &Arc<RunControl>,
) -> Result<QueryResult, ExecutorError> {
    let started = Instant::now();
    let deadline = started
        .checked_add(request.limits.timeout)
        .ok_or_else(internal_error)?;
    verify_source_identity(&request.database_path, &request.expected_source_identity)?;

    let flags = OpenFlags::SQLITE_OPEN_READ_ONLY
        | OpenFlags::SQLITE_OPEN_NO_MUTEX
        | OpenFlags::SQLITE_OPEN_NOFOLLOW
        | OpenFlags::SQLITE_OPEN_EXRESCODE;
    let connection = Connection::open_with_flags(&request.database_path, flags)
        .map_err(|error| map_sqlite_error(&error, control, started, request.limits.timeout))?;
    if !connection.is_readonly("main").map_err(|_| source_error())? {
        return Err(source_error());
    }

    harden_connection(&connection, request)?;
    let interrupt = Arc::new(connection.get_interrupt_handle());
    control.arm(Arc::clone(&interrupt))?;

    if Instant::now() >= deadline {
        return Err(timeout_error());
    }
    let cancelled = Arc::clone(control);
    connection
        .progress_handler(
            PROGRESS_INTERVAL_OPS,
            Some(move || cancelled.cancelled.load(Ordering::SeqCst) || Instant::now() >= deadline),
        )
        .map_err(|_| internal_error())?;

    if control.cancelled.load(Ordering::SeqCst) {
        interrupt.interrupt();
        return Err(cancelled_error());
    }

    let result = execute_statement(&connection, request, control, started)?;
    verify_source_identity(&request.database_path, &request.expected_source_identity)?;
    Ok(result)
}

fn verify_source_identity(
    database_path: &Path,
    expected: &ExpectedSourceIdentity,
) -> Result<(), ExecutorError> {
    let actual = capture_source_identity(database_path)?;
    if actual != *expected {
        return Err(source_changed_error());
    }
    Ok(())
}

fn reject_active_journals(database_path: &Path) -> Result<(), ExecutorError> {
    for suffix in ["-wal", "-shm", "-journal"] {
        let file_name = database_path.file_name().ok_or_else(source_error)?;
        let mut sidecar_name = file_name.to_os_string();
        sidecar_name.push(suffix);
        let sidecar_path = database_path.with_file_name(sidecar_name);
        match fs::symlink_metadata(&sidecar_path) {
            Ok(_) => return Err(source_active_journal_error()),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(_) => return Err(source_error()),
        }
    }
    Ok(())
}

#[cfg(unix)]
fn source_identity(
    _database_path: &Path,
    metadata: &fs::Metadata,
) -> Result<ExpectedSourceIdentity, ExecutorError> {
    use std::os::unix::fs::MetadataExt;

    Ok(ExpectedSourceIdentity {
        dev: metadata.dev(),
        ino: metadata.ino(),
        ctime_ns: unix_timestamp_ns(metadata.ctime(), metadata.ctime_nsec())?,
        mtime_ns: unix_timestamp_ns(metadata.mtime(), metadata.mtime_nsec())?,
        size: metadata.size(),
    })
}

#[cfg(unix)]
fn unix_timestamp_ns(seconds: i64, nanoseconds: i64) -> Result<u64, ExecutorError> {
    if !(0..1_000_000_000).contains(&nanoseconds) {
        return Err(source_error());
    }
    let value = i128::from(seconds)
        .checked_mul(1_000_000_000)
        .and_then(|value| value.checked_add(i128::from(nanoseconds)))
        .and_then(|value| u64::try_from(value).ok())
        .ok_or_else(source_error)?;
    Ok(value)
}

#[cfg(windows)]
fn source_identity(
    database_path: &Path,
    _metadata: &fs::Metadata,
) -> Result<ExpectedSourceIdentity, ExecutorError> {
    use std::fs::File;
    use std::mem::{size_of, zeroed};
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::Storage::FileSystem::{
        BY_HANDLE_FILE_INFORMATION, FILE_BASIC_INFO, FileBasicInfo, GetFileInformationByHandle,
        GetFileInformationByHandleEx,
    };

    let file = File::open(database_path).map_err(|_| source_error())?;
    let handle = file.as_raw_handle();
    // SAFETY: both output structures are initialized before they are read,
    // their exact sizes are passed to the corresponding Win32 APIs, and the
    // borrowed file handle remains alive for the duration of both calls.
    let (handle_info, basic_info) = unsafe {
        let mut handle_info: BY_HANDLE_FILE_INFORMATION = zeroed();
        if GetFileInformationByHandle(handle, &mut handle_info) == 0 {
            return Err(source_error());
        }
        let mut basic_info: FILE_BASIC_INFO = zeroed();
        if GetFileInformationByHandleEx(
            handle,
            FileBasicInfo,
            (&raw mut basic_info).cast(),
            u32::try_from(size_of::<FILE_BASIC_INFO>()).map_err(|_| internal_error())?,
        ) == 0
        {
            return Err(source_error());
        }
        (handle_info, basic_info)
    };

    let ino = (u64::from(handle_info.nFileIndexHigh) << 32) | u64::from(handle_info.nFileIndexLow);
    let size = (u64::from(handle_info.nFileSizeHigh) << 32) | u64::from(handle_info.nFileSizeLow);
    Ok(ExpectedSourceIdentity {
        dev: u64::from(handle_info.dwVolumeSerialNumber),
        ino,
        ctime_ns: windows_filetime_to_unix_ns(basic_info.ChangeTime)?,
        mtime_ns: windows_filetime_to_unix_ns(basic_info.LastWriteTime)?,
        size,
    })
}

#[cfg(windows)]
fn windows_filetime_to_unix_ns(filetime: i64) -> Result<u64, ExecutorError> {
    const WINDOWS_TO_UNIX_EPOCH_100NS: i128 = 116_444_736_000_000_000;
    i128::from(filetime)
        .checked_sub(WINDOWS_TO_UNIX_EPOCH_100NS)
        .and_then(|value| value.checked_mul(100))
        .and_then(|value| u64::try_from(value).ok())
        .ok_or_else(source_error)
}

#[cfg(not(any(unix, windows)))]
fn source_identity(
    _database_path: &Path,
    _metadata: &fs::Metadata,
) -> Result<ExpectedSourceIdentity, ExecutorError> {
    Err(source_error())
}

fn harden_connection(connection: &Connection, request: &QueryRequest) -> Result<(), ExecutorError> {
    for (config, enabled) in [
        (DbConfig::SQLITE_DBCONFIG_DEFENSIVE, true),
        (DbConfig::SQLITE_DBCONFIG_TRUSTED_SCHEMA, false),
        (DbConfig::SQLITE_DBCONFIG_DQS_DML, false),
        (DbConfig::SQLITE_DBCONFIG_DQS_DDL, false),
        (DbConfig::SQLITE_DBCONFIG_ENABLE_TRIGGER, false),
        (DbConfig::SQLITE_DBCONFIG_ENABLE_FTS3_TOKENIZER, false),
        (DbConfig::SQLITE_DBCONFIG_ENABLE_ATTACH_CREATE, false),
        (DbConfig::SQLITE_DBCONFIG_ENABLE_ATTACH_WRITE, false),
        (DbConfig::SQLITE_DBCONFIG_ENABLE_COMMENTS, false),
    ] {
        let actual = connection
            .set_db_config(config, enabled)
            .map_err(|_| internal_error())?;
        if actual != enabled {
            return Err(internal_error());
        }
    }

    connection
        .busy_timeout(BUSY_TIMEOUT.min(request.limits.timeout))
        .map_err(|_| internal_error())?;
    connection
        .pragma_update(None, "temp_store", "MEMORY")
        .map_err(|_| internal_error())?;
    connection
        .pragma_update(None, "cache_size", -8_192_i32)
        .map_err(|_| internal_error())?;
    connection
        .pragma_update(None, "threads", 0_i32)
        .map_err(|_| internal_error())?;
    connection
        .pragma_update(None, "hard_heap_limit", 64 * 1024 * 1024_i32)
        .map_err(|_| internal_error())?;
    connection
        .pragma_update(None, "query_only", true)
        .map_err(|_| internal_error())?;

    for (limit, value) in [
        (Limit::SQLITE_LIMIT_LENGTH, MAX_SQLITE_VALUE_BYTES as i32),
        (Limit::SQLITE_LIMIT_SQL_LENGTH, MAX_SQL_BYTES as i32),
        (Limit::SQLITE_LIMIT_COLUMN, MAX_COLUMNS as i32),
        (Limit::SQLITE_LIMIT_EXPR_DEPTH, 100),
        (Limit::SQLITE_LIMIT_COMPOUND_SELECT, 16),
        (Limit::SQLITE_LIMIT_VDBE_OP, 100_000_000),
        (Limit::SQLITE_LIMIT_FUNCTION_ARG, 32),
        (Limit::SQLITE_LIMIT_ATTACHED, 0),
        (Limit::SQLITE_LIMIT_LIKE_PATTERN_LENGTH, 10_000),
        (Limit::SQLITE_LIMIT_VARIABLE_NUMBER, MAX_PARAMETERS as i32),
        (Limit::SQLITE_LIMIT_TRIGGER_DEPTH, 0),
        (Limit::SQLITE_LIMIT_WORKER_THREADS, 0),
        (Limit::SQLITE_LIMIT_PARSER_DEPTH, 100),
    ] {
        connection
            .set_limit(limit, value)
            .map_err(|_| internal_error())?;
    }

    let relations: HashSet<String> = request
        .allowed_relations
        .iter()
        .map(|name| name.to_ascii_lowercase())
        .collect();
    connection
        .authorizer(Some(move |context: AuthContext<'_>| {
            authorize_query(context, &relations)
        }))
        .map_err(|_| internal_error())?;
    Ok(())
}

fn authorize_query(context: AuthContext<'_>, relations: &HashSet<String>) -> Authorization {
    match context.action {
        AuthAction::Select | AuthAction::Recursive => Authorization::Allow,
        AuthAction::Read {
            table_name,
            column_name,
        } if (context.database_name == Some("main")
            // SQLite reports no database name for the zero-column READ used by
            // count(*). ATTACH is disabled and every non-empty column read must
            // still identify main explicitly.
            || (context.database_name.is_none() && column_name.is_empty()))
            && relations.contains(&table_name.to_ascii_lowercase()) =>
        {
            Authorization::Allow
        }
        AuthAction::Function { function_name }
            if SAFE_FUNCTIONS.contains(&function_name.to_ascii_lowercase().as_str()) =>
        {
            Authorization::Allow
        }
        _ => Authorization::Deny,
    }
}

fn execute_statement(
    connection: &Connection,
    request: &QueryRequest,
    control: &RunControl,
    started: Instant,
) -> Result<QueryResult, ExecutorError> {
    let prepare_flags = PrepFlags::SQLITE_PREPARE_PERSISTENT | PrepFlags::SQLITE_PREPARE_NO_VTAB;
    let mut statement = connection
        .prepare_with_flags(&request.sql, prepare_flags)
        .map_err(|error| map_sqlite_error(&error, control, started, request.limits.timeout))?;
    if !statement.readonly() || statement.column_count() == 0 {
        return Err(executor_error(
            ExecutorErrorCode::QueryDenied,
            "The compiled query is not a read-only result query.",
            false,
        ));
    }
    validate_parameter_layout(&statement, request.parameters.len())?;

    let columns: Vec<String> = statement
        .column_names()
        .iter()
        .map(|name| (*name).to_owned())
        .collect();
    let dynamic_columns;
    let expected_columns = if request.allow_dynamic_result_schema {
        validate_unique_names(&columns, false)?;
        dynamic_columns = columns
            .iter()
            .map(|name| ExpectedColumn {
                name: name.clone(),
                logical_type: ExpectedLogicalType::Scalar,
                nullable: true,
            })
            .collect::<Vec<_>>();
        dynamic_columns.as_slice()
    } else {
        let expected_names: Vec<&str> = request
            .expected_columns
            .iter()
            .map(|column| column.name.as_str())
            .collect();
        if !columns
            .iter()
            .map(String::as_str)
            .eq(expected_names.iter().copied())
        {
            return Err(executor_error(
                ExecutorErrorCode::QueryResultInvalid,
                "The query result schema did not match the compiled output schema.",
                false,
            ));
        }
        request.expected_columns.as_slice()
    };

    check_query_plan(connection, request, control, started, prepare_flags)?;

    let mut cursor = statement
        .query(params_from_iter(request.parameters.iter()))
        .map_err(|error| map_sqlite_error(&error, control, started, request.limits.timeout))?;
    let mut byte_count = encoded_names_size(&columns)?;
    if byte_count > request.limits.max_bytes {
        return Err(executor_error(
            ExecutorErrorCode::QueryResultInvalid,
            "The query result schema exceeded its byte budget.",
            false,
        ));
    }

    let mut rows = Vec::new();
    let mut truncated_by = None;
    loop {
        let next = cursor
            .next()
            .map_err(|error| map_sqlite_error(&error, control, started, request.limits.timeout))?;
        let Some(row) = next else {
            break;
        };
        if rows.len() >= request.limits.max_rows as usize {
            truncated_by = Some(TruncationReason::RowLimit);
            break;
        }

        let remaining_bytes = request
            .limits
            .max_bytes
            .checked_sub(byte_count)
            .ok_or_else(internal_error)?;
        let Some((decoded, row_bytes)) = decode_row(row, expected_columns, remaining_bytes)? else {
            truncated_by = Some(TruncationReason::ByteLimit);
            break;
        };
        let Some(next_byte_count) = byte_count.checked_add(row_bytes) else {
            return Err(internal_error());
        };
        if next_byte_count > request.limits.max_bytes {
            truncated_by = Some(TruncationReason::ByteLimit);
            break;
        }
        byte_count = next_byte_count;
        rows.push(decoded);
    }

    if control.cancelled.load(Ordering::SeqCst) {
        return Err(cancelled_error());
    }
    if started.elapsed() >= request.limits.timeout {
        return Err(timeout_error());
    }

    Ok(QueryResult {
        columns,
        row_count: rows.len() as u32,
        rows,
        byte_count,
        truncated_by,
        duration: started.elapsed(),
    })
}

fn validate_parameter_layout(
    statement: &rusqlite::Statement<'_>,
    parameter_count: usize,
) -> Result<(), ExecutorError> {
    if statement.parameter_count() != parameter_count {
        return Err(invalid_request());
    }
    let mut all_anonymous = true;
    let mut all_numbered = true;
    for index in 1..=statement.parameter_count() {
        let expected = format!("?{index}");
        let actual = statement.parameter_name(index);
        all_anonymous &= actual.is_none();
        all_numbered &= actual == Some(expected.as_str());
    }
    if !all_anonymous && !all_numbered {
        return Err(invalid_request());
    }
    Ok(())
}

fn check_query_plan(
    connection: &Connection,
    request: &QueryRequest,
    control: &RunControl,
    started: Instant,
    prepare_flags: PrepFlags,
) -> Result<(), ExecutorError> {
    if sqlite_version() != PINNED_SQLITE_EQP_VERSION {
        return Err(plan_unverified_error());
    }
    let explain_sql = format!("EXPLAIN QUERY PLAN {}", request.sql);
    let mut statement = connection
        .prepare_with_flags(&explain_sql, prepare_flags)
        .map_err(|error| map_sqlite_error(&error, control, started, request.limits.timeout))?;
    validate_parameter_layout(&statement, request.parameters.len())?;
    let mut cursor = statement
        .query(params_from_iter(request.parameters.iter()))
        .map_err(|error| map_sqlite_error(&error, control, started, request.limits.timeout))?;

    let mut steps = 0_u32;
    let mut full_scans = 0_u32;
    let mut temp_btrees = 0_u32;
    while let Some(row) = cursor
        .next()
        .map_err(|error| map_sqlite_error(&error, control, started, request.limits.timeout))?
    {
        steps = steps.checked_add(1).ok_or_else(internal_error)?;
        if steps > request.plan_budget.max_steps {
            return Err(plan_budget_error());
        }

        let detail = match row.get_ref(3).map_err(|_| result_error())? {
            ValueRef::Text(value) => std::str::from_utf8(value).map_err(|_| result_error())?,
            _ => return Err(result_error()),
        };
        let classification = classify_eqp_detail(detail).ok_or_else(plan_unverified_error)?;
        if classification.full_scan {
            full_scans = full_scans.checked_add(1).ok_or_else(internal_error)?;
            if full_scans > request.plan_budget.max_full_scans {
                return Err(plan_budget_error());
            }
        }
        if classification.temp_btree {
            temp_btrees = temp_btrees.checked_add(1).ok_or_else(internal_error)?;
            if temp_btrees > request.plan_budget.max_temp_btrees {
                return Err(plan_budget_error());
            }
        }
    }
    if steps == 0 {
        return Err(result_error());
    }
    Ok(())
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum EqpDetailClass {
    Scan,
    Search,
    TempBtree,
    Subquery,
    Compound,
    Control,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct EqpClassification {
    class: EqpDetailClass,
    full_scan: bool,
    temp_btree: bool,
}

/// Classifies the documented detail families emitted by bundled SQLite 3.53.2.
///
/// EQP text is intentionally treated as a versioned structural defense, not a
/// cost oracle. A new or malformed family fails closed until the pinned corpus
/// is reviewed. Physical relation/index names may contain Unicode and spaces,
/// so only the stable family prefix and the non-empty suffix are constrained.
fn classify_eqp_detail(detail: &str) -> Option<EqpClassification> {
    if detail.is_empty()
        || detail.trim() != detail
        || detail.len() > 4_096
        || detail.chars().any(char::is_control)
    {
        return None;
    }

    let classified = |class, full_scan, temp_btree| EqpClassification {
        class,
        full_scan,
        temp_btree,
    };
    if matches!(detail, "SCAN CONSTANT ROW" | "SCAN CONSTANT ROWS") {
        return Some(classified(EqpDetailClass::Control, false, false));
    }
    if reviewed_suffix(detail, "SCAN ") {
        return Some(classified(EqpDetailClass::Scan, true, false));
    }
    if reviewed_suffix(detail, "SEARCH ") {
        return Some(classified(EqpDetailClass::Search, false, false));
    }
    if matches!(
        detail,
        "USE TEMP B-TREE FOR ORDER BY"
            | "USE TEMP B-TREE FOR GROUP BY"
            | "USE TEMP B-TREE FOR DISTINCT"
            | "USE TEMP B-TREE FOR RIGHT PART OF ORDER BY"
    ) {
        return Some(classified(EqpDetailClass::TempBtree, false, true));
    }

    for prefix in [
        "SCALAR SUBQUERY ",
        "CORRELATED SCALAR SUBQUERY ",
        "LIST SUBQUERY ",
        "CORRELATED LIST SUBQUERY ",
    ] {
        if detail
            .strip_prefix(prefix)
            .is_some_and(reviewed_decimal_identifier)
        {
            return Some(classified(EqpDetailClass::Subquery, false, false));
        }
    }
    if reviewed_suffix(detail, "CO-ROUTINE ") || reviewed_suffix(detail, "MATERIALIZE ") {
        return Some(classified(EqpDetailClass::Subquery, false, false));
    }

    let compound = matches!(
        detail,
        "COMPOUND QUERY"
            | "LEFT-MOST SUBQUERY"
            | "UNION ALL"
            | "UNION USING TEMP B-TREE"
            | "INTERSECT USING TEMP B-TREE"
            | "EXCEPT USING TEMP B-TREE"
            | "MERGE (UNION)"
            | "MERGE (UNION ALL)"
            | "MERGE (INTERSECT)"
            | "MERGE (EXCEPT)"
            | "LEFT"
            | "RIGHT"
    );
    if compound {
        return Some(classified(
            EqpDetailClass::Compound,
            false,
            detail.ends_with("USING TEMP B-TREE"),
        ));
    }

    if matches!(
        detail,
        "MULTI-INDEX OR" | "SETUP" | "RECURSIVE STEP" | "CREATE BLOOM FILTER"
    ) || detail
        .strip_prefix("INDEX ")
        .is_some_and(reviewed_decimal_identifier)
        || reviewed_suffix(detail, "BLOOM FILTER ON ")
    {
        return Some(classified(EqpDetailClass::Control, false, false));
    }

    None
}

fn reviewed_suffix(detail: &str, prefix: &str) -> bool {
    detail
        .strip_prefix(prefix)
        .is_some_and(|suffix| !suffix.is_empty() && suffix.trim() == suffix)
}

fn reviewed_decimal_identifier(value: &str) -> bool {
    !value.is_empty() && value.bytes().all(|byte| byte.is_ascii_digit())
}

fn encoded_names_size(columns: &[String]) -> Result<u32, ExecutorError> {
    let bytes = columns.iter().try_fold(0_u64, |total, name| {
        total.checked_add(encoded_string_size(name) + 16)
    });
    u32::try_from(bytes.ok_or_else(internal_error)?).map_err(|_| internal_error())
}

fn decode_row(
    row: &rusqlite::Row<'_>,
    expected_columns: &[ExpectedColumn],
    max_bytes: u32,
) -> Result<Option<(Vec<QueryCell>, u32)>, ExecutorError> {
    let column_count = expected_columns.len();
    let mut cells = Vec::with_capacity(column_count);
    let mut byte_count = 24_u64 + (column_count as u64 * 8);
    if byte_count > u64::from(max_bytes) {
        return Ok(None);
    }
    for (index, expected_column) in expected_columns.iter().enumerate() {
        let value = row.get_ref(index).map_err(|_| result_error())?;
        validate_result_type(value, expected_column)?;
        let value_bytes = match value {
            ValueRef::Null => 1_u64,
            ValueRef::Integer(value) => encoded_integer_size(value),
            ValueRef::Real(_) => 8,
            ValueRef::Text(value) => {
                encoded_string_size(std::str::from_utf8(value).map_err(|_| result_error())?)
            }
            ValueRef::Blob(_) => return Err(result_error()),
        };
        byte_count = byte_count
            .checked_add(value_bytes + 16)
            .ok_or_else(internal_error)?;
        if byte_count > u64::from(max_bytes) {
            return Ok(None);
        }

        let cell = match value {
            ValueRef::Null => (QueryCell::Null, 1_u64),
            ValueRef::Integer(value) => (QueryCell::Integer(value), 8),
            ValueRef::Real(value) if value.is_finite() => (QueryCell::Real(value), 8),
            ValueRef::Real(_) => return Err(result_error()),
            ValueRef::Text(value) => {
                let text = std::str::from_utf8(value).map_err(|_| result_error())?;
                (QueryCell::Text(text.to_owned()), value.len() as u64)
            }
            ValueRef::Blob(_) => return Err(result_error()),
        }
        .0;
        cells.push(cell);
    }
    let byte_count = u32::try_from(byte_count).map_err(|_| result_error())?;
    Ok(Some((cells, byte_count)))
}

fn validate_result_type(
    value: ValueRef<'_>,
    expected: &ExpectedColumn,
) -> Result<(), ExecutorError> {
    let valid = match value {
        ValueRef::Null => expected.nullable,
        ValueRef::Integer(value) => match expected.logical_type {
            ExpectedLogicalType::Integer
            | ExpectedLogicalType::Number
            | ExpectedLogicalType::Scalar => true,
            ExpectedLogicalType::Boolean => matches!(value, 0 | 1),
            ExpectedLogicalType::Real | ExpectedLogicalType::Text => false,
        },
        ValueRef::Real(value) => {
            value.is_finite()
                && matches!(
                    expected.logical_type,
                    ExpectedLogicalType::Real
                        | ExpectedLogicalType::Number
                        | ExpectedLogicalType::Scalar
                )
        }
        ValueRef::Text(_) => matches!(
            expected.logical_type,
            ExpectedLogicalType::Text | ExpectedLogicalType::Scalar
        ),
        ValueRef::Blob(_) => false,
    };
    if valid { Ok(()) } else { Err(result_error()) }
}

fn encoded_string_size(value: &str) -> u64 {
    let utf16_bytes = (value.encode_utf16().count() as u64) * 2;
    let json_bytes = value.chars().fold(0_u64, |total, character| {
        total
            + match character {
                '\u{0000}'..='\u{001f}' => 6,
                '"' | '\\' => 2,
                _ => character.len_utf8() as u64,
            }
    });
    utf16_bytes.max(json_bytes)
}

fn encoded_integer_size(value: i64) -> u64 {
    encoded_string_size(&value.to_string())
}

fn map_sqlite_error(
    error: &SqliteError,
    control: &RunControl,
    started: Instant,
    timeout: Duration,
) -> ExecutorError {
    match error.sqlite_error_code() {
        Some(SqliteErrorCode::OperationInterrupted) => {
            if control.cancelled.load(Ordering::SeqCst) {
                cancelled_error()
            } else if started.elapsed() >= timeout {
                executor_error(
                    ExecutorErrorCode::QueryTimedOut,
                    "The local query exceeded its execution deadline.",
                    true,
                )
            } else {
                executor_error(
                    ExecutorErrorCode::QueryExecutionFailed,
                    "The local query was interrupted.",
                    true,
                )
            }
        }
        Some(SqliteErrorCode::DatabaseBusy | SqliteErrorCode::DatabaseLocked) => executor_error(
            ExecutorErrorCode::QueryBusy,
            "The local SQLite source is busy.",
            true,
        ),
        Some(SqliteErrorCode::AuthorizationForStatementDenied) => executor_error(
            ExecutorErrorCode::QueryDenied,
            "The compiled query requested a forbidden SQLite capability.",
            false,
        ),
        Some(
            SqliteErrorCode::CannotOpen
            | SqliteErrorCode::PermissionDenied
            | SqliteErrorCode::SystemIoFailure
            | SqliteErrorCode::DatabaseCorrupt
            | SqliteErrorCode::NotADatabase
            | SqliteErrorCode::NoLargeFileSupport,
        ) => source_error(),
        Some(SqliteErrorCode::ReadOnly) => executor_error(
            ExecutorErrorCode::QueryDenied,
            "The compiled query is not read-only.",
            false,
        ),
        Some(SqliteErrorCode::TooBig) => executor_error(
            ExecutorErrorCode::QueryCellLimitExceeded,
            "The query returned a value above the per-cell byte limit.",
            false,
        ),
        Some(SqliteErrorCode::OutOfMemory) => resource_exhausted_error(),
        Some(SqliteErrorCode::TypeMismatch) => result_error(),
        Some(SqliteErrorCode::ParameterOutOfRange) => invalid_request(),
        Some(SqliteErrorCode::SchemaChanged) => executor_error(
            ExecutorErrorCode::QueryExecutionFailed,
            "The SQLite schema changed while the query was running.",
            true,
        ),
        _ if matches!(error, SqliteError::MultipleStatement) => executor_error(
            ExecutorErrorCode::QueryDenied,
            "The compiled query must contain exactly one statement.",
            false,
        ),
        _ => executor_error(
            ExecutorErrorCode::QueryExecutionFailed,
            "The local query could not be executed.",
            false,
        ),
    }
}

fn timeout_error() -> ExecutorError {
    executor_error(
        ExecutorErrorCode::QueryTimedOut,
        "The local query exceeded its execution deadline.",
        true,
    )
}

fn plan_budget_error() -> ExecutorError {
    executor_error(
        ExecutorErrorCode::QueryBudgetExceeded,
        "The query plan exceeded its structural budget.",
        false,
    )
}

fn plan_unverified_error() -> ExecutorError {
    executor_error(
        ExecutorErrorCode::QueryPlanUnverified,
        "The query plan could not be verified.",
        false,
    )
}

fn resource_exhausted_error() -> ExecutorError {
    executor_error(
        ExecutorErrorCode::ResourceExhausted,
        "The local query exhausted its resource allowance.",
        true,
    )
}

fn lock<T>(mutex: &Mutex<T>) -> Result<MutexGuard<'_, T>, ExecutorError> {
    mutex.lock().map_err(|_| internal_error())
}

fn executor_error(
    code: ExecutorErrorCode,
    message: &'static str,
    retryable: bool,
) -> ExecutorError {
    ExecutorError {
        code,
        message,
        retryable,
    }
}

fn invalid_request() -> ExecutorError {
    executor_error(
        ExecutorErrorCode::InvalidRequest,
        "The query execution request is invalid.",
        false,
    )
}

fn source_error() -> ExecutorError {
    executor_error(
        ExecutorErrorCode::SourceUnavailable,
        "The local SQLite source is unavailable.",
        true,
    )
}

fn source_changed_error() -> ExecutorError {
    executor_error(
        ExecutorErrorCode::SourceChanged,
        "The local SQLite source changed after it was selected.",
        false,
    )
}

fn source_active_journal_error() -> ExecutorError {
    executor_error(
        ExecutorErrorCode::SourceActiveJournal,
        "The local SQLite source has an active journal.",
        true,
    )
}

fn cancelled_error() -> ExecutorError {
    executor_error(
        ExecutorErrorCode::QueryCancelled,
        "The local query was cancelled.",
        false,
    )
}

fn result_error() -> ExecutorError {
    executor_error(
        ExecutorErrorCode::QueryResultInvalid,
        "The query returned an unsupported or invalid value.",
        false,
    )
}

fn internal_error() -> ExecutorError {
    executor_error(
        ExecutorErrorCode::Internal,
        "The local query executor failed internally.",
        true,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs::{self, OpenOptions};
    use std::io::Write;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::thread;

    const ROW_COUNT_FIXTURE: &str = include_str!("../tests/fixtures/reference-row-count.json");
    const ROW_COUNT_EXPECTED: &str =
        include_str!("../tests/fixtures/reference-row-count.expected.json");

    static NEXT_TEST_ID: AtomicU64 = AtomicU64::new(1);

    struct TestDatabase {
        path: PathBuf,
    }

    impl TestDatabase {
        fn new() -> Self {
            let sequence = NEXT_TEST_ID.fetch_add(1, Ordering::Relaxed);
            let path = test_directory().join(format!(
                "receiptbi-sqlite-core-{}-{sequence}.sqlite",
                std::process::id()
            ));
            let _ = fs::remove_file(&path);
            let connection = Connection::open(&path).expect("create test database");
            connection
                .execute_batch(
                    "CREATE TABLE items(id INTEGER PRIMARY KEY, value TEXT NOT NULL);\
                     INSERT INTO items(value) VALUES ('alpha'), ('beta'), ('gamma');\
                     CREATE TABLE other(id INTEGER PRIMARY KEY);",
                )
                .expect("initialize test database");
            drop(connection);
            Self { path }
        }

        fn row_count_fixture() -> Self {
            let sequence = NEXT_TEST_ID.fetch_add(1, Ordering::Relaxed);
            let path = test_directory().join(format!(
                "receiptbi-sqlite-row-count-{}-{sequence}.sqlite",
                std::process::id()
            ));
            let _ = fs::remove_file(&path);
            let connection = Connection::open(&path).expect("create row-count database");
            connection
                .execute_batch(
                    "CREATE TABLE \"数据 表\"(id INTEGER PRIMARY KEY);\
                     INSERT INTO \"数据 表\"(id) VALUES (1), (2), (3);",
                )
                .expect("initialize row-count database");
            drop(connection);
            Self { path }
        }

        fn identity(&self) -> ExpectedSourceIdentity {
            let metadata = fs::symlink_metadata(&self.path).expect("test metadata");
            source_identity(&self.path, &metadata).expect("test source identity")
        }

        fn sidecar(&self, suffix: &str) -> PathBuf {
            let mut name = self.path.file_name().expect("test filename").to_os_string();
            name.push(suffix);
            self.path.with_file_name(name)
        }
    }

    impl Drop for TestDatabase {
        fn drop(&mut self) {
            for suffix in ["-wal", "-shm", "-journal"] {
                let _ = fs::remove_file(self.sidecar(suffix));
            }
            let _ = fs::remove_file(&self.path);
        }
    }

    fn test_directory() -> PathBuf {
        fs::canonicalize(std::env::temp_dir()).expect("canonical test directory")
    }

    fn next_query_id() -> String {
        format!(
            "test-query-{}",
            NEXT_TEST_ID.fetch_add(1, Ordering::Relaxed)
        )
    }

    fn request(
        database: &TestDatabase,
        sql: &str,
        parameters: Vec<QueryParameter>,
        allowed_relations: &[&str],
        expected_columns: Vec<ExpectedColumn>,
    ) -> QueryRequest {
        QueryRequest {
            query_id: next_query_id(),
            database_path: database.path.clone(),
            expected_source_identity: database.identity(),
            sql: sql.to_owned(),
            parameters,
            allowed_relations: allowed_relations
                .iter()
                .map(|relation| (*relation).to_owned())
                .collect(),
            expected_columns,
            allow_dynamic_result_schema: false,
            plan_budget: QueryPlanBudget {
                max_steps: 64,
                max_full_scans: 8,
                max_temp_btrees: 4,
            },
            limits: QueryLimits {
                max_rows: 100,
                max_bytes: 64 * 1024,
                timeout: Duration::from_secs(5),
            },
        }
    }

    fn expected(name: &str, logical_type: ExpectedLogicalType, nullable: bool) -> ExpectedColumn {
        ExpectedColumn {
            name: name.to_owned(),
            logical_type,
            nullable,
        }
    }

    fn execute(request: QueryRequest) -> Result<QueryResult, ExecutorError> {
        let executor = QueryExecutor::new();
        let mut registered = executor.register(request)?;
        registered.execute()
    }

    fn execution_error(request: QueryRequest) -> ExecutorError {
        match QueryExecutor::new().register(request) {
            Err(error) => error,
            Ok(mut registered) => registered.execute().expect_err("query must fail"),
        }
    }

    fn eqp_details(connection: &Connection, sql: &str) -> Vec<String> {
        let explain = format!("EXPLAIN QUERY PLAN {sql}");
        let mut statement = connection.prepare(&explain).expect("prepare EQP fixture");
        statement
            .query_map([], |row| row.get::<_, String>(3))
            .expect("query EQP fixture")
            .collect::<rusqlite::Result<Vec<_>>>()
            .expect("collect EQP fixture")
    }

    #[test]
    fn executor_error_taxonomy_and_integer_bytes() {
        let control = RunControl::new();
        let oom = SqliteError::SqliteFailure(
            rusqlite::ffi::Error::new(rusqlite::ffi::SQLITE_NOMEM),
            None,
        );
        let mapped = map_sqlite_error(&oom, &control, Instant::now(), Duration::from_secs(1));
        assert_eq!(mapped.code(), ExecutorErrorCode::ResourceExhausted);
        assert_eq!(
            mapped.safe_message(),
            "The local query exhausted its resource allowance."
        );
        assert!(mapped.retryable());

        let too_big = SqliteError::SqliteFailure(
            rusqlite::ffi::Error::new(rusqlite::ffi::SQLITE_TOOBIG),
            None,
        );
        assert_eq!(
            map_sqlite_error(&too_big, &control, Instant::now(), Duration::from_secs(1)).code(),
            ExecutorErrorCode::QueryCellLimitExceeded
        );
        assert_ne!(
            resource_exhausted_error().code(),
            plan_budget_error().code()
        );

        for value in [i64::MIN, -1, 0, 9, 10, i64::MAX] {
            assert_eq!(
                encoded_integer_size(value),
                encoded_string_size(&value.to_string())
            );
        }

        let database = TestDatabase::new();
        let boundary_request = request(
            &database,
            "SELECT ?1 AS value UNION ALL SELECT ?2",
            vec![
                QueryParameter::Integer(i64::MIN),
                QueryParameter::Integer(i64::MAX),
            ],
            &["items"],
            vec![expected("value", ExpectedLogicalType::Integer, false)],
        );
        verify_source_identity(
            &boundary_request.database_path,
            &boundary_request.expected_source_identity,
        )
        .expect("verify boundary source before execution");
        let result = execute(boundary_request).expect("execute boundary integers");
        let expected_bytes = encoded_names_size(&["value".to_owned()]).unwrap()
            + u32::try_from(24 + 8 + encoded_integer_size(i64::MIN) + 16).unwrap()
            + u32::try_from(24 + 8 + encoded_integer_size(i64::MAX) + 16).unwrap();
        assert_eq!(result.byte_count, expected_bytes);
        assert_eq!(
            result.rows,
            vec![
                vec![QueryCell::Integer(i64::MIN)],
                vec![QueryCell::Integer(i64::MAX)]
            ]
        );
    }

    #[test]
    fn accepts_compiler_anonymous_parameters_and_rejects_ambiguous_layouts() {
        let connection = Connection::open_in_memory().expect("open parameter fixture");
        let anonymous = connection
            .prepare("SELECT ? AS first, ? AS second")
            .expect("prepare anonymous parameters");
        validate_parameter_layout(&anonymous, 2)
            .expect("compiler-owned anonymous positions are exact by order");

        let mixed = connection
            .prepare("SELECT ? AS first, ?2 AS second")
            .expect("prepare mixed parameters");
        assert_eq!(
            validate_parameter_layout(&mixed, 2)
                .expect_err("mixed parameter layout must fail")
                .code(),
            ExecutorErrorCode::InvalidRequest
        );
        assert_eq!(
            validate_parameter_layout(&anonymous, 1)
                .expect_err("parameter count mismatch must fail")
                .code(),
            ExecutorErrorCode::InvalidRequest
        );
    }

    #[test]
    fn eqp_classifier_reviewed_families_and_version_gate() {
        assert_eq!(sqlite_version(), PINNED_SQLITE_EQP_VERSION);
        for (detail, class, full_scan, temp_btree) in [
            ("SCAN items", EqpDetailClass::Scan, true, false),
            (
                "SEARCH items USING INTEGER PRIMARY KEY (rowid=?)",
                EqpDetailClass::Search,
                false,
                false,
            ),
            (
                "USE TEMP B-TREE FOR ORDER BY",
                EqpDetailClass::TempBtree,
                false,
                true,
            ),
            ("SCALAR SUBQUERY 1", EqpDetailClass::Subquery, false, false),
            ("COMPOUND QUERY", EqpDetailClass::Compound, false, false),
            ("SCAN CONSTANT ROW", EqpDetailClass::Control, false, false),
            ("SCAN CONSTANT ROWS", EqpDetailClass::Control, false, false),
        ] {
            assert_eq!(
                classify_eqp_detail(detail),
                Some(EqpClassification {
                    class,
                    full_scan,
                    temp_btree,
                })
            );
        }
        for detail in [
            "",
            " SCAN items",
            "SCAN ",
            "FUTURE PLAN NODE items",
            "SCALAR SUBQUERY one",
            "USE TEMP B-TREE FOR FUTURE OPERATION",
        ] {
            assert_eq!(classify_eqp_detail(detail), None, "{detail}");
        }
        assert_eq!(
            plan_unverified_error().code(),
            ExecutorErrorCode::QueryPlanUnverified
        );

        let database = TestDatabase::new();
        let connection = Connection::open_with_flags(
            &database.path,
            OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NOFOLLOW,
        )
        .expect("open EQP fixture");
        let fixtures = [
            ("SELECT id FROM items", vec!["SCAN items"]),
            (
                "SELECT id FROM items WHERE id = 1",
                vec!["SEARCH items USING INTEGER PRIMARY KEY (rowid=?)"],
            ),
            (
                "SELECT value FROM items ORDER BY value",
                vec!["SCAN items", "USE TEMP B-TREE FOR ORDER BY"],
            ),
            (
                "SELECT (SELECT count(*) FROM items) AS n",
                vec!["SCAN CONSTANT ROW", "SCALAR SUBQUERY 1", "SCAN items"],
            ),
            (
                "SELECT 1 UNION ALL SELECT 2",
                vec![
                    "COMPOUND QUERY",
                    "LEFT-MOST SUBQUERY",
                    "SCAN CONSTANT ROW",
                    "UNION ALL",
                    "SCAN CONSTANT ROW",
                ],
            ),
        ];
        for (sql, expected_details) in fixtures {
            let actual = eqp_details(&connection, sql);
            assert_eq!(actual, expected_details, "{sql}");
            assert!(
                actual
                    .iter()
                    .all(|detail| classify_eqp_detail(detail).is_some())
            );
        }

        let mut scan_budget = request(
            &database,
            "SELECT a.id AS value FROM items a CROSS JOIN items b",
            vec![],
            &["items"],
            vec![expected("value", ExpectedLogicalType::Integer, false)],
        );
        scan_budget.plan_budget.max_full_scans = 1;
        assert_eq!(
            execution_error(scan_budget).code(),
            ExecutorErrorCode::QueryBudgetExceeded
        );

        let mut temp_budget = request(
            &database,
            "SELECT value FROM items ORDER BY value",
            vec![],
            &["items"],
            vec![expected("value", ExpectedLogicalType::Text, false)],
        );
        temp_budget.plan_budget.max_temp_btrees = 0;
        assert_eq!(
            execution_error(temp_budget).code(),
            ExecutorErrorCode::QueryBudgetExceeded
        );
    }

    #[test]
    fn crate_row_count_fixture_executes_with_fresh_identity() {
        assert!(ROW_COUNT_FIXTURE.contains("trusted-query-fixture@1"));
        assert!(
            ROW_COUNT_FIXTURE
                .contains(r#""sql": "SELECT COUNT(*) AS \"row_count\" FROM \"数据 表\"""#)
        );
        assert!(ROW_COUNT_EXPECTED.contains(r#""fixtureRowCount": "3""#));

        let database = TestDatabase::row_count_fixture();
        let result = execute(request(
            &database,
            "SELECT COUNT(*) AS \"row_count\" FROM \"数据 表\"",
            vec![],
            &["数据 表"],
            vec![expected("row_count", ExpectedLogicalType::Integer, false)],
        ))
        .expect("execute crate row-count fixture");
        assert_eq!(result.row_count, 1);
        assert_eq!(result.rows, vec![vec![QueryCell::Integer(3)]]);
        assert_eq!(result.truncated_by, None);
    }

    #[test]
    fn focused_attack_and_boundary_corpus() {
        let database = TestDatabase::new();
        let denied_cases = [
            "SELECT id AS value FROM items; SELECT id FROM items",
            "DELETE FROM items RETURNING id AS value",
            "PRAGMA table_info(items)",
            "ATTACH DATABASE ':memory:' AS other",
            "SELECT random() AS value",
            "SELECT id AS value FROM other",
            "SELECT name AS value FROM pragma_table_info('items')",
        ];
        for sql in denied_cases {
            let error = execution_error(request(
                &database,
                sql,
                vec![],
                &["items"],
                vec![expected("value", ExpectedLogicalType::Integer, false)],
            ));
            assert!(
                matches!(
                    error.code(),
                    ExecutorErrorCode::QueryDenied
                        | ExecutorErrorCode::QueryExecutionFailed
                        | ExecutorErrorCode::QueryResultInvalid
                ),
                "{sql}: {error:?}"
            );
        }

        let named_parameter = request(
            &database,
            "SELECT :value AS value",
            vec![QueryParameter::Integer(1)],
            &["items"],
            vec![expected("value", ExpectedLogicalType::Integer, false)],
        );
        assert_eq!(
            execution_error(named_parameter).code(),
            ExecutorErrorCode::InvalidRequest
        );

        for (sql, expected_column) in [
            (
                "SELECT 'text' AS value",
                expected("value", ExpectedLogicalType::Integer, false),
            ),
            (
                "SELECT NULL AS value",
                expected("value", ExpectedLogicalType::Text, false),
            ),
            (
                "SELECT x'00' AS value",
                expected("value", ExpectedLogicalType::Text, false),
            ),
            (
                "SELECT 1e999 AS value",
                expected("value", ExpectedLogicalType::Real, false),
            ),
        ] {
            assert_eq!(
                execution_error(request(
                    &database,
                    sql,
                    vec![],
                    &["items"],
                    vec![expected_column],
                ))
                .code(),
                ExecutorErrorCode::QueryResultInvalid,
                "{sql}"
            );
        }

        let mut row_limited = request(
            &database,
            "SELECT id AS value FROM items ORDER BY id",
            vec![],
            &["items"],
            vec![expected("value", ExpectedLogicalType::Integer, false)],
        );
        row_limited.limits.max_rows = 1;
        let row_result = execute(row_limited).expect("row-limited query");
        assert_eq!(row_result.row_count, 1);
        assert_eq!(row_result.truncated_by, Some(TruncationReason::RowLimit));

        let connection = Connection::open(&database.path).expect("open byte fixture");
        connection
            .execute(
                "UPDATE items SET value = ?1 WHERE id = 1",
                ["x".repeat(600)],
            )
            .expect("update byte fixture");
        drop(connection);
        let mut byte_limited = request(
            &database,
            "SELECT value FROM items WHERE id = 1",
            vec![],
            &["items"],
            vec![expected("value", ExpectedLogicalType::Text, false)],
        );
        byte_limited.limits.max_bytes = MIN_RESULT_BYTES;
        let byte_result = execute(byte_limited).expect("byte-limited query");
        assert_eq!(byte_result.row_count, 0);
        assert_eq!(byte_result.truncated_by, Some(TruncationReason::ByteLimit));
    }

    #[test]
    fn dynamic_result_schema_preserves_scalar_types_and_rejects_duplicate_columns() {
        let database = TestDatabase::new();
        let mut dynamic = request(
            &database,
            "SELECT id, value FROM items ORDER BY id",
            vec![],
            &["items"],
            vec![expected("placeholder", ExpectedLogicalType::Text, true)],
        );
        dynamic.expected_columns.clear();
        dynamic.allow_dynamic_result_schema = true;

        let result = execute(dynamic).expect("dynamic-schema query");
        assert_eq!(result.columns, vec!["id", "value"]);
        assert_eq!(
            result.rows[0],
            vec![QueryCell::Integer(1), QueryCell::Text("alpha".to_owned())]
        );

        let mut duplicate = request(
            &database,
            "SELECT id AS value, value FROM items",
            vec![],
            &["items"],
            vec![expected("placeholder", ExpectedLogicalType::Text, true)],
        );
        duplicate.expected_columns.clear();
        duplicate.allow_dynamic_result_schema = true;
        assert_eq!(
            execution_error(duplicate).code(),
            ExecutorErrorCode::InvalidRequest
        );
    }

    #[test]
    fn source_identity_and_journal_boundaries() {
        let database = TestDatabase::new();
        let baseline = database.identity();
        verify_source_identity(&database.path, &baseline).expect("baseline identity");

        let journal = database.sidecar("-wal");
        fs::write(&journal, b"active").expect("create journal marker");
        assert_eq!(
            verify_source_identity(&database.path, &baseline)
                .expect_err("active journal must fail")
                .code(),
            ExecutorErrorCode::SourceActiveJournal
        );
        fs::remove_file(&journal).expect("remove journal marker");

        let stale_request = request(
            &database,
            "SELECT count(*) AS value FROM items",
            vec![],
            &["items"],
            vec![expected("value", ExpectedLogicalType::Integer, false)],
        );
        OpenOptions::new()
            .append(true)
            .open(&database.path)
            .expect("open changed source")
            .write_all(b"x")
            .expect("change source");
        assert_eq!(
            execution_error(stale_request).code(),
            ExecutorErrorCode::SourceChanged
        );
    }

    #[test]
    fn cancellation_timeout_and_registration_linearization() {
        let database = TestDatabase::new();
        let executor = QueryExecutor::new();
        let first_request = request(
            &database,
            "SELECT id AS value FROM items",
            vec![],
            &["items"],
            vec![expected("value", ExpectedLogicalType::Integer, false)],
        );
        let duplicate_request = first_request.clone();
        let mut registered = executor.register(first_request).expect("register first");
        assert_eq!(
            executor
                .register(duplicate_request)
                .err()
                .expect("duplicate must fail")
                .code(),
            ExecutorErrorCode::DuplicateQuery
        );
        let busy_request = request(
            &database,
            "SELECT id AS value FROM items",
            vec![],
            &["items"],
            vec![expected("value", ExpectedLogicalType::Integer, false)],
        );
        assert_eq!(
            executor
                .register(busy_request)
                .err()
                .expect("busy must fail")
                .code(),
            ExecutorErrorCode::QueryBusy
        );
        assert_eq!(
            executor.cancel(registered.query_id()).unwrap(),
            CancelDisposition::Requested
        );
        assert_eq!(
            registered.execute().expect_err("cancel before open").code(),
            ExecutorErrorCode::QueryCancelled
        );
        drop(registered);

        let mut long_request = request(
            &database,
            "WITH RECURSIVE counter(value) AS (VALUES(1) UNION ALL SELECT value + 1 FROM counter WHERE value < 100000000) SELECT sum(value) AS value FROM counter",
            vec![],
            &["items"],
            vec![expected("value", ExpectedLogicalType::Integer, true)],
        );
        long_request.limits.timeout = Duration::from_secs(60);
        let query_id = long_request.query_id.clone();
        let executor_for_thread = executor.clone();
        let mut running = executor_for_thread
            .register(long_request)
            .expect("register cancellable query");
        let worker = thread::spawn(move || running.execute());
        thread::sleep(Duration::from_millis(10));
        assert!(matches!(
            executor.cancel(&query_id).unwrap(),
            CancelDisposition::Requested | CancelDisposition::AlreadyRequested
        ));
        assert_eq!(
            worker
                .join()
                .expect("join cancellable query")
                .expect_err("cooperative query must cancel")
                .code(),
            ExecutorErrorCode::QueryCancelled
        );

        let mut timed = request(
            &database,
            "WITH RECURSIVE counter(value) AS (VALUES(1) UNION ALL SELECT value + 1 FROM counter WHERE value < 100000000) SELECT sum(value) AS value FROM counter",
            vec![],
            &["items"],
            vec![expected("value", ExpectedLogicalType::Integer, true)],
        );
        timed.limits.timeout = MIN_TIMEOUT;
        assert_eq!(
            execution_error(timed).code(),
            ExecutorErrorCode::QueryTimedOut
        );
    }
}
