# Runtime patches for marimo 0.24.0 bugs affecting MCP tool use, all fixed
# upstream but not yet in a release.
#
# marimo 0.24.0 has (at least) two call sites that read the camelCase
# `.inputSchema` attribute off `mcp.types.Tool` objects the MCP SDK returns:
#
#   1. MCPClient._add_server_tools() (marimo/_server/ai/mcp/client.py),
#      rebuilding every discovered tool via
#      `Tool(name=..., inputSchema=tool.inputSchema, _meta=...)`.
#   2. ToolManager._convert_mcp_tool() (marimo/_server/ai/tools/tool_manager.py),
#      reading `parameters=mcp_tool.inputSchema` when exposing MCP tools to
#      the assistant (e.g. answering "what MCP tools are available?").
#
# The `mcp` package resolved by uv (2.1.1) renamed that field to
# `input_schema`, so both accesses raise AttributeError, breaking tool
# discovery and tool listing entirely -- for every server, before any tool
# schema is even inspected. (If `fastmcp` has been imported somewhere in the
# process, it installs a warn-once compat property for `.inputSchema` --
# that's the `FastMCPDeprecationWarning` you may see -- but the first-ever
# access in the process, before that import happens, is still a hard
# AttributeError, which is what actually gets caught and logged.) Both are
# fixed upstream on main (commit 849f16b6d, "feat(mcp): migrate to MCP 2
# (#10581)"), swapping the manual reconstruction for
# `tool.model_copy(update={"meta": metadata})` / reading `.input_schema`
# directly -- no field-name coupling at all. Not in a release yet (HEAD was
# 99 commits past the 0.24.0 tag as of 2026-09-05, no tag contains it).
#
# There's a third, independent bug fixed by _patch_form_toolsets() below --
# see its docstring (marimo #10574 / PR #10573).
#
# TODO(mcp-2-migration): delete this file and the PYTHONPATH export in
# entrypoint.sh once dev-marimo's pyproject.toml is bumped to a marimo
# release that includes both commit 849f16b6d and PR #10573. The self-checks
# below should make each patch a no-op automatically at that point, but clean
# this up anyway.
#
# This file is auto-imported by Python's `site` module at interpreter
# startup because entrypoint.sh puts this directory on PYTHONPATH -- see
# https://docs.python.org/3/library/site.html.

import inspect


def _patch_mcp_client() -> None:
    try:
        from marimo._server.ai.mcp import client as mcp_client_module
    except ImportError:
        return  # marimo not installed / MCP support unavailable; nothing to patch

    MCPClient = mcp_client_module.MCPClient

    try:
        source = inspect.getsource(MCPClient._add_server_tools)
    except (OSError, TypeError):
        return  # can't introspect; don't risk patching blind

    if "tool.inputSchema" not in source:
        # Upstream fix has landed (or this isn't the version we think it is).
        # Nothing to do -- this file and its PYTHONPATH wiring can be deleted.
        return

    def _patched_add_server_tools(self, connection, tools) -> None:  # type: ignore[no-untyped-def]
        server_name = connection.definition.name

        for tool in tools:
            namespaced_name = self._create_namespaced_tool_name(
                server_name, tool.name
            )

            metadata = dict(tool.meta or {})
            metadata.update(
                server_name=server_name,
                namespaced_name=namespaced_name,
            )
            # model_copy sidesteps the inputSchema/input_schema field-name
            # mismatch entirely by not reconstructing the Tool at all.
            mcp_tool = tool.model_copy(update={"meta": metadata})

            connection.tools.append(mcp_tool)
            self.tool_registry[namespaced_name] = mcp_tool

        mcp_client_module.LOGGER.debug(
            f"[sitecustomize patch] Added {len(tools)} tools from {server_name}"
        )

    MCPClient._add_server_tools = _patched_add_server_tools
    mcp_client_module.LOGGER.warning(
        "Patched MCPClient._add_server_tools at startup to work around "
        "marimo/mcp-2 inputSchema incompatibility (see scripts/sitecustomize.py)."
    )


def _patch_tool_manager() -> None:
    try:
        from marimo._server.ai.tools import tool_manager as tool_manager_module
    except ImportError:
        return

    ToolManager = tool_manager_module.ToolManager

    try:
        source = inspect.getsource(ToolManager._convert_mcp_tool)
    except (OSError, TypeError):
        return

    if "mcp_tool.inputSchema" not in source:
        # Upstream fix has landed. Nothing to do -- this file and its
        # PYTHONPATH wiring can be deleted.
        return

    from marimo._server.ai.tools.types import ToolDefinition

    def _patched_convert_mcp_tool(self, mcp_tool):  # type: ignore[no-untyped-def]
        meta = mcp_tool.meta or {}
        namespaced_name = (
            meta.get("namespaced_name") if isinstance(meta, dict) else None
        )
        return ToolDefinition(
            name=namespaced_name or mcp_tool.name,
            description=mcp_tool.description or "No description available",
            parameters=mcp_tool.input_schema,
            source="mcp",
            mode=["ask", "agent"],
        )

    ToolManager._convert_mcp_tool = _patched_convert_mcp_tool
    tool_manager_module.LOGGER.warning(
        "Patched ToolManager._convert_mcp_tool at startup to work around "
        "marimo/mcp-2 inputSchema incompatibility (see scripts/sitecustomize.py)."
    )


def _patch_form_toolsets() -> None:
    """marimo #10574 / PR #10573 (rob's own fix, merged upstream on main as
    commit 2b34ad25, not yet in a release): form_toolsets() registered every
    tool via `toolset.add_function(tool_fn, ...)`, and pydantic-ai infers the
    JSON schema it sends to the model from the *Python signature* of the
    internal dispatch closure `tool_fn(_tool_name=..., **kwargs)` -- not from
    the tool's real `parameters`. Every tool (MCP, backend, frontend) ends up
    exposed to the model as `{"_tool_name": {...}, "additionalProperties":
    true}`, discarding real argument names/types. This is why the model looks
    like it's "ignoring" tools -- it was never told what arguments they take.

    Fix: `Tool.from_schema(..., json_schema=tool.parameters)` builds the
    pydantic-ai Tool from the tool's real schema instead of introspecting the
    closure's signature.
    """
    try:
        from marimo._ai import _pydantic_ai_utils as pau_module
    except ImportError:
        return

    try:
        source = inspect.getsource(pau_module.form_toolsets)
    except (OSError, TypeError):
        return

    if "add_function" not in source:
        # Upstream fix has landed (uses Tool.from_schema/add_tool instead).
        # Nothing to do -- this file and its PYTHONPATH wiring can be deleted.
        return

    from dataclasses import dataclass
    from typing import Any, Awaitable, Callable

    @dataclass(frozen=True)
    class _ToolFunction:
        name: str
        source: str
        tool_invoker: "Callable[[str, dict[str, Any]], Awaitable[Any]]"

        async def __call__(self, **kwargs: Any) -> Any:
            if self.source == "frontend":
                from pydantic_ai import CallDeferred

                raise CallDeferred(
                    metadata={
                        "source": "frontend",
                        "tool_name": self.name,
                        "kwargs": kwargs,
                    }
                )
            result = await self.tool_invoker(self.name, kwargs)
            return pau_module.asdict(result)

    def _patched_form_toolsets(tools, tool_invoker):  # type: ignore[no-untyped-def]
        from pydantic_ai import FunctionToolset, Tool

        toolset = FunctionToolset()
        for tool in tools:
            toolset.add_tool(
                Tool.from_schema(
                    function=_ToolFunction(
                        name=tool.name,
                        source=tool.source,
                        tool_invoker=tool_invoker,
                    ),
                    name=tool.name,
                    description=tool.description,
                    json_schema=tool.parameters,
                )
            )
        return toolset, any(t.source == "frontend" for t in tools)

    pau_module.form_toolsets = _patched_form_toolsets
    pau_module.LOGGER.warning(
        "Patched form_toolsets at startup to send real tool JSON schemas to "
        "the model instead of a generic placeholder (marimo #10574 / PR "
        "#10573; see scripts/sitecustomize.py)."
    )


_patch_mcp_client()
_patch_tool_manager()
_patch_form_toolsets()
