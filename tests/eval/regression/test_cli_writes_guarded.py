"""Every write CLI command is @guarded, under its MCP tool's name (HLD I-1, I-3, I-8).

A write CLI command must route through vmware_policy's guard() + audit_call() —
the same enforcement @vmware_tool gives the MCP surface — so ``vmware-vdi session
logoff`` run through Bash is authorized and audited to ~/.vmware/audit.db
exactly like the ``session_logoff`` MCP tool.

It must also be guarded under the MCP tool's *name*. A deny rule names an
operation; ``@guarded`` without an explicit name authorizes and audits under
the Python function name (``session_logoff_cmd``), so a rule written against
``session_logoff`` refused the agent and let the same logoff through the CLI,
and the one audit sink recorded the two surfaces under two names.

The write set is DERIVED, never hand-listed (踩坑 #43): a tool annotated
``readOnlyHint=False`` is a write; the ops functions its body calls — reached by
a bare (possibly aliased) name OR ``module.func`` on an ops-module import — are
the state-changing ops; a CLI command calling one is a write command. The MCP
twin of a CLI command is the write tool whose body calls the same ops function.
A command counts whether Typer registers it by decorator (``@session_app.command``)
or by the call form ``app.command("images")(images_cmd)`` that cli/__init__.py uses.

Everything about the CLI is read from the AST, not by introspecting the
imported command objects: ``@cli_errors`` sits above ``@guarded``, so what a
runtime survey sees on the registered object depends on every outer wrapper
copying ``_guarded_tool`` through — a property of the wrappers, not of the
guard. The one runtime cross-check below only confirms the AST reader agrees
with the decorator where the runtime value is visible.

Pointing a glob at a directory that does not exist returns zero files and passes
vacuously — the "empty results read as no problem" shape — so every scan
asserts it found something, and the derived sets carry floors.
"""

from __future__ import annotations

import ast
import asyncio
import importlib
import inspect
import pathlib
from dataclasses import dataclass

_REPO = pathlib.Path(__file__).resolve().parents[3]
_PKG_NAME = "vmware_vdi"
_PKG = _REPO / _PKG_NAME

# Guarded CLI commands with no MCP write twin. They keep their own function name
# as the policy operation name; each one needs the reason it has no twin.
_CLI_ONLY_WRITES: dict[str, str] = {}

# Named commands the derivation must reach — so a broad-but-wrong derivation
# cannot satisfy the floor: the destructive writes with the widest blast radius
# (a forced logoff kicks users; push-image recomposes a whole pool).
_MUST_DERIVE: tuple[str, ...] = (
    "session_logoff_cmd",
    "machine_reset_cmd",
    "machine_remove_cmd",
    "pool_push_image_cmd",
)
_WRITE_FLOOR = 8  # 11 write commands today


@dataclass(frozen=True)
class _Command:
    label: str  # "<file>:<function>"
    module: str  # importable module that defines it
    name: str  # Python function name
    ops: frozenset[str]  # real ops function names its body calls
    guarded: tuple[str, str] | None  # (policy operation name, risk_level) or None


def _cli_files() -> list[pathlib.Path]:
    files = sorted((_PKG / "cli").glob("*.py"))
    assert files, f"no CLI sources under {_PKG / 'cli'} — scan would be vacuous"
    return files


def _tool_files() -> list[pathlib.Path]:
    files = sorted((_PKG / "mcp_server" / "tools").glob("*.py"))
    assert files, f"no MCP tool sources under {_PKG / 'mcp_server' / 'tools'} — derivation would be empty"
    return files


def _module_name(path: pathlib.Path) -> str:
    base = f"{_PKG_NAME}.cli"
    return base if path.stem == "__init__" else f"{base}.{path.stem}"


def _write_tool_names() -> frozenset[str]:
    server = importlib.import_module(f"{_PKG_NAME}.mcp_server.server")
    names = frozenset(
        t.name
        for t in asyncio.run(server.mcp.list_tools())
        if getattr(getattr(t, "annotations", None), "readOnlyHint", None) is False
    )
    assert names, "no write tools (readOnlyHint=False) registered — derivation vacuous"
    return names


def _ops_refs(tree: ast.AST) -> tuple[dict[str, str], set[str]]:
    """(local name -> REAL ops function name, ops-module aliases).

    ``from <pkg>.ops.mod import real as _alias`` maps ``_alias -> real`` so an
    aliased call (the tools alias ``task_cancel as _c``) resolves to the
    same op an un-aliased import names; ``from <pkg>.ops import mod as _m``
    records ``_m`` so ``_m.func()`` resolves to ``func``.
    """
    func_map: dict[str, str] = {}
    mods: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            parts = n.module.split(".")
            if "ops" not in parts:
                continue
            if parts[-1] == "ops":
                mods.update(a.asname or a.name for a in n.names)
            else:
                for a in n.names:
                    func_map[a.asname or a.name] = a.name
    return func_map, mods


def _ops_calls(node: ast.AST, func_map: dict[str, str], mods: set[str]) -> frozenset[str]:
    out: set[str] = set()
    for c in ast.walk(node):
        if not isinstance(c, ast.Call):
            continue
        f = c.func
        if isinstance(f, ast.Name) and f.id in func_map:
            out.add(func_map[f.id])
        elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in mods:
            out.add(f.attr)
    return frozenset(out)


def _decorator(node: ast.FunctionDef, name: str) -> ast.expr | None:
    """The decorator whose callee is ``name`` (bare or ``x.name``), else None."""
    for d in node.decorator_list:
        t = d.func if isinstance(d, ast.Call) else d
        if (isinstance(t, ast.Name) and t.id == name) or (isinstance(t, ast.Attribute) and t.attr == name):
            return d
    return None


def _default(fn, param: str) -> str:
    return inspect.signature(fn).parameters[param].default


def _literal_kw(call: ast.Call, key: str) -> str | None:
    for kw in call.keywords:
        if kw.arg == key:
            assert isinstance(kw.value, ast.Constant), f"{key}= is not a literal — the AST reader cannot judge it"
            return kw.value.value
    return None


def _guarded_spec(node: ast.FunctionDef) -> tuple[str, str] | None:
    """(operation name, risk_level) exactly as vmware_policy.guarded resolves them."""
    from vmware_policy import guarded

    d = _decorator(node, "guarded")
    if d is None:
        return None
    if not isinstance(d, ast.Call):  # bare @guarded — not a valid use, treat as defaults
        return node.name, _default(guarded, "risk_level")
    tool: str | None = None
    if d.args:
        assert isinstance(d.args[0], ast.Constant), f"{node.name}: @guarded name is not a literal"
        tool = d.args[0].value
    tool = tool or _literal_kw(d, "tool")
    risk = _literal_kw(d, "risk_level") or _default(guarded, "risk_level")
    return tool or node.name, risk


def _registered_command_names(trees: list[ast.AST]) -> set[str]:
    """Functions Typer registers: ``@x.command(...)`` or the call form ``x.command(...)(fn)``."""
    names: set[str] = set()
    for tree in trees:
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and any(
                isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "command"
                for d in n.decorator_list
            ):
                names.add(n.name)
            elif (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Call)
                and isinstance(n.func.func, ast.Attribute)
                and n.func.func.attr == "command"
            ):
                names.update(a.id for a in n.args if isinstance(a, ast.Name))
    return names


def _cli_commands() -> list[_Command]:
    parsed = [(p, ast.parse(p.read_text(encoding="utf-8"))) for p in _cli_files()]
    registered = _registered_command_names([t for _, t in parsed])
    out: list[_Command] = []
    for path, tree in parsed:
        func_map, mods = _ops_refs(tree)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in registered:
                out.append(
                    _Command(
                        label=f"{path.name}:{node.name}",
                        module=_module_name(path),
                        name=node.name,
                        ops=_ops_calls(node, func_map, mods),
                        guarded=_guarded_spec(node),
                    )
                )
    assert out, "no registered CLI commands found — scan would be vacuous"
    return out


def _mcp_write_tools() -> dict[str, tuple[str, frozenset[str]]]:
    """MCP write tool name -> (risk_level, ops functions its body calls)."""
    from vmware_policy import vmware_tool

    targets = _write_tool_names()
    out: dict[str, tuple[str, frozenset[str]]] = {}
    for path in _tool_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        func_map, mods = _ops_refs(tree)
        for node in tree.body:
            if not (isinstance(node, ast.FunctionDef) and node.name in targets):
                continue
            d = _decorator(node, "vmware_tool")
            assert d is not None, f"MCP write tool {node.name} has no @vmware_tool"
            risk = (_literal_kw(d, "risk_level") if isinstance(d, ast.Call) else None) or _default(
                vmware_tool, "risk_level"
            )
            out[node.name] = (risk, _ops_calls(node, func_map, mods))
    missing = targets - set(out)
    assert not missing, f"write tools registered but not found in {_PKG_NAME}/mcp_server/tools: {sorted(missing)}"
    return out


def _op_to_tools(tools: dict[str, tuple[str, frozenset[str]]]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for tool, (_, ops) in tools.items():
        for op in ops:
            out.setdefault(op, set()).add(tool)
    return out


def test_every_write_cli_command_is_guarded():
    op_tools = _op_to_tools(_mcp_write_tools())
    assert op_tools, "no write ops derived from the MCP write tools — vacuous"
    writing = [c for c in _cli_commands() if c.ops & op_tools.keys()]
    assert len(writing) >= _WRITE_FLOOR, (
        f"only {len(writing)} write CLI commands derived ({[c.label for c in writing]}) — the "
        f"MCP→ops→CLI derivation is likely stale; a check matching nothing is worse than none."
    )
    names = {c.name for c in writing}
    for must in _MUST_DERIVE:
        assert must in names, f"{must} is no longer derived as a write command — the derivation stopped resolving it"
    unguarded = [c.label for c in writing if c.guarded is None]
    assert not unguarded, (
        f"these CLI commands call a [WRITE] ops function but are not @guarded, so they "
        f"bypass policy + audit (HLD I-1): {unguarded}"
    )


def test_guarded_cli_writes_carry_their_mcp_tool_name():
    """A deny rule names a tool; it must stop the CLI twin of that tool too (HLD I-3)."""
    tools = _mcp_write_tools()
    op_tools = _op_to_tools(tools)
    guarded = [c for c in _cli_commands() if c.guarded is not None]
    assert guarded, "no @guarded CLI commands found — scan would be vacuous"

    problems: list[str] = []
    checked: list[str] = []
    for c in guarded:
        op_name, risk = c.guarded
        twins = set().union(*(op_tools.get(o, set()) for o in c.ops)) if c.ops else set()
        if len(twins) > 1:
            problems.append(f"{c.label}: ambiguous — calls ops of several MCP tools {sorted(twins)}")
            continue
        if not twins:
            if c.name not in _CLI_ONLY_WRITES:
                problems.append(
                    f"{c.label}: @guarded but no MCP write tool calls the same ops — add it to "
                    f"_CLI_ONLY_WRITES with the reason, or fix the derivation"
                )
            elif op_name != c.name:
                problems.append(f"{c.label}: CLI-only write guarded as {op_name!r}; keep its own name")
            continue
        (twin,) = twins
        checked.append(c.name)
        if c.name in _CLI_ONLY_WRITES:
            problems.append(f"{c.label}: listed as CLI-only but has MCP twin {twin!r} — drop the allowance")
        if op_name != twin:
            problems.append(f"{c.label}: guarded as {op_name!r}, MCP tool is {twin!r}")
        elif risk != tools[twin][0]:
            problems.append(f"{c.label}: risk {risk!r}, MCP tool {twin!r} risk {tools[twin][0]!r}")

    stale = set(_CLI_ONLY_WRITES) - {c.name for c in guarded}
    if stale:
        problems.append(f"_CLI_ONLY_WRITES names commands that are not @guarded CLI commands: {sorted(stale)}")

    assert len(checked) >= _WRITE_FLOOR, f"only {checked} checked against an MCP twin — derivation likely stale"
    assert not problems, (
        "CLI writes whose policy operation name or risk differs from their MCP tool, so one deny "
        "rule does not scope both surfaces — pass the MCP tool name to @guarded(...): " + "; ".join(problems)
    )


def test_ast_reader_agrees_with_the_decorator():
    """Where the guarded name is visible at runtime, it is the one the AST derived.

    Guards the reader above against drifting from vmware_policy.guarded's own
    rule (``tool or func.__name__``). Only commands whose wrapper stack exposes
    ``_guarded_tool`` can be compared; at least one must, or this proves nothing.
    """
    compared = 0
    for c in _cli_commands():
        if c.guarded is None:
            continue
        fn = getattr(importlib.import_module(c.module), c.name, None)
        runtime = getattr(fn, "_guarded_tool", None)
        if runtime is None:
            continue
        compared += 1
        assert runtime == c.guarded[0], f"{c.label}: AST reads {c.guarded[0]!r}, decorator records {runtime!r}"
        assert fn._risk_level == c.guarded[1], f"{c.label}: AST risk {c.guarded[1]!r}, decorator {fn._risk_level!r}"
    assert compared, "no guarded command exposes _guarded_tool at runtime — the cross-check compared nothing"


def test_one_deny_rule_naming_the_mcp_tool_stops_the_cli_command(tmp_path, monkeypatch):
    """The point of the naming rule, end to end: deny ``session_logoff`` and the CLI is refused too.

    The refusal happens in guard(), before the command body — so the connection
    helper must never be reached. Before the fix the CLI was guarded as
    ``session_logoff_cmd`` and this rule matched nothing on that surface.
    """
    import vmware_policy.policy as pm
    from typer.testing import CliRunner
    from vmware_policy import PolicyDenied

    from vmware_vdi.cli import app
    from vmware_vdi.cli import session as cli_session

    rules = tmp_path / "rules.yaml"
    rules.write_text(
        'deny:\n  - name: no-logoff\n    operations: ["session_logoff"]\n    reason: frozen\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(pm, "_engine", pm.PolicyEngine(rules))

    def _must_not_connect(*_a, **_k):
        raise AssertionError("the command body ran — the deny rule did not stop the CLI")

    monkeypatch.setattr(cli_session, "_get_connection", _must_not_connect)
    result = CliRunner().invoke(app, ["session", "logoff", "--id", "s-1", "--dry-run"])
    # Refused cleanly: exit 1 and a message naming the rule, not a traceback.
    assert result.exit_code == 1, (result.exit_code, result.output, result.exception)
    assert not isinstance(result.exception, PolicyDenied), "a denied write crashed with a traceback"
    assert "Denied by policy" in result.output and "no-logoff" in result.output, result.output
