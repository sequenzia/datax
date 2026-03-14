"""DataX dev server CLI.

Manages backend (FastAPI) and frontend (Vite) dev servers with PID tracking,
health checking, log tailing, and clean process group shutdown.

Runtime artifacts are stored in `.datax/` at the project root (gitignored).
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from enum import Enum
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.json import JSON as RichJSON
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="dx",
    help="DataX dev server CLI — start, stop, and monitor backend & frontend servers.",
    no_args_is_help=True,
)
console = Console()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BACKEND_PORT = 8000
FRONTEND_PORT = 5173
HEALTH_URL = f"http://localhost:{BACKEND_PORT}/health"
READY_URL = f"http://localhost:{BACKEND_PORT}/ready"


class Service(str, Enum):
    backend = "backend"
    frontend = "frontend"


SERVICE_CONFIG: dict[str, dict[str, object]] = {
    "backend": {
        "cmd": [
            "uv", "run", "uvicorn", "app.main:create_app",
            "--factory", "--reload", "--host", "127.0.0.1", "--port", "8000",
        ],
        "cwd_rel": "apps/backend",
        "port": BACKEND_PORT,
    },
    "frontend": {
        "cmd": ["pnpm", "dev"],
        "cwd_rel": "apps/frontend",
        "port": FRONTEND_PORT,
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_root() -> Path:
    """Walk up from cwd to find the project root (contains pyproject.toml with datax)."""
    cur = Path.cwd()
    for parent in [cur, *cur.parents]:
        candidate = parent / "pyproject.toml"
        if candidate.exists() and "datax" in candidate.read_text():
            return parent
    console.print(
        "[red]Not in DataX project root. Run from the directory containing pyproject.toml[/red]"
    )
    raise typer.Exit(1)


def _datax_dir(root: Path) -> Path:
    d = root / ".datax"
    d.mkdir(exist_ok=True)
    return d


def _pids_path(root: Path) -> Path:
    return _datax_dir(root) / "pids.json"


def _read_pids(root: Path) -> dict[str, int]:
    path = _pids_path(root)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write_pids(root: Path, pids: dict[str, int]) -> None:
    _pids_path(root).write_text(json.dumps(pids, indent=2) + "\n")


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _clean_stale_pids(root: Path) -> dict[str, int]:
    """Read PIDs and remove any that are no longer alive."""
    pids = _read_pids(root)
    alive = {name: pid for name, pid in pids.items() if _is_alive(pid)}
    if alive != pids:
        _write_pids(root, alive)
    return alive


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def _log_path(root: Path, service: str) -> Path:
    return _datax_dir(root) / f"{service}.log"


def _tail_lines(path: Path, n: int) -> str:
    if not path.exists():
        return "(no log file)"
    lines = path.read_text().splitlines()
    return "\n".join(lines[-n:])


def _wait_healthy(timeout: int) -> bool:
    """Poll the backend health endpoint until it responds 200 or timeout."""
    import httpx

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(HEALTH_URL, timeout=2)
            if resp.status_code == 200:
                return True
        except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException):
            pass
        time.sleep(0.5)
    return False


def _kill_service(pid: int, name: str) -> None:
    """Send SIGTERM to the process group, escalate to SIGKILL after 5s."""
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return

    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not _is_alive(pid):
            return
        time.sleep(0.2)

    # Escalate
    try:
        os.killpg(pgid, signal.SIGKILL)
        console.print(f"[yellow]{name} required SIGKILL[/yellow]")
    except ProcessLookupError:
        pass


def _start_service(
    root: Path, name: str, pids: dict[str, int], timeout: int
) -> dict[str, int]:
    """Start a single service, returning the updated pids dict."""
    cfg = SERVICE_CONFIG[name]
    port = cfg["port"]
    cmd: list[str] = cfg["cmd"]  # type: ignore[assignment]
    cwd = root / cfg["cwd_rel"]

    # Already running?
    if name in pids and _is_alive(pids[name]):
        console.print(f"[cyan]{name}[/cyan] is already running (PID {pids[name]})")
        return pids

    # Port conflict?
    if _port_in_use(port):  # type: ignore[arg-type]
        console.print(
            f"[red]Port {port} is already in use. "
            f"Run `dx status` or `lsof -i :{port}`[/red]"
        )
        raise typer.Exit(1)

    log_file = _log_path(root, name).open("a")
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=log_file,
        start_new_session=True,
    )
    log_file.close()

    pids[name] = proc.pid
    _write_pids(root, pids)

    if name == "backend":
        with console.status(f"[cyan]Waiting for {name} health check...[/cyan]"):
            if _wait_healthy(timeout):
                console.print(
                    f"[green]✓[/green] {name} started (PID {proc.pid}, port {port})"
                )
            else:
                console.print(
                    f"[red]{name} did not become healthy within {timeout}s. "
                    f"Check `dx logs backend`[/red]"
                )
                console.print(_tail_lines(_log_path(root, name), 20))
                raise typer.Exit(1)
    else:
        # Frontend: give it a moment and verify the process is alive
        time.sleep(1.5)
        if not _is_alive(proc.pid):
            console.print(
                f"[red]{name} failed to start. Last 20 lines from `.datax/{name}.log`:[/red]"
            )
            console.print(_tail_lines(_log_path(root, name), 20))
            del pids[name]
            _write_pids(root, pids)
            raise typer.Exit(1)
        console.print(
            f"[green]✓[/green] {name} started (PID {proc.pid}, port {port})"
        )

    return pids


def _stop_service(root: Path, name: str, pids: dict[str, int]) -> dict[str, int]:
    """Stop a single service, returning the updated pids dict."""
    if name not in pids or not _is_alive(pids[name]):
        console.print(f"[dim]{name} is not running[/dim]")
        pids.pop(name, None)
        _write_pids(root, pids)
        return pids

    pid = pids[name]
    _kill_service(pid, name)
    console.print(f"[green]✓[/green] {name} stopped (was PID {pid})")
    del pids[name]
    _write_pids(root, pids)
    return pids


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def start(
    service: Annotated[
        Optional[Service],
        typer.Argument(help="Service to start (omit for both)"),
    ] = None,
    timeout: Annotated[
        int,
        typer.Option("--timeout", "-t", help="Health check timeout in seconds"),
    ] = 30,
) -> None:
    """Start dev servers."""
    root = _find_root()
    pids = _clean_stale_pids(root)

    targets = [service.value] if service else ["backend", "frontend"]
    for name in targets:
        pids = _start_service(root, name, pids, timeout)


@app.command()
def stop(
    service: Annotated[
        Optional[Service],
        typer.Argument(help="Service to stop (omit for both)"),
    ] = None,
) -> None:
    """Stop dev servers."""
    root = _find_root()
    pids = _clean_stale_pids(root)

    targets = [service.value] if service else ["backend", "frontend"]
    for name in targets:
        pids = _stop_service(root, name, pids)


@app.command()
def restart(
    service: Annotated[
        Optional[Service],
        typer.Argument(help="Service to restart (omit for both)"),
    ] = None,
    timeout: Annotated[
        int,
        typer.Option("--timeout", "-t", help="Health check timeout in seconds"),
    ] = 30,
) -> None:
    """Restart dev servers (stop then start)."""
    root = _find_root()
    pids = _clean_stale_pids(root)

    targets = [service.value] if service else ["backend", "frontend"]
    for name in targets:
        pids = _stop_service(root, name, pids)
    for name in targets:
        pids = _start_service(root, name, pids, timeout)


@app.command()
def status() -> None:
    """Show status of dev servers."""
    root = _find_root()
    pids = _clean_stale_pids(root)

    table = Table(title="DataX Dev Servers")
    table.add_column("Service", style="bold")
    table.add_column("Status")
    table.add_column("PID")
    table.add_column("Port")

    for name, cfg in SERVICE_CONFIG.items():
        pid = pids.get(name)
        if pid and _is_alive(pid):
            status_str = "[green]running[/green]"
            pid_str = str(pid)
        else:
            status_str = "[red]stopped[/red]"
            pid_str = "-"
        table.add_row(name, status_str, pid_str, str(cfg["port"]))

    console.print(table)


@app.command()
def logs(
    service: Annotated[
        Service,
        typer.Argument(help="Service to tail logs for"),
    ],
    lines: Annotated[
        int,
        typer.Option("--lines", "-n", help="Number of initial lines to show"),
    ] = 50,
) -> None:
    """Tail logs for a service (delegates to tail -f)."""
    root = _find_root()
    log = _log_path(root, service.value)
    if not log.exists():
        console.print(f"[dim]No log file for {service.value} yet[/dim]")
        raise typer.Exit(0)

    try:
        subprocess.run(
            ["tail", "-n", str(lines), "-f", str(log)],
            check=False,
        )
    except KeyboardInterrupt:
        pass


@app.command()
def health() -> None:
    """Check backend health and readiness endpoints."""
    import httpx

    for label, url in [("Health", HEALTH_URL), ("Ready", READY_URL)]:
        try:
            resp = httpx.get(url, timeout=5)
            color = "green" if resp.status_code == 200 else "yellow"
            panel = Panel(
                RichJSON(resp.text),
                title=f"[{color}]{label} ({resp.status_code})[/{color}]",
                border_style=color,
            )
        except httpx.ConnectError:
            panel = Panel(
                "[red]Connection refused — backend is not running[/red]",
                title=f"[red]{label}[/red]",
                border_style="red",
            )
        except httpx.TimeoutException:
            panel = Panel(
                "[red]Request timed out[/red]",
                title=f"[red]{label}[/red]",
                border_style="red",
            )
        console.print(panel)
