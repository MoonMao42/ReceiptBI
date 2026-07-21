"""Credential compatibility tests for desktop key rotation."""

from __future__ import annotations

import base64

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Encryptor
from app.db.tables import Connection, Model
from app.services.credential_migration import (
    LEGACY_DESKTOP_ENCRYPTION_KEY,
    rotate_legacy_desktop_credentials,
)


@pytest.mark.asyncio
async def test_only_legacy_desktop_credentials_are_rotated(db_session: AsyncSession):
    legacy = Encryptor(LEGACY_DESKTOP_ENCRYPTION_KEY)
    current = Encryptor(base64.urlsafe_b64encode(b"n" * 32).decode())
    legacy_connection = Connection(
        name="legacy",
        driver="sqlite",
        password_encrypted=legacy.encrypt("database-secret"),
    )
    current_model = Model(
        name="current",
        provider="openai",
        model_id="gpt-test",
        api_key_encrypted=current.encrypt("current-secret"),
    )
    unknown_model = Model(
        name="unknown",
        provider="openai",
        model_id="gpt-test",
        api_key_encrypted="not-a-fernet-token",
    )
    db_session.add_all([legacy_connection, current_model, unknown_model])
    await db_session.flush()
    original_current = current_model.api_key_encrypted

    migrated, unreadable = await rotate_legacy_desktop_credentials(
        db_session,
        current_encryptor=current,
    )

    assert (migrated, unreadable) == (1, 1)
    assert current.decrypt(legacy_connection.password_encrypted) == "database-secret"
    assert current_model.api_key_encrypted == original_current
    assert unknown_model.api_key_encrypted == "not-a-fernet-token"
