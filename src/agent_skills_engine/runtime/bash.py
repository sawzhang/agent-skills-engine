"""
Bash execution runtime.
"""

from __future__ import annotations

import asyncio
import os

from agent_skills_engine.runtime.base import ExecutionResult, SkillRuntime


class BashRuntime(SkillRuntime):
    """
    Bash-based skill execution runtime.

    Executes commands using the system shell.
    """

    def __init__(
        self,
        shell: str = "/bin/bash",
        default_timeout: float = 30.0,
        max_output_size: int = 1_000_000,  # 1MB
    ) -> None:
        self.shell = shell
        self.default_timeout = default_timeout
        self.max_output_size = max_output_size

    async def execute(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> ExecutionResult:
        """Execute a single command."""
        timer = self._timer()
        timeout = timeout or self.default_timeout

        # Merge environment
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=full_env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ExecutionResult.error_result(
                    error=f"Command timed out after {timeout}s",
                    exit_code=-1,
                    duration_ms=timer.elapsed_ms(),
                )

            output = self._decode_output(stdout)
            error_output = self._decode_output(stderr)

            if process.returncode == 0:
                return ExecutionResult.success_result(
                    output=output,
                    duration_ms=timer.elapsed_ms(),
                )
            else:
                return ExecutionResult.error_result(
                    error=error_output or f"Command failed with exit code {process.returncode}",
                    exit_code=process.returncode or 1,
                    output=output,
                    duration_ms=timer.elapsed_ms(),
                )

        except Exception as e:
            return ExecutionResult.error_result(
                error=str(e),
                exit_code=-1,
                duration_ms=timer.elapsed_ms(),
            )

    async def execute_script(
        self,
        script: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> ExecutionResult:
        """Execute a multi-line script."""
        timer = self._timer()
        timeout = timeout or self.default_timeout

        # Merge environment
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        try:
            process = await asyncio.create_subprocess_exec(
                self.shell,
                "-c",
                script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=full_env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ExecutionResult.error_result(
                    error=f"Script timed out after {timeout}s",
                    exit_code=-1,
                    duration_ms=timer.elapsed_ms(),
                )

            output = self._decode_output(stdout)
            error_output = self._decode_output(stderr)

            if process.returncode == 0:
                return ExecutionResult.success_result(
                    output=output,
                    duration_ms=timer.elapsed_ms(),
                )
            else:
                return ExecutionResult.error_result(
                    error=error_output or f"Script failed with exit code {process.returncode}",
                    exit_code=process.returncode or 1,
                    output=output,
                    duration_ms=timer.elapsed_ms(),
                )

        except Exception as e:
            return ExecutionResult.error_result(
                error=str(e),
                exit_code=-1,
                duration_ms=timer.elapsed_ms(),
            )

    def _decode_output(self, data: bytes) -> str:
        """Decode command output, truncating if necessary."""
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            text = str(data)

        if len(text) > self.max_output_size:
            text = text[: self.max_output_size] + "\n... (output truncated)"

        return text
