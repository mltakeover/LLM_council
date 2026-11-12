"""One-command launcher for the LLM Council backend and frontend."""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv

DEFAULT_BACKEND_PORT = 8001
DEFAULT_FRONTEND_PORT = 5173
LOCAL_HOST = "127.0.0.1"


def _is_project_root(path: Path) -> bool:
    return (path / "backend" / "main.py").is_file() and (
        path / "frontend" / "package.json"
    ).is_file()


def find_project_root(start: Path | None = None) -> Path:
    """Find a source checkout containing both application halves."""

    current = (start or Path.cwd()).resolve()
    candidates = [current, *current.parents]
    candidates.append(Path(__file__).resolve().parents[1])

    for candidate in candidates:
        resolved = candidate.resolve()
        if _is_project_root(resolved):
            return resolved

    raise RuntimeError(
        "Could not find the LLM Council project files. Run this command from "
        "the repository or one of its subdirectories."
    )


def _npm_executable() -> str:
    executable = "npm.cmd" if sys.platform == "win32" else "npm"
    if shutil.which(executable):
        return executable
    raise RuntimeError("npm was not found. Install Node.js 20 or newer and try again.")


def _vite_executable(frontend_dir: Path) -> Path:
    name = "vite.cmd" if sys.platform == "win32" else "vite"
    return frontend_dir / "node_modules" / ".bin" / name


def ensure_frontend_dependencies(
    frontend_dir: Path,
    *,
    install_missing: bool = True,
) -> None:
    """Install the locked frontend dependencies only when Vite is absent."""

    if _vite_executable(frontend_dir).is_file():
        return
    if not install_missing:
        raise RuntimeError(
            "Frontend dependencies are missing. Run `npm ci` in frontend/ or "
            "start again without --skip-install."
        )

    print("Frontend dependencies are missing; running npm ci...", flush=True)
    subprocess.run([_npm_executable(), "ci"], cwd=frontend_dir, check=True)


def backend_command(*, reload: bool = True) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host",
        LOCAL_HOST,
        "--port",
        str(DEFAULT_BACKEND_PORT),
    ]
    if reload:
        command.append("--reload")
    return command


def frontend_command(
    *,
    open_browser: bool = False,
) -> list[str]:
    command = [
        _npm_executable(),
        "run",
        "dev",
        "--",
        "--host",
        LOCAL_HOST,
        "--port",
        str(DEFAULT_FRONTEND_PORT),
        "--strictPort",
    ]
    if open_browser:
        command.append("--open")
    return command


def _process_options(root: Path, env: dict[str, str]) -> dict[str, object]:
    options: dict[str, object] = {"cwd": root, "env": env}
    if sys.platform == "win32":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    return options


def _terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return

    try:
        if sys.platform == "win32":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass

    try:
        process.kill()
        process.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        pass


def run_services(args: argparse.Namespace) -> int:
    root = find_project_root()
    frontend_dir = root / "frontend"
    load_dotenv(root / ".env")

    _npm_executable()
    ensure_frontend_dependencies(
        frontend_dir,
        install_missing=not args.skip_install,
    )

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"

    processes: list[subprocess.Popen] = []
    stop_requested = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True

    previous_handlers = {
        signum: signal.signal(signum, request_stop)
        for signum in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        processes.append(
            subprocess.Popen(
                backend_command(
                    reload=not args.no_reload,
                ),
                **_process_options(root, env),
            )
        )
        processes.append(
            subprocess.Popen(
                frontend_command(
                    open_browser=args.open,
                ),
                **_process_options(frontend_dir, env),
            )
        )

        print(f"LLM Council UI: localhost:{DEFAULT_FRONTEND_PORT}", flush=True)
        print(f"Backend API:    {LOCAL_HOST}:{DEFAULT_BACKEND_PORT}", flush=True)
        print("Press Ctrl+C to stop both services.", flush=True)

        while not stop_requested and all(process.poll() is None for process in processes):
            time.sleep(0.25)

        if stop_requested:
            print("\nStopping LLM Council...", flush=True)
            return 0
        failed = next((process.returncode for process in processes if process.returncode), None)
        return failed or 0
    except KeyboardInterrupt:
        print("\nStopping LLM Council...", flush=True)
        return 0
    finally:
        for process in reversed(processes):
            _terminate_process(process)
        for signum, previous_handler in previous_handlers.items():
            signal.signal(signum, previous_handler)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="llm-council",
        description="Start the LLM Council backend and frontend together.",
    )
    parser.add_argument("--open", action="store_true", help="open the UI in the default browser")
    parser.add_argument("--no-reload", action="store_true", help="disable backend auto-reload")
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="do not run npm ci when frontend dependencies are missing",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run_services(args)
    except (RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
