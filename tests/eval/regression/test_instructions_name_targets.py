"""The server's `instructions` is the only place a client learns which servers exist.

Background, 2026-09-15. Every tool in this skill takes ``target``, and a client
that is never told what the configured targets are calls them without one, gets
the default, and answers about whatever system happens to be first. That is not
hypothetical: in Monitor the default was a standalone ESXi host, so "how many VMs
does the vCenter have" was answered from that host, confidently and wrongly. This
server shipped **empty** instructions, so a client was told nothing at all — not
the targets, and not what the skill does.

What this pins:

* the configured target **names and hosts** reach the built instructions, and the
  default is marked as the default — so the model can pick one on purpose;
* ``domain`` is listed when set and omitted when not: it is what tells two
  Connection Servers in different AD domains apart, and an empty one is noise;
* both marker phrases are present, because those are what a client and the
  family gate look for;
* all three branches keep the ``Configured targets:`` sentence — the listing,
  "none yet" when the file is readable but empty, and "could not be read
  (<Type>)" when it is not. A missing config is the normal state before ``init``
  and must not stop the server from starting; a client shown no listing at all
  cannot tell "no targets" from "could not read them";
* the unreadable branch interpolates only the exception's **type** — its text
  quotes the config path, and this string goes straight into client context.

The config loader is monkeypatched rather than written to disk: this must hold on
a machine with no ``~/.vmware-vdi/config.yaml``, which is exactly where the
fallback path is reachable.
"""

from __future__ import annotations

import pytest

from vmware_vdi.config import AppConfig, TargetConfig
from vmware_vdi.mcp_server import _shared

LISTING_MARKER = "Configured targets:"
RULE_MARKER = "Choosing a target:"

_TARGETS = {
    "lab-cs": TargetConfig(
        host="cs01.lab.example.local", username="administrator", domain="LAB"
    ),
    "dmz-cs": TargetConfig(host="10.44.0.9", username="svc-horizon"),
}


def _loaded_config() -> AppConfig:
    return AppConfig(targets=_TARGETS, default_target="lab-cs")


@pytest.fixture()
def instructions(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(_shared, "load_config", _loaded_config)
    return _shared._target_instructions()


def test_every_configured_target_is_named(instructions: str) -> None:
    for name, target in _TARGETS.items():
        assert name in instructions, f"target {name!r} is not named in the instructions"
        assert target.host in instructions, f"host of {name!r} is not in the instructions"


def test_the_default_target_is_marked_and_only_it(instructions: str) -> None:
    assert "lab-cs (cs01.lab.example.local, domain LAB, default)" in instructions
    # Marking two defaults would be worse than marking none: it reads as a
    # choice already made, and the model would stop asking.
    assert instructions.count(", default)") == 1


def test_domain_is_listed_when_set_and_omitted_when_not(instructions: str) -> None:
    assert "domain LAB" in instructions
    # The domainless target renders with host alone — no empty "domain " fragment.
    assert "dmz-cs (10.44.0.9)" in instructions
    assert instructions.count("domain ") == 1


def test_both_marker_phrases_are_present(instructions: str) -> None:
    for marker in (LISTING_MARKER, RULE_MARKER):
        assert marker in instructions, f"{marker!r} missing from the instructions"


def test_the_instructions_say_what_the_skill_is(instructions: str) -> None:
    """Empty instructions told a client neither the targets nor the skill.

    Only capabilities this skill's own SKILL.md claims — nothing invented here.
    """
    assert "Horizon" in instructions
    assert "desktop pools" in instructions


def test_an_unreadable_config_names_the_type_and_the_remedy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The branch a customer who installed but never ran `init` actually hits.

    The gate probes under an empty HOME because of this: with the operator's
    config present this branch is unreachable, which is how it shipped broken.
    """
    secret_path = "Config file not found: /Users/somebody/.vmware-vdi/config.yaml"

    def _raises() -> AppConfig:
        raise FileNotFoundError(secret_path)

    monkeypatch.setattr(_shared, "load_config", _raises)
    text = _shared._target_instructions()  # must not raise

    assert text.strip(), "instructions collapsed to an empty string"
    assert LISTING_MARKER in text, "the listing sentence was dropped, not explained"
    assert RULE_MARKER in text
    assert "could not be read (FileNotFoundError)" in text
    assert "vmware-vdi doctor" in text
    # Only the exception's TYPE may be interpolated: its text quotes the config
    # path, and these instructions go straight into client context.
    assert secret_path not in text
    assert "/Users/somebody" not in text


def test_the_exception_type_is_whatever_actually_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A parse error and a missing file must not read as the same thing."""

    def _raises() -> AppConfig:
        raise ValueError("bad yaml at line 3")

    monkeypatch.setattr(_shared, "load_config", _raises)
    text = _shared._target_instructions()

    assert "could not be read (ValueError)" in text
    assert "bad yaml at line 3" not in text


def test_a_readable_config_with_no_targets_says_none_yet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read-but-empty is a different state from unreadable, and gets its own text."""
    monkeypatch.setattr(_shared, "load_config", lambda: AppConfig(targets={}))
    text = _shared._target_instructions()

    assert LISTING_MARKER in text
    assert RULE_MARKER in text
    assert "none yet" in text
    assert "~/.vmware-vdi/config.yaml" in text
    # Not the unreadable wording: the file was read fine.
    assert "could not be read" not in text


def test_the_listing_is_built_not_hardcoded() -> None:
    """A different config must produce a different listing.

    A hardcoded sentence would satisfy every assertion above and still drift from
    the operator's file the day they edit it.
    """
    other = AppConfig(
        targets={"hq-cs": TargetConfig(host="cs-hq.example.net", username="admin")},
        default_target="hq-cs",
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(_shared, "load_config", _loaded_config)
        first = _shared._target_instructions()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(_shared, "load_config", lambda: other)
        second = _shared._target_instructions()

    assert first != second
    assert "hq-cs (cs-hq.example.net, default)" in second
    assert "lab-cs" not in second
