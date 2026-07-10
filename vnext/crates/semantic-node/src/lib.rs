//! Node-API boundary for the deterministic semantic core.

use std::path::PathBuf;

use napi::{Error, Result, Status};
use napi_derive::napi;

#[napi(object)]
pub struct SemanticDoctor {
    pub contract: String,
    #[napi(js_name = "compilerVersion")]
    pub compiler_version: String,
    pub target: String,
}

#[napi(js_name = "hello")]
pub fn hello() -> SemanticDoctor {
    SemanticDoctor {
        contract: "semantic-napi@1".to_owned(),
        compiler_version: querygpt_semantic_core::version().to_owned(),
        target: env!("QUERYGPT_RUST_TARGET").to_owned(),
    }
}

#[napi(js_name = "version")]
pub fn version() -> String {
    querygpt_semantic_core::version().to_owned()
}

/// Builds a sandbox path from one safe component per array item.
///
/// The root must be an absolute host-native path. Unsafe input is surfaced as
/// a JavaScript `TypeError`-class invalid-argument error rather than repaired or
/// normalized silently.
#[napi(js_name = "joinSandboxPath")]
pub fn join_sandbox_path(root: String, components: Vec<String>) -> Result<String> {
    let root = PathBuf::from(root);
    let path = querygpt_semantic_core::join_sandbox_path(&root, &components)
        .map_err(|error| Error::new(Status::InvalidArg, error.to_string()))?;

    path.into_os_string().into_string().map_err(|_| {
        Error::new(
            Status::GenericFailure,
            "sandbox path could not be represented as UTF-8".to_owned(),
        )
    })
}
