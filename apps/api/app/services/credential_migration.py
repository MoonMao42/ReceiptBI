"""One-time compatibility migration for legacy desktop credentials."""

from __future__ import annotations

import base64
import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Encryptor, encryptor
from app.db.tables import Connection, Model

LEGACY_DESKTOP_ENCRYPTION_KEY = "your-encryption-key-32-bytes-long"


async def rotate_legacy_desktop_credentials(
    session: AsyncSession,
    *,
    current_encryptor: Encryptor = encryptor,
) -> tuple[int, int]:
    """Re-encrypt credentials that still use the old shared desktop key.

    Values encrypted with the current key are left untouched. Values that can
    be decrypted by neither key are also left untouched so a wrong key can
    never silently destroy user credentials.
    """

    legacy_key = base64.urlsafe_b64encode(
        hashlib.sha256(LEGACY_DESKTOP_ENCRYPTION_KEY.encode()).digest()
    ).decode()
    legacy_encryptor = Encryptor(legacy_key)
    migrated = 0
    unreadable = 0

    records = [
        *(await session.scalars(select(Connection))).all(),
        *(await session.scalars(select(Model))).all(),
    ]
    for record in records:
        attribute = "password_encrypted" if isinstance(record, Connection) else "api_key_encrypted"
        ciphertext = getattr(record, attribute)
        if not ciphertext:
            continue

        try:
            current_encryptor.decrypt(ciphertext)
            continue
        except Exception:
            pass

        try:
            plaintext = legacy_encryptor.decrypt(ciphertext)
        except Exception:
            unreadable += 1
            continue

        setattr(record, attribute, current_encryptor.encrypt(plaintext))
        migrated += 1

    return migrated, unreadable
