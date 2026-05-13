"""Subprocess-адаптер к локальному TypeScript CLI поверх `@cursor/sdk`."""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from orchestrator.settings import Settings

Mode = Literal["prompt", "rag"]


@dataclass(frozen=True)
class CursorSdkResult:
    text: str
    status: str
    agent_id: str | None = None
    run_id: str | None = None
    duration_ms: int | None = None


class CursorSdkError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status: str = "error",
        retryable: bool = False,
        returncode: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.retryable = retryable
        self.returncode = returncode


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _orchestrator_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_cli_script() -> Path:
    return _orchestrator_root() / "cursor_agent_cli" / "dist" / "main.js"


def _resolve_path(raw: str, *, base: Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else base / path


def _output_preview(text: str, *, limit: int = 1200) -> str:
    stripped = (text or "").strip()
    if len(stripped) <= limit:
        return stripped
    return f"{stripped[:limit]}..."


def run_cursor_agent(
    *,
    mode: Mode,
    messages: list[dict[str, Any]] | None = None,
    question: str | None = None,
    system_prompt: str | None = None,
    mcp_server_url: str | None = None,
    model: str | None = None,
    timeout: int | None = None,
) -> CursorSdkResult:
    settings = Settings()
    cli_script = _resolve_path(
        settings.cursor_cli_script or str(_default_cli_script()),
        base=_orchestrator_root(),
    )
    if not cli_script.is_file():
        raise CursorSdkError(f"Cursor SDK CLI script not found: {cli_script}", status="startup_error")

    agent_cwd = _resolve_path(settings.cursor_agent_cwd or str(_repo_root()), base=_repo_root())
    api_key = settings.cursor_api_key
    if not api_key:
        raise CursorSdkError("CURSOR_API_KEY is required", status="startup_error")

    payload: dict[str, Any] = {
        "mode": mode,
        "model": model or settings.cursor_model,
        "cwd": str(agent_cwd),
    }
    if mode == "prompt":
        payload["messages"] = messages or []
    else:
        payload["question"] = question or ""
        payload["systemPrompt"] = system_prompt or ""
        payload["mcpServerUrl"] = mcp_server_url or settings.mcp_server_url

    env = os.environ.copy()
    env["CURSOR_API_KEY"] = api_key
    env["CURSOR_MODEL"] = model or settings.cursor_model

    effective_timeout = timeout if timeout is not None else settings.cursor_cli_timeout
    try:
        completed = subprocess.run(
            [settings.cursor_node_command, str(cli_script)],
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            encoding="utf-8",
            cwd=str(agent_cwd),
            env=env,
            timeout=effective_timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CursorSdkError(
            f"Cursor SDK CLI timed out after {effective_timeout}s",
            status="error",
            retryable=True,
        ) from exc
    except OSError as exc:
        raise CursorSdkError(f"Cannot start Cursor SDK CLI: {exc}", status="startup_error") from exc

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    try:
        parsed = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError as exc:
        detail = _output_preview(stdout or stderr)
        raise CursorSdkError(
            f"Cursor SDK CLI returned invalid JSON: {detail}",
            status="error",
            returncode=completed.returncode,
        ) from exc

    if completed.returncode != 0 or not parsed.get("ok"):
        message = str(parsed.get("error") or _output_preview(stderr) or "Cursor SDK CLI failed")
        raise CursorSdkError(
            message,
            status=str(parsed.get("status") or "error"),
            retryable=bool(parsed.get("retryable")),
            returncode=completed.returncode,
        )

    result = str(parsed.get("result") or "").strip()
    return CursorSdkResult(
        text=result,
        status=str(parsed.get("status") or "finished"),
        agent_id=parsed.get("agentId"),
        run_id=parsed.get("runId"),
        duration_ms=parsed.get("durationMs"),
    )


def call_prompt(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    timeout: int | None = None,
) -> str:
    return run_cursor_agent(mode="prompt", messages=messages, model=model, timeout=timeout).text


def call_rag(
    *,
    question: str,
    system_prompt: str,
    mcp_server_url: str | None = None,
    model: str | None = None,
    timeout: int | None = None,
) -> str:
    return run_cursor_agent(
        mode="rag",
        question=question,
        system_prompt=system_prompt,
        mcp_server_url=mcp_server_url,
        model=model,
        timeout=timeout,
    ).text
