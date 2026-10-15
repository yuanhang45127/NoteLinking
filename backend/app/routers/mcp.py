"""MCP 路由：列出已配置的 stdio MCP server 与其工具、代理工具调用。

连接的 server 来自「设置 → MCP 服务器」（settings.mcp_servers）。
"""
from fastapi import APIRouter, HTTPException

from ..schemas import McpCallIn
from ..services import mcp_client

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


@router.get("/servers")
def list_servers():
    """全部已配置 server：id/name/command/enabled/tools/error（连不上的记 error）。"""
    return {"servers": mcp_client.list_server_tools()}


@router.post("/call")
def call_tool(body: McpCallIn):
    """调用某个 server 的工具，原样返回 MCP result（含 isError）。"""
    try:
        result = mcp_client.call_tool(body.server, body.tool, body.arguments or {})
    except mcp_client.MCPError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"result": result}
