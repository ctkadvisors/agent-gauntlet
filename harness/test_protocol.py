"""Dependency-free regression tests for the agent protocol."""

from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from harness.agent import Agent
from harness.run import run_task


def response(message: dict, finish_reason: str, completion_tokens: int = 1,
             reasoning_tokens: int | None = None) -> dict:
    usage = {"prompt_tokens": 2, "completion_tokens": completion_tokens}
    if reasoning_tokens is not None:
        usage["completion_tokens_details"] = {
            "reasoning_tokens": reasoning_tokens,
        }
    return {
        "choices": [{"message": message, "finish_reason": finish_reason}],
        "usage": usage,
    }


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


class HTTPStub:
    def __init__(self, *responses: dict):
        self.responses = list(responses)
        self.payloads: list[dict] = []

    def __call__(self, request, timeout):
        self.payloads.append(json.loads(request.data))
        return FakeResponse(json.dumps(self.responses.pop(0)).encode())


class ProtocolTests(unittest.TestCase):
    def make_agent(self, workspace: Path, **kwargs) -> Agent:
        return Agent("http://example.invalid", "test-model", workspace, **kwargs)

    def test_length_is_not_a_clean_stop(self):
        message = {"role": "assistant", "content": "partial",
                   "reasoning_content": "thinking"}
        http = HTTPStub(response(message, "length", completion_tokens=16,
                                 reasoning_tokens=12))
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("urllib.request.urlopen", http):
            agent = self.make_agent(Path(tmp), temperature=0.3, max_tokens=16,
                                    request_options={"top_p": 0.9})
            stats = agent.run("task")

        self.assertEqual(stats["termination_reason"], "length")
        self.assertEqual(stats["tokens_completion"], 16)
        self.assertEqual(stats["tokens_reasoning"], 12)
        self.assertEqual(agent.transcript[0]["reasoning_content"], "thinking")
        self.assertEqual(stats["temperature"], 0.3)
        self.assertEqual(http.payloads[0]["max_tokens"], 16)
        self.assertEqual(http.payloads[0]["temperature"], 0.3)
        self.assertEqual(http.payloads[0]["top_p"], 0.9)

    def test_stop_is_recorded(self):
        http = HTTPStub(response({"role": "assistant", "content": "done"},
                                 "stop"))
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("urllib.request.urlopen", http):
            stats = self.make_agent(Path(tmp)).run("task")

        self.assertEqual(stats["termination_reason"], "stop")
        self.assertIsNone(stats["tokens_reasoning"])
        self.assertEqual(http.payloads[0]["temperature"], 0.2)
        self.assertEqual(http.payloads[0]["max_tokens"], 2048)

    def test_exhausted_turns_are_recorded(self):
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call-1",
                "type": "function",
                "function": {"name": "bash", "arguments": '{"command":"true"}'},
            }],
        }
        http = HTTPStub(response(message, "tool_calls"))
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("urllib.request.urlopen", http):
            stats = self.make_agent(Path(tmp), max_turns=1).run("task")

        self.assertEqual(stats["termination_reason"], "max_turns")

    def test_missing_tool_call_id_is_a_protocol_error(self):
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": None,
                "type": "function",
                "function": {"name": "bash", "arguments": '{"command":"true"}'},
            }],
        }
        http = HTTPStub(response(message, "tool_calls"))
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("urllib.request.urlopen", http):
            agent = self.make_agent(Path(tmp))
            stats = agent.run("task")

        self.assertEqual(stats["termination_reason"], "protocol_error")
        self.assertEqual(len(agent.transcript), 1)

    def test_agent_exception_still_restores_accepts_and_writes_json(self):
        class FailingAgent:
            def __init__(self, endpoint, model, workspace, **kwargs):
                self.workspace = workspace
                self.transcript = [{"role": "assistant", "content": "x" * 500_000}]
                self.turns = 1
                self.tokens_prompt = 2
                self.tokens_completion = 3
                self.tokens_reasoning = None

            def run(self, prompt):
                (self.workspace / "guard.txt").write_text("tampered", encoding="utf-8")
                raise RuntimeError("server timeout")

        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "infra"
            fixture = task_dir / "fixture"
            fixture.mkdir(parents=True)
            (fixture / "guard.txt").write_text("pristine", encoding="utf-8")
            (task_dir / "task.yaml").write_text(
                "prompt: task\n"
                "acceptance: test \"$(cat guard.txt)\" = pristine && touch acceptance-attempted\n"
                "protected: guard.txt\n",
                encoding="utf-8",
            )
            provenance = {"server": "local", "quantization": "opaque"}
            request_options = {"extra_body": {"chat_template_kwargs": {"thinking": True}}}
            with mock.patch("harness.run.Agent", FailingAgent):
                result = run_task(task_dir, "http://example.invalid", "test-model",
                                  request_options=request_options,
                                  provenance=provenance)

            workspace = Path(result["workspace"])
            self.assertTrue(result["passed"])
            self.assertEqual(result["infra_status"], "error")
            self.assertIn("server timeout", result["infra_error"])
            self.assertEqual(result["termination_reason"], "infra_error")
            self.assertTrue((workspace / "acceptance-attempted").exists())
            self.assertEqual((workspace / "guard.txt").read_text(), "pristine")
            transcript = json.loads(
                (workspace / "gauntlet-transcript.json").read_text(encoding="utf-8")
            )
            self.assertIsInstance(transcript, list)
            self.assertLessEqual(
                len((workspace / "gauntlet-transcript.json").read_text(encoding="utf-8")),
                400_000,
            )
            self.assertEqual(result["request_options"], request_options)
            self.assertEqual(result["provenance"], provenance)

    def test_acceptance_timeout_becomes_a_result(self):
        class StoppingAgent:
            def __init__(self, endpoint, model, workspace, **kwargs):
                self.transcript = []

            def run(self, prompt):
                return {
                    "turns": 1, "seconds": 0.0, "tokens_prompt": 2,
                    "tokens_completion": 1, "tokens_reasoning": None,
                    "termination_reason": "stop",
                }

        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "timeout"
            (task_dir / "fixture").mkdir(parents=True)
            (task_dir / "task.yaml").write_text(
                "prompt: task\nacceptance: slow-command\n", encoding="utf-8")
            timeout = subprocess.TimeoutExpired("slow-command", 300)
            with mock.patch("harness.run.Agent", StoppingAgent), \
                    mock.patch("harness.run.subprocess.run", side_effect=timeout):
                result = run_task(task_dir, "http://example.invalid", "test-model")

        self.assertFalse(result["passed"])
        self.assertEqual(result["acceptance_status"], "timeout")


if __name__ == "__main__":
    unittest.main()
