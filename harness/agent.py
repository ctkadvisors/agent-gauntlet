"""Minimal tool-loop agent: the thinnest possible harness around a model.

Deliberately spartan — two tools (bash, write_file), OpenAI-compatible
tool-calling, capped turns. The point is to measure the MODEL's agentic
competence, not a scaffold's cleverness. Anything a model can't do here
(explore a repo, run tests, edit files, iterate) it won't do better with
more machinery around it.
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command in the task workspace. Returns stdout+stderr (truncated).",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write full contents to a file path relative to the workspace root.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        },
    },
]

SYSTEM = (
    "You are a software engineering agent working in a git-less workspace at the "
    "current directory. Use the bash tool to explore and run tests, and write_file "
    "to change files. Work until the task's acceptance criterion passes, then reply "
    "with a short summary (no tool call) to finish."
)


class Agent:
    def __init__(self, endpoint: str, model: str, workspace: Path,
                 max_turns: int = 30, timeout_s: int = 120,
                 temperature: float = 0.2, max_tokens: int = 2048,
                 request_options: dict | None = None):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.workspace = workspace
        self.max_turns = max_turns
        self.timeout_s = timeout_s
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.request_options = request_options if request_options is not None else {}
        self.tokens_prompt = 0
        self.tokens_completion = 0
        self.tokens_reasoning: int | None = None
        self._reasoning_usage_complete = True
        self._chat_count = 0
        self.turns = 0
        self.seconds = 0.0
        self.termination_reason: str | None = None
        self.protocol_error: str | None = None
        self.transcript: list[dict] = []

    def _chat(self, messages: list[dict]) -> tuple[dict, str | None]:
        payload = {
            "model": self.model, "messages": messages, "tools": TOOLS,
            "temperature": self.temperature, "max_tokens": self.max_tokens,
        }
        payload.update(self.request_options)
        req = urllib.request.Request(
            f"{self.endpoint}/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=600) as resp:
            out = json.load(resp)
        usage = out.get("usage") or {}
        self.tokens_prompt += usage.get("prompt_tokens", 0)
        self.tokens_completion += usage.get("completion_tokens", 0)
        self._chat_count += 1
        details = usage.get("completion_tokens_details") or {}
        reasoning_tokens = details.get("reasoning_tokens")
        if reasoning_tokens is None:
            self._reasoning_usage_complete = False
            self.tokens_reasoning = None
        elif self._reasoning_usage_complete:
            self.tokens_reasoning = (self.tokens_reasoning or 0) + reasoning_tokens
        choice = out["choices"][0]
        return choice["message"], choice.get("finish_reason")

    def _run_tool(self, name: str, args: dict) -> str:
        if name == "bash":
            # shell=True is the point: this tool executes model-authored
            # shell strings by design, confined to a throwaway workspace.
            # Run the gauntlet only against models/endpoints you trust, on
            # a box where a hostile `rm -rf ~` would be survivable.
            try:
                proc = subprocess.run(
                    args.get("command", ""), shell=True, cwd=self.workspace,
                    capture_output=True, text=True, timeout=self.timeout_s,
                )
                out = (proc.stdout + proc.stderr).strip()
            except subprocess.TimeoutExpired:
                out = f"[timeout after {self.timeout_s}s]"
            return out[:6000] or "[no output]"
        if name == "write_file":
            target = (self.workspace / args["path"]).resolve()
            if not str(target).startswith(str(self.workspace.resolve())):
                return "[refused: path escapes workspace]"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(args["content"], encoding="utf-8")
            return f"[wrote {args['path']}]"
        return f"[unknown tool {name}]"

    def run(self, task_prompt: str) -> dict:
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": task_prompt}]
        t0 = time.time()
        seen_call_ids: set[str] = set()
        self.termination_reason = "max_turns"
        try:
            for _ in range(self.max_turns):
                self.turns += 1
                msg, finish_reason = self._chat(messages)
                self.transcript.append(msg)
                calls = msg.get("tool_calls") or []
                messages.append({k: v for k, v in msg.items() if v is not None})
                if finish_reason == "length":
                    self.termination_reason = "length"
                    break
                if not calls:
                    if finish_reason == "stop":
                        self.termination_reason = "stop"
                    else:
                        self.termination_reason = "protocol_error"
                        self.protocol_error = (
                            f"response without tool calls ended with {finish_reason!r}"
                        )
                    break
                call_ids = [call.get("id") for call in calls]
                if (any(not isinstance(call_id, str) or not call_id
                        for call_id in call_ids)
                        or len(set(call_ids)) != len(call_ids)
                        or any(call_id in seen_call_ids for call_id in call_ids)):
                    self.termination_reason = "protocol_error"
                    self.protocol_error = "tool calls require unique, non-empty string ids"
                    break
                seen_call_ids.update(call_ids)
                for call in calls:
                    fn = call["function"]
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    result = self._run_tool(fn["name"], args)
                    self.transcript.append({"tool": fn["name"], "args": args,
                                            "result": result[:2000]})
                    messages.append({"role": "tool", "tool_call_id": call["id"],
                                     "content": result})
        finally:
            self.seconds = round(time.time() - t0, 1)
        reasoning_tokens = (
            self.tokens_reasoning
            if self._chat_count and self._reasoning_usage_complete else None
        )
        return {"turns": self.turns, "seconds": self.seconds,
                "tokens_prompt": self.tokens_prompt,
                "tokens_completion": self.tokens_completion,
                "tokens_reasoning": reasoning_tokens,
                "termination_reason": self.termination_reason,
                "protocol_error": self.protocol_error,
                "temperature": self.request_options.get("temperature", self.temperature),
                "max_tokens": self.request_options.get("max_tokens", self.max_tokens)}
