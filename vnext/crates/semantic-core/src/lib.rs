//! Deterministic primitives for the local semantic compiler.
//!
//! This crate is deliberately independent from Node.js and any network or UI
//! runtime. The first slice establishes a stable core identity and the path
//! boundary used by local analysis sandboxes.

use std::error::Error;
use std::fmt::{self, Display, Formatter};
use std::path::{Component, Path, PathBuf};

/// Stable machine-readable name for the semantic engine.
pub const SEMANTIC_CORE_NAME: &str = "querygpt-semantic-core";

/// Returns the semantic core crate version compiled into the native module.
#[must_use]
pub const fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// Returns a small deterministic identity string for integration probes.
#[must_use]
pub fn hello() -> String {
    format!("{SEMANTIC_CORE_NAME}@{}", version())
}

/// Classifies why a caller-provided sandbox path component was rejected.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UnsafePathReason {
    Empty,
    NullByte,
    AbsoluteOrRooted,
    PrefixOrAlternateStream,
    Parent,
    CurrentDirectory,
    ContainsSeparator,
    WindowsReservedName,
    WindowsTrailingDotOrSpace,
}

impl Display for UnsafePathReason {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> fmt::Result {
        let message = match self {
            Self::Empty => "empty components are not allowed",
            Self::NullByte => "NUL bytes are not allowed",
            Self::AbsoluteOrRooted => "absolute or rooted components are not allowed",
            Self::PrefixOrAlternateStream => {
                "Windows prefixes and alternate data streams are not allowed"
            }
            Self::Parent => "parent-directory components are not allowed",
            Self::CurrentDirectory => "current-directory components are not allowed",
            Self::ContainsSeparator => "each input must be exactly one path component",
            Self::WindowsReservedName => "Windows reserved device names are not allowed",
            Self::WindowsTrailingDotOrSpace => {
                "components ending in a dot or space are not portable to Windows"
            }
        };

        formatter.write_str(message)
    }
}

/// Error returned when an untrusted sandbox-relative component is unsafe.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SandboxPathError {
    InvalidRoot,
    UnsafeComponent {
        index: usize,
        value: String,
        reason: UnsafePathReason,
    },
}

impl Display for SandboxPathError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidRoot => formatter.write_str(
                "sandbox root must be an absolute, normalized host path without '.' or '..' components",
            ),
            Self::UnsafeComponent {
                index,
                value,
                reason,
            } => write!(
                formatter,
                "unsafe sandbox path component at index {index} ({value:?}): {reason}"
            ),
        }
    }
}

impl Error for SandboxPathError {}

/// Joins untrusted relative components beneath a trusted absolute sandbox root.
///
/// Every item in `components` must be one portable filename component. Nested
/// strings such as `"runs/123"` are rejected; callers pass `"runs"` and
/// `"123"` separately. This removes host-specific separator ambiguity and
/// makes lexical containment possible without touching the filesystem.
///
/// This is a lexical construction boundary, not filesystem authorization.
/// Sandbox owners must also prevent or verify symlink traversal when opening
/// files beneath the returned path.
pub fn join_sandbox_path(root: &Path, components: &[String]) -> Result<PathBuf, SandboxPathError> {
    validate_root(root)?;

    let mut result = PathBuf::from(root);
    for (index, component) in components.iter().enumerate() {
        validate_untrusted_component(index, component)?;
        result.push(component);
    }

    Ok(result)
}

fn validate_root(root: &Path) -> Result<(), SandboxPathError> {
    if !root.is_absolute()
        || root
            .components()
            .any(|component| matches!(component, Component::CurDir | Component::ParentDir))
    {
        return Err(SandboxPathError::InvalidRoot);
    }

    Ok(())
}

fn validate_untrusted_component(index: usize, value: &str) -> Result<(), SandboxPathError> {
    let rejected = |reason| SandboxPathError::UnsafeComponent {
        index,
        value: value.to_owned(),
        reason,
    };

    if value.is_empty() {
        return Err(rejected(UnsafePathReason::Empty));
    }
    if value.contains('\0') {
        return Err(rejected(UnsafePathReason::NullByte));
    }

    // `Path::components` is authoritative for the host OS. The additional
    // lexical checks below deliberately recognize both separator styles so a
    // Windows attack string is still rejected by tests and builds on macOS.
    for component in Path::new(value).components() {
        match component {
            Component::Prefix(_) => {
                return Err(rejected(UnsafePathReason::PrefixOrAlternateStream));
            }
            Component::RootDir => {
                return Err(rejected(UnsafePathReason::AbsoluteOrRooted));
            }
            Component::ParentDir => return Err(rejected(UnsafePathReason::Parent)),
            Component::CurDir => return Err(rejected(UnsafePathReason::CurrentDirectory)),
            Component::Normal(_) => {}
        }
    }

    if value.starts_with('/') || value.starts_with('\\') {
        return Err(rejected(UnsafePathReason::AbsoluteOrRooted));
    }
    if value.contains(':') {
        return Err(rejected(UnsafePathReason::PrefixOrAlternateStream));
    }

    for lexical_component in value.split(['/', '\\']) {
        match lexical_component {
            ".." => return Err(rejected(UnsafePathReason::Parent)),
            "." => return Err(rejected(UnsafePathReason::CurrentDirectory)),
            _ => {}
        }
    }

    if value.contains(['/', '\\']) {
        return Err(rejected(UnsafePathReason::ContainsSeparator));
    }
    if value.ends_with(['.', ' ']) {
        return Err(rejected(UnsafePathReason::WindowsTrailingDotOrSpace));
    }
    if is_windows_reserved_name(value) {
        return Err(rejected(UnsafePathReason::WindowsReservedName));
    }

    Ok(())
}

fn is_windows_reserved_name(value: &str) -> bool {
    let base_name = value.split('.').next().unwrap_or(value);
    let uppercase = base_name.to_ascii_uppercase();

    matches!(uppercase.as_str(), "CON" | "PRN" | "AUX" | "NUL")
        || is_numbered_windows_device(&uppercase, "COM")
        || is_numbered_windows_device(&uppercase, "LPT")
}

fn is_numbered_windows_device(value: &str, prefix: &str) -> bool {
    value
        .strip_prefix(prefix)
        .is_some_and(|suffix| matches!(suffix, "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9"))
}

#[cfg(test)]
mod tests {
    use super::{SandboxPathError, UnsafePathReason, hello, join_sandbox_path, version};
    use std::path::{Path, PathBuf};

    fn absolute_test_root() -> PathBuf {
        std::env::temp_dir().join("querygpt-semantic-core-tests")
    }

    fn assert_rejected(input: &str, expected_reason: UnsafePathReason) {
        let error = join_sandbox_path(&absolute_test_root(), &[input.to_owned()])
            .expect_err("malicious path component must be rejected");

        assert!(matches!(
            error,
            SandboxPathError::UnsafeComponent {
                index: 0,
                reason,
                ..
            } if reason == expected_reason
        ));
    }

    #[test]
    fn exposes_a_deterministic_identity() {
        assert_eq!(hello(), format!("querygpt-semantic-core@{}", version()));
        assert_eq!(version(), env!("CARGO_PKG_VERSION"));
    }

    #[test]
    fn joins_only_individual_components_with_pathbuf() {
        let root = absolute_test_root();
        let path = join_sandbox_path(
            &root,
            &[
                "runs".to_owned(),
                "run-01".to_owned(),
                "result.json".to_owned(),
            ],
        )
        .expect("portable components should be accepted");

        assert_eq!(path, root.join("runs").join("run-01").join("result.json"));
    }

    #[test]
    fn rejects_posix_looking_escape_components() {
        assert_rejected("/etc", UnsafePathReason::AbsoluteOrRooted);
        assert_rejected("..", UnsafePathReason::Parent);
        assert_rejected("../secret", UnsafePathReason::Parent);
        assert_rejected("safe/../../secret", UnsafePathReason::Parent);
        assert_rejected("safe/nested", UnsafePathReason::ContainsSeparator);
    }

    #[test]
    fn rejects_windows_looking_escape_components_on_every_host() {
        assert_rejected("C:\\Windows", UnsafePathReason::PrefixOrAlternateStream);
        assert_rejected("C:relative", UnsafePathReason::PrefixOrAlternateStream);
        assert_rejected("\\\\server\\share", UnsafePathReason::AbsoluteOrRooted);
        assert_rejected("..\\secret", UnsafePathReason::Parent);
        assert_rejected("safe\\..\\secret", UnsafePathReason::Parent);
        assert_rejected("file.txt:secret", UnsafePathReason::PrefixOrAlternateStream);
    }

    #[test]
    fn rejects_windows_name_aliases_and_normalization_collisions() {
        assert_rejected("CON", UnsafePathReason::WindowsReservedName);
        assert_rejected("com1.log", UnsafePathReason::WindowsReservedName);
        assert_rejected("report.", UnsafePathReason::WindowsTrailingDotOrSpace);
        assert_rejected("report ", UnsafePathReason::WindowsTrailingDotOrSpace);
    }

    #[test]
    fn rejects_non_absolute_or_non_normalized_roots() {
        assert_eq!(
            join_sandbox_path(Path::new("relative-root"), &["safe".to_owned()]),
            Err(SandboxPathError::InvalidRoot)
        );

        let root_with_parent = absolute_test_root().join("child").join("..");
        assert_eq!(
            join_sandbox_path(&root_with_parent, &["safe".to_owned()]),
            Err(SandboxPathError::InvalidRoot)
        );
    }
}
