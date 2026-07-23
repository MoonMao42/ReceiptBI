"""One-time import of the legacy TypeScript model configuration.

The source database is opened read-only.  Credential plaintext exists only long
enough to authenticate the legacy AES-GCM envelope and re-encrypt it with the
current Fernet key; it is never returned or logged.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import os
import sqlite3
import stat
import tempfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.fernet import InvalidToken
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Encryptor
from app.db.tables import Model
from app.models.config import ModelCreate, ModelExtraOptions

_REQUIRED_MODEL_COLUMNS = {
    "id",
    "name",
    "provider",
    "model_id",
    "base_url",
    "api_key_encrypted",
    "extra_options",
    "is_default",
    "is_active",
    "created_at",
    "updated_at",
}
_EXTRA_OPTION_KEYS = {
    "api_format",
    "headers",
    "query_params",
    "api_key_optional",
    "healthcheck_mode",
}
_SQLITE_HEADER = b"SQLite format 3\0"
_SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")
_PRIVATE_ACCESS_MASK = stat.S_IRWXG | stat.S_IRWXO
_TEMPORARY_NAME_LENGTH = 8
_TEMPORARY_NAME_CHARACTERS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_")
_TEMPORARY_SUFFIX = ".tmp"


class LegacyModelImportError(RuntimeError):
    """A fail-closed legacy import error with no credential material."""


@dataclass(frozen=True, slots=True)
class LegacyModelImportResult:
    status: Literal["imported", "already_present", "empty"]
    model_id: UUID | None = None
    credential_migrated: bool = False


@dataclass(frozen=True, slots=True)
class _LegacyModel:
    id: UUID
    name: str
    provider: str
    model_id: str
    base_url: str | None
    credential: str | None
    extra_options: dict[str, object]
    is_active: bool


@dataclass(frozen=True, slots=True)
class _ValidatedRoot:
    lexical: Path
    resolved: Path


def _absolute_path(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _validated_root(allowed_root: Path) -> _ValidatedRoot:
    root = _absolute_path(allowed_root)
    try:
        root_stat = root.lstat()
        if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
            raise LegacyModelImportError("Legacy model data root is invalid.")
        resolved = root.resolve(strict=True)
    except LegacyModelImportError:
        raise
    except (FileNotFoundError, OSError, RuntimeError):
        raise LegacyModelImportError("Legacy model data root is invalid.") from None
    return _ValidatedRoot(lexical=root, resolved=resolved)


def _relative_to_root(candidate: Path, root: _ValidatedRoot, *, label: str) -> Path:
    try:
        return candidate.relative_to(root.lexical)
    except ValueError:
        raise LegacyModelImportError(
            f"Legacy model {label} is outside the desktop data root."
        ) from None


def _validate_directory_chain(
    directory: Path,
    *,
    root: _ValidatedRoot,
    require_private: bool,
) -> Path:
    relative = _relative_to_root(directory, root, label="snapshot")
    cursor = root.lexical
    try:
        directories: list[Path] = []
        for component in relative.parts:
            cursor /= component
            directories.append(cursor)
        if not directories:
            directories.append(cursor)
        for cursor in directories:
            cursor_stat = cursor.lstat()
            if stat.S_ISLNK(cursor_stat.st_mode) or not stat.S_ISDIR(cursor_stat.st_mode):
                raise LegacyModelImportError("Legacy model snapshot path cannot contain symlinks.")
            if os.name != "nt" and require_private:
                if cursor_stat.st_mode & _PRIVATE_ACCESS_MASK:
                    raise LegacyModelImportError("Legacy model snapshot directory is not private.")
                if hasattr(os, "getuid") and cursor_stat.st_uid != os.getuid():
                    raise LegacyModelImportError(
                        "Legacy model snapshot directory has an unsafe owner."
                    )

        resolved = directory.resolve(strict=True)
        resolved.relative_to(root.resolved)
    except LegacyModelImportError:
        raise
    except (FileNotFoundError, OSError, RuntimeError, ValueError):
        raise LegacyModelImportError(
            "Legacy model snapshot directory could not be validated."
        ) from None
    return resolved


def _snapshot_location(snapshot_path: Path, *, allowed_root: Path) -> tuple[Path, Path]:
    root = _validated_root(allowed_root)
    snapshot = _absolute_path(snapshot_path)
    _relative_to_root(snapshot, root, label="snapshot")
    parent = _validate_directory_chain(
        snapshot.parent,
        root=root,
        require_private=True,
    )
    return snapshot, parent


def _is_private_regular_file_stat(file_stat: os.stat_result) -> bool:
    if stat.S_ISLNK(file_stat.st_mode) or not stat.S_ISREG(file_stat.st_mode):
        return False
    if os.name == "nt":
        return True
    if stat.S_IMODE(file_stat.st_mode) not in {0o400, 0o600}:
        return False
    return not hasattr(os, "getuid") or file_stat.st_uid == os.getuid()


def _assert_private_regular_file(
    path: Path,
    *,
    require_single_link: bool = True,
) -> os.stat_result:
    try:
        file_stat = path.lstat()
    except (FileNotFoundError, OSError):
        raise LegacyModelImportError("Legacy model snapshot is unavailable.") from None
    if not _is_private_regular_file_stat(file_stat):
        if stat.S_ISLNK(file_stat.st_mode) or not stat.S_ISREG(file_stat.st_mode):
            raise LegacyModelImportError("Legacy model snapshot is not a regular file.")
        raise LegacyModelImportError("Legacy model snapshot is not private.")
    if require_single_link and file_stat.st_nlink != 1:
        raise LegacyModelImportError("Legacy model snapshot has unsafe hard links.")
    return file_stat


def _is_snapshot_temporary_name(name: str, snapshot_name: str) -> bool:
    prefix = f".{snapshot_name}."
    if not name.startswith(prefix) or not name.endswith(_TEMPORARY_SUFFIX):
        return False
    random_name = name[len(prefix) : -len(_TEMPORARY_SUFFIX)]
    return len(random_name) == _TEMPORARY_NAME_LENGTH and set(random_name).issubset(
        _TEMPORARY_NAME_CHARACTERS
    )


def _recover_published_snapshot_temp_links(snapshot: Path, *, parent: Path) -> None:
    """Finish a hard-link publication interrupted before temp cleanup."""

    final_stat = _assert_private_regular_file(snapshot, require_single_link=False)
    should_fsync = final_stat.st_nlink > 1
    try:
        with os.scandir(parent) as entries:
            for entry in entries:
                if not _is_snapshot_temporary_name(entry.name, snapshot.name):
                    continue
                candidate = parent / entry.name
                try:
                    candidate_stat = candidate.lstat()
                except FileNotFoundError:
                    continue
                if not _is_private_regular_file_stat(candidate_stat):
                    continue
                if (candidate_stat.st_dev, candidate_stat.st_ino) != (
                    final_stat.st_dev,
                    final_stat.st_ino,
                ):
                    continue
                try:
                    candidate.unlink()
                except FileNotFoundError:
                    continue
                should_fsync = True
        if should_fsync:
            # This also makes a concurrent recovery's unlink durable before we
            # accept the final based on its now-single link count.
            _fsync_directory(parent)
    except OSError:
        raise LegacyModelImportError(
            "Legacy model snapshot publication could not be recovered safely."
        ) from None


def _assert_no_snapshot_sidecars(snapshot_path: Path) -> None:
    for suffix in _SQLITE_SIDECAR_SUFFIXES:
        sidecar = Path(f"{snapshot_path}{suffix}")
        try:
            sidecar.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            raise LegacyModelImportError(
                "Legacy model snapshot sidecars could not be validated."
            ) from None
        raise LegacyModelImportError("Legacy model snapshot is not standalone.")


def _open_immutable_snapshot(snapshot_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"{snapshot_path.as_uri()}?mode=ro&immutable=1",
        uri=True,
    )
    connection.execute("PRAGMA query_only = ON")
    return connection


def _validate_standalone_snapshot(snapshot_path: Path, *, allowed_root: Path) -> Path:
    snapshot, _parent = _snapshot_location(snapshot_path, allowed_root=allowed_root)
    before = _assert_private_regular_file(snapshot)
    _assert_no_snapshot_sidecars(snapshot)

    descriptor: int | None = None
    try:
        descriptor = os.open(
            snapshot,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        opened_stat = os.fstat(descriptor)
        if (opened_stat.st_dev, opened_stat.st_ino) != (before.st_dev, before.st_ino):
            raise LegacyModelImportError("Legacy model snapshot changed during validation.")
        if os.read(descriptor, len(_SQLITE_HEADER)) != _SQLITE_HEADER:
            raise LegacyModelImportError("Legacy model snapshot is not a SQLite database.")
    except LegacyModelImportError:
        raise
    except OSError:
        raise LegacyModelImportError("Legacy model snapshot could not be read safely.") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)

    try:
        with closing(_open_immutable_snapshot(snapshot)) as connection:
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()
            quick_check = connection.execute("PRAGMA quick_check").fetchall()
    except sqlite3.Error:
        raise LegacyModelImportError(
            "Legacy model snapshot is not a valid SQLite database."
        ) from None

    if not journal_mode or str(journal_mode[0]).lower() != "delete":
        raise LegacyModelImportError("Legacy model snapshot is not standalone.")
    if quick_check != [("ok",)]:
        raise LegacyModelImportError("Legacy model snapshot failed its integrity check.")

    after = _assert_private_regular_file(snapshot)
    _assert_no_snapshot_sidecars(snapshot)
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise LegacyModelImportError("Legacy model snapshot changed during validation.")
    return snapshot.resolve(strict=True)


def validate_legacy_model_source(source_path: Path, *, allowed_root: Path) -> Path:
    """Resolve a desktop-provided source without accepting escapes or symlinks."""

    root = _validated_root(allowed_root)
    source = _absolute_path(source_path)
    relative = _relative_to_root(source, root, label="source")

    try:
        cursor = root.lexical
        for component in relative.parts:
            cursor /= component
            cursor_stat = cursor.lstat()
            if stat.S_ISLNK(cursor_stat.st_mode):
                raise LegacyModelImportError("Legacy model source cannot contain symlinks.")
        if not stat.S_ISREG(source.lstat().st_mode):
            raise LegacyModelImportError("Legacy model source is not a regular file.")
        resolved_source = source.resolve(strict=True)
        resolved_source.relative_to(root.resolved)
    except LegacyModelImportError:
        raise
    except (FileNotFoundError, OSError, RuntimeError, ValueError):
        raise LegacyModelImportError("Legacy model source could not be validated.") from None
    return resolved_source


def _validate_source_sidecars(source_path: Path, *, allowed_root: Path) -> None:
    root = _validated_root(allowed_root)
    for suffix in _SQLITE_SIDECAR_SUFFIXES:
        sidecar = Path(f"{source_path}{suffix}")
        try:
            sidecar.relative_to(root.resolved)
        except ValueError:
            raise LegacyModelImportError(
                "Legacy model source sidecar is outside the desktop data root."
            ) from None
        try:
            sidecar_stat = sidecar.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            raise LegacyModelImportError(
                "Legacy model source sidecars could not be validated."
            ) from None
        if stat.S_ISLNK(sidecar_stat.st_mode) or not stat.S_ISREG(sidecar_stat.st_mode):
            raise LegacyModelImportError("Legacy model source sidecar is unsafe.")


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _cleanup_temporary_snapshot(temporary: Path) -> None:
    for candidate in (
        temporary,
        *(Path(f"{temporary}{suffix}") for suffix in _SQLITE_SIDECAR_SUFFIXES),
    ):
        try:
            candidate.unlink()
        except FileNotFoundError:
            continue
        except OSError:
            # Preparation has already failed closed; a private unpublished temp
            # is safer to retain than masking the original validation failure.
            continue


def _create_online_snapshot(source_path: Path, temporary: Path) -> None:
    try:
        with closing(_open_source_read_only(source_path)) as source:
            with closing(sqlite3.connect(f"{temporary.as_uri()}?mode=rw", uri=True)) as destination:
                source.backup(destination, pages=256, sleep=0.05)
                journal_mode = destination.execute("PRAGMA journal_mode = DELETE").fetchone()
                if not journal_mode or str(journal_mode[0]).lower() != "delete":
                    raise LegacyModelImportError(
                        "Legacy model snapshot could not be made standalone."
                    )
                destination.commit()
                if destination.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise LegacyModelImportError(
                        "Legacy model snapshot failed its integrity check."
                    )
    except LegacyModelImportError:
        raise
    except (OSError, sqlite3.Error):
        raise LegacyModelImportError("Legacy model snapshot could not be created safely.") from None


def prepare_legacy_model_snapshot(
    *,
    source_path: Path | None,
    snapshot_path: Path,
    allowed_root: Path,
) -> Path:
    """Prepare or reuse the immutable standalone database used by the importer.

    A live source is consumed only through SQLite's online backup API, so
    committed WAL frames are included without copying or checkpointing the
    active database. Publication is a same-directory, hard-link no-overwrite
    operation: an already published final is always validated and authoritative.
    """

    snapshot, parent = _snapshot_location(snapshot_path, allowed_root=allowed_root)
    try:
        snapshot.lstat()
    except FileNotFoundError:
        pass
    except OSError:
        raise LegacyModelImportError("Legacy model snapshot could not be validated.") from None
    else:
        _recover_published_snapshot_temp_links(snapshot, parent=parent)
        return _validate_standalone_snapshot(snapshot, allowed_root=allowed_root)

    if source_path is None:
        raise LegacyModelImportError("Legacy model source is required for a new snapshot.")

    source = validate_legacy_model_source(source_path, allowed_root=allowed_root)
    _validate_source_sidecars(source, allowed_root=allowed_root)
    try:
        source_before = source.stat()
    except OSError:
        raise LegacyModelImportError("Legacy model source could not be validated.") from None

    descriptor: int | None = None
    temporary: Path | None = None
    published = False
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{snapshot.name}.",
            suffix=_TEMPORARY_SUFFIX,
            dir=parent,
        )
        temporary = Path(temporary_name)
        if os.name != "nt":
            os.fchmod(descriptor, 0o600)
        os.close(descriptor)
        descriptor = None

        _create_online_snapshot(source, temporary)
        _validate_source_sidecars(source, allowed_root=allowed_root)
        source_after = source.stat()
        if (source_before.st_dev, source_before.st_ino) != (
            source_after.st_dev,
            source_after.st_ino,
        ):
            raise LegacyModelImportError("Legacy model source changed during snapshotting.")

        with temporary.open("rb") as temporary_file:
            os.fsync(temporary_file.fileno())
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        _assert_no_snapshot_sidecars(temporary)

        try:
            os.link(temporary, snapshot, follow_symlinks=False)
        except FileExistsError:
            _recover_published_snapshot_temp_links(snapshot, parent=parent)
            return _validate_standalone_snapshot(snapshot, allowed_root=allowed_root)
        published = True
        _fsync_directory(parent)
    except LegacyModelImportError:
        raise
    except (FileNotFoundError, OSError):
        raise LegacyModelImportError(
            "Legacy model snapshot could not be published safely."
        ) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            _cleanup_temporary_snapshot(temporary)
            if published:
                try:
                    _fsync_directory(parent)
                except OSError:
                    # The final hard link is already durable from the first
                    # directory fsync. Failure to persist temp cleanup is safe.
                    pass

    return _validate_standalone_snapshot(snapshot, allowed_root=allowed_root)


def _open_source_read_only(source_path: Path) -> sqlite3.Connection:
    resolved = source_path.expanduser().resolve(strict=True)
    connection = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _validated_source_row(source_path: Path) -> _LegacyModel | None:
    try:
        with closing(_open_source_read_only(source_path)) as source:
            table = source.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'models'"
            ).fetchone()
            if table is None:
                raise LegacyModelImportError("Legacy model schema is missing.")

            columns = {
                str(row["name"])
                for row in source.execute("SELECT name FROM pragma_table_info('models')")
            }
            if not _REQUIRED_MODEL_COLUMNS.issubset(columns):
                raise LegacyModelImportError("Legacy model schema is incompatible.")

            rows = source.execute(
                """
                SELECT id, name, provider, model_id, base_url, api_key_encrypted,
                       extra_options, is_default, is_active, created_at, updated_at
                FROM models
                ORDER BY created_at, id
                LIMIT 2
                """
            ).fetchall()
    except LegacyModelImportError:
        raise
    except (OSError, sqlite3.Error):
        raise LegacyModelImportError("Legacy model database could not be read safely.") from None

    if not rows:
        return None
    if len(rows) != 1:
        raise LegacyModelImportError("Legacy model database contains multiple records.")

    row = rows[0]
    try:
        source_id = UUID(str(row["id"]))
        raw_extra = json.loads(row["extra_options"] or "{}")
        if not isinstance(raw_extra, dict) or not set(raw_extra).issubset(_EXTRA_OPTION_KEYS):
            raise ValueError
        extra = ModelExtraOptions.model_validate(raw_extra).model_dump()
        validated = ModelCreate.model_validate(
            {
                "name": row["name"],
                "provider": row["provider"],
                "model_id": row["model_id"],
                "base_url": row["base_url"],
                "extra_options": extra,
                "is_default": False,
            }
        )
        if len(validated.model_id) > 100 or (
            validated.base_url is not None and len(validated.base_url) > 500
        ):
            raise ValueError
        credential = row["api_key_encrypted"]
        if credential is not None and not isinstance(credential, str):
            raise ValueError
        default_value = int(row["is_default"])
        active_value = int(row["is_active"])
        if default_value not in (0, 1) or active_value not in (0, 1):
            raise ValueError
        is_active = bool(active_value)
    except (TypeError, ValueError, json.JSONDecodeError, ValidationError):
        raise LegacyModelImportError("Legacy model record is invalid.") from None

    return _LegacyModel(
        id=source_id,
        name=validated.name,
        provider=validated.provider,
        model_id=validated.model_id,
        base_url=validated.base_url,
        credential=credential,
        extra_options=validated.extra_options.model_dump(),
        is_active=is_active,
    )


def _decode_legacy_aes_key(value: str) -> bytes:
    try:
        padded = value.strip() + "=" * (-len(value.strip()) % 4)
        decoded = base64.b64decode(padded.replace("-", "+").replace("_", "/"), validate=True)
    except (ValueError, binascii.Error):
        raise LegacyModelImportError("Legacy credential key is invalid.") from None
    if len(decoded) != 32:
        raise LegacyModelImportError("Legacy credential key is invalid.")
    return decoded


def _decrypt_legacy_v1(envelope: str, key_value: str) -> bytearray:
    if not envelope.startswith("v1."):
        raise LegacyModelImportError("Legacy credential format is unsupported.")
    try:
        payload = base64.b64decode(envelope[3:], validate=True)
    except (ValueError, binascii.Error):
        raise LegacyModelImportError("Legacy credential format is invalid.") from None
    if len(payload) <= 28:
        raise LegacyModelImportError("Legacy credential format is invalid.")

    key = bytearray(_decode_legacy_aes_key(key_value))
    try:
        # Legacy TS layout: 12-byte IV, ciphertext, 16-byte GCM authentication tag.
        plaintext = AESGCM(bytes(key)).decrypt(payload[:12], payload[12:], None)
    except (InvalidTag, ValueError):
        raise LegacyModelImportError("Legacy credential could not be authenticated.") from None
    finally:
        key[:] = b"\0" * len(key)

    if not plaintext or len(plaintext) > 4096:
        raise LegacyModelImportError("Legacy credential plaintext is invalid.")
    return bytearray(plaintext)


def _matches_legacy_record(existing: Model, legacy: _LegacyModel) -> bool:
    return (
        existing.name == legacy.name
        and existing.provider == legacy.provider
        and existing.model_id == legacy.model_id
        and existing.base_url == legacy.base_url
        and (existing.extra_options or {}) == legacy.extra_options
        and bool(existing.is_default) is False
        and bool(existing.is_active) is legacy.is_active
    )


def _credentials_match(
    existing: Model,
    legacy_plaintext: bytearray | None,
    current_encryptor: Encryptor,
) -> bool:
    """Compare credential plaintext without returning or logging it."""

    current_envelope = existing.api_key_encrypted
    if legacy_plaintext is None:
        return current_envelope is None
    if not current_envelope:
        return False

    try:
        current_plaintext = bytearray(current_encryptor.decrypt(current_envelope), "utf-8")
    except (InvalidToken, UnicodeDecodeError, TypeError, ValueError):
        return False
    try:
        return hmac.compare_digest(current_plaintext, legacy_plaintext)
    finally:
        current_plaintext[:] = b"\0" * len(current_plaintext)


async def import_legacy_ts_model(
    db: AsyncSession,
    *,
    source_path: Path,
    legacy_encryption_key: str | None,
    current_encryptor: Encryptor,
) -> LegacyModelImportResult:
    """Import the single legacy model without changing existing target models.

    Existing defaults remain untouched.  The legacy UUID is preserved, while its
    credential is authenticated and re-encrypted before the target transaction.
    """

    legacy = _validated_source_row(source_path)
    if legacy is None:
        return LegacyModelImportResult(status="empty")

    legacy_plaintext: bytearray | None = None
    if legacy.credential is not None:
        if legacy_encryption_key is None:
            raise LegacyModelImportError("Legacy credential key is required.")
        legacy_plaintext = _decrypt_legacy_v1(legacy.credential, legacy_encryption_key)

    try:
        existing_models = list((await db.execute(select(Model))).scalars())
        for existing in existing_models:
            if UUID(str(existing.id)) != legacy.id:
                continue

            fields_match = _matches_legacy_record(existing, legacy)
            credential_matches = _credentials_match(
                existing,
                legacy_plaintext,
                current_encryptor,
            )
            if not fields_match or not credential_matches:
                raise LegacyModelImportError("Target model conflicts with legacy data.")
            return LegacyModelImportResult(
                status="already_present",
                model_id=UUID(str(existing.id)),
                credential_migrated=False,
            )

        encrypted_credential: str | None = None
        if legacy_plaintext is not None:
            try:
                encrypted_credential = current_encryptor.encrypt(legacy_plaintext.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                raise LegacyModelImportError("Legacy credential plaintext is invalid.") from None

        imported = Model(
            id=legacy.id,
            name=legacy.name,
            provider=legacy.provider,
            model_id=legacy.model_id,
            base_url=legacy.base_url,
            api_key_encrypted=encrypted_credential,
            extra_options=legacy.extra_options,
            # Never displace a current selection during a historical one-time import.
            is_default=False,
            is_active=legacy.is_active,
        )
        db.add(imported)
        try:
            await db.flush()
        except SQLAlchemyError:
            await db.rollback()
            raise LegacyModelImportError("Target model transaction failed.") from None

        return LegacyModelImportResult(
            status="imported",
            model_id=legacy.id,
            credential_migrated=encrypted_credential is not None,
        )
    finally:
        if legacy_plaintext is not None:
            legacy_plaintext[:] = b"\0" * len(legacy_plaintext)


__all__ = [
    "LegacyModelImportError",
    "LegacyModelImportResult",
    "import_legacy_ts_model",
    "prepare_legacy_model_snapshot",
    "validate_legacy_model_source",
]
