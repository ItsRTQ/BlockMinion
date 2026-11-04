"""SEC-002: the only place the controller spawns an external process.

- Minimal, explicit environment (no os.environ passthrough).
- Own process group/session so a timeout kills Gradle *and* its children (daemons, javac).
- Output goes to a file, never into memory unbounded.
- Returns a record (pid, duration, exit code, killed) for the Footprint.
"""
from __future__ import annotations
import os
import re
import signal
import subprocess
import time
from pathlib import Path

DEFAULT_TIMEOUT = int(os.environ.get("CRAFTCTL_BUILD_TIMEOUT", "1800"))  # first build downloads Gradle + Minecraft

# Environment variables forwarded to child processes. Everything else is dropped.
ENV_ALLOWLIST_COMMON = ("PATH", "JAVA_HOME", "GRADLE_USER_HOME", "GRADLE_OPTS", "LANG", "LC_ALL", "TZ",
                        "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy")
ENV_ALLOWLIST_POSIX = ("HOME", "USER", "TMPDIR", "SHELL", "DISPLAY")
ENV_ALLOWLIST_WINDOWS = ("USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP",
                         "SystemRoot", "SystemDrive", "ComSpec", "PATHEXT", "ProgramFiles", "ProgramData",
                         "USERNAME", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE")


def controlled_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    names = ENV_ALLOWLIST_COMMON + (ENV_ALLOWLIST_WINDOWS if os.name == "nt" else ENV_ALLOWLIST_POSIX)
    env = {k: os.environ[k] for k in names if k in os.environ}
    env["JAVA_TOOL_OPTIONS"] = (os.environ.get("JAVA_TOOL_OPTIONS", "") + " -Dfile.encoding=UTF-8").strip()
    if extra:
        env.update(extra)
    return env


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def run_logged(cmd: list[str], *, cwd: Path, log: Path, timeout: int = DEFAULT_TIMEOUT,
               env: dict[str, str] | None = None, stdin_text: str | None = None) -> dict:
    """Run cmd with stdout+stderr written to `log`. Never raises on process failure.
    stdin_text, if given, is fed to the process and the pipe closed (prompts must not go on the
    command line: Windows limits it and it would be echoed into logs)."""
    env = env or controlled_env()
    popen_kwargs: dict = {}
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    killed = False
    with log.open("wb") as f:
        shown = " ".join(a if len(a) <= 200 else a[:200] + "…" for a in cmd)
        f.write(f"$ {shown}\n".encode())
        f.flush()  # the child writes to the fd directly; without this the header lands after its output
        proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=f, stderr=subprocess.STDOUT, env=env,
                                stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL, **popen_kwargs)
        try:
            if stdin_text is not None:
                try:
                    proc.stdin.write(stdin_text.encode("utf-8"))
                except (BrokenPipeError, OSError):
                    pass
                finally:
                    proc.stdin.close()
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                pass
            killed = True
            code = 124
            f.write(f"\n[craftctl] timeout after {timeout}s; process tree killed\n".encode())
    return {"pid": proc.pid, "exit_code": code, "killed": killed, "timeout_s": timeout,
            "duration_s": round(time.time() - started, 1), "cmd": cmd}


def run_watch(cmd: list[str], *, cwd: Path, log: Path, timeout: int, ready: "re.Pattern[str]",
              stop_input: str | None = None, env: dict[str, str] | None = None, grace: int = 60) -> dict:
    """Run a long-lived process, tail its log until `ready` matches (or timeout), then ask it to stop
    via stdin (e.g. a Minecraft server's `stop`) and wait `grace` seconds before killing the tree."""
    env = env or controlled_env()
    popen_kwargs: dict = {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)} if os.name == "nt" else {"start_new_session": True}
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    matched = False
    with log.open("wb") as f:
        f.write(f"$ {' '.join(cmd)}\n".encode()); f.flush()
        proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=f, stderr=subprocess.STDOUT, env=env,
                                stdin=subprocess.PIPE if stop_input is not None else subprocess.DEVNULL, **popen_kwargs)  # a test server blocks on an open pipe
        pos = 0
        while time.time() - started < timeout and proc.poll() is None:
            time.sleep(1.0)
            with log.open("rb") as r:
                r.seek(pos); chunk = r.read(); pos += len(chunk)
            if chunk and ready.search(chunk.decode("utf-8", "replace")):
                matched = True
                break
        exited_early = proc.poll() is not None and not matched
        if proc.poll() is None:
            if stop_input is not None:
                try:
                    proc.stdin.write(stop_input.encode()); proc.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
            try:
                proc.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                _kill_tree(proc)
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    pass
        try:
            proc.stdin.close()
        except Exception:
            pass
        code = proc.returncode
        if not matched:
            f.write(f"\n[craftctl] {'process exited before the ready marker' if exited_early else f'ready marker not seen within {timeout}s'}\n".encode())
    return {"pid": proc.pid, "exit_code": code, "ready": matched, "exited_early": exited_early,
            "duration_s": round(time.time() - started, 1), "timeout_s": timeout, "cmd": cmd}
