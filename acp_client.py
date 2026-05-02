#!/usr/bin/env python3
"""
Headless ACP client for zsh-acp plugin.
Pure Python standard library — no external dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "zsh-acp"
CONFIG_FILE = CONFIG_DIR / "config.json"
SESSIONS_FILE = CONFIG_DIR / "sessions.json"

DEFAULT_CONFIG = {
    "default_agent": "kimi",
    "default_permissions": "approve_reads",
    "agents": {
        "kimi": {
            "command": "kimi",
            "args": ["acp"],
            "env": {},
        },
        "claude": {
            "command": "npx",
            "args": ["-y", "@agentclientprotocol/claude-agent-acp"],
            "env": {},
        },
        "codex": {
            "command": "npx",
            "args": ["-y", "@zed-industries/codex-acp"],
            "env": {},
        },
        "gemini": {
            "command": "gemini",
            "args": ["--acp"],
            "env": {},
        },
        "copilot": {
            "command": "copilot",
            "args": ["--acp", "--stdio"],
            "env": {},
        },
        "opencode": {
            "command": "npx",
            "args": ["-y", "opencode-ai", "acp"],
            "env": {},
        },
        "qwen": {
            "command": "qwen",
            "args": ["--acp"],
            "env": {},
        },
    },
}


class ACPClient:
    def __init__(
        self,
        agent_cmd: str,
        agent_args: list[str],
        agent_env: dict[str, str],
        permissions: str,
    ) -> None:
        self.agent_cmd = agent_cmd
        self.agent_args = agent_args
        self.agent_env = agent_env
        self.permissions = permissions

        self.proc: subprocess.Popen | None = None
        self._req_id = 0
        self._responses: dict[int | str, dict] = {}
        self._queue: queue.Queue[str] = queue.Queue()
        self._reader: threading.Thread | None = None
        self.session_id: str | None = None
        self.capabilities: dict = {}

    def start(self) -> None:
        env = os.environ.copy()
        env.update(self.agent_env)
        self.proc = subprocess.Popen(
            [self.agent_cmd] + self.agent_args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=env,
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        assert self.proc is not None
        assert self.proc.stdout is not None
        while self.proc.poll() is None:
            try:
                line = self.proc.stdout.readline()
                if not line:
                    break
                self._queue.put(line.rstrip("\n"))
            except Exception:
                break

    def _send(self, msg: dict) -> None:
        assert self.proc is not None
        assert self.proc.stdin is not None
        data = json.dumps(msg, ensure_ascii=False) + "\n"
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def request(self, method: str, params: dict) -> int | str:
        self._req_id += 1
        req_id = self._req_id
        msg = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        self._send(msg)
        return req_id

    def handle_one(self) -> bool:
        try:
            line = self._queue.get(timeout=0.1)
        except queue.Empty:
            return False

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            return True

        msg_id = msg.get("id")
        method = msg.get("method")

        # Agent -> Client request (has both method and id)
        if method is not None and msg_id is not None:
            if method == "session/request_permission":
                self._on_permission(msg)
            return True

        # Response to our request (has id, no method)
        if msg_id is not None:
            self._responses[msg_id] = msg
            return True

        # Notification (has method, no id)
        if method == "session/update":
            self._on_update(msg.get("params", {}))
        return True

    def _on_update(self, params: dict) -> None:
        update = params.get("update", {})

        if "agentMessageChunk" in update:
            text = update["agentMessageChunk"].get("text", "")
            if text:
                print(text, end="", flush=True)

        elif "agentThoughtChunk" in update:
            # Skip thoughts in headless mode to reduce noise
            pass

        elif "toolCall" in update:
            tc = update["toolCall"]
            name = tc.get("name", "?")
            print(f"\n[Tool: {name}]", end="", flush=True)

        elif "toolCallUpdate" in update:
            tcu = update["toolCallUpdate"]
            status = tcu.get("status", "")
            if status == "completed":
                print(" ✓", flush=True)
            elif status == "failed":
                print(" ✗", flush=True)
            elif status == "pending":
                print(" ...", end="", flush=True)

        elif "plan" in update:
            plan = update["plan"]
            entries = plan.get("entries", [])
            if entries:
                print(f"\n[Plan: {len(entries)} tasks]", flush=True)

    def _on_permission(self, msg: dict) -> None:
        params = msg.get("params", {})
        msg_id = msg["id"]
        options = params.get("options", [])
        tool_call = params.get("toolCall", {})
        tool_name = tool_call.get("name", "?")

        choice: str | None = None

        if self.permissions == "approve_all":
            for opt in options:
                if opt.get("kind") in ("allow_once", "allow"):
                    choice = opt["id"]
                    break
        elif self.permissions == "deny_all":
            for opt in options:
                if opt.get("kind") in ("deny_once", "deny"):
                    choice = opt["id"]
                    break
        else:  # approve_reads
            # Heuristic: common read-only tool names
            read_names = {"read_file", "view", "read", "cat", "ls", "grep", "find", "head", "tail"}
            is_read = tool_name in read_names or "read" in tool_name.lower()
            if is_read:
                for opt in options:
                    if opt.get("kind") in ("allow_once", "allow"):
                        choice = opt["id"]
                        break
            else:
                # For write ops we still approve to avoid hanging in headless mode,
                # but only once.
                for opt in options:
                    if opt.get("kind") in ("allow_once", "allow"):
                        choice = opt["id"]
                        break

        if choice is None and options:
            choice = options[0]["id"]

        self._send({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "outcome": {
                    "outcome": "selected",
                    "optionId": choice,
                }
            },
        })

    def wait_for(self, req_id: int | str, timeout: float = 120) -> dict | None:
        start = time.time()
        while time.time() - start < timeout:
            if req_id in self._responses:
                return self._responses.pop(req_id)
            self.handle_one()
            time.sleep(0.05)
        return None

    def initialize(self) -> list[dict] | None:
        req_id = self.request(
            "initialize",
            {
                "protocolVersion": 1,
                "capabilities": {
                    "fs": {"readTextFile": True, "writeTextFile": False},
                    "terminal": True,
                },
                "clientInfo": {"name": "zsh-acp", "version": "0.1.0"},
            },
        )
        resp = self.wait_for(req_id, timeout=30)
        if resp is None:
            return None
        if "error" in resp:
            err = resp["error"]
            print(f"initialize error: {err.get('message', err)}", file=sys.stderr)
            return None
        result = resp.get("result", {})
        self.capabilities = result.get("capabilities", {})
        return result.get("authenticationMethods", [])

    def authenticate(self, method_id: str) -> bool:
        req_id = self.request("authenticate", {"methodId": method_id})
        resp = self.wait_for(req_id, timeout=30)
        return resp is not None and "result" in resp

    def new_session(self, cwd: str) -> bool:
        req_id = self.request(
            "session/new",
            {
                "cwd": cwd,
                "mcpServers": [],
            },
        )
        resp = self.wait_for(req_id, timeout=30)
        if resp is None or "error" in resp:
            if resp and "error" in resp:
                err = resp["error"]
                print(f"session/new error: {err.get('message', err)}", file=sys.stderr)
            return False
        self.session_id = resp["result"].get("sessionId")
        return self.session_id is not None

    def load_session(self, cwd: str, session_id: str) -> bool:
        req_id = self.request(
            "session/load",
            {
                "sessionId": session_id,
                "cwd": cwd,
                "mcpServers": [],
            },
        )
        resp = self.wait_for(req_id, timeout=30)
        if resp is None or "error" in resp:
            return False
        self.session_id = resp["result"].get("sessionId", session_id)
        return True

    def prompt(self, text: str) -> int | str:
        return self.request(
            "session/prompt",
            {
                "sessionId": self.session_id,
                "prompt": [{"type": "text", "text": text}],
            },
        )

    def run(self, text: str, timeout: float = 300) -> None:
        req_id = self.prompt(text)
        resp = self.wait_for(req_id, timeout=timeout)
        if resp is None:
            print("\n[Timeout]", flush=True)
        elif "error" in resp:
            err = resp["error"]
            print(f"\n[Error: {err.get('message', 'unknown')}]", flush=True)
        else:
            stop_reason = resp["result"].get("stopReason", "unknown")
            if stop_reason != "end_turn":
                print(f"\n[Done: {stop_reason}]", flush=True)

    def shutdown(self) -> None:
        if self.proc is None:
            return
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        return DEFAULT_CONFIG.copy()
    with open(CONFIG_FILE) as f:
        return json.load(f)


def load_sessions() -> dict:
    if not SESSIONS_FILE.exists():
        return {}
    with open(SESSIONS_FILE) as f:
        return json.load(f)


def save_sessions(sessions: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(SESSIONS_FILE, "w") as f:
        json.dump(sessions, f, indent=2)


def session_key(agent: str, cwd: str, name: str) -> str:
    return f"{agent}:{cwd}:{name}"


def interactive_init() -> None:
    agents = list(DEFAULT_CONFIG["agents"].keys())
    print("No ACP configuration found.")
    print("Please select your default agent:\n")
    for i, name in enumerate(agents, 1):
        info = DEFAULT_CONFIG["agents"][name]
        cmd = " ".join([info["command"]] + info["args"])
        print(f"  {i}. {name:12s}  ({cmd})")
    print()

    selected = None
    while selected is None:
        try:
            choice = input("Enter number: ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(agents):
                selected = agents[idx]
            else:
                print("Invalid choice, try again.")
        except (ValueError, EOFError):
            print("Invalid choice, try again.")

    config = DEFAULT_CONFIG.copy()
    config["default_agent"] = selected
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

    print(f"\nConfiguration saved to {CONFIG_FILE}")
    print(f"Default agent set to: {selected}")
    print("You can edit this file to add custom agents or change commands.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Headless ACP client for zsh")
    parser.add_argument("--init", action="store_true", help="Interactive first-time setup")
    parser.add_argument("--agent", default="", help="Agent name from config")
    parser.add_argument("--session", default="zsh-session", help="Session name")
    parser.add_argument("--cwd", default=os.getcwd(), help="Working directory")
    parser.add_argument(
        "--permissions",
        default="approve_reads",
        choices=["approve_reads", "approve_all", "deny_all"],
        help="Permission policy",
    )
    parser.add_argument("prompt", nargs="*", help="Prompt text")
    args = parser.parse_args()

    if args.init:
        interactive_init()
        return

    if not args.agent:
        print("--agent is required", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    agents = config.get("agents", {})

    if args.agent not in agents:
        print(f"Unknown agent: {args.agent}", file=sys.stderr)
        print(f"Available: {', '.join(agents.keys())}", file=sys.stderr)
        sys.exit(1)

    agent_cfg = agents[args.agent]
    cmd = agent_cfg.get("command", args.agent)
    agent_args = agent_cfg.get("args", [])
    agent_env = agent_cfg.get("env", {})

    text = " ".join(args.prompt)
    if not text:
        print("Empty prompt", file=sys.stderr)
        sys.exit(1)

    client = ACPClient(cmd, agent_args, agent_env, args.permissions)
    client.start()

    # Initialize
    auth_methods = client.initialize()
    if auth_methods is None:
        print("Failed to initialize ACP agent", file=sys.stderr)
        sys.exit(1)

    # Authenticate if required
    if auth_methods:
        if not client.authenticate(auth_methods[0]["id"]):
            print("Authentication failed", file=sys.stderr)
            sys.exit(1)

    # Session management
    sessions = load_sessions()
    key = session_key(args.agent, args.cwd, args.session)
    can_load = client.capabilities.get("loadSession", False)

    loaded = False
    if key in sessions and can_load:
        loaded = client.load_session(args.cwd, sessions[key])

    if not loaded:
        if not client.new_session(args.cwd):
            print("Failed to create session", file=sys.stderr)
            sys.exit(1)
        sessions[key] = client.session_id
        save_sessions(sessions)

    # Run prompt
    try:
        client.run(text)
    finally:
        client.shutdown()


if __name__ == "__main__":
    main()
