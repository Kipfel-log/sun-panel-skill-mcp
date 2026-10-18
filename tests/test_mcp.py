from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sun-panel" / "scripts"))
from mcp import Client
from sun_panel_mcp import build_server
from test_client import MockPanel


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock = MockPanel()

    async def asyncTearDown(self):
        await asyncio.to_thread(self.mock.close)

    async def test_readonly_tool_discovery_and_calls(self):
        async with Client(build_server(self.mock.client())) as client:
            tools = await client.list_tools()
            names = {t.name for t in tools.tools}
            self.assertEqual(len(names), 6)
            self.assertNotIn("sun_panel_create_item", names)
            result = await client.call_tool("sun_panel_list_groups", {})
            self.assertFalse(result.is_error)
            payload = json.loads(result.content[0].text)
            self.assertEqual(payload["data"]["count"], 2)
            denied = await client.call_tool("sun_panel_update_item", {"item": {"onlyName": "existing", "title": "oops"}})
            self.assertTrue(denied.is_error)

    async def test_write_tool_schema_preview_and_execution(self):
        async with Client(build_server(self.mock.client(True), allow_write=True)) as client:
            tools = await client.list_tools()
            self.assertEqual(len(tools.tools), 8)
            patch = {"item": {"onlyName": "existing", "title": "MCP 修改"}}
            preview = await client.call_tool("sun_panel_preview_update", patch)
            self.assertFalse(preview.is_error)
            self.assertEqual(self.mock.items["existing"]["title"], "原来的标题")
            result = await client.call_tool("sun_panel_update_item", patch)
            self.assertFalse(result.is_error)
            payload = json.loads(result.content[0].text)
            self.assertTrue(payload["verified"])
            self.assertEqual(self.mock.items["existing"]["title"], "MCP 修改")
            invalid = await client.call_tool("sun_panel_update_item", {"item": {"onlyName": "existing", "sort": 99}})
            self.assertTrue(invalid.is_error)


if __name__ == "__main__":
    unittest.main()
