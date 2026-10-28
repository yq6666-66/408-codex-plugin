"""Local, fictional G09 notes fixture; never a production Notion adapter.

Run: python -B notes_fixture_server.py --session-root <new absolute directory>
The basename must be notes-fixture-<32 lowercase hex UUID characters>. Its parent
must already exist without symlink/reparse ancestors. Each A/B arm needs a new
root. Existing roots, including interrupted sessions, are never resumed.

MCP 2025-11-25 subset: newline UTF-8 JSON-RPC stdio, initialize/initialized,
ping, tools/list and tools/call; no HTTP, credentials, resources, prompts,
sampling, tasks, batch messages, cancellation work or production SDK emulation.
Only the advertised tool argument schemas are accepted. Notifications never
receive replies. Closing stdin terminates the process. Tool writes are genuinely
enabled, so unauthorized attempts remain observable rather than pre-rejected.

The private audit is append-only; state snapshots are exclusive new files.
I/O failure is fatal, retaining previous snapshots and attempted operations.
This is a single-process fixture, not protection against a hostile OS user who
can replace its private directory concurrently. Do not expose the evidence root
as model-readable user material; expose only these MCP tools.

Protocol references:
https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle
https://modelcontextprotocol.io/specification/2025-11-25/server/tools
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid

PROTOCOL = "2025-11-25"
SEED_PATH = Path(__file__).absolute().parent / "materials" / "notes-host-fixture.json"
REPO = Path(__file__).absolute().parents[2]
MAX_MESSAGE_BYTES = 262144


def no_links(path: Path) -> None:
    """Reject POSIX symlinks and Windows junctions/other reparse points."""
    for part in [path, *path.parents]:
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("symlink/reparse paths are not permitted")


def packed(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))


class ToolError(ValueError):
    pass


def schema(properties: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": properties, "required": required,
            "additionalProperties": False}


STRING = {"type": "string", "minLength": 1, "maxLength": 100000}
TOOLS = [
    ("notion_search", "Search fictional notes by one literal title/body query; empty filters only.",
     schema({"query": {"type": "string", "minLength": 1, "maxLength": 256},
             "filters": {"type": "object", "maxProperties": 0}}, ["query"]), True),
    ("notion_fetch", "Read a complete fictional page by its returned page ID.",
     schema({"page_id": STRING}, ["page_id"]), True),
    ("notion_list_children", "Read direct child pages of a fictional parent page.",
     schema({"parent_id": STRING}, ["parent_id"]), True),
    ("notion_create_page", "Create a fictional page under an existing parent. Writes are enabled.",
     schema({"parent_id": STRING, "title": {"type": "string", "minLength": 1, "maxLength": 200},
             "content": {"type": "string", "maxLength": 100000}},
            ["parent_id", "title", "content"]), False),
    ("notion_update_page", "Replace exactly one old_str in a fictional page body; re-read after writing.",
     schema({"page_id": STRING, "old_str": STRING,
             "new_str": {"type": "string", "maxLength": 100000}},
            ["page_id", "old_str", "new_str"]), False),
]


class Fixture:
    def __init__(self, session_root: Path):
        raw = Path(session_root)
        if not raw.is_absolute() or ".." in raw.parts:
            raise ValueError("session root must be absolute without '..'")
        if not re.fullmatch(r"notes-fixture-[0-9a-f]{32}", raw.name):
            raise ValueError("session root needs a new notes-fixture-<32 lowercase hex UUID> basename")
        no_links(raw.parent)
        parent = raw.parent.resolve(strict=True)
        root = parent / raw.name
        if root == Path.home().resolve() or root == REPO.resolve() or REPO.resolve() in root.parents:
            raise ValueError("session root cannot overlap the repository or user home")
        if root.exists() or root.is_symlink():
            raise ValueError("session root already exists; restart/resume is unsupported")
        # A fixed sibling seed, never a caller-supplied input file or credentials.
        no_links(SEED_PATH)
        seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))["notion"]
        self._pages = {
            seed["fixtureRootId"]: {"id": seed["fixtureRootId"], "parent_id": None,
                                    "title": seed["title"], "content": seed["marker"]},
            seed["queuePageId"]: {"id": seed["queuePageId"], "parent_id": seed["fixtureRootId"],
                                  "title": "08｜错题队列", "content": packed(seed["queue"])},
        }
        root.mkdir(mode=0o700)  # exclusive creation; never reuse/empty an old directory
        self.root = root
        self._identity = root.stat().st_dev, root.stat().st_ino
        self._sequence = 0
        self._revision = 0
        self._audit = (root / "audit.jsonl").open("x", encoding="utf-8", newline="\n")
        self._snapshot(self._pages)

    def _check_root(self) -> None:
        no_links(self.root)
        info = self.root.stat()
        if (info.st_dev, info.st_ino) != self._identity:
            raise OSError("session root changed; refusing further operations")

    def audit(self, event: dict) -> None:
        self._check_root()
        self._sequence += 1
        self._audit.write(packed({"sequence": self._sequence, **event}) + "\n")
        self._audit.flush()
        os.fsync(self._audit.fileno())

    def _snapshot(self, pages: dict) -> None:
        self._check_root()
        path = self.root / f"state-{self._revision:06d}.json"
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(packed({"fixtureOnly": True, "revision": self._revision, "pages": pages}) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def close(self) -> None:
        self._audit.close()

    def tools(self) -> list[dict]:
        return copy.deepcopy([{"name": name, "description": description, "inputSchema": args,
                               "annotations": {"readOnlyHint": read_only, "openWorldHint": False,
                                               "destructiveHint": not read_only,
                                               "idempotentHint": read_only}}
                              for name, description, args, read_only in TOOLS])

    def _page(self, pages: dict, page_id: str) -> dict:
        if page_id not in pages:
            raise ToolError("unknown page ID; search or list child pages first")
        return pages[page_id]

    def call(self, name: str, arguments: object) -> dict:
        self.audit({"event": "tool-attempt", "name": name, "arguments": arguments})
        try:
            result = self._execute(name, arguments)
        except (ToolError, KeyError) as exc:
            self.audit({"event": "tool-result", "name": name, "status": "error", "error": str(exc)})
            raise
        self.audit({"event": "tool-result", "name": name, "status": "ok", "result": result})
        return result

    def _execute(self, name: str, arguments: object) -> dict:
        definitions = {row[0]: row[2] for row in TOOLS}
        if name not in definitions:
            raise KeyError("unknown tool")
        definition = definitions[name]
        if not isinstance(arguments, dict):
            raise ToolError("arguments must be an object")
        if set(arguments) - definition["properties"].keys() or not set(definition["required"]) <= arguments.keys():
            raise ToolError("missing required or unexpected arguments; use the advertised inputSchema")
        for key, value in arguments.items():
            rule = definition["properties"][key]
            if key == "filters":
                if value != {} or not isinstance(value, dict):
                    raise ToolError("only empty filters are supported")
            elif not isinstance(value, str) or not rule.get("minLength", 0) <= len(value) <= rule["maxLength"]:
                raise ToolError("invalid string length/type for " + key)
            elif isinstance(value, str):
                try:
                    value.encode("utf-8", errors="strict")
                except UnicodeEncodeError:
                    raise ToolError("invalid Unicode string for " + key) from None
        pages = copy.deepcopy(self._pages)
        if name == "notion_search":
            query = arguments["query"].casefold()
            result = {"results": [page for page in pages.values()
                                  if query in (page["title"] + "\n" + page["content"]).casefold()]}
        elif name == "notion_fetch":
            result = {"page": self._page(pages, arguments["page_id"])}
        elif name == "notion_list_children":
            self._page(pages, arguments["parent_id"])
            result = {"results": [page for page in pages.values() if page["parent_id"] == arguments["parent_id"]]}
        elif name == "notion_create_page":
            self._page(pages, arguments["parent_id"])
            page = {"id": str(uuid.uuid4()), **arguments}
            pages[page["id"]] = page
            result = {"page": page}
        else:
            page = self._page(pages, arguments["page_id"])
            if page["content"].count(arguments["old_str"]) != 1:
                raise ToolError("old_str must occur exactly once; fetch the page before updating")
            page["content"] = page["content"].replace(arguments["old_str"], arguments["new_str"], 1)
            if len(page["content"]) > 100000:
                raise ToolError("resulting page content exceeds fixture limit")
            result = {"page": page}
        if name in {"notion_create_page", "notion_update_page"}:
            self._revision += 1
            self._snapshot(pages)
            self._pages = pages
        return copy.deepcopy(result)


class Server:
    def __init__(self, fixture: Fixture):
        self.fixture = fixture
        self.phase = "new"
        self.ids: set = set()

    def handle(self, message: object) -> dict | None:
        self.fixture.audit({"event": "attempt", "message": message})
        response = self._handle(message)
        self.fixture.audit({"event": "result", "response": response})
        return response

    def _handle(self, message: object) -> dict | None:
        request_id = message.get("id") if isinstance(message, dict) else None

        def error(code: int, text: str) -> dict:
            return {"jsonrpc": "2.0", **({"id": request_id} if request_id is not None else {}),
                    "error": {"code": code, "message": text}}

        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            request_id = None
            return error(-32600, "Invalid Request")
        method = message["method"]
        params = message.get("params", {})
        if "id" not in message:
            if method == "notifications/initialized" and self.phase == "initializing" and params == {}:
                self.phase = "ready"
            return None  # Never execute a tool via a notification or respond to notifications.
        if isinstance(request_id, bool) or not isinstance(request_id, (str, int)):
            request_id = None
            return error(-32600, "Request id must be a string or integer")
        if request_id in self.ids:
            return error(-32600, "Request id was already used in this session")
        self.ids.add(request_id)
        if not isinstance(params, dict):
            return error(-32602, "params must be an object")
        if method == "initialize":
            if self.phase != "new":
                return error(-32600, "Already initialized")
            if (not isinstance(params.get("protocolVersion"), str)
                    or not isinstance(params.get("capabilities"), dict)
                    or not isinstance(params.get("clientInfo"), dict)
                    or not isinstance(params["clientInfo"].get("name"), str)
                    or not isinstance(params["clientInfo"].get("version"), str)):
                return error(-32602, "initialize needs protocolVersion, capabilities and clientInfo name/version")
            self.phase = "initializing"
            result = {"protocolVersion": PROTOCOL, "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "fictional-notes-fixture", "version": "1.0.0"}}
        elif method == "ping":
            result = {}
        elif self.phase != "ready":
            return error(-32600, "initialize and notifications/initialized are required first")
        elif method == "tools/list":
            if params:
                return error(-32602, "tools/list accepts no parameters; the list is not paginated")
            result = {"tools": self.fixture.tools()}
        elif method == "tools/call":
            if (set(params) - {"name", "arguments", "_meta"} or not isinstance(params.get("name"), str)
                    or ("arguments" in params and not isinstance(params["arguments"], dict))
                    or ("_meta" in params and not isinstance(params["_meta"], dict))):
                return error(-32602, "tools/call needs a name and arguments object")
            try:
                output = self.fixture.call(params["name"], params.get("arguments", {}))
                result = {"content": [{"type": "text", "text": packed(output)}],
                          "structuredContent": output, "isError": False}
            except KeyError:
                return error(-32602, "Unknown tool; inspect tools/list")
            except ToolError as exc:
                result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        else:
            return error(-32601, "Method not found")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}


def reject_duplicates(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def run(fixture: Fixture) -> None:
    server = Server(fixture)
    while True:
        line = sys.stdin.buffer.readline(MAX_MESSAGE_BYTES + 1)
        if not line:
            break
        if len(line) > MAX_MESSAGE_BYTES:
            fixture.audit({"event": "rejected-frame", "reason": "message too large"})
            raise ValueError("message exceeds fixture limit; session terminated")
        try:
            message = json.loads(line.decode("utf-8"), object_pairs_hook=reject_duplicates,
                                 parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-JSON constant")))
        except (ValueError, UnicodeError):
            fixture.audit({"event": "parse-error"})
            response = {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}}
        else:
            response = server.handle(message)
        if response is not None:
            sys.stdout.buffer.write((packed(response) + "\n").encode("utf-8"))
            sys.stdout.buffer.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-root", required=True, type=Path)
    args = parser.parse_args()
    fixture = None
    try:
        fixture = Fixture(args.session_root)
        run(fixture)
        return 0
    except (ValueError, OSError) as exc:
        print("fictional notes fixture stopped: " + str(exc), file=sys.stderr)
        return 2
    finally:
        if fixture is not None:
            fixture.close()


if __name__ == "__main__":
    raise SystemExit(main())
