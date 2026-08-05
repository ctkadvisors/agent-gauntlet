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
                 max_turns: int = 30, timeout_s: int = 120):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.workspace = workspace
        self.max_turns = max_turns
        self.timeout_s = timeout_s
        self.tokens_prompt = 0
        self.tokens_completion = 0
        self.transcript: list[dict] = []

    def _chat(self, messages: list[dict]) -> dict:
        payload = {
            "model": self.model, "messages": messages, "tools": TOOLS,
            "temperature": 0.2, "max_tokens": 2048,
        }
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
        return out["choices"][0]["message"]

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
        turns = 0
        for _ in range(self.max_turns):
            turns += 1
            msg = self._chat(messages)
            self.transcript.append(msg)
            calls = msg.get("tool_calls") or []
            messages.append({k: v for k, v in msg.items() if v is not None})
            if not calls:
                break
            for call in calls:
                fn = call["function"]
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = self._run_tool(fn["name"], args)
                self.transcript.append({"tool": fn["name"], "args": args,
                                        "result": result[:2000]})
                messages.append({"role": "tool", "tool_call_id": call.get("id", "0"),
                                 "content": result})
        return {"turns": turns, "seconds": round(time.time() - t0, 1),
                "tokens_prompt": self.tokens_prompt,
                "tokens_completion": self.tokens_completion}
