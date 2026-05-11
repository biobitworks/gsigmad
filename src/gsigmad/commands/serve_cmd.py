"""gsigmad serve -- start MCP server."""
from __future__ import annotations

import typer


def serve(
    transport: str = typer.Option(
        "stdio",
        "--transport",
        "-t",
        help="Transport protocol: stdio or sse.",
    ),
    port: int = typer.Option(
        8000,
        "--port",
        "-p",
        help="Port for SSE transport (ignored for stdio).",
    ),
) -> None:
    """Start the gsigmad MCP server for AI agent integration."""
    try:
        from gsigmad.mcp_server import mcp
    except SystemExit as exc:
        import rich

        rich.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport == "sse":
        mcp.run(transport="sse", port=port)
    else:
        import rich

        rich.print(
            f"[red]Error:[/red] Unknown transport: {transport}. Use 'stdio' or 'sse'."
        )
        raise typer.Exit(code=1)
