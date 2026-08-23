# SPDX-License-Identifier: GPL-3.0-or-later
"""Two calls in one file are not a link between them.

``x_obfuscation`` required a decode *and* dynamic code execution in the same
body, and then treated their co-occurrence as proof that one fed the other. On
``Sandman13sq/DmrVBM-blender-to-gms2`` -- found by the 677-file corpus campaign
-- the ``exec()`` is real and the ``zlib`` calls are real, and they have
nothing to do with each other: the ``zlib`` calls compress mesh and image data
on the way into a game-engine format. The file was escalated to RED and an
artist was told its content was "deliberately hidden".

The rule now establishes the relationship instead of assuming it: the decoded
value has to reach the call that runs code, directly or through one binding.
Nothing is silenced when no link is found -- ``exec`` stays ALARMING under
``x_dynamic_code`` and the decode stays NOTABLE under ``x_decodes_data``. What
the file no longer gets is a sentence claiming the two are one hidden payload.

Every sample is written here by hand. Nothing is fetched, nothing is executed.
"""

from __future__ import annotations

import pytest

from blend_xray import explain, strings_en, strings_fr
from blend_xray.banner import REACHES_OUTSIDE_KEYS
from blend_xray.explain import Severity


def keys_of(source: str) -> set[str]:
    return {st.key for st in explain.explain_source(source).statements}


# ==========================================================================
# 1. The reproduction: unrelated compression, unrelated exec.
# ==========================================================================
#: The DmrVBM shape -- zlib on mesh and image payloads, an exec elsewhere that
#: never touches either.
UNRELATED_ZLIB_AND_EXEC = """
import bpy
import zlib

def read_mesh(stream):
    return zlib.decompress(stream.read())

def read_image(stream):
    return zlib.decompress(stream.read())

def make_props(names):
    for name in names:
        exec("bpy.types.Object." + name + " = bpy.props.FloatProperty()")
"""


def test_unrelated_decode_and_exec_do_not_claim_hiding() -> None:
    keys = keys_of(UNRELATED_ZLIB_AND_EXEC)
    assert "x_obfuscation" not in keys


def test_neither_half_is_silenced_by_dropping_the_link() -> None:
    """The honest outcome is two separate findings, not one merged claim."""
    statements = explain.explain_source(UNRELATED_ZLIB_AND_EXEC).statements
    by_key = {st.key: st for st in statements}
    assert by_key["x_dynamic_code"].severity is Severity.ALARMING
    assert by_key["x_decodes_data"].severity is Severity.NOTABLE


def test_the_unlinked_pairing_no_longer_spends_the_red_banner() -> None:
    """``x_dynamic_code`` is deliberately outside the RED set; this was inside it."""
    assert not (keys_of(UNRELATED_ZLIB_AND_EXEC) & REACHES_OUTSIDE_KEYS)


def test_the_unlinked_pairing_does_not_call_the_listing_incomplete() -> None:
    """``obfuscated`` makes the report say it could not see everything."""
    assert explain.explain_source(UNRELATED_ZLIB_AND_EXEC).obfuscated is False


# ==========================================================================
# 2. A real link still fires, through every hop the rule promises.
# ==========================================================================
DIRECT = "import base64\nexec(base64.b64decode('cHJpbnQoMSk='))\n"

ONE_BINDING = """
import base64
payload = base64.b64decode('cHJpbnQoMSk=')
exec(payload)
"""

DECODE_CHAIN = """
import base64
import zlib
code = zlib.decompress(base64.b64decode(BLOB)).decode('utf-8')
exec(code)
"""

NESTED_IN_COMPILE = """
import base64
blob = base64.b64decode('cHJpbnQoMSk=')
exec(compile(blob, '<s>', 'exec'))
"""

ALIASED_EXEC = """
import base64
e = exec
e(base64.b64decode('cHJpbnQoMSk='))
"""

EVAL_KEYWORD_ARG = """
import base64
eval(base64.b64decode('MQ=='), {}, {})
"""

#: How a class writes it. Restricting the binding hop to a bare local name
#: dropped this from RED to AMBER on the most ordinary shape there is.
ATTRIBUTE_BINDING = """
import base64

class Loader:
    def prepare(self):
        self.payload = base64.b64decode('cHJpbnQoMSk=')

    def run(self):
        exec(self.payload)
"""

MULTI_TARGET_BINDING = """
import base64
a = b = base64.b64decode('cHJpbnQoMSk=')
exec(b)
"""

ANNOTATED_BINDING = """
import base64
payload: bytes = base64.b64decode('cHJpbnQoMSk=')
exec(payload)
"""


@pytest.mark.parametrize(
    "source",
    [
        DIRECT,
        ONE_BINDING,
        DECODE_CHAIN,
        NESTED_IN_COMPILE,
        ALIASED_EXEC,
        EVAL_KEYWORD_ARG,
        ATTRIBUTE_BINDING,
        MULTI_TARGET_BINDING,
        ANNOTATED_BINDING,
    ],
)
def test_a_decoded_value_that_reaches_the_run_is_still_alarming(source: str) -> None:
    statements = explain.explain_source(source).statements
    hit = next(st for st in statements if st.key == "x_obfuscation")
    assert hit.severity is Severity.ALARMING


@pytest.mark.parametrize("source", [DIRECT, ONE_BINDING, DECODE_CHAIN])
def test_the_established_link_is_in_the_evidence(source: str) -> None:
    """A reader must be able to check the claim, not just read it."""
    statements = explain.explain_source(source).statements
    hit = next(st for st in statements if st.key == "x_obfuscation")
    assert any("then exec" in item for item in hit.evidence)


@pytest.mark.parametrize(
    "source", [DIRECT, ATTRIBUTE_BINDING, MULTI_TARGET_BINDING, ANNOTATED_BINDING]
)
def test_the_linked_case_still_spends_the_red_banner(source: str) -> None:
    assert "x_obfuscation" in keys_of(source) & REACHES_OUTSIDE_KEYS


def test_a_target_this_cannot_name_is_a_stated_limit_not_a_silence() -> None:
    """``d['payload']`` is past what one hop of binding can follow.

    The finding drops to the two honest halves rather than to nothing: the
    ``exec`` stays ALARMING and the decode stays NOTABLE. Pinned so the limit
    is a decision on the record, not something a later reader discovers.
    """
    source = (
        "import base64\n"
        "store = {}\n"
        "store['payload'] = base64.b64decode('cHJpbnQoMSk=')\n"
        "exec(store['payload'])\n"
    )
    keys = keys_of(source)
    assert "x_obfuscation" not in keys
    assert "x_dynamic_code" in keys
    assert "x_decodes_data" in keys


def test_two_bindings_away_is_not_claimed_as_a_link() -> None:
    """The rule promises one hop. Past that it says less, and says so.

    The file is still ALARMING on ``x_dynamic_code``; what it does not get is
    the "hidden payload" sentence on a chain this analysis did not follow.
    """
    source = (
        "import base64\n"
        "first = base64.b64decode('cHJpbnQoMSk=')\n"
        "second = first\n"
        "exec(second)\n"
    )
    keys = keys_of(source)
    assert "x_obfuscation" not in keys
    assert "x_dynamic_code" in keys


# ==========================================================================
# 3. The sentence must not outrun what was established.
# ==========================================================================
def test_the_sentence_describes_the_decode_reaching_the_run() -> None:
    statements = explain.explain_source(DIRECT).statements
    hit = next(st for st in statements if st.key == "x_obfuscation")
    assert "runs the result as code" in hit.text


@pytest.mark.parametrize("catalogue", [strings_en.EN, strings_fr.FR], ids=["en", "fr"])
def test_no_language_still_asserts_deliberate_hiding(catalogue: dict[str, str]) -> None:
    """Both catalogues had to move; a stale French sentence is still a claim."""
    for key in ("x_obfuscation", "banner_what_x_obfuscation"):
        text = catalogue[key]
        assert "deliberately hidden" not in text
        assert "délibérément dissimulé" not in text
