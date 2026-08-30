"""The doctor must diagnose the config file the tools will actually load.

Family sweep after the same class of defect was found on real hardware in the
Aria skill, 2026-08-30, where `doctor` reported every check PASS against
``~/.vmware-aria/config.yaml`` while every tool opened the file named by
``$VMWARE_ARIA_CONFIG``.

This skill was affected differently, and it is worth being precise about how,
because the difference is the whole reason the fix here is one function rather
than four. ``load_config()`` has always honoured ``VMWARE_VDI_CONFIG``, and the
credentials and connectivity checks call it with no argument, so they were
already looking at the right file. Only ``_check_config`` had its own copy of
the rule — it asked whether ``CONFIG_FILE`` exists — so this doctor could not
produce the green-while-broken report Aria produced: with the variable pointing
at a missing file it still failed, because the very next line called
``load_config()`` and got the exception.

What it produced instead was the mirror image: with the variable pointing at a
perfectly good config and no file at the default path, the doctor reported
"Config file missing — copy config.example.yaml to ~/.vmware-vdi/config.yaml"
while the tools worked, and the two checks below it read the real file and
listed its targets. A false alarm naming a path nothing reads, whose remedy is
to create a second config that will then be ignored.

Same defect, opposite polarity, one cause: the rule written down twice. It now
lives in ``resolve_config_path`` alone — two copies of a rule do not disagree
loudly, they disagree slowly (CLAUDE.md 形态 #6).
"""

from __future__ import annotations

import inspect

import pytest

from vmware_vdi import config as cfg
from vmware_vdi import doctor as doc

_ONE_TARGET = """
targets:
  only-in-the-default:
    host: 127.0.0.1
    port: 1
    username: administrator
default_target: only-in-the-default
"""

# A different count, so the report itself says which file was opened.
_THREE_TARGETS = """
targets:
  a:
    host: 127.0.0.1
    port: 1
    username: administrator
  b:
    host: 127.0.0.1
    port: 1
    username: administrator
  c:
    host: 127.0.0.1
    port: 1
    username: administrator
"""


def _flat(text: str) -> str:
    """The report with whitespace removed, so the assertions about *which file*
    do not depend on where Rich chose to wrap a long path."""
    return "".join(text.split())


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    default = tmp_path / "default.yaml"
    monkeypatch.setattr(cfg, "CONFIG_FILE", default)
    monkeypatch.delenv("VMWARE_VDI_CONFIG", raising=False)
    # Rich elides long details at 80 columns, so an assertion about a tmp_path
    # would be measuring the terminal rather than the doctor.
    monkeypatch.setenv("COLUMNS", "300")
    return default


def test_the_env_var_decides_which_file_is_resolved(sandbox, tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere.yaml"
    elsewhere.write_text(_THREE_TARGETS)
    monkeypatch.setenv("VMWARE_VDI_CONFIG", str(elsewhere))

    assert cfg.resolve_config_path() == elsewhere


def test_an_explicit_path_still_beats_the_env_var(sandbox, tmp_path, monkeypatch):
    """The control on precedence: an explicit path is the caller saying which
    file they mean, and it has to keep winning."""
    explicit = tmp_path / "explicit.yaml"
    explicit.write_text(_ONE_TARGET)
    monkeypatch.setenv("VMWARE_VDI_CONFIG", str(tmp_path / "ignored.yaml"))

    assert cfg.resolve_config_path(explicit) == explicit
    assert len(cfg.load_config(explicit).targets) == 1


def test_with_neither_it_is_the_default(sandbox):
    assert cfg.resolve_config_path() == cfg.CONFIG_FILE


def test_doctor_does_not_call_a_working_config_missing(sandbox, tmp_path, monkeypatch):
    """The reported failure, in this skill's polarity.

    $VMWARE_VDI_CONFIG names a real, valid config; nothing exists at the default
    path. The tools load fine. The doctor used to answer "Config file missing"
    and point at the default — and the checks below it went on to read the real
    file and list its three targets, in the same report.
    """
    elsewhere = tmp_path / "elsewhere.yaml"
    elsewhere.write_text(_THREE_TARGETS)
    monkeypatch.setenv("VMWARE_VDI_CONFIG", str(elsewhere))
    assert len(cfg.load_config().targets) == 3, "the tools can read this config"

    ok, msg = doc._check_config()
    out = _flat(msg)

    assert ok is True, (
        "doctor called a config missing that the tools load without complaint; "
        "the remedy it gives creates a second file that will be ignored"
    )
    assert str(elsewhere) in out, "the check must name the file it looked at"
    assert "3target(s)" in out


def test_doctor_still_fails_when_the_resolved_file_is_missing(
    sandbox, tmp_path, monkeypatch
):
    """The other control: honest red stays red.

    The default here is a real, valid config — and it is still not the file the
    tools will open, so the answer is a failure that names the file that is
    actually missing.
    """
    sandbox.write_text(_ONE_TARGET)
    missing = tmp_path / "not-there.yaml"
    monkeypatch.setenv("VMWARE_VDI_CONFIG", str(missing))

    ok, msg = doc._check_config()

    assert ok is False
    assert str(missing) in _flat(msg)


def test_with_no_env_var_the_default_is_still_what_is_checked(sandbox):
    """And the third control: unset, nothing about the report changes."""
    sandbox.write_text(_ONE_TARGET)

    ok, msg = doc._check_config()

    assert ok is True
    assert str(sandbox) in _flat(msg)
    assert "1target(s)" in _flat(msg)


def test_the_doctor_and_load_config_cannot_disagree():
    """Structural, not behavioural: the doctor may not name the default config
    path at all — whichever check needs to know which file is in play asks the
    resolver, so a future edit cannot silently desynchronise them again."""
    assert "resolve_config_path" in inspect.getsource(cfg.load_config), (
        "load_config resolves the config path by itself again; that is the "
        "duplication this test exists to prevent"
    )
    assert "CONFIG_FILE" not in inspect.getsource(doc), (
        "a doctor check names the default config path directly, so it can "
        "report on a file the tools will not open"
    )
