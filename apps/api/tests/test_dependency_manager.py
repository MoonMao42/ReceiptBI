"""Focused reliability tests for project-local dependency installation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import app.services.dependency_manager as dependency_module
from app.services.dependency_manager import ProjectDependencyManager
from app.services.python_sandbox import PythonSandbox


def _write_distribution(
    target: Path,
    distribution_name: str,
    module_name: str,
    *,
    version: str = "1.0.0",
) -> None:
    package_dir = target / module_name
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "__init__.py").write_text("READY = True\n", encoding="utf-8")
    metadata_dir = target / f"{distribution_name.replace('-', '_')}-{version}.dist-info"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    (metadata_dir / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {distribution_name}\nVersion: {version}\n",
        encoding="utf-8",
    )
    (metadata_dir / "top_level.txt").write_text(f"{module_name}\n", encoding="utf-8")
    (metadata_dir / "RECORD").write_text(
        f"{module_name}/__init__.py,,\n{metadata_dir.name}/METADATA,,\n",
        encoding="utf-8",
    )


def _write_resolution_report(
    arguments: list[str],
    distributions_to_install: list[tuple[str, str]],
    *,
    wheel: bool = True,
) -> None:
    report_path = Path(arguments[arguments.index("--report") + 1])
    install = []
    for name, version in distributions_to_install:
        suffix = "whl" if wheel else "tar.gz"
        artifact_name = f"{name.replace('-', '_')}-{version}-py3-none-any.{suffix}"
        install.append(
            {
                "download_info": {
                    "url": f"https://packages.example.invalid/{artifact_name}",
                    "archive_info": {"hashes": {"sha256": "a" * 64}},
                },
                "metadata": {"name": name, "version": version},
            }
        )
    report_path.write_text(json.dumps({"version": "1", "install": install}), encoding="utf-8")


def test_python_preflight_finds_only_unavailable_import_roots(tmp_path: Path):
    project_path = tmp_path / ".python"
    available = project_path / "receiptbi_available_probe"
    available.mkdir(parents=True)
    (available / "__init__.py").write_text("READY = True\n", encoding="utf-8")
    sandbox = PythonSandbox(extra_paths=[str(project_path)])

    assert sandbox.missing_modules(
        """
import receiptbi_available_probe
import receiptbi_missing_probe_739
from receiptbi_missing_probe_739.tools import value
import os
"""
    ) == ["receiptbi_missing_probe_739"]


@pytest.mark.asyncio
async def test_install_uses_staging_then_atomically_commits(tmp_path: Path, monkeypatch):
    manager = ProjectDependencyManager(tmp_path / "project")
    _write_distribution(manager.target, "old-helper", "old_helper")
    manager._record_install(["old-helper"])
    pip_targets: list[Path] = []
    smoke_targets: list[Path] = []

    async def fake_pip(
        arguments: list[str], timeout: float, *, extra_paths: tuple[str, ...] = ()
    ) -> tuple[int, str]:
        del timeout
        if "--dry-run" in arguments:
            assert "--target" not in arguments
            assert extra_paths and Path(extra_paths[0]) != manager.target
            assert (Path(extra_paths[0]) / "old_helper" / "__init__.py").is_file()
            _write_resolution_report(arguments, [("demo-pkg", "1.2.3")])
            return 0, "resolved"
        staging = Path(arguments[arguments.index("--target") + 1])
        pip_targets.append(staging)
        assert "--no-deps" in arguments
        assert arguments[-1] == (
            f"https://packages.example.invalid/demo_pkg-1.2.3-py3-none-any.whl#sha256={'a' * 64}"
        )
        assert staging != manager.target
        assert (staging / "old_helper" / "__init__.py").is_file()
        _write_distribution(staging, "demo-pkg", "demo_pkg", version="1.2.3")
        return 0, "ok"

    async def fake_smoke(target: Path, packages: list[str], timeout: int) -> None:
        del timeout
        smoke_targets.append(target)
        assert packages == ["demo-pkg>=1"]
        assert (target / "demo_pkg" / "__init__.py").is_file()

    monkeypatch.setattr(manager, "_run_pip", fake_pip)
    monkeypatch.setattr(manager, "_smoke_test", fake_smoke)

    message = await manager.install(["demo-pkg>=1"])

    assert message == "已为当前项目安装：demo-pkg>=1"
    assert pip_targets == smoke_targets
    assert (manager.target / "old_helper" / "__init__.py").is_file()
    assert (manager.target / "demo_pkg" / "__init__.py").is_file()
    assert manager.describe() == {
        "requested": ["demo-pkg>=1", "old-helper"],
        "installed": [
            {"name": "demo-pkg", "version": "1.2.3"},
            {"name": "old-helper", "version": "1.0.0"},
        ],
    }
    assert list(manager.project_dir.glob(".python.staging.*")) == []
    assert list(manager.project_dir.glob(".python.backup.*")) == []
    assert list(manager.project_dir.glob(".python-dependencies.json.*.tmp")) == []


@pytest.mark.asyncio
async def test_already_satisfied_requirement_skips_target_install(tmp_path: Path, monkeypatch):
    manager = ProjectDependencyManager(tmp_path / "project")
    _write_distribution(manager.target, "demo-helper", "demo_helper", version="2.0.0")
    manager._record_install(["demo-helper>=1"])
    original_module = manager.target / "demo_helper" / "__init__.py"
    original_inode = original_module.stat().st_ino
    calls: list[list[str]] = []

    async def fake_pip(
        arguments: list[str], timeout: float, *, extra_paths: tuple[str, ...] = ()
    ) -> tuple[int, str]:
        del timeout
        calls.append(arguments)
        assert "--dry-run" in arguments
        assert "--target" not in arguments
        assert extra_paths and (Path(extra_paths[0]) / "demo_helper").is_dir()
        _write_resolution_report(arguments, [])
        return 0, "Requirement already satisfied"

    async def fake_smoke(target: Path, packages: list[str], timeout: float) -> None:
        del timeout
        assert packages == ["demo-helper>=2"]
        assert (target / "demo_helper").is_dir()

    monkeypatch.setattr(manager, "_run_pip", fake_pip)
    monkeypatch.setattr(manager, "_smoke_test", fake_smoke)

    await manager.install(["demo-helper>=2"])

    assert len(calls) == 1
    assert original_module.stat().st_ino == original_inode
    assert manager.describe()["requested"] == ["demo-helper>=1", "demo-helper>=2"]
    assert list(manager.project_dir.glob(".python-resolution.*.json")) == []


@pytest.mark.asyncio
async def test_failed_smoke_keeps_previous_environment_and_manifest(tmp_path: Path, monkeypatch):
    manager = ProjectDependencyManager(tmp_path / "project")
    _write_distribution(manager.target, "old-helper", "old_helper")
    manager._record_install(["old-helper"])
    previous_manifest = manager.manifest_path.read_text(encoding="utf-8")

    async def fake_pip(
        arguments: list[str], timeout: float, *, extra_paths: tuple[str, ...] = ()
    ) -> tuple[int, str]:
        del timeout
        if "--dry-run" in arguments:
            assert extra_paths
            _write_resolution_report(arguments, [("broken-helper", "1.0.0")])
            return 0, "resolved"
        staging = Path(arguments[arguments.index("--target") + 1])
        _write_distribution(staging, "broken-helper", "broken_helper")
        return 0, "ok"

    async def fail_smoke(target: Path, packages: list[str], timeout: int) -> None:
        del target, packages, timeout
        raise RuntimeError("依赖导入验收失败")

    monkeypatch.setattr(manager, "_run_pip", fake_pip)
    monkeypatch.setattr(manager, "_smoke_test", fail_smoke)

    with pytest.raises(RuntimeError, match="导入验收失败"):
        await manager.install(["broken-helper"])

    assert (manager.target / "old_helper" / "__init__.py").is_file()
    assert not (manager.target / "broken_helper").exists()
    assert manager.manifest_path.read_text(encoding="utf-8") == previous_manifest
    assert list(manager.project_dir.glob(".python.staging.*")) == []


def test_manifest_swap_failure_rolls_back_environment(tmp_path: Path, monkeypatch):
    manager = ProjectDependencyManager(tmp_path / "project")
    _write_distribution(manager.target, "old-helper", "old_helper")
    manager._record_install(["old-helper"])
    previous_manifest = manager.manifest_path.read_text(encoding="utf-8")
    staging = manager._prepare_staging()
    _write_distribution(staging, "new-helper", "new_helper")
    real_replace = dependency_module.os.replace

    def fail_manifest_replace(source, destination):
        if Path(destination) == manager.manifest_path:
            raise OSError("simulated manifest failure")
        return real_replace(source, destination)

    monkeypatch.setattr(dependency_module.os, "replace", fail_manifest_replace)

    with pytest.raises(OSError, match="manifest failure"):
        manager._commit(staging, ["new-helper"])

    assert (manager.target / "old_helper" / "__init__.py").is_file()
    assert not (manager.target / "new_helper").exists()
    assert manager.manifest_path.read_text(encoding="utf-8") == previous_manifest


@pytest.mark.asyncio
async def test_project_lock_serializes_concurrent_installs(tmp_path: Path, monkeypatch):
    manager = ProjectDependencyManager(tmp_path / "project")
    active = 0
    max_active = 0

    async def fake_pip(
        arguments: list[str], timeout: float, *, extra_paths: tuple[str, ...] = ()
    ) -> tuple[int, str]:
        nonlocal active, max_active
        del timeout
        active += 1
        max_active = max(max_active, active)
        try:
            await asyncio.sleep(0.08)
            if "--dry-run" in arguments:
                assert extra_paths
                requirement = arguments[-1]
                _write_resolution_report(arguments, [(requirement, "1.0.0")])
                return 0, "resolved"
            staging = Path(arguments[arguments.index("--target") + 1])
            artifact = arguments[-1]
            requirement = "alpha-helper" if "alpha_helper" in artifact else "beta-helper"
            _write_distribution(staging, requirement, requirement.replace("-", "_"))
            return 0, "ok"
        finally:
            active -= 1

    async def fake_smoke(target: Path, packages: list[str], timeout: int) -> None:
        del target, packages, timeout

    monkeypatch.setattr(manager, "_run_pip", fake_pip)
    monkeypatch.setattr(manager, "_smoke_test", fake_smoke)

    await asyncio.gather(manager.install(["alpha-helper"]), manager.install(["beta-helper"]))

    assert max_active == 1
    assert manager.describe()["requested"] == ["alpha-helper", "beta-helper"]
    assert (manager.target / "alpha_helper").is_dir()
    assert (manager.target / "beta_helper").is_dir()


@pytest.mark.asyncio
async def test_cancelling_install_kills_pip_subprocess(monkeypatch):
    started = asyncio.Event()

    class FakeProcess:
        def __init__(self):
            self.returncode = None
            self.killed = False
            self.finished = asyncio.Event()

        async def communicate(self):
            started.set()
            await self.finished.wait()
            return b"", None

        def kill(self):
            self.killed = True
            self.returncode = -9
            self.finished.set()

    process = FakeProcess()

    async def fake_create_subprocess_exec(*args, **kwargs):
        del args, kwargs
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    task = asyncio.create_task(
        ProjectDependencyManager._install_with_subprocess(["install", "demo"], timeout=30)
    )
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.killed is True


@pytest.mark.asyncio
async def test_frozen_install_requires_wheels(tmp_path: Path, monkeypatch):
    manager = ProjectDependencyManager(tmp_path / "project")
    captured: list[list[str]] = []

    async def fake_pip(
        arguments: list[str], timeout: float, *, extra_paths: tuple[str, ...] = ()
    ) -> tuple[int, str]:
        del timeout
        captured.append(arguments)
        if "--dry-run" in arguments:
            assert extra_paths
            _write_resolution_report(arguments, [("demo-helper", "1.0.0")])
            return 0, "resolved"
        staging = Path(arguments[arguments.index("--target") + 1])
        _write_distribution(staging, "demo-helper", "demo_helper")
        return 0, "ok"

    async def fake_smoke(target: Path, packages: list[str], timeout: int) -> None:
        del target, packages, timeout

    monkeypatch.setattr(dependency_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(manager, "_run_pip", fake_pip)
    monkeypatch.setattr(manager, "_smoke_test", fake_smoke)

    await manager.install(["demo-helper"])

    assert len(captured) == 2
    assert all("--only-binary=:all:" in arguments for arguments in captured)
    assert "--dry-run" in captured[0]
    assert "--target" not in captured[0]
    assert "--no-deps" in captured[1]
    assert "--target" in captured[1]


@pytest.mark.asyncio
async def test_frozen_resolution_rejects_source_artifact_before_install(
    tmp_path: Path, monkeypatch
):
    manager = ProjectDependencyManager(tmp_path / "project")
    calls = 0

    async def fake_pip(
        arguments: list[str], timeout: float, *, extra_paths: tuple[str, ...] = ()
    ) -> tuple[int, str]:
        nonlocal calls
        del timeout
        calls += 1
        assert "--dry-run" in arguments
        assert extra_paths
        _write_resolution_report(arguments, [("source-helper", "1.0.0")], wheel=False)
        return 0, "resolved"

    monkeypatch.setattr(dependency_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(manager, "_run_pip", fake_pip)

    with pytest.raises(RuntimeError, match="只允许安装预编译 wheel"):
        await manager.install(["source-helper"])

    assert calls == 1
    assert not manager.target.exists()


@pytest.mark.parametrize("requirement", ["numpy", "Pydantic_AI>=1", "pip==25.0"])
def test_core_packages_cannot_be_shadowed(tmp_path: Path, requirement: str):
    manager = ProjectDependencyManager(tmp_path / "project")

    with pytest.raises(ValueError, match="内置核心库不可由项目覆盖"):
        manager._validate_packages([requirement])


@pytest.mark.asyncio
async def test_import_smoke_runs_against_staged_package(tmp_path: Path):
    target = tmp_path / "staging"
    _write_distribution(target, "demo-helper", "demo_helper")

    await ProjectDependencyManager._smoke_test(target, ["demo-helper"], timeout=10)


@pytest.mark.asyncio
async def test_transitive_core_distribution_aborts_before_commit(tmp_path: Path, monkeypatch):
    manager = ProjectDependencyManager(tmp_path / "project")
    pip_calls = 0

    async def fake_pip(
        arguments: list[str], timeout: float, *, extra_paths: tuple[str, ...] = ()
    ) -> tuple[int, str]:
        nonlocal pip_calls
        del timeout
        pip_calls += 1
        assert "--dry-run" in arguments
        assert extra_paths
        _write_resolution_report(
            arguments,
            [("demo-helper", "1.0.0"), ("numpy", "2.3.0")],
        )
        return 0, "resolved"

    monkeypatch.setattr(manager, "_run_pip", fake_pip)

    with pytest.raises(RuntimeError, match="覆盖内置核心库.*numpy"):
        await manager.install(["demo-helper"])

    assert pip_calls == 1
    assert not manager.target.exists()
    assert not manager.manifest_path.exists()
