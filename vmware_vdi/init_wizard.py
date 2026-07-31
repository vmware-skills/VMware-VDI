"""Friendly first-run onboarding: `vmware-vdi init`.

Prompts for the Horizon Connection Server, writes config.yaml + a 0600 .env (password
obfuscated to b64:), tests the /rest/login, and — on success — DISCOVERS the estate
(pools / machines / sessions) so the user immediately sees what they connected to and
what to run next. Every failure is a teaching message, not a traceback.
"""

from __future__ import annotations

import base64
import os

import yaml
from dotenv import set_key
from rich.console import Console
from rich.prompt import Confirm, Prompt

from vmware_vdi.config import CONFIG_DIR, CONFIG_FILE, ENV_FILE, ConfigError

console = Console()


def _write_env(target: str, password: str) -> str:
    """Write the password to .env as a grep-safe b64: token (0600) AND into os.environ.

    ``config.py`` ran ``load_dotenv`` at import — before this wizard prompted — so writing
    only to disk would leave the just-set password invisible to the connection test in this
    same process (and a re-init to rotate a password would silently validate the old one).
    Setting ``os.environ`` here closes that gap. Written via dotenv's own ``set_key`` so the
    stored value is exactly what ``load_dotenv`` would read (踩坑 #38).
    """
    key = f"VMWARE_VDI_{target.upper().replace('-', '_')}_PASSWORD"
    token = "b64:" + base64.b64encode(password.encode("utf-8")).decode("ascii")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    ENV_FILE.touch(exist_ok=True)
    os.chmod(ENV_FILE, 0o600)
    set_key(str(ENV_FILE), key, token, quote_mode="never")
    os.chmod(ENV_FILE, 0o600)
    os.environ[key] = token
    return key


def _discover(target: str) -> None:
    """After a successful login, show what we connected to + friendly next steps."""
    from vmware_vdi.connection import ConnectionManager, VdiApiError

    try:
        client = ConnectionManager.from_config().connect(target)
        from vmware_vdi.ops.monitor import health_summary
        from vmware_vdi.ops.pools import list_pools

        health = health_summary(client)
        pools = list_pools(client)
    except (VdiApiError, ConfigError) as exc:
        console.print(f"[yellow]Connected, but estate discovery hit an error:[/] {exc}")
        return

    console.print("\n[bold green]✓ Connected.[/] Here is what this Connection Server manages:\n")
    console.print(f"  [cyan]Desktop pools[/]: {pools['total']}")
    for p in pools["items"][:8]:
        en = "[green]enabled[/]" if p["enabled"] else "[dim]disabled[/]"
        console.print(f"    • {p['name']}  [{p['type']}, {en}]  [dim]id={p['id']}[/]")
    if pools["total"] > 8:
        console.print(f"    [dim]… and {pools['total'] - 8} more (vmware-vdi pool list)[/]")
    console.print(
        f"  [cyan]Machines[/]: {health['machines']['total']} "
        f"([yellow]{health['machines']['problem']}[/] need attention)"
    )
    console.print(f"  [cyan]Active sessions[/]: {health['sessions']['total']}")

    console.print("\n[bold]Try next:[/]")
    console.print("  [green]vmware-vdi health[/]                 one-glance VDI health")
    console.print("  [green]vmware-vdi pool list[/]              your desktop pools")
    console.print("  [green]vmware-vdi session list[/]           who is logged in")
    console.print("  [green]vmware-vdi machine list --state AGENT_UNREACHABLE[/]   broken desktops")
    console.print(
        "\n[dim]Write operations (logoff, reset, push-image) preview their blast radius and ask twice "
        "before acting. To run fully read-only, point this target at a read-only Horizon admin role.[/]\n"
    )


def run_init(force: bool = False, skip_test: bool = False) -> int:
    """Interactive setup. Returns 0 on success, non-zero on failure/abort."""
    console.print("\n[bold cyan]vmware-vdi setup[/] — connect to a Horizon Connection Server\n")

    if CONFIG_FILE.exists() and not force and not Confirm.ask(
        f"[yellow]{CONFIG_FILE} already exists. Overwrite?[/]", default=False
    ):
        console.print("[dim]Keeping existing config. Run 'vmware-vdi doctor' to check it.[/]")
        return 0

    console.print("[dim]The Connection Server is your Horizon broker (https://<server>). "
                  "Use a Horizon admin account; a read-only role is enough for read commands.[/]\n")
    host = Prompt.ask("Connection Server host (FQDN or IP)").strip()
    if not host:
        console.print("[red]A host is required.[/]")
        return 1
    username = Prompt.ask("Admin username", default="Administrator").strip()
    domain = Prompt.ask("Active Directory domain (e.g. ACME; blank for a local account)", default="").strip()
    password = Prompt.ask("Password", password=True)
    if not password:
        console.print("[red]A password is required.[/]")
        return 1
    target = Prompt.ask("Name this target", default="default").strip() or "default"
    verify_ssl = Confirm.ask(
        "Verify the server's TLS certificate? (answer No only for a self-signed lab cert)", default=True
    )

    # Merge into any existing config so adding a second Connection Server does not
    # delete the first (only this target's entry is replaced).
    existing: dict = {}
    if CONFIG_FILE.exists():
        try:
            existing = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            existing = {}
    targets = existing.get("targets") if isinstance(existing.get("targets"), dict) else {}
    targets[target] = {"host": host, "username": username, "domain": domain, "port": 443, "verify_ssl": verify_ssl}
    config = {"default_target": target, "targets": targets}
    CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    CONFIG_FILE.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    if len(targets) > 1:
        console.print(f"[dim]Default target is now '{target}' ({len(targets)} targets configured; "
                      f"pass --target to use another).[/]")
    key = _write_env(target, password)
    console.print(f"\n[green]✓ Wrote[/] {CONFIG_FILE}\n[green]✓ Wrote[/] {ENV_FILE} [dim](0600, password obfuscated; {key})[/]")

    if skip_test:
        console.print("[dim]Skipped the connection test (--skip-test).[/]")
        return 0

    console.print("\n[dim]Testing the connection…[/]")
    from vmware_vdi.connection import ConnectionManager, VdiApiError

    try:
        ConnectionManager.from_config().connect(target)._login()
    except (VdiApiError, ConfigError) as exc:
        console.print(f"[red]Connection test failed:[/] {exc}")
        console.print("[dim]Config was saved — fix the value above and re-run 'vmware-vdi init --force', "
                      "or 'vmware-vdi doctor' to re-check.[/]")
        return 1

    _discover(target)
    return 0
