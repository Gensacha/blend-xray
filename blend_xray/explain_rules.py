# SPDX-License-Identifier: GPL-3.0-or-later
"""Rule tables for :mod:`blend_xray.explain`.

Kept separate from the walking logic so a reader auditing "what does Blend X-Ray
consider alarming?" can answer it from one screen of data, without reading any
control flow. Names are matched exactly or as a dotted prefix (``subprocess``
matches ``subprocess.Popen``).
"""

from __future__ import annotations

from typing import Final

# --------------------------------------------------------------------------
# Benign: expected in a legitimate asset or rig file.
# --------------------------------------------------------------------------
BENIGN_IMPORT_OPS: Final[frozenset[str]] = frozenset(
    {
        "bpy.ops.import_scene",
        "bpy.ops.import_mesh",
        "bpy.ops.import_curve",
        "bpy.ops.import_anim",
        "bpy.ops.wm.obj_import",
        "bpy.ops.wm.usd_import",
        "bpy.ops.wm.alembic_import",
        "bpy.ops.wm.stl_import",
        "bpy.ops.wm.ply_import",
        "bpy.ops.wm.gpencil_import_svg",
        "bpy.ops.wm.collada_import",
    }
)

UI_BASES: Final[frozenset[str]] = frozenset(
    {
        "bpy.types.Panel",
        "bpy.types.Operator",
        "bpy.types.Menu",
        "bpy.types.UIList",
        "bpy.types.Header",
        "bpy.types.PropertyGroup",
        "bpy.types.AddonPreferences",
        "bpy.types.NodeTree",
        "bpy.types.Node",
        "Panel",
        "Operator",
        "Menu",
        "PropertyGroup",
    }
)

# --------------------------------------------------------------------------
# Notable: worth showing the user, normal in some add-ons, unusual in a model.
# --------------------------------------------------------------------------
WRITE_CALLS: Final[frozenset[str]] = frozenset(
    {
        "shutil.copy",
        "shutil.copy2",
        "shutil.copyfile",
        "shutil.copytree",
        "shutil.move",
        "os.rename",
        "os.replace",
        "os.write",
        "pathlib.Path.write_text",
        "pathlib.Path.write_bytes",
        "Path.write_text",
        "Path.write_bytes",
        "json.dump",
        "pickle.dump",
        "urllib.request.urlretrieve",
    }
)

DELETE_CALLS: Final[frozenset[str]] = frozenset(
    {
        "os.remove",
        "os.unlink",
        "os.rmdir",
        "os.removedirs",
        "shutil.rmtree",
        "pathlib.Path.unlink",
        "Path.unlink",
    }
)

MAKEDIR_CALLS: Final[frozenset[str]] = frozenset(
    {"os.makedirs", "os.mkdir", "pathlib.Path.mkdir", "Path.mkdir"}
)

# --------------------------------------------------------------------------
# Alarming: surface these first.
# --------------------------------------------------------------------------
#: Modules that open an *outbound* connection. The sentence this drives says
#: "connects to the internet" and puts the file in the RED banner, so nothing
#: belongs here unless importing or calling it can actually open a socket.
#:
#: ``urllib`` (bare) is deliberately absent and must never come back. Matching
#: is exact-or-dotted-prefix, so the bare package name swallows every sibling
#: submodule under it: with ``urllib`` in this set, ``from urllib.parse import
#: quote`` -- percent-encoding a string, no I/O of any kind -- produced
#: "ALARMING x_network | connects to the internet" and the loudest banner the
#: tool has. Only the submodules that actually speak a protocol are listed, so
#: ``urllib.request`` fires and ``urllib.parse`` does not.
#:
#: ``webbrowser`` and ``socketserver`` were moved out of this set into their
#: own rules below; see each one for why.
NETWORK_MODULES: Final[frozenset[str]] = frozenset(
    {
        "requests",
        "urllib2",
        "urllib3",
        "urllib.request",
        "http.client",
        "httplib",
        "httpx",
        "aiohttp",
        "socket",
        "ftplib",
        "telnetlib",
        "smtplib",
        "poplib",
        "imaplib",
        "xmlrpc.client",
        "paramiko",
    }
)

#: Modules whose job is to *listen*, not to dial out.
#:
#: ``socketserver`` used to sit in :data:`NETWORK_MODULES` and print "connects
#: to the internet", which is the wrong direction: a server accepts inbound
#: connections. It stays alarming and stays in the RED set, because a Blender
#: file that opens a port on the artist's machine is reaching outside Blender
#: as surely as one that dials out -- arguably more so. Its sibling stdlib
#: servers are listed with it; leaving them out would have made the corrected
#: rule narrower than the wrong one it replaces.
NETWORK_LISTEN_MODULES: Final[frozenset[str]] = frozenset(
    {
        "socketserver",
        "SocketServer",
        "http.server",
        "BaseHTTPServer",
        "xmlrpc.server",
        "wsgiref.simple_server",
    }
)

#: Handing a URL to the operating system's default browser.
#:
#: ``webbrowser`` used to sit in :data:`NETWORK_MODULES`. It opens no socket:
#: it launches the user's browser on a URL, which is what the "Documentation"
#: button of a great many legitimate add-ons does. That is worth naming --
#: the URL is chosen by the file, and a browser request is a channel out --
#: but it is not "connects to the internet" and it does not deserve RED.
BROWSER_CALLS: Final[frozenset[str]] = frozenset({"webbrowser"})

SUBPROCESS_CALLS: Final[frozenset[str]] = frozenset(
    {
        "subprocess",
        "os.system",
        "os.popen",
        "os.popen2",
        "os.popen3",
        "os.execv",
        "os.execve",
        "os.execl",
        "os.execlp",
        "os.execvp",
        "os.spawnl",
        "os.spawnv",
        "os.startfile",
        "pty.spawn",
        "commands.getoutput",
        "commands.getstatusoutput",
        "multiprocessing.Process",
    }
)

#: Windows binaries repeatedly abused to fetch and run a second stage.
#: Matched case-insensitively against string literals, not against call names.
LIVING_OFF_LAND: Final[frozenset[str]] = frozenset(
    {
        "powershell",
        "pwsh.exe",
        "cmd.exe",
        "cmd /c",
        "cmd /k",
        "curl ",
        "wget ",
        "certutil",
        "bitsadmin",
        "mshta",
        "rundll32",
        "regsvr32",
        "wscript",
        "cscript",
        "schtasks",
        "invoke-webrequest",
        "invoke-expression",
        "downloadstring",
        "-encodedcommand",
        "-windowstyle hidden",
        "/bin/sh",
        "/bin/bash",
        "bash -c",
        "sh -c",
        "osascript",
    }
)

# --------------------------------------------------------------------------
# Dynamic code, split four ways.
#
# One table used to carry all of these under one sentence -- "builds and runs
# code while it executes, so what it does is not visible in the file". That is
# true of exec() and false of everything else that was in it: compile() builds
# and does not run, __import__('os') is an import whose target is written in
# the file in plain sight, and pickle.load() runs whatever a *data file* says.
# Four constructs, four different things to tell a reader, four keys.
# --------------------------------------------------------------------------

#: Builds code at run time *and* runs it. The original sentence is true here
#: and only here.
DYNAMIC_CODE_CALLS: Final[frozenset[str]] = frozenset(
    {
        "exec",
        "eval",
        "types.FunctionType",
        "types.CodeType",
    }
)

#: Turns text or bytes into a code object without running it. Something else
#: has to run the result, and that something else is its own finding.
CODE_BUILD_CALLS: Final[frozenset[str]] = frozenset({"compile", "marshal.loads"})

#: Reconstructs Python objects from a serialised stream. These can execute
#: code as a side effect of loading -- but what executes lives in the data
#: file, not in the script, so the honest sentence names the mechanism and
#: says the payload is somewhere this tool cannot see.
DESERIALISE_CALLS: Final[frozenset[str]] = frozenset(
    {"pickle.load", "pickle.loads", "dill.load", "dill.loads"}
)

#: Imports a module chosen at run time. Whether this hides anything depends
#: entirely on the argument: ``__import__("os")`` names its target in the
#: file, ``__import__(name)`` does not. :class:`blend_xray.explain._Collector`
#: tracks the two separately and they produce different statements.
RUNTIME_IMPORT_CALLS: Final[frozenset[str]] = frozenset(
    {"__import__", "importlib.import_module", "importlib.__import__"}
)

# --------------------------------------------------------------------------
# Obfuscation shapes -- the constructs used to keep a static reader out.
#
# None of these is loud on its own merit; they are loud because they are
# vanishingly rare in real rig code. Measured over the 100 parseable script
# bodies in the two measurement corpora (see README, "Measured on real files"):
# getattr against
# __builtins__, zero; two string literals joined with "+", zero; a call whose
# callee is one of the indirection calls below, zero. The one shape that was
# NOT rare is "a call whose func is any call at all" -- 20 of the 100 bodies,
# because CloudRig writes `type(frames)(...)`. That is why the rule below is
# keyed on the *inner* callee rather than on the shape alone.
# --------------------------------------------------------------------------

#: Names that stand for "the builtins namespace" when reached as a value.
BUILTINS_NAMES: Final[frozenset[str]] = frozenset({"__builtins__", "builtins"})

#: Calls that hand back something else to call or import. Reaching one of
#: these and immediately calling the result is how ``__import__``/``exec``/
#: ``urlopen`` get used without any of their names appearing as a call.
INDIRECTION_CALLS: Final[frozenset[str]] = frozenset(
    {
        "getattr",
        "vars",
        "globals",
        "locals",
        "__import__",
        "importlib.import_module",
        "eval",
        "exec",
        "compile",
    }
)

#: Calls whose *argument* naming something is the whole point, so an argument
#: assembled from concatenated literals is an attempt to keep that name out of
#: any search of the file.
NAME_TAKING_CALLS: Final[frozenset[str]] = frozenset(
    {
        "getattr",
        "setattr",
        "hasattr",
        "__import__",
        "importlib.import_module",
        "importlib.__import__",
        "exec",
        "eval",
        "compile",
    }
)

#: Turning encoded or compressed bytes back into their original form.
#:
#: The table is right; the sentence it used to drive was not. "The content is
#: deliberately hidden and has to be decoded before you can see what it does"
#: was printed for a bare ``zlib.decompress`` of a data blob, which hides
#: nothing and is not code, and it put the file in RED. On its own a decode is
#: NOTABLE and says only what it does. It becomes the RED obfuscation finding
#: when the same body also runs code it built at run time -- decode *plus*
#: execute is the shape the alarming sentence actually describes. See
#: :func:`blend_xray.explain._decode_statements`.
DECODE_CALLS: Final[frozenset[str]] = frozenset(
    {
        "base64.b64decode",
        "base64.b32decode",
        "base64.b16decode",
        "base64.b85decode",
        "base64.a85decode",
        "base64.decodebytes",
        "base64.decodestring",
        "base64.urlsafe_b64decode",
        "codecs.decode",
        "bytes.fromhex",
        "binascii.unhexlify",
        "binascii.a2b_base64",
        "zlib.decompress",
        "bz2.decompress",
        "lzma.decompress",
        "gzip.decompress",
    }
)

LOWLEVEL_MODULES: Final[frozenset[str]] = frozenset(
    {
        "ctypes",
        "cffi",
        "win32api",
        "win32com",
        "win32file",
        "win32process",
        "win32security",
        "pywintypes",
        "mmap",
    }
)

#: Substrings that indicate the script arranges to run again later.
#: Matched against lower-cased string literals.
#:
#: Deliberately specific. Bare "appdata" or "startup" fire on ordinary add-on
#: code that caches files or names a function `startup`, and a false alarm here
#: teaches the user to ignore the tool -- which is the exact failure mode
#: Blend X-Ray exists to avoid.
PERSISTENCE_MARKERS: Final[tuple[str, ...]] = (
    "start menu\\programs\\startup",
    "start menu/programs/startup",
    "currentversion\\run",
    "currentversion/run",
    "software\\microsoft\\windows\\currentversion\\run",
    ".config/autostart",
    "library/launchagents",
    "library/launchdaemons",
    "launchagents",
    "launchdaemons",
    "crontab",
    "/etc/cron",
    "systemd/user",
    "com.apple.loginitems",
    "schtasks",
    "/create /sc",
)

#: Substrings that indicate the script reads secret stores.
CREDENTIAL_MARKERS: Final[tuple[str, ...]] = (
    "login data",
    "cookies.sqlite",
    "logins.json",
    "key4.db",
    "key3.db",
    "signons.sqlite",
    "wallet.dat",
    "/.ssh",
    "\\.ssh",
    "id_rsa",
    "keychain",
    "user data\\default",
    "user data/default",
    "\\mozilla\\firefox\\profiles",
    "/mozilla/firefox/profiles",
    "google\\chrome\\user data",
    "browsermetrics",
    "credentials.json",
    ".aws/credentials",
    "metamask",
    "exodus\\exodus",
    "electrum",
    "keystore",
)

#: A bare dotted string is only reported as a host name when its last label is
#: one of these. Without this allow-list, ordinary literals like "rig.snap",
#: "out.bin" or "mesh.data" get reported as network hosts, and a tool that
#: cries wolf gets ignored. Full URLs are matched separately and do not depend
#: on this list, so a host on an exotic TLD is still caught inside a URL.
KNOWN_TLDS: Final[frozenset[str]] = frozenset(
    {
        # generic
        "com",
        "net",
        "org",
        "info",
        "biz",
        "edu",
        "gov",
        "mil",
        "int",
        "io",
        "co",
        "ai",
        "app",
        "dev",
        "xyz",
        "top",
        "site",
        "online",
        "shop",
        "store",
        "live",
        "life",
        "world",
        "space",
        "website",
        "tech",
        "cloud",
        "digital",
        "link",
        "click",
        "download",
        "stream",
        "host",
        "press",
        "news",
        "blog",
        "wiki",
        "zone",
        "systems",
        "network",
        # commonly abused
        "tk",
        "ml",
        "ga",
        "cf",
        "gq",
        "pw",
        "cc",
        "ws",
        "su",
        "buzz",
        "icu",
        "cyou",
        "quest",
        "monster",
        "bond",
        "sbs",
        "rest",
        "fun",
        "work",
        "loan",
        "men",
        "date",
        "party",
        "review",
        "trade",
        "science",
        "racing",
        # country codes seen in asset-marketplace traffic
        "uk",
        "de",
        "fr",
        "nl",
        "es",
        "it",
        "pl",
        "ru",
        "ua",
        "cn",
        "jp",
        "kr",
        "in",
        "br",
        "mx",
        "ca",
        "au",
        "nz",
        "za",
        "tr",
        "ir",
        "vn",
        "id",
        "th",
        "ph",
        "my",
        "sg",
        "hk",
        "tw",
        "se",
        "no",
        "fi",
        "dk",
        "cz",
        "sk",
        "hu",
        "ro",
        "bg",
        "gr",
        "pt",
        "be",
        "ch",
        "at",
        "ie",
        "us",
        "tv",
        "me",
        "eu",
        "asia",
    }
)

#: Extensions that must NOT be mistaken for a hostname's TLD.
FILE_EXTENSION_BLOCKLIST: Final[frozenset[str]] = frozenset(
    {
        "py",
        "pyc",
        "pyd",
        "pyo",
        "txt",
        "md",
        "rst",
        "json",
        "xml",
        "yaml",
        "yml",
        "obj",
        "fbx",
        "abc",
        "usd",
        "usda",
        "usdc",
        "usdz",
        "stl",
        "ply",
        "gltf",
        "glb",
        "dae",
        "blend",
        "blend1",
        "exr",
        "png",
        "jpg",
        "jpeg",
        "tif",
        "tiff",
        "tga",
        "bmp",
        "hdr",
        "webp",
        "mp3",
        "wav",
        "ogg",
        "flac",
        "mp4",
        "mov",
        "avi",
        "mkv",
        "zip",
        "tar",
        "gz",
        "bz2",
        "xz",
        "7z",
        "rar",
        "csv",
        "log",
        "ini",
        "cfg",
        "conf",
        "toml",
        "html",
        "htm",
        "css",
        "js",
        "ts",
        "so",
        "dll",
        "dylib",
        "osl",
        "oso",
        "osotmp",
        "sqlite",
        "db",
        "bak",
        "tmp",
        "cache",
        "lock",
        "sh",
        "bat",
        "ps1",
        "cmd",
        "vbs",
        "self",
        "types",
        "ops",
        "utils",
        "context",
        "data",
        "app",
        "handlers",
    }
)
