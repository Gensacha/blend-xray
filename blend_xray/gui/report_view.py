# SPDX-License-Identifier: GPL-3.0-or-later
"""The scrollable report area: draws :mod:`blend_xray.gui.render` elements.

Raw source is inserted into the same Text widget as everything else but under
an *elided* tag, so it occupies no space until the reader asks for it. That is
the whole trick behind the collapse toggle -- the text is present (and so is
copied, searched and selected with the rest) without dominating the screen.

Indentation is a *tag*, not leading spaces, because the widget wraps on word
boundaries: see :data:`blend_xray.gui.theme.INDENT_PIXELS`. Section rules are
drawn as a one-pixel frame sized to the window rather than written as dashes,
for the same reason the CLI's ASCII box is not reproduced here -- a fixed
character count stops in the middle of a proportional-font window.

Nothing in here decides *what* to say; that is :mod:`blend_xray.gui.render`.
This module only knows about colours, fonts and widgets.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from .. import strings
from .render import Element, Line, Separator, Source, plain_text
from .theme import (
    COLOURS,
    MAX_INDENT_LEVEL,
    MONO_FAMILY,
    MONO_SIZE,
    TAG_SOURCE,
    TAG_STYLES,
    UI_FAMILY,
    UI_SIZE,
    indent_margins,
    indent_tag,
)

#: Horizontal padding inside the Text widget, mirrored when sizing a rule.
TEXT_PAD: int = 14


class ReportView(ttk.Frame):
    """A read-only Text widget with tagged colours and collapsible sources."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self._elements: list[Element] = []
        self._collapsed: dict[str, bool] = {}
        self._next_source_id = 0
        self._rules: list[tk.Frame] = []

        self._ui_font = tkfont.Font(family=UI_FAMILY, size=UI_SIZE)
        self._mono_font = tkfont.Font(family=MONO_FAMILY, size=MONO_SIZE)

        self.text = tk.Text(
            self,
            wrap="word",
            font=self._ui_font,
            background=COLOURS["surface"],
            foreground=COLOURS["foreground"],
            relief="flat",
            padx=TEXT_PAD,
            pady=10,
            spacing1=1,
            spacing3=2,
            insertwidth=0,
            highlightthickness=0,
        )
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self._configure_tags()
        self.text.configure(state="disabled")
        self.text.bind("<Configure>", self._on_resize)

    def _configure_tags(self) -> None:
        for tag, (role, bold) in TAG_STYLES.items():
            font = tkfont.Font(font=self._ui_font)
            font.configure(weight="bold" if bold else "normal")
            if tag == TAG_SOURCE:
                font = self._mono_font
            self.text.tag_configure(tag, foreground=COLOURS[role], font=font)
        self.text.tag_configure(
            TAG_SOURCE,
            background=COLOURS["source_background"],
            spacing1=0,
            spacing3=0,
        )
        # Configured after the style tags and never overlapping their options,
        # so the two sets compose instead of competing. lmargin2 is what keeps
        # a wrapped evidence line under its statement instead of back at the
        # left edge; see theme.INDENT_PIXELS.
        for level in range(MAX_INDENT_LEVEL + 1):
            self.text.tag_configure(indent_tag(level), **indent_margins(level))

    # -- content ------------------------------------------------------------
    def clear(self) -> None:
        """Drop every element, widget and tag from a previous scan."""
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        for rule in self._rules:
            rule.destroy()
        self._rules = []
        self._elements = []
        self._collapsed = {}
        self._next_source_id = 0

    def append(self, elements: list[Element]) -> None:
        """Draw more elements at the end, keeping what is already there.

        Lines are inserted without their leading spaces: the indent is carried
        by a tag so that it survives word wrapping. ``Line.rendered()`` keeps
        the spaces for :meth:`plain_text`, where they are the only indent a
        clipboard paste has.
        """
        self._elements.extend(elements)
        self.text.configure(state="normal")
        for element in elements:
            if isinstance(element, Source):
                self._insert_source(element)
            elif isinstance(element, Separator):
                self._insert_rule()
            else:
                tags = (element.tag, indent_tag(element.indent))
                self.text.insert("end", element.text + "\n", tags)
        self.text.configure(state="disabled")

    def _insert_rule(self) -> None:
        """A one-pixel line that spans the window, however wide it becomes."""
        rule = tk.Frame(self.text, height=1, background=COLOURS["border"])
        self.text.window_create("end", window=rule, pady=5)
        self.text.insert("end", "\n")
        self._rules.append(rule)
        self._size_rule(rule)

    def _size_rule(self, rule: tk.Frame) -> None:
        rule.configure(width=max(80, self.text.winfo_width() - 2 * TEXT_PAD - 4))

    def _on_resize(self, _event: object = None) -> None:
        for rule in self._rules:
            self._size_rule(rule)

    def _insert_source(self, source: Source) -> None:
        """A toggle button, then the body hidden behind an elided tag."""
        self._next_source_id += 1
        tag = f"src{self._next_source_id}"
        lines = len(source.body.splitlines()) or 1

        button = ttk.Button(self.text)
        button.configure(command=lambda: self._toggle(tag, button, lines))
        self.text.insert("end", " ", indent_tag(source.indent))
        self.text.window_create("end", window=button, padx=2, pady=2)
        self.text.insert("end", "\n")

        self.text.insert(
            "end", source.body.rstrip("\n") + "\n", (TAG_SOURCE, indent_tag(source.indent), tag)
        )
        self._collapsed[tag] = True
        self.text.tag_configure(tag, elide=True)
        button.configure(text=strings.t("gui_source_show", lines=lines))

    def _toggle(self, tag: str, button: ttk.Button, lines: int) -> None:
        collapsed = not self._collapsed.get(tag, True)
        self._collapsed[tag] = collapsed
        self.text.tag_configure(tag, elide=collapsed)
        key = "gui_source_show" if collapsed else "gui_source_hide"
        button.configure(text=strings.t(key, lines=lines))

    def plain_text(self) -> str:
        """Everything currently drawn, sources expanded, for the clipboard."""
        return plain_text(self._elements)

    def has_content(self) -> bool:
        return bool(self._elements)

    def show_message(self, message: str, tag: str) -> None:
        """Replace the whole view with a single line -- used for idle and errors."""
        self.clear()
        self.append([Line(message, tag)])
