# SPDX-License-Identifier: GPL-3.0-or-later
"""A method call on a local variable is not a module reference.

The 677-file corpus campaign found this on ``BradyAJohnston/MolecularNodes``,
a well-known add-on::

    socket = node.inputs.new('NodeSocketFloat', 'Scale')
    socket.default_value_set(1.0)

That drew ``ALARMING x_network`` and the RED "reaches outside Blender" banner,
and renaming the variable to ``sock_ui`` made it vanish -- the signature of a
rule keyed on a name rather than on a fact. ``socket`` is not a special case:
it is the name of Blender's own ``NodeSocket`` type and one of the most common
local variable names in the ecosystem, and every other table entry that is
also a plausible identifier carries the same exposure.

So the systematic test below is the real regression: it walks *every* table
matched against call names, takes the root of every entry, and asserts that a
body which merely uses that root as a local variable produces nothing. The
hand-written cases either side of it pin the two directions a reader cares
about -- ordinary add-on code stays quiet, and a genuine import still fires.

Every sample is written here by hand. Nothing is fetched, nothing is executed.
"""

from __future__ import annotations

import pytest

from blend_xray import explain
from blend_xray.explain import Severity
from blend_xray.explain_rules import (
    BENIGN_IMPORT_OPS,
    BROWSER_CALLS,
    CODE_BUILD_CALLS,
    DECODE_CALLS,
    DELETE_CALLS,
    DESERIALISE_CALLS,
    DYNAMIC_CODE_CALLS,
    MAKEDIR_CALLS,
    NETWORK_LISTEN_MODULES,
    NETWORK_MODULES,
    SUBPROCESS_CALLS,
    WRITE_CALLS,
)
from blend_xray.resolve import IMPORT_FREE_ROOTS


def keys_of(source: str) -> set[str]:
    return {st.key for st in explain.explain_source(source).statements}


# ==========================================================================
# 1. The reproduction, in the shape it was found in.
# ==========================================================================
MOLECULAR_NODES_SHAPE = """
import bpy

def add_scale_input(node):
    socket = node.inputs.new('NodeSocketFloat', 'Scale')
    socket.default_value_set(1.0)
    return socket
"""


def test_a_node_socket_variable_is_not_the_socket_module() -> None:
    assert "x_network" not in keys_of(MOLECULAR_NODES_SHAPE)


def test_the_node_socket_shape_raises_nothing_alarming_at_all() -> None:
    """The banner reads the severities, so the fix has to reach them."""
    explanation = explain.explain_source(MOLECULAR_NODES_SHAPE)
    assert explanation.max_severity is not Severity.ALARMING


def test_renaming_the_variable_no_longer_changes_the_verdict() -> None:
    """The bug's own tell: ``sock_ui`` was quiet where ``socket`` shouted."""
    renamed = MOLECULAR_NODES_SHAPE.replace("socket", "sock_ui")
    assert keys_of(MOLECULAR_NODES_SHAPE) == keys_of(renamed)


# ==========================================================================
# 2. Every table entry that is also a plausible identifier.
# ==========================================================================
#: Every rule table that is matched against collected *call* names, by the
#: statement key it feeds. ``x_obfuscation`` and ``x_decodes_data`` share
#: :data:`DECODE_CALLS`; both are asserted, because the fix has to hold for
#: whichever of the two the body would otherwise have reached.
CALL_TABLES: dict[str, frozenset[str]] = {
    "x_network": NETWORK_MODULES,
    "x_network_listen": NETWORK_LISTEN_MODULES,
    "x_subprocess": SUBPROCESS_CALLS,
    "x_opens_browser": BROWSER_CALLS,
    "x_file_write": WRITE_CALLS,
    "x_file_delete": DELETE_CALLS,
    "x_makedirs": MAKEDIR_CALLS,
    "x_compile_code": CODE_BUILD_CALLS,
    "x_deserialise": DESERIALISE_CALLS,
    "x_dynamic_code": DYNAMIC_CODE_CALLS,
    "x_decodes_data": DECODE_CALLS,
    "x_obfuscation": DECODE_CALLS,
    "x_import_geometry": BENIGN_IMPORT_OPS,
}


def _shadow_cases() -> list[tuple[str, str]]:
    """``(statement key, entry)`` for every entry a variable could shadow.

    Entries rooted in :data:`~blend_xray.resolve.IMPORT_FREE_ROOTS` are left
    out: ``exec``, ``compile`` and ``bytes.fromhex`` have no import to find,
    and ``bpy`` is in a driver's namespace with no import statement possible,
    so grounding them would disable the rules instead of correcting them.
    """
    cases = []
    for key, table in CALL_TABLES.items():
        for entry in sorted(table):
            if entry.partition(".")[0] not in IMPORT_FREE_ROOTS:
                cases.append((key, entry))
    return cases


def shadowing_body(entry: str) -> str:
    """Blender-shaped code whose local variable is named after ``entry``.

    The variable holds a node socket, the way the add-on this was found in
    holds one, and the method called on it is a real Blender method that
    appears in no rule table.
    """
    root, _, rest = entry.partition(".")
    leaf = rest or "default_value_set"
    return (
        "import bpy\n"
        "\n"
        "def build(node, value):\n"
        f"    {root} = node.inputs.new('NodeSocketFloat', 'Scale')\n"
        f"    {root}.{leaf}(value)\n"
        f"    return {root}\n"
    )


@pytest.mark.parametrize(("key", "entry"), _shadow_cases(), ids=lambda v: str(v))
def test_a_local_variable_named_after_a_table_entry_fires_nothing(key: str, entry: str) -> None:
    assert key not in keys_of(shadowing_body(entry))


# The ones worth naming in full, because they are the identifiers Blender add-on
# code actually uses. Each is real add-on shape, not a synthesised line.
SOCKET_UI = """
import bpy

class NODE_OT_add_input(bpy.types.Operator):
    bl_idname = 'node.add_input'

    def execute(self, context):
        for socket in context.node.inputs:
            socket.hide_value = True
        return {'FINISHED'}
"""

PICKLE_PARAM = """
import bpy

def restore(pickle):
    scene = pickle.load(bpy.context.scene)
    pickle.dump(scene)
    return scene
"""

CODECS_PARAM = """
def normalise(codecs, raw):
    return codecs.decode(raw)
"""

TYPES_LOCAL = """
import bpy

def collect(context):
    types = context.scene.node_tree
    return types.FunctionType(context)
"""

REQUESTS_LOCAL = """
import bpy

def drain(queue):
    requests = queue.pending
    requests.get('pose')
    return requests
"""


@pytest.mark.parametrize(
    ("source", "key"),
    [
        (SOCKET_UI, "x_network"),
        (PICKLE_PARAM, "x_deserialise"),
        (PICKLE_PARAM, "x_file_write"),
        (CODECS_PARAM, "x_decodes_data"),
        (TYPES_LOCAL, "x_dynamic_code"),
        (REQUESTS_LOCAL, "x_network"),
    ],
)
def test_real_addon_shapes_do_not_fire(source: str, key: str) -> None:
    assert key not in keys_of(source)


# ==========================================================================
# 3. A real import still fires, through every spelling of the binding.
# ==========================================================================
def test_a_genuine_socket_import_and_call_still_fires() -> None:
    """The case the fix must not cost: an actual outbound socket."""
    source = "import socket\ns = socket.socket()\ns.connect(('example.com', 80))\n"
    statements = explain.explain_source(source).statements
    network = next(st for st in statements if st.key == "x_network")
    assert network.severity is Severity.ALARMING
    assert "socket.socket" in network.evidence


@pytest.mark.parametrize(
    "source",
    [
        # import x
        "import socket\nsocket.socket()\n",
        # import x as y -- the aliasing the check must not be defeated by
        "import socket as sk\nsk.socket()\n",
        # import a.b as y
        "import urllib.request as ur\nur.urlopen('http://x.example.com')\n",
        # from a import b
        "from urllib import request\nrequest.urlopen('http://x.example.com')\n",
        # from a import b as c
        "from urllib import request as rq\nrq.urlopen('http://x.example.com')\n",
        # from a.b import c
        "from socket import socket\nsocket()\n",
        # a plain rebinding of an imported module
        "import socket\ns = socket\ns.socket()\n",
        # the import written below the use
        "def go():\n    socket.socket()\nimport socket\n",
        # the import buried in a function body
        "def go():\n    import socket\n    socket.socket()\n",
        # `import *` binds names we cannot enumerate without running the
        # module, so the binding map cannot hold them -- the module name in
        # the import set is what keeps this loud, and it must stay that way.
        "from socket import *\ns = socket(AF_INET, SOCK_STREAM)\ns.connect((h, 4444))\n",
    ],
)
def test_every_spelling_of_a_real_import_still_fires(source: str) -> None:
    assert "x_network" in keys_of(source)


def test_an_alias_cannot_be_used_to_hide_a_module() -> None:
    """``import socket as sk`` must not read as "no socket here"."""
    statements = explain.explain_source("import socket as sk\nsk.socket()\n").statements
    network = next(st for st in statements if st.key == "x_network")
    assert any("socket.socket" in item for item in network.evidence)


def test_evidence_quotes_the_line_as_written_and_names_what_it_stands_for() -> None:
    """A reader has to be able to find the line *and* check the claim."""
    statements = explain.explain_source(
        "import urllib.request as ur\nur.urlopen('http://x.example.com')\n"
    ).statements
    network = next(st for st in statements if st.key == "x_network")
    assert "ur.urlopen (urllib.request.urlopen)" in network.evidence


def test_a_relative_import_is_not_read_as_a_stdlib_module() -> None:
    """``from .socket import connect`` is a sibling file, not the stdlib.

    An add-on with its own ``socket.py`` would otherwise have been handed a
    network finding — the same class of mistake as the bug this file exists
    for, arriving from the other direction.
    """
    assert "x_network" not in keys_of("from .socket import connect\nconnect(host)\n")
    assert "x_subprocess" not in keys_of("from .os import system\nsystem('x')\n")


def test_an_import_wins_over_a_later_local_of_the_same_name() -> None:
    """Shadowing the name afterwards must not disarm the real import."""
    source = "import socket\ns = socket.socket()\nsocket = 3\n"
    assert "x_network" in keys_of(source)


@pytest.mark.parametrize(
    ("source", "key"),
    [
        ("import os\nos.system('ls')\n", "x_subprocess"),
        ("import subprocess\nsubprocess.Popen(['ls'])\n", "x_subprocess"),
        ("import webbrowser\nwebbrowser.open('https://x.example.com')\n", "x_opens_browser"),
        ("import shutil\nshutil.rmtree('/tmp/x')\n", "x_file_delete"),
        ("import os\nos.makedirs('/tmp/x')\n", "x_makedirs"),
        ("import pickle\npickle.loads(b'x')\n", "x_deserialise"),
        ("import zlib\nzlib.decompress(b'x')\n", "x_decodes_data"),
        # `from pathlib import Path` binds a name that is not a module; the
        # table spells it both ways and both spellings have to resolve.
        ("from pathlib import Path\nPath.mkdir('x')\n", "x_makedirs"),
        ("from pathlib import Path\nPath.write_text('a', 'b')\n", "x_file_write"),
        ("import bpy\nbpy.ops.import_scene.obj(filepath='x.obj')\n", "x_import_geometry"),
        ("import bpy\nbpy.utils.register_class(None)\n", "x_register"),
        ("compile('1+1', '<s>', 'eval')\n", "x_compile_code"),
        ("exec('print(1)')\n", "x_dynamic_code"),
    ],
)
def test_the_ordinary_positives_are_untouched(source: str, key: str) -> None:
    assert key in keys_of(source)


@pytest.mark.parametrize(
    ("source", "key"),
    [
        ("from os import system\nsystem('ls')\n", "x_subprocess"),
        ("from subprocess import Popen\nPopen(['ls'])\n", "x_subprocess"),
        ("from shutil import rmtree\nrmtree('/tmp/x')\n", "x_file_delete"),
        ("from base64 import b64decode\nb64decode('eA==')\n", "x_decodes_data"),
    ],
)
def test_from_imports_are_caught_now_that_bindings_are_read(source: str, key: str) -> None:
    """Resolving the binding closed a gap as well as one.

    ``from os import system`` puts ``os.system`` in the import set but writes
    the call as a bare ``system(...)``, which matched no entry of a table full
    of dotted module paths. These fired nothing at all before the call names
    were resolved through their bindings.
    """
    assert key in keys_of(source)


# ==========================================================================
# 4. Driver expressions are the one body that gets its namespace handed to it.
# ==========================================================================
#: A driver is a single expression. It can hold no ``import`` -- so requiring
#: one would silence every module rule on the path a payload actually uses --
#: and no assignment either, so the local variable this whole check exists to
#: stop cannot be created in one. Both halves are asserted below.
DRIVER_PAYLOADS = [
    ("os.system('calc.exe')", "x_subprocess"),
    ("socket.socket()", "x_network"),
    ("subprocess.Popen(['calc.exe'])", "x_subprocess"),
    ("urllib.request.urlopen('http://x.example.com')", "x_network"),
    ("base64.b64decode(BLOB)", "x_decodes_data"),
    # The decode-reaches-the-run link has to see through the same namespace,
    # or a driver quietly loses the finding that the module body keeps.
    ("exec(base64.b64decode(BLOB))", "x_obfuscation"),
]


@pytest.mark.parametrize(("expression", "key"), DRIVER_PAYLOADS)
def test_a_driver_expression_still_fires_without_an_import(expression: str, key: str) -> None:
    explanation = explain.explain_source(expression, ambient_names=True)
    assert key in {st.key for st in explanation.statements}


@pytest.mark.parametrize(("expression", "key"), DRIVER_PAYLOADS)
def test_the_same_text_in_a_module_body_does_not(expression: str, key: str) -> None:
    """The default has to stay strict, or defect 1 comes straight back."""
    assert key not in keys_of(expression)


def test_the_scanner_passes_ambient_names_for_drivers() -> None:
    """The flag is worth nothing if the driver path does not set it.

    ``os.system('calc.exe')`` in a driver reported nothing at all while this
    was unwired, which is the loudest possible way for a flag to be missing.
    """
    from blend_xray import guards, scanner

    explanation = scanner._explain_driver(
        "os.system('calc.exe')", {}, guards.Deadline(guards.Limits().max_seconds)
    )
    assert "x_subprocess" in {st.key for st in explanation.statements}
    assert explanation.alarming is True
