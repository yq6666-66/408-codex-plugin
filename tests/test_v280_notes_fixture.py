from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
import uuid

REPO = Path(__file__).resolve().parents[1]
SERVER_PATH = REPO / "eval" / "v2.8-acceptance" / "notes_fixture_server.py"
spec = importlib.util.spec_from_file_location("v280_notes_fixture", SERVER_PATH)
fixture_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture_module)
SEED_PATH = SERVER_PATH.parent / "materials" / "notes-host-fixture.json"
ROOT_ID = "11111111-1111-4111-8111-111111111111"
QUEUE_ID = "22222222-2222-4222-8222-222222222222"


class StdioClient:
    def __init__(self, root):
        self.root = root
        self.proc = subprocess.Popen([sys.executable, "-B", str(SERVER_PATH), "--session-root", str(root)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.lines = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self.number = 0

    def _read(self):
        for line in self.proc.stdout:
            self.lines.put(line)

    def send(self, message):
        self.proc.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def request(self, method, params=None):
        self.number += 1
        self.send({"jsonrpc": "2.0", "id": self.number, "method": method,
                   **({"params": params} if params is not None else {})})
        response = json.loads(self.lines.get(timeout=10))
        if response["id"] != self.number:
            raise AssertionError("unexpected response to a notification or wrong request id")
        return response

    def initialize(self, version="2025-11-25"):
        result = self.request("initialize", {"protocolVersion": version, "capabilities": {},
                                            "clientInfo": {"name": "fixture-tests", "version": "1"}})
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return result

    def tool(self, name, arguments):
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self):
        if hasattr(self, "closed_result"):
            return self.closed_result
        if self.proc.stdin and not self.proc.stdin.closed:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=10)
            raise AssertionError("fixture did not exit when stdin closed")
        self.reader.join(timeout=5)
        error = self.proc.stderr.read().decode("utf-8")
        self.proc.stdout.close()
        self.proc.stderr.close()
        self.closed_result = self.proc.returncode, error
        return self.closed_result


class NotesFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="408-notes-fixture-tests-")
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name).resolve()

    def new_root(self):
        return self.parent / ("notes-fixture-" + uuid.uuid4().hex)

    def client(self):
        client = StdioClient(self.new_root())
        self.addCleanup(client.close)
        return client

    def audit(self, root):
        return [json.loads(line) for line in (root / "audit.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_stdio_initialize_discover_read_and_clean_disconnect(self):
        original = SEED_PATH.read_bytes()
        client = self.client()
        initialization = client.initialize()
        self.assertEqual(initialization["result"]["protocolVersion"], "2025-11-25")
        self.assertEqual(set(initialization["result"]["capabilities"]), {"tools"})
        tools = client.request("tools/list")["result"]["tools"]
        self.assertEqual(len(tools), 5)
        self.assertEqual(sum(t["annotations"]["readOnlyHint"] for t in tools), 3)
        search = client.tool("notion_search", {"query": "kaoyan-408-brain:1.0", "filters": {}})
        self.assertEqual([p["id"] for p in search["result"]["structuredContent"]["results"]], [ROOT_ID])
        children = client.tool("notion_list_children", {"parent_id": ROOT_ID})
        self.assertEqual(children["result"]["structuredContent"]["results"][0]["id"], QUEUE_ID)
        read = client.tool("notion_fetch", {"page_id": QUEUE_ID})["result"]
        self.assertEqual(json.loads(read["content"][0]["text"]), read["structuredContent"])
        queue_record = json.loads(read["structuredContent"]["page"]["content"])
        self.assertEqual(queue_record["recordType"], "ReviewQueue")
        self.assertEqual(len(queue_record["items"]), 2)
        self.assertEqual(client.close(), (0, ""))
        self.assertEqual(SEED_PATH.read_bytes(), original)
        self.assertEqual(len(list(client.root.glob("state-*.json"))), 1)

    def test_real_writes_are_persisted_and_success_and_failure_audited(self):
        client = self.client()
        client.initialize()
        created = client.tool("notion_create_page", {"parent_id": ROOT_ID, "title": "虚构学习记录",
                                                     "content": "观察甲；保留批注"})["result"]["structuredContent"]["page"]
        updated = client.tool("notion_update_page", {"page_id": created["id"],
                                                     "old_str": "观察甲", "new_str": "观察乙"})
        self.assertFalse(updated["result"]["isError"])
        read = client.tool("notion_fetch", {"page_id": created["id"]})
        self.assertEqual(read["result"]["structuredContent"]["page"]["content"], "观察乙；保留批注")
        failure = client.tool("notion_update_page", {"page_id": created["id"], "old_str": "不存在", "new_str": "x"})
        self.assertTrue(failure["result"]["isError"])
        failure2 = client.tool("notion_create_page", {"parent_id": "unknown", "title": "x", "content": "x"})
        self.assertTrue(failure2["result"]["isError"])
        client.close()
        snapshots = sorted(client.root.glob("state-*.json"))
        self.assertEqual(len(snapshots), 3)
        self.assertNotIn(created["id"], json.loads(snapshots[0].read_text(encoding="utf-8"))["pages"])
        self.assertEqual(json.loads(snapshots[-1].read_text(encoding="utf-8"))["revision"], 2)
        events = self.audit(client.root)
        attempts = [e for e in events if e["event"] == "attempt" and e["message"].get("method") == "tools/call"]
        self.assertEqual(len(attempts), 5)
        self.assertEqual(sum(e["message"]["params"]["name"] in {"notion_create_page", "notion_update_page"}
                             for e in attempts), 4)
        self.assertEqual(sum(e.get("response", {}).get("result", {}).get("isError", False)
                             for e in events if e.get("response") is not None), 2)

    def test_unknown_tool_id_extra_parameters_and_paths_do_not_change_state(self):
        client = self.client()
        client.initialize()
        before = (client.root / "state-000000.json").read_bytes()
        self.assertEqual(client.tool("not_a_tool", {})["error"]["code"], -32602)
        self.assertTrue(client.tool("notion_fetch", {"page_id": "unknown"})["result"]["isError"])
        self.assertTrue(client.tool("notion_fetch", {"page_id": str(SEED_PATH)})["result"]["isError"])
        self.assertTrue(client.tool("notion_update_page", {"page_id": ROOT_ID, "old_str": "a", "new_str": "b",
                                                           "path": "../../outside"})["result"]["isError"])
        self.assertTrue(client.tool("notion_create_page", {"parent_id": ROOT_ID, "title": "x"})["result"]["isError"])
        self.assertTrue(client.tool("notion_search", {"query": "x", "filters": {"owner": "user"}})["result"]["isError"])
        self.assertEqual(client.request("tools/call", {"name": "notion_fetch", "path": "x"})["error"]["code"], -32602)
        self.assertEqual(client.request("tools/call", {"name": "notion_fetch", "arguments": []})["error"]["code"], -32602)
        client.close()
        self.assertEqual((client.root / "state-000000.json").read_bytes(), before)
        self.assertEqual(len(list(client.root.glob("state-*.json"))), 1)
        self.assertEqual(len([e for e in self.audit(client.root) if e["event"] == "attempt"]), 10)

    def test_protocol_errors_notifications_and_version_negotiation(self):
        client = self.client()
        self.assertEqual(client.request("tools/list")["error"]["code"], -32600)
        self.assertEqual(client.initialize("unsupported-future")["result"]["protocolVersion"], "2025-11-25")
        client.send({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 900}})
        client.send({"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "notion_create_page",
                      "arguments": {"parent_id": ROOT_ID, "title": "must not create", "content": "x"}}})
        self.assertEqual(client.request("ping")["result"], {})
        self.assertEqual(client.request("resources/list")["error"]["code"], -32601)
        self.assertEqual(client.request("tools/list", {"cursor": "fake"})["error"]["code"], -32602)
        client.proc.stdin.write(b'not-json\n')
        client.proc.stdin.flush()
        self.assertEqual(json.loads(client.lines.get(timeout=10))["error"]["code"], -32700)
        client.send([{"jsonrpc": "2.0", "id": 10, "method": "ping"}])
        self.assertEqual(json.loads(client.lines.get(timeout=10))["error"]["code"], -32600)
        client.send({"jsonrpc": "2.0", "id": True, "method": "ping"})
        self.assertEqual(json.loads(client.lines.get(timeout=10))["error"]["code"], -32600)
        client.send({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        self.assertEqual(json.loads(client.lines.get(timeout=10))["error"]["code"], -32600)
        self.assertEqual(client.close(), (0, ""))
        self.assertEqual(len(list(client.root.glob("state-*.json"))), 1)

    def test_cross_instance_and_returned_data_isolation(self):
        left = fixture_module.Fixture(self.new_root())
        right = fixture_module.Fixture(self.new_root())
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        page = left.call("notion_fetch", {"page_id": ROOT_ID})
        page["page"]["content"] = "tampered alias"
        tool_definitions = left.tools()
        tool_definitions[0]["inputSchema"]["properties"]["query"]["maxLength"] = 0
        self.assertNotEqual(left.tools(), tool_definitions)
        self.assertEqual(left.call("notion_fetch", {"page_id": ROOT_ID})["page"]["content"], "kaoyan-408-brain:1.0")
        created = left.call("notion_create_page", {"parent_id": ROOT_ID, "title": "only left", "content": "fictional"})
        created["page"]["content"] = "tampered"
        self.assertEqual(left.call("notion_fetch", {"page_id": created["page"]["id"]})["page"]["content"], "fictional")
        self.assertEqual(right.call("notion_search", {"query": "only left"}), {"results": []})

    def test_stdio_invalid_unicode_write_attempts_are_audited_without_state_change(self):
        client = self.client()
        client.initialize()
        before = (client.root / "state-000000.json").read_bytes()
        calls = [
            ("notion_create_page", {"parent_id": ROOT_ID, "title": "\ud800", "content": "fictional"}),
            ("notion_update_page", {"page_id": ROOT_ID, "old_str": "kaoyan", "new_str": "\udfff"}),
        ]
        for name, arguments in calls:
            # JSON escapes can encode isolated surrogates although UTF-8 cannot.
            client.number += 1
            request = {"jsonrpc": "2.0", "id": client.number, "method": "tools/call",
                       "params": {"name": name, "arguments": arguments}}
            client.proc.stdin.write((json.dumps(request, ensure_ascii=True) + "\n").encode("ascii"))
            client.proc.stdin.flush()
            response = json.loads(client.lines.get(timeout=10))
            self.assertEqual(response["id"], client.number)
            self.assertTrue(response["result"]["isError"])
            self.assertIn("invalid Unicode", response["result"]["content"][0]["text"])
        fetched = client.tool("notion_fetch", {"page_id": ROOT_ID})
        self.assertEqual(fetched["result"]["structuredContent"]["page"]["content"], "kaoyan-408-brain:1.0")
        self.assertEqual(client.request("ping")["result"], {})
        self.assertEqual(client.close(), (0, ""))
        self.assertEqual((client.root / "state-000000.json").read_bytes(), before)
        self.assertEqual(len(list(client.root.glob("state-*.json"))), 1)
        events = self.audit(client.root)
        for name, arguments in calls:
            self.assertTrue(any(e["event"] == "tool-attempt" and e["name"] == name
                                and e["arguments"] == arguments for e in events))
            self.assertTrue(any(e["event"] == "tool-result" and e["name"] == name
                                and e["status"] == "error" for e in events))

    def test_existing_output_and_invalid_location_rejected_without_overwriting(self):
        root = self.new_root()
        root.mkdir()
        sentinel = root / "audit.jsonl"
        sentinel.write_text("original sentinel", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "already exists"):
            fixture_module.Fixture(root)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "original sentinel")
        for invalid in (Path("relative"), self.parent / "ordinary-name", self.parent / "missing" / self.new_root().name,
                        REPO / self.new_root().name, Path.home()):
            with self.subTest(invalid=invalid), self.assertRaises((ValueError, FileNotFoundError)):
                fixture_module.Fixture(invalid)

    def test_restart_is_rejected_with_old_evidence_unchanged(self):
        fixture = fixture_module.Fixture(self.new_root())
        fixture.close()
        before = {p.name: p.read_bytes() for p in fixture.root.iterdir()}
        with self.assertRaisesRegex(ValueError, "restart/resume"):
            fixture_module.Fixture(fixture.root)
        self.assertEqual({p.name: p.read_bytes() for p in fixture.root.iterdir()}, before)

    def test_link_output_and_link_ancestor_rejected(self):
        target = self.parent / "target"
        target.mkdir()
        alias = self.parent / "alias"
        try:
            alias.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("OS does not permit creating a test symlink")
        with self.assertRaisesRegex(ValueError, "symlink/reparse"):
            fixture_module.Fixture(alias / self.new_root().name)
        root_alias = self.new_root()
        root_alias.symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError):
            fixture_module.Fixture(root_alias)
        self.assertEqual(list(target.iterdir()), [])

    def test_write_io_failure_preserves_old_state_and_attempt_audit(self):
        fixture = fixture_module.Fixture(self.new_root())
        self.addCleanup(fixture.close)
        server = fixture_module.Server(fixture)
        server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}})
        server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        before = (fixture.root / "state-000000.json").read_bytes()
        with mock.patch.object(fixture, "_snapshot", side_effect=OSError("simulated disk failure")):
            with self.assertRaisesRegex(OSError, "disk failure"):
                server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                    "name": "notion_update_page", "arguments": {"page_id": ROOT_ID,
                    "old_str": "kaoyan", "new_str": "changed"}}})
        self.assertEqual((fixture.root / "state-000000.json").read_bytes(), before)
        self.assertEqual(fixture.call("notion_fetch", {"page_id": ROOT_ID})["page"]["content"], "kaoyan-408-brain:1.0")
        failed_attempts = [e for e in self.audit(fixture.root) if e["event"] == "tool-attempt"
                           and e["name"] == "notion_update_page"]
        self.assertEqual(len(failed_attempts), 1)
        self.assertFalse(any(e["event"] == "tool-result" and e["name"] == "notion_update_page"
                             for e in self.audit(fixture.root)))

    def test_stdio_startup_refusal_has_no_protocol_noise_or_state_changes(self):
        root = self.new_root()
        fixture = fixture_module.Fixture(root)
        fixture.close()
        before = {p.name: p.read_bytes() for p in root.iterdir()}
        result = subprocess.run([sys.executable, "-B", str(SERVER_PATH), "--session-root", str(root)],
                                input=b"", capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"restart/resume", result.stderr)
        self.assertEqual({p.name: p.read_bytes() for p in root.iterdir()}, before)

    def test_json_duplicates_nonfinite_and_oversized_frames(self):
        client = self.client()
        client.initialize()
        for raw in (b'{"jsonrpc":"2.0","id":9,"method":"ping","id":10}\n',
                    b'{"jsonrpc":"2.0","id":NaN,"method":"ping"}\n', b'\xff\n'):
            client.proc.stdin.write(raw)
            client.proc.stdin.flush()
            self.assertEqual(json.loads(client.lines.get(timeout=10))["error"]["code"], -32700)
        client.proc.stdin.write(b" " * (fixture_module.MAX_MESSAGE_BYTES + 1) + b"\n")
        client.proc.stdin.flush()
        exit_code, error = client.close()
        self.assertEqual(exit_code, 2)
        self.assertIn("message exceeds fixture limit", error)
        self.assertEqual(self.audit(client.root)[-1]["event"], "rejected-frame")


if __name__ == "__main__":
    unittest.main()
