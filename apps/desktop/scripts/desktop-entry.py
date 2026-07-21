"""PyInstaller entry point with a lightweight frozen-runtime self-check."""

import json
import multiprocessing
import os
import platform
import re
import sys
from importlib import metadata
from pathlib import Path


def _canonicalize_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _normalize_architecture(value: str) -> str:
    normalized = value.lower()
    if normalized in {"aarch64", "arm64"}:
        return "arm64"
    if normalized in {"amd64", "x64", "x86_64"}:
        return "x64"
    return normalized


def _find_distribution_inventory() -> Path | None:
    candidates: list[Path] = []
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        candidates.append(Path(frozen_root) / "builtin-distributions.json")

    executable_dir = Path(sys.executable).resolve().parent
    candidates.extend(
        [
            executable_dir / "builtin-distributions.json",
            executable_dir / "_internal" / "builtin-distributions.json",
            Path(__file__).resolve().parent / "builtin-distributions.json",
        ]
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def _run_self_check() -> int:
    errors: list[str] = []
    inventory_path = _find_distribution_inventory()
    expected_distributions: dict[str, str] = {}

    if inventory_path is None:
        errors.append("builtin-distributions.json was not found")
    else:
        try:
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            if not isinstance(inventory, dict):
                raise TypeError("distribution inventory must be a JSON object")
            if inventory.get("schema_version") != 1:
                errors.append("unsupported distribution inventory schema")
            for item in inventory.get("distributions", []):
                name = item.get("canonical_name")
                version = item.get("version")
                if not name or not version:
                    errors.append("invalid distribution inventory entry")
                    continue
                expected_distributions[name] = version
        except (AttributeError, OSError, TypeError, ValueError) as error:
            errors.append(f"unable to read distribution inventory: {error}")

    discovered_distributions: dict[str, str] = {}
    try:
        for distribution in metadata.distributions():
            name = distribution.metadata.get("Name")
            if name:
                discovered_distributions[_canonicalize_distribution_name(name)] = (
                    distribution.version
                )
    except Exception as error:  # pragma: no cover - exercised only in a broken frozen app
        errors.append(f"unable to enumerate bundled metadata: {error}")

    missing_metadata = sorted(set(expected_distributions) - set(discovered_distributions))
    version_mismatches = sorted(
        name
        for name, expected_version in expected_distributions.items()
        if name in discovered_distributions
        and discovered_distributions[name] != expected_version
    )
    metadata_ready = bool(expected_distributions) and not missing_metadata and not version_mismatches

    pip_ready = False
    pip_version: str | None = None
    try:
        import pip  # noqa: F401
        from pip._internal.cli.main import main as pip_main

        pip_version = metadata.version("pip")
        pip_ready = callable(pip_main)
    except Exception as error:  # pragma: no cover - exercised only in a broken frozen app
        errors.append(f"pip runtime is unavailable: {error}")

    machine = platform.machine()
    architecture = _normalize_architecture(machine)
    expected_architecture_raw = os.environ.get("RECEIPTBI_EXPECTED_ARCH")
    expected_architecture = (
        _normalize_architecture(expected_architecture_raw)
        if expected_architecture_raw
        else None
    )
    architecture_matches = (
        expected_architecture is None or architecture == expected_architecture
    )
    if not architecture_matches:
        errors.append(
            f"architecture mismatch: expected {expected_architecture}, got {architecture}"
        )

    ready = metadata_ready and pip_ready and architecture_matches and not errors
    report = {
        "status": "ok" if ready else "error",
        "frozen": bool(getattr(sys, "frozen", False)),
        "executable": sys.executable,
        "python_version": platform.python_version(),
        "machine": machine,
        "architecture": architecture,
        "expected_architecture": expected_architecture,
        "architecture_matches": architecture_matches,
        "inventory_path": str(inventory_path) if inventory_path else None,
        "expected_distribution_count": len(expected_distributions),
        "discovered_distribution_count": len(discovered_distributions),
        "metadata_ready": metadata_ready,
        "missing_metadata": missing_metadata,
        "version_mismatches": version_mismatches,
        "pip_ready": pip_ready,
        "pip_version": pip_version,
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if ready else 1


if __name__ == "__main__":
    # Required before importing the application when a frozen sandbox worker
    # re-enters this executable through multiprocessing spawn.
    multiprocessing.freeze_support()

if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))

if __name__ == "__main__" and "--self-check" in sys.argv:
    raise SystemExit(_run_self_check())

import uvicorn  # noqa: E402
from app.main import app  # noqa: E402

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "18080"))
    uvicorn.run(app, host=host, port=port, log_level="info")
