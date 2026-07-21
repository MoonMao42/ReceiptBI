"""Tests for the isolated legacy TypeScript model importer."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Encryptor
from app.db.tables import Model
from app.services.legacy_ts_model_import import (
    LegacyModelImportError,
    import_legacy_ts_model,
    prepare_legacy_model_snapshot,
    validate_legacy_model_source,
)


def _legacy_envelope(secret: str, key: bytes) -> str:
    iv = bytes(range(12))
    encrypted = AESGCM(key).encrypt(iv, secret.encode(), None)
    return f"v1.{base64.b64encode(iv + encrypted).decode()}"


def _create_legacy_db(
    path: Path,
    *,
    secret: str = "legacy-test-secret",
    key: bytes = b"l" * 32,
    rows: int = 1,
    model_id: UUID | None = None,
) -> UUID:
    source_model_id = model_id or uuid4()
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE models (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                provider TEXT NOT NULL,
                model_id TEXT NOT NULL,
                base_url TEXT,
                api_key_encrypted TEXT,
                extra_options TEXT NOT NULL,
                is_default INTEGER NOT NULL,
                is_active INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        for index in range(rows):
            row_id = source_model_id if index == 0 else uuid4()
            connection.execute(
                """
                INSERT INTO models VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(row_id),
                    f"Legacy gateway {index}",
                    "custom",
                    f"gpt-legacy-{index}",
                    "https://gateway.example.test/v1",
                    _legacy_envelope(secret, key),
                    json.dumps(
                        {
                            "api_format": "openai_compatible",
                            "headers": {},
                            "query_params": {},
                            "api_key_optional": False,
                            "healthcheck_mode": "chat_completion",
                        }
                    ),
                    1,
                    1,
                    "2026-04-19T05:38:51.000Z",
                    "2026-04-19T05:38:51.000Z",
                ),
            )
    return source_model_id


def _matching_current_model(
    *,
    model_id: UUID,
    current_encryptor: Encryptor,
    secret: str = "legacy-test-secret",
    name: str = "Legacy gateway 0",
) -> Model:
    return Model(
        id=model_id,
        name=name,
        provider="custom",
        model_id="gpt-legacy-0",
        base_url="https://gateway.example.test/v1",
        api_key_encrypted=current_encryptor.encrypt(secret),
        extra_options={
            "api_format": "openai_compatible",
            "headers": {},
            "query_params": {},
            "api_key_optional": False,
            "healthcheck_mode": "chat_completion",
        },
        is_default=False,
        is_active=True,
    )


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _private_directory(path: Path) -> Path:
    path.mkdir(parents=True, mode=0o700)
    path.chmod(0o700)
    return path


def test_source_path_must_be_a_regular_file_beneath_the_desktop_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "desktop"
    source = root / "migration-backups" / "model-config.sqlite3"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"sqlite")

    assert validate_legacy_model_source(source, allowed_root=root) == source.resolve()

    outside = tmp_path / "outside.sqlite3"
    outside.write_bytes(b"sqlite")
    with pytest.raises(LegacyModelImportError, match="outside"):
        validate_legacy_model_source(outside, allowed_root=root)

    source.unlink()
    source.symlink_to(outside)
    with pytest.raises(LegacyModelImportError, match="symlinks"):
        validate_legacy_model_source(source, allowed_root=root)


def test_prepare_snapshot_uses_online_backup_for_live_wal_without_mutating_sources(
    tmp_path: Path,
) -> None:
    root = _private_directory(tmp_path / "desktop")
    source = _private_directory(root / "data") / "querygpt-ts.db"
    backups = _private_directory(root / "migration-backups")
    snapshot = _private_directory(backups / "migration-id") / "model-config.sqlite3"
    environment = root / ".env"
    environment.write_bytes(b"ENCRYPTION_KEY=legacy-key-sentinel\n")
    environment.chmod(0o600)

    writer = sqlite3.connect(source)
    try:
        assert writer.execute("PRAGMA journal_mode = WAL").fetchone() == ("wal",)
        writer.execute("PRAGMA wal_autocheckpoint = 0")
        writer.execute("CREATE TABLE committed_rows (value TEXT NOT NULL)")
        writer.commit()
        writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        writer.execute("INSERT INTO committed_rows VALUES ('from-live-wal')")
        writer.commit()

        wal = Path(f"{source}-wal")
        shm = Path(f"{source}-shm")
        journal = Path(f"{source}-journal")
        # A zero-header journal is inactive, but still proves that the online
        # backup never deletes or rewrites a pre-existing rollback sidecar.
        journal.write_bytes(bytes(512))
        journal.chmod(0o600)
        assert wal.stat().st_size > 0
        source_assets = {
            path: path.read_bytes()
            for path in (source, wal, journal, environment)
        }
        shm_identity = (shm.stat().st_dev, shm.stat().st_ino)

        prepared = prepare_legacy_model_snapshot(
            source_path=source,
            snapshot_path=snapshot,
            allowed_root=root,
        )

        assert prepared == snapshot.resolve()
        assert snapshot.stat().st_mode & 0o777 == 0o600
        assert snapshot.stat().st_nlink == 1
        assert not any(Path(f"{snapshot}{suffix}").exists() for suffix in ("-wal", "-shm", "-journal"))
        with sqlite3.connect(f"{snapshot.as_uri()}?mode=ro&immutable=1", uri=True) as copied:
            assert copied.execute("PRAGMA journal_mode").fetchone() == ("delete",)
            assert copied.execute("PRAGMA quick_check").fetchall() == [("ok",)]
            assert copied.execute("SELECT value FROM committed_rows").fetchall() == [
                ("from-live-wal",)
            ]

        assert {path: path.read_bytes() for path in source_assets} == source_assets
        assert shm.exists() and shm.is_file()
        assert (shm.stat().st_dev, shm.stat().st_ino) == shm_identity
        assert list(snapshot.parent.glob(f".{snapshot.name}.*.tmp*")) == []
    finally:
        writer.close()


def test_prepare_snapshot_reuses_valid_final_without_requiring_source(tmp_path: Path) -> None:
    root = _private_directory(tmp_path / "desktop")
    source = _private_directory(root / "data") / "querygpt-ts.db"
    snapshot = _private_directory(root / "archive") / "model-config.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE marker (value TEXT NOT NULL)")
        connection.execute("INSERT INTO marker VALUES ('authoritative-final')")
    first = prepare_legacy_model_snapshot(
        source_path=source,
        snapshot_path=snapshot,
        allowed_root=root,
    )
    original = snapshot.read_bytes()

    source.unlink()
    reused = prepare_legacy_model_snapshot(
        source_path=None,
        snapshot_path=snapshot,
        allowed_root=root,
    )

    assert reused == first
    assert snapshot.read_bytes() == original
    with sqlite3.connect(f"{snapshot.as_uri()}?mode=ro&immutable=1", uri=True) as copied:
        assert copied.execute("SELECT value FROM marker").fetchone() == (
            "authoritative-final",
        )


def test_prepare_snapshot_recovers_crash_leftover_hard_link(tmp_path: Path) -> None:
    root = _private_directory(tmp_path / "desktop")
    source = root / "source.sqlite3"
    snapshot = _private_directory(root / "archive") / "model-config.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE marker (value TEXT NOT NULL)")
        connection.execute("INSERT INTO marker VALUES ('crash-recovery')")
    prepare_legacy_model_snapshot(
        source_path=source,
        snapshot_path=snapshot,
        allowed_root=root,
    )
    leftover = snapshot.parent / f".{snapshot.name}.deadbeef.tmp"
    os.link(snapshot, leftover)
    assert snapshot.stat().st_nlink == 2

    reused = prepare_legacy_model_snapshot(
        source_path=None,
        snapshot_path=snapshot,
        allowed_root=root,
    )

    assert reused == snapshot.resolve()
    assert not leftover.exists()
    assert snapshot.stat().st_nlink == 1
    with sqlite3.connect(f"{snapshot.as_uri()}?mode=ro&immutable=1", uri=True) as copied:
        assert copied.execute("SELECT value FROM marker").fetchone() == (
            "crash-recovery",
        )


def test_snapshot_recovery_does_not_delete_unrelated_temp_shaped_entries(
    tmp_path: Path,
) -> None:
    root = _private_directory(tmp_path / "desktop")
    source = root / "source.sqlite3"
    snapshot = _private_directory(root / "archive") / "model-config.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE marker (value TEXT)")
    prepare_legacy_model_snapshot(
        source_path=source,
        snapshot_path=snapshot,
        allowed_root=root,
    )

    unrelated = snapshot.parent / f".{snapshot.name}.cafebabe.tmp"
    unrelated.write_bytes(b"unrelated-private-file")
    unrelated.chmod(0o600)
    symlink = snapshot.parent / f".{snapshot.name}.abc12345.tmp"
    symlink.symlink_to(snapshot)
    directory = snapshot.parent / f".{snapshot.name}.12345678.tmp"
    directory.mkdir(mode=0o700)

    reused = prepare_legacy_model_snapshot(
        source_path=None,
        snapshot_path=snapshot,
        allowed_root=root,
    )

    assert reused == snapshot.resolve()
    assert unrelated.read_bytes() == b"unrelated-private-file"
    assert symlink.is_symlink()
    assert directory.is_dir()
    assert snapshot.stat().st_nlink == 1


def test_snapshot_recovery_keeps_outside_hard_link_and_fails_closed(
    tmp_path: Path,
) -> None:
    root = _private_directory(tmp_path / "desktop")
    source = root / "source.sqlite3"
    snapshot = _private_directory(root / "archive") / "model-config.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE marker (value TEXT)")
    prepare_legacy_model_snapshot(
        source_path=source,
        snapshot_path=snapshot,
        allowed_root=root,
    )
    outside = tmp_path / "outside-hard-link.sqlite3"
    os.link(snapshot, outside)

    with pytest.raises(LegacyModelImportError, match="unsafe hard links"):
        prepare_legacy_model_snapshot(
            source_path=None,
            snapshot_path=snapshot,
            allowed_root=root,
        )

    assert outside.exists()
    assert (outside.stat().st_dev, outside.stat().st_ino) == (
        snapshot.stat().st_dev,
        snapshot.stat().st_ino,
    )
    assert snapshot.stat().st_nlink == 2


def test_prepare_snapshot_fails_closed_for_unsafe_target_or_invalid_final(
    tmp_path: Path,
) -> None:
    root = _private_directory(tmp_path / "desktop")
    source = root / "source.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE marker (value TEXT)")

    public_parent = root / "public-archive"
    public_parent.mkdir(mode=0o755)
    public_parent.chmod(0o755)
    with pytest.raises(LegacyModelImportError, match="not private"):
        prepare_legacy_model_snapshot(
            source_path=source,
            snapshot_path=public_parent / "model-config.sqlite3",
            allowed_root=root,
        )

    private_parent = _private_directory(root / "private-archive")
    invalid = private_parent / "model-config.sqlite3"
    invalid.write_bytes(b"not sqlite")
    invalid.chmod(0o600)
    with pytest.raises(LegacyModelImportError, match="not a SQLite"):
        prepare_legacy_model_snapshot(
            source_path=source,
            snapshot_path=invalid,
            allowed_root=root,
        )

    invalid.unlink()
    outside = tmp_path / "outside.sqlite3"
    with pytest.raises(LegacyModelImportError, match="outside"):
        prepare_legacy_model_snapshot(
            source_path=source,
            snapshot_path=outside,
            allowed_root=root,
        )


@pytest.mark.asyncio
async def test_imports_alongside_current_model_and_reencrypts_credential(
    db_session: AsyncSession, tmp_path: Path
):
    source = tmp_path / "querygpt-ts.db"
    legacy_key = b"l" * 32
    secret = "legacy-test-secret"
    legacy_id = _create_legacy_db(source, secret=secret, key=legacy_key)
    source_digest = _digest(source)
    current_encryptor = Encryptor(base64.urlsafe_b64encode(b"c" * 32).decode())
    current = Model(
        name="Current",
        provider="openai",
        model_id="gpt-current",
        api_key_encrypted=current_encryptor.encrypt("current-test-secret"),
        is_default=True,
    )
    db_session.add(current)
    await db_session.commit()

    result = await import_legacy_ts_model(
        db_session,
        source_path=source,
        legacy_encryption_key=base64.urlsafe_b64encode(legacy_key).decode(),
        current_encryptor=current_encryptor,
    )

    models = list((await db_session.execute(select(Model).order_by(Model.name))).scalars())
    imported = next(model for model in models if UUID(str(model.id)) == legacy_id)
    assert result.status == "imported"
    assert result.credential_migrated is True
    assert len(models) == 2
    assert imported.is_default is False
    assert imported.is_active is True
    assert current.is_default is True
    assert imported.api_key_encrypted is not None
    assert not imported.api_key_encrypted.startswith("v1.")
    assert current_encryptor.decrypt(imported.api_key_encrypted) == secret
    assert _digest(source) == source_digest
    assert secret not in repr(result)

    repeated = await import_legacy_ts_model(
        db_session,
        source_path=source,
        legacy_encryption_key=base64.urlsafe_b64encode(legacy_key).decode(),
        current_encryptor=current_encryptor,
    )
    assert repeated.status == "already_present"
    assert repeated.model_id == legacy_id
    assert repeated.credential_migrated is False
    assert secret not in repr(repeated)
    assert len(list((await db_session.execute(select(Model))).scalars())) == 2


@pytest.mark.asyncio
async def test_same_uuid_with_wrong_current_credential_fails_closed(
    db_session: AsyncSession, tmp_path: Path
):
    source = tmp_path / "querygpt-ts.db"
    legacy_secret = "legacy-test-secret"
    current_secret = "different-current-secret"
    legacy_id = _create_legacy_db(source, secret=legacy_secret)
    source_digest = _digest(source)
    current_encryptor = Encryptor(base64.urlsafe_b64encode(b"c" * 32).decode())
    existing = _matching_current_model(
        model_id=legacy_id,
        current_encryptor=current_encryptor,
        secret=current_secret,
    )
    db_session.add(existing)
    await db_session.commit()
    original_envelope = existing.api_key_encrypted

    with pytest.raises(LegacyModelImportError, match="conflicts") as error:
        await import_legacy_ts_model(
            db_session,
            source_path=source,
            legacy_encryption_key=base64.urlsafe_b64encode(b"l" * 32).decode(),
            current_encryptor=current_encryptor,
        )

    models = list((await db_session.execute(select(Model))).scalars())
    assert len(models) == 1
    assert models[0].api_key_encrypted == original_envelope
    assert _digest(source) == source_digest
    assert legacy_secret not in str(error.value)
    assert current_secret not in str(error.value)
    assert legacy_secret not in repr(error.value)
    assert current_secret not in repr(error.value)


@pytest.mark.asyncio
async def test_same_identity_with_different_uuid_is_imported_separately(
    db_session: AsyncSession, tmp_path: Path
):
    source = tmp_path / "querygpt-ts.db"
    legacy_key = b"l" * 32
    legacy_id = _create_legacy_db(source, key=legacy_key)
    current_encryptor = Encryptor(base64.urlsafe_b64encode(b"c" * 32).decode())
    existing = _matching_current_model(
        model_id=uuid4(),
        current_encryptor=current_encryptor,
    )
    db_session.add(existing)
    await db_session.commit()

    result = await import_legacy_ts_model(
        db_session,
        source_path=source,
        legacy_encryption_key=base64.urlsafe_b64encode(legacy_key).decode(),
        current_encryptor=current_encryptor,
    )

    models = list((await db_session.execute(select(Model))).scalars())
    assert result.status == "imported"
    assert result.model_id == legacy_id
    assert {UUID(str(model.id)) for model in models} == {UUID(str(existing.id)), legacy_id}


@pytest.mark.asyncio
async def test_same_uuid_with_field_mismatch_fails_closed(
    db_session: AsyncSession, tmp_path: Path
):
    source = tmp_path / "querygpt-ts.db"
    secret = "legacy-test-secret"
    legacy_id = _create_legacy_db(source, secret=secret)
    source_digest = _digest(source)
    current_encryptor = Encryptor(base64.urlsafe_b64encode(b"c" * 32).decode())
    existing = _matching_current_model(
        model_id=legacy_id,
        current_encryptor=current_encryptor,
        secret=secret,
        name="Conflicting current name",
    )
    db_session.add(existing)
    await db_session.commit()
    original_envelope = existing.api_key_encrypted

    with pytest.raises(LegacyModelImportError, match="conflicts") as error:
        await import_legacy_ts_model(
            db_session,
            source_path=source,
            legacy_encryption_key=base64.urlsafe_b64encode(b"l" * 32).decode(),
            current_encryptor=current_encryptor,
        )

    models = list((await db_session.execute(select(Model))).scalars())
    assert len(models) == 1
    assert models[0].name == "Conflicting current name"
    assert models[0].api_key_encrypted == original_envelope
    assert _digest(source) == source_digest
    assert secret not in str(error.value)
    assert secret not in repr(error.value)


@pytest.mark.asyncio
async def test_wrong_legacy_key_fails_without_writing(db_session: AsyncSession, tmp_path: Path):
    source = tmp_path / "querygpt-ts.db"
    _create_legacy_db(source)
    current_encryptor = Encryptor(base64.urlsafe_b64encode(b"c" * 32).decode())

    with pytest.raises(LegacyModelImportError, match="could not be authenticated") as error:
        await import_legacy_ts_model(
            db_session,
            source_path=source,
            legacy_encryption_key=base64.urlsafe_b64encode(b"x" * 32).decode(),
            current_encryptor=current_encryptor,
        )

    assert "legacy-test-secret" not in str(error.value)
    assert list((await db_session.execute(select(Model))).scalars()) == []


@pytest.mark.asyncio
async def test_missing_legacy_key_fails_only_when_a_credential_needs_it(
    db_session: AsyncSession, tmp_path: Path
):
    source = tmp_path / "querygpt-ts.db"
    _create_legacy_db(source)

    with pytest.raises(LegacyModelImportError, match="key is required"):
        await import_legacy_ts_model(
            db_session,
            source_path=source,
            legacy_encryption_key=None,
            current_encryptor=Encryptor(base64.urlsafe_b64encode(b"c" * 32).decode()),
        )

    assert list((await db_session.execute(select(Model))).scalars()) == []


@pytest.mark.asyncio
async def test_multiple_legacy_rows_fail_without_writing(db_session: AsyncSession, tmp_path: Path):
    source = tmp_path / "querygpt-ts.db"
    _create_legacy_db(source, rows=2)

    with pytest.raises(LegacyModelImportError, match="multiple records"):
        await import_legacy_ts_model(
            db_session,
            source_path=source,
            legacy_encryption_key=base64.urlsafe_b64encode(b"l" * 32).decode(),
            current_encryptor=Encryptor(base64.urlsafe_b64encode(b"c" * 32).decode()),
        )

    assert list((await db_session.execute(select(Model))).scalars()) == []
