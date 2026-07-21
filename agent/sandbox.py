"""Sandboxed code execution for Moonshot-Agent-X.

Two backends are provided:

- DockerSandbox: runs generated code inside a throwaway, network-disabled
  Docker container. This is the intended production backend — it's the
  real isolation boundary between "code an LLM just wrote" and the host.
- SubprocessSandbox: runs code as a resource-limited local subprocess.
  Used automatically when no Docker daemon is available (e.g. this dev
  environment) so the agent loop is still runnable end-to-end. It is
  NOT a security boundary — resource limits only, no filesystem/network
  isolation — and should not be used to run untrusted code in production.
"""

from __future__ import annotations

import resource
import shutil
import subprocess
import sys
import tempfile
import textwrap
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class Sandbox(ABC):
    @abstractmethod
    def run(self, code: str, timeout: int = 15) -> ExecutionResult:
        raise NotImplementedError

    @abstractmethod
    def run_tests(self, code: str, test_code: str, timeout: int = 15) -> ExecutionResult:
        """Run pytest for generated code and a supplied test module."""
        raise NotImplementedError


class DockerSandbox(Sandbox):
    """Executes code inside an ephemeral, network-disabled Docker container.

    Requires a Docker daemon reachable from this process and the `docker`
    Python SDK (installed via requirements.txt). The container is created
    fresh per run and removed afterward; no state persists between calls.
    """

    def __init__(
        self,
        image: str = "python:3.12-slim",
        mem_limit: str = "256m",
        cpu_quota: int = 50000,  # ~0.5 CPU, in Docker's 100000-per-CPU units
        network_disabled: bool = True,
    ):
        import docker  # deferred import: only needed for this backend

        self._client = docker.from_env()
        self.image = image
        self.mem_limit = mem_limit
        self.cpu_quota = cpu_quota
        self.network_disabled = network_disabled

    def run(self, code: str, timeout: int = 15) -> ExecutionResult:
        container = self._client.containers.run(
            self.image,
            command=["python3", "-c", code],
            detach=True,
            mem_limit=self.mem_limit,
            cpu_quota=self.cpu_quota,
            network_disabled=self.network_disabled,
            # No bind mounts: the container gets no access to the host fs.
        )
        try:
            result = container.wait(timeout=timeout)
            exit_code = result.get("StatusCode", 1)
            logs = container.logs(stdout=True, stderr=False).decode(errors="replace")
            errs = container.logs(stdout=False, stderr=True).decode(errors="replace")
            return ExecutionResult(stdout=logs, stderr=errs, exit_code=exit_code)
        except Exception as exc:  # covers docker.errors.APIError / timeouts
            return ExecutionResult(stdout="", stderr=str(exc), exit_code=1, timed_out=True)
        finally:
            try:
                container.remove(force=True)
            except Exception:
                pass

    def run_tests(self, code: str, test_code: str, timeout: int = 15) -> ExecutionResult:
        with tempfile.TemporaryDirectory(prefix="agentx_tests_") as tmp_dir:
            directory = Path(tmp_dir)
            (directory / "generated.py").write_text(code)
            (directory / "test_generated.py").write_text(test_code)
            container = self._client.containers.run(
                self.image,
                command=["python3", "-m", "pytest", "-q"],
                detach=True,
                mem_limit=self.mem_limit,
                cpu_quota=self.cpu_quota,
                network_disabled=self.network_disabled,
                volumes={str(directory): {"bind": "/work", "mode": "ro"}},
                working_dir="/work",
            )
            try:
                result = container.wait(timeout=timeout)
                return ExecutionResult(
                    stdout=container.logs(stdout=True, stderr=False).decode(errors="replace"),
                    stderr=container.logs(stdout=False, stderr=True).decode(errors="replace"),
                    exit_code=result.get("StatusCode", 1),
                )
            except Exception as exc:
                return ExecutionResult("", str(exc), 1, timed_out=True)
            finally:
                container.remove(force=True)


class SubprocessSandbox(Sandbox):
    """Fallback sandbox: runs code as a local subprocess with CPU/memory
    limits and a hard timeout, in a throwaway temp directory.

    This provides basic blast-radius control (a runaway loop or memory
    leak gets killed) but is NOT process or filesystem isolation. Treat
    it strictly as a development convenience, not a security boundary.
    """

    _warning_emitted = False

    def __init__(self, mem_limit_mb: int = 256, cpu_seconds: int = 10):
        if not type(self)._warning_emitted:
            warnings.warn(
                "SubprocessSandbox is not a security boundary; use DockerSandbox for untrusted code.",
                RuntimeWarning,
                stacklevel=2,
            )
            type(self)._warning_emitted = True
        self.mem_limit_mb = mem_limit_mb
        self.cpu_seconds = cpu_seconds

    def _limit_resources(self):
        mem_bytes = self.mem_limit_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        resource.setrlimit(resource.RLIMIT_CPU, (self.cpu_seconds, self.cpu_seconds))

    def run(self, code: str, timeout: int = 15) -> ExecutionResult:
        tmp_dir = Path(tempfile.mkdtemp(prefix="agentx_"))
        script_path = tmp_dir / "attempt.py"
        script_path.write_text(code)

        preexec = self._limit_resources if sys.platform != "win32" else None
        try:
            proc = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                preexec_fn=preexec,
            )
            return ExecutionResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)
        except subprocess.TimeoutExpired as exc:
            return ExecutionResult(
                stdout=exc.stdout or "",
                stderr=(exc.stderr or "") + "\n[sandbox] execution timed out",
                exit_code=124,
                timed_out=True,
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def run_tests(self, code: str, test_code: str, timeout: int = 15) -> ExecutionResult:
        tmp_dir = Path(tempfile.mkdtemp(prefix="agentx_tests_"))
        try:
            (tmp_dir / "generated.py").write_text(code)
            (tmp_dir / "test_generated.py").write_text(test_code)
            preexec = self._limit_resources if sys.platform != "win32" else None
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q"],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                preexec_fn=preexec,
            )
            return ExecutionResult(proc.stdout, proc.stderr, proc.returncode)
        except subprocess.TimeoutExpired as exc:
            return ExecutionResult(
                exc.stdout or "",
                (exc.stderr or "") + "\n[sandbox] test execution timed out",
                124,
                timed_out=True,
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def get_sandbox(prefer: str = "auto") -> Sandbox:
    """Factory. 'docker' / 'subprocess' force a backend; 'auto' uses Docker
    if a daemon is reachable, otherwise falls back to the subprocess
    sandbox so the framework runs out of the box in dev environments."""
    if prefer == "subprocess":
        return SubprocessSandbox()
    if prefer == "docker":
        return DockerSandbox()
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return DockerSandbox()
    except Exception:
        return SubprocessSandbox()
