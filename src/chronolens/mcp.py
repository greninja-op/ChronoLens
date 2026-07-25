"""MCP — talk to the SigNoz MCP server for real, over JSON-RPC.

Foundry installs the SigNoz **MCP server** alongside SigNoz itself, and the
hackathon scores MCP usage explicitly. Being "MCP-compatible" (issuing queries
that *look* like the ones MCP would run) is not the same as using MCP, so this
module is a genuine client: it performs the `initialize` handshake, lists the
server's tools, and invokes them with `tools/call`.

Protocol notes discovered against the running server (`SigNozMCP`, protocol
`2024-11-05`):

* Transport is **Streamable HTTP** at ``/mcp`` — a plain JSON-RPC ``POST`` per
  message. The ``Accept`` header must allow *both* ``application/json`` and
  ``text/event-stream``, or the server refuses the request.
* Auth is required: without an ``SIGNOZ-API-KEY`` header the endpoint answers
  ``401 Authorization or SIGNOZ-API-KEY header required``.
* A response may come back as an SSE frame (``data: {...}``) rather than a bare
  JSON body, so the parser handles both.
* Tool results arrive as ``result.content[] {type:"text", text:"<json>"}`` — the
  payload is JSON *inside* a text block, so it needs a second decode.

Everything fails soft: MCP is an enrichment path, never a dependency of the
control loop.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import Config

PROTOCOL_VERSION = "2024-11-05"


class MCPError(RuntimeError):
    """An MCP call failed (transport, protocol, or tool-level)."""


@dataclass
class MCPResult:
    tool: str
    ok: bool
    data: Any = None            # decoded payload (dict/list) when the tool returns JSON
    text: str = ""              # raw text block, for non-JSON tools (e.g. docs)
    error: str = ""
    arguments: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"tool": self.tool, "ok": self.ok, "arguments": self.arguments,
                "data": self.data, "text": self.text[:2000], "error": self.error}


def _parse_rpc(resp: httpx.Response) -> dict[str, Any]:
    """Decode a JSON-RPC reply that may arrive as JSON or as an SSE frame."""
    body = resp.text or ""
    ctype = resp.headers.get("content-type", "")
    if "text/event-stream" in ctype or body.lstrip().startswith(("event:", "data:")):
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                chunk = line[5:].strip()
                if chunk and chunk != "[DONE]":
                    try:
                        return json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
        raise MCPError("could not decode an SSE frame from the MCP server")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise MCPError(f"invalid JSON from MCP server: {body[:200]}") from exc


class MCPClient:
    """A minimal, dependency-free MCP client for the SigNoz MCP server."""

    def __init__(self, cfg: Config | None = None, timeout: float = 45.0):
        self.cfg = cfg or Config.load()
        self.url = self.cfg.signoz_mcp_url
        self._id = 0
        self._ready = False
        self.server_info: dict[str, Any] = {}
        self._client = httpx.Client(timeout=timeout, headers={
            "Content-Type": "application/json",
            # BOTH content types are required by the Streamable-HTTP transport.
            "Accept": "application/json, text/event-stream",
            "SIGNOZ-API-KEY": self.cfg.signoz_api_key,
        })

    # -- plumbing ---------------------------------------------------------
    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _rpc(self, method: str, params: dict | None = None,
             *, notify: bool = False) -> dict[str, Any]:
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if not notify:
            msg["id"] = self._next_id()
        if params is not None:
            msg["params"] = params
        try:
            resp = self._client.post(self.url, json=msg)
        except Exception as exc:
            raise MCPError(f"MCP transport error on {method}: {exc}") from exc
        if resp.status_code >= 400:
            raise MCPError(f"MCP {method} -> HTTP {resp.status_code}: {resp.text[:160]}")
        if notify:
            return {}
        payload = _parse_rpc(resp)
        if "error" in payload:
            err = payload["error"]
            raise MCPError(f"MCP {method} error: {err.get('message', err)}")
        return payload.get("result", {}) or {}

    def connect(self) -> dict[str, Any]:
        """Run the MCP handshake. Idempotent."""
        if self._ready:
            return self.server_info
        result = self._rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "chronolens", "version": "1.0"},
        })
        self.server_info = result.get("serverInfo", {}) or {}
        # the spec requires this notification before normal operation
        try:
            self._rpc("notifications/initialized", notify=True)
        except MCPError:
            pass
        self._ready = True
        return self.server_info

    # -- api --------------------------------------------------------------
    def list_tools(self) -> list[dict[str, Any]]:
        """Every tool the SigNoz MCP server advertises."""
        self.connect()
        return list(self._rpc("tools/list", {}).get("tools") or [])

    def tool_names(self) -> list[str]:
        return [t.get("name", "") for t in self.list_tools() if t.get("name")]

    def call(self, tool: str, arguments: dict | None = None) -> MCPResult:
        """Invoke one MCP tool. Never raises — failures come back on the result."""
        args = arguments or {}
        try:
            self.connect()
            result = self._rpc("tools/call", {"name": tool, "arguments": args})
        except MCPError as exc:
            return MCPResult(tool=tool, ok=False, error=str(exc), arguments=args)

        if result.get("isError"):
            return MCPResult(tool=tool, ok=False, arguments=args,
                             error=_first_text(result) or "tool reported an error")
        text = _first_text(result)
        data: Any = None
        if text:
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = None          # non-JSON tool (docs search, prose answers)
        return MCPResult(tool=tool, ok=True, data=data, text=text, arguments=args)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "MCPClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _first_text(result: dict[str, Any]) -> str:
    """Pull the text block out of an MCP tool result."""
    for item in result.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            return str(item.get("text") or "")
    return ""


def mcp_status(cfg: Config | None = None) -> dict[str, Any]:
    """Health + capability snapshot of the MCP server, for the UI. Fails soft."""
    cfg = cfg or Config.load()
    try:
        with MCPClient(cfg) as mcp:
            info = mcp.connect()
            names = mcp.tool_names()
        return {"connected": True, "url": cfg.signoz_mcp_url,
                "server": info.get("name", "unknown"),
                "version": info.get("version", ""),
                "protocol": PROTOCOL_VERSION,
                "tool_count": len(names), "tools": names}
    except Exception as exc:
        return {"connected": False, "url": cfg.signoz_mcp_url, "error": str(exc),
                "tool_count": 0, "tools": []}
