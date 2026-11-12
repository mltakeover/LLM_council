import sys
from pathlib import Path

import pytest

from backend import cli


def test_find_project_root_from_nested_directory(tmp_path: Path) -> None:
    root = tmp_path / "LLM_council"
    nested = root / "frontend" / "src"
    nested.mkdir(parents=True)
    (root / "backend").mkdir()
    (root / "backend" / "main.py").touch()
    (root / "frontend" / "package.json").touch()

    assert cli.find_project_root(nested) == root


def test_backend_command_uses_active_python_and_reload() -> None:
    command = cli.backend_command()

    assert command[:4] == [sys.executable, "-m", "uvicorn", "backend.main:app"]
    assert command[4:8] == ["--host", "127.0.0.1", "--port", "8001"]
    assert command[-1] == "--reload"


def test_frontend_command_uses_strict_local_port() -> None:
    command = cli.frontend_command(open_browser=True)
    npm = "npm.cmd" if sys.platform == "win32" else "npm"

    assert command == [
        npm,
        "run",
        "dev",
        "--",
        "--host",
        "127.0.0.1",
        "--port",
        "5173",
        "--strictPort",
        "--open",
    ]


def test_missing_frontend_dependencies_can_fail_without_install(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Frontend dependencies are missing"):
        cli.ensure_frontend_dependencies(tmp_path, install_missing=False)
