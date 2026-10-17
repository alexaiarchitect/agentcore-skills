"""An MCP server that breaks the Runtime contract in three ways (fixture)."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("library", host="127.0.0.1")


@mcp.tool()
def lookup_book(title: str) -> str:
    """Find a book by title."""
    return title


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
