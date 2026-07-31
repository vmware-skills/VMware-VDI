"""vmware-vdi Typer CLI. Sub-apps (session/machine/pool/…) are registered as ops verticals land.

The `mcp` subcommand is the primary MCP entry point — using it avoids re-resolving the
package over the network the way `uvx` does (踩坑 #25), so enterprise TLS-proxy environments
work through the installed console script on PATH.
"""

from __future__ import annotations

from typing import Annotated

import typer

app = typer.Typer(
    name="vmware-vdi",
    help="VMware / Omnissa Horizon VDI intelligent operations.",
    no_args_is_help=True,
)


@app.command("init")
def init_cmd(
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing config without asking")] = False,
    skip_test: Annotated[bool, typer.Option("--skip-test", help="Don't test the connection after writing config")] = False,
) -> None:
    """Friendly first-run setup: connect to a Horizon Connection Server and discover your pools."""
    from vmware_vdi.init_wizard import run_init

    raise typer.Exit(run_init(force=force, skip_test=skip_test))


@app.command("doctor")
def doctor_cmd() -> None:
    """Diagnose config, credentials, and Connection Server connectivity."""
    from vmware_vdi.doctor import run_doctor

    raise typer.Exit(run_doctor())


@app.command("mcp")
def mcp_cmd() -> None:
    """Run the MCP server (stdio). Point your MCP client here via the installed console script."""
    from vmware_vdi.mcp_server.server import main

    main()


# Ops verticals register their sub-apps here as they land.
from vmware_vdi.cli.machine import machine_app
from vmware_vdi.cli.pool import pool_app
from vmware_vdi.cli.session import session_app

app.add_typer(session_app, name="session")
app.add_typer(machine_app, name="machine")
app.add_typer(pool_app, name="pool")

from vmware_vdi.cli.monitor import (
    entitlement_app,
    events_cmd,
    farm_app,
    health_cmd,
    stats_cmd,
    utilization_cmd,
)

app.command("health")(health_cmd)
app.command("stats")(stats_cmd)
app.command("utilization")(utilization_cmd)
app.command("events")(events_cmd)
app.add_typer(farm_app, name="farm")

# catalog.py adds entitlement write commands to entitlement_app, so import it after monitor.
from vmware_vdi.cli.catalog import (
    ad_search_cmd,
    app_pool_app,
    images_cmd,
    task_app,
)

app.add_typer(entitlement_app, name="entitlement")
app.add_typer(app_pool_app, name="app-pool")
app.add_typer(task_app, name="task")
app.command("images")(images_cmd)
app.command("ad-search")(ad_search_cmd)
