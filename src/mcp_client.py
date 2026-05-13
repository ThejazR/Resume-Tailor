"""Stdio MCP client that spawns the email server and calls its send_email tool."""
import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from src.config import PROJECT_ROOT


async def _call(to: str, subject: str, body: str, attachment_path: str) -> dict:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.email_server"],
        cwd=str(PROJECT_ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            if tool_names != ["send_email"]:
                raise RuntimeError(
                    f"MCP server exposed unexpected tools: {tool_names}"
                )

            result = await session.call_tool(
                "send_email",
                {
                    "to": to,
                    "subject": subject,
                    "body": body,
                    "attachment_path": str(Path(attachment_path).resolve()),
                },
            )

            if result.isError:
                text = " ".join(
                    getattr(c, "text", "") for c in result.content
                ) or "unknown error"
                raise RuntimeError(f"send_email failed: {text}")

            data = getattr(result, "structuredContent", None)
            if data:
                return data
            text = " ".join(getattr(c, "text", "") for c in result.content)
            return {"status": "sent", "raw": text}


def send_via_mcp(to: str, subject: str, body: str, attachment_path: str) -> dict:
    return asyncio.run(_call(to, subject, body, attachment_path))
