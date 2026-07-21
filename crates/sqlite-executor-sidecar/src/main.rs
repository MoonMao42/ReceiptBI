//! One-shot JSON boundary between the FastAPI process and the trusted SQLite core.
//!
//! The process accepts exactly one request on stdin and emits exactly one
//! structured response on stdout. Process termination is the outer cancellation
//! boundary; the core additionally owns its SQLite progress timeout.

use std::io::{self, Read};
use std::path::PathBuf;
use std::process::ExitCode;
use std::time::Duration;

use receiptbi_sqlite_executor_core::{
    ExecutorError, ExecutorErrorCode, ExpectedSourceIdentity, QueryCell, QueryExecutor,
    QueryLimits, QueryPlanBudget, QueryRequest, TruncationReason, capture_source_identity,
};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

const REQUEST_CONTRACT: &str = "receiptbi-sqlite-execute@1";
const RESULT_CONTRACT: &str = "receiptbi-sqlite-result@1";

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct ExecuteRequest {
    contract: String,
    query_id: String,
    database_path: PathBuf,
    sql: String,
    allowed_relations: Vec<String>,
    max_rows: u32,
    max_bytes: u32,
    timeout_ms: u32,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct SourceIdentityOutput {
    dev: u64,
    ino: u64,
    ctime_ns: u64,
    mtime_ns: u64,
    size: u64,
}

impl From<ExpectedSourceIdentity> for SourceIdentityOutput {
    fn from(identity: ExpectedSourceIdentity) -> Self {
        Self {
            dev: identity.dev,
            ino: identity.ino,
            ctime_ns: identity.ctime_ns,
            mtime_ns: identity.mtime_ns,
            size: identity.size,
        }
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ErrorOutput {
    code: &'static str,
    message: &'static str,
    retryable: bool,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ExecuteResponse {
    contract: &'static str,
    query_id: String,
    ok: bool,
    source_identity: Option<SourceIdentityOutput>,
    columns: Vec<String>,
    rows: Vec<Map<String, Value>>,
    row_count: u32,
    byte_count: u32,
    truncated_by: Option<&'static str>,
    duration_ms: u64,
    error: Option<ErrorOutput>,
}

impl ExecuteResponse {
    fn invalid_request(query_id: String) -> Self {
        Self::failure(
            query_id,
            None,
            ErrorOutput {
                code: "invalid_request",
                message: "The trusted SQLite request was invalid.",
                retryable: false,
            },
        )
    }

    fn failure(
        query_id: String,
        source_identity: Option<SourceIdentityOutput>,
        error: ErrorOutput,
    ) -> Self {
        Self {
            contract: RESULT_CONTRACT,
            query_id,
            ok: false,
            source_identity,
            columns: Vec::new(),
            rows: Vec::new(),
            row_count: 0,
            byte_count: 0,
            truncated_by: None,
            duration_ms: 0,
            error: Some(error),
        }
    }
}

fn main() -> ExitCode {
    let response = execute_from_stdin();
    let ok = response.ok;
    match serde_json::to_string(&response) {
        Ok(encoded) => println!("{encoded}"),
        Err(_) => return ExitCode::from(2),
    }
    if ok {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    }
}

fn execute_from_stdin() -> ExecuteResponse {
    let mut encoded = String::new();
    if io::stdin().read_to_string(&mut encoded).is_err() {
        return ExecuteResponse::invalid_request(String::new());
    }
    let request = match serde_json::from_str::<ExecuteRequest>(&encoded) {
        Ok(request) => request,
        Err(_) => return ExecuteResponse::invalid_request(String::new()),
    };
    let query_id = request.query_id.clone();
    if request.contract != REQUEST_CONTRACT {
        return ExecuteResponse::invalid_request(query_id);
    }

    let source_identity = match capture_source_identity(&request.database_path) {
        Ok(identity) => identity,
        Err(error) => {
            return ExecuteResponse::failure(query_id, None, error_output(error));
        }
    };
    let public_identity = SourceIdentityOutput::from(source_identity.clone());
    let query = QueryRequest {
        query_id: request.query_id.clone(),
        database_path: request.database_path,
        expected_source_identity: source_identity,
        sql: request.sql,
        parameters: Vec::new(),
        allowed_relations: request.allowed_relations,
        expected_columns: Vec::new(),
        allow_dynamic_result_schema: true,
        plan_budget: QueryPlanBudget {
            max_steps: 64,
            max_full_scans: 8,
            max_temp_btrees: 4,
        },
        limits: QueryLimits {
            max_rows: request.max_rows,
            max_bytes: request.max_bytes,
            timeout: Duration::from_millis(u64::from(request.timeout_ms)),
        },
    };

    let executor = QueryExecutor::new();
    let mut registered = match executor.register(query) {
        Ok(registered) => registered,
        Err(error) => {
            return ExecuteResponse::failure(query_id, Some(public_identity), error_output(error));
        }
    };
    let result = match registered.execute() {
        Ok(result) => result,
        Err(error) => {
            return ExecuteResponse::failure(query_id, Some(public_identity), error_output(error));
        }
    };

    let rows = result
        .rows
        .into_iter()
        .map(|row| {
            result
                .columns
                .iter()
                .cloned()
                .zip(row.into_iter().map(cell_value))
                .collect::<Map<_, _>>()
        })
        .collect();
    ExecuteResponse {
        contract: RESULT_CONTRACT,
        query_id: request.query_id,
        ok: true,
        source_identity: Some(public_identity),
        columns: result.columns,
        rows,
        row_count: result.row_count,
        byte_count: result.byte_count,
        truncated_by: result.truncated_by.map(|reason| match reason {
            TruncationReason::RowLimit => "row_limit",
            TruncationReason::ByteLimit => "byte_limit",
        }),
        duration_ms: u64::try_from(result.duration.as_millis()).unwrap_or(u64::MAX),
        error: None,
    }
}

fn cell_value(cell: QueryCell) -> Value {
    match cell {
        QueryCell::Null => Value::Null,
        QueryCell::Integer(value) => Value::from(value),
        QueryCell::Real(value) => serde_json::Number::from_f64(value)
            .map(Value::Number)
            .unwrap_or(Value::Null),
        QueryCell::Text(value) => Value::String(value),
    }
}

fn error_output(error: ExecutorError) -> ErrorOutput {
    ErrorOutput {
        code: match error.code() {
            ExecutorErrorCode::InvalidRequest => "invalid_request",
            ExecutorErrorCode::DuplicateQuery => "duplicate_query",
            ExecutorErrorCode::SourceUnavailable => "source_unavailable",
            ExecutorErrorCode::SourceChanged => "source_changed",
            ExecutorErrorCode::SourceActiveJournal => "source_active_journal",
            ExecutorErrorCode::QueryDenied => "query_denied",
            ExecutorErrorCode::QueryBudgetExceeded => "query_budget_exceeded",
            ExecutorErrorCode::QueryPlanUnverified => "query_plan_unverified",
            ExecutorErrorCode::ResourceExhausted => "resource_exhausted",
            ExecutorErrorCode::QueryCellLimitExceeded => "query_cell_limit_exceeded",
            ExecutorErrorCode::QueryBusy => "query_busy",
            ExecutorErrorCode::QueryCancelled => "query_cancelled",
            ExecutorErrorCode::QueryTimedOut => "query_timed_out",
            ExecutorErrorCode::QueryResultInvalid => "query_result_invalid",
            ExecutorErrorCode::QueryExecutionFailed => "query_execution_failed",
            ExecutorErrorCode::Internal => "internal",
        },
        message: error.safe_message(),
        retryable: error.retryable(),
    }
}
