#!/usr/bin/env python3
"""notiz – Markdown-Notizen im Terminal.

Editor links (normale Navigation, kein Vim), Live-Vorschau rechts
mit gerenderten Tabellen und Bildern.

Aufruf:  note [datei]   – ohne Endung wird .md angehängt,
                          die Datei wird angelegt, falls sie fehlt.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from rich.style import Style
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.theme import Theme
from textual.widgets import Footer, Header, Markdown, TextArea
from textual.widgets.text_area import TextAreaTheme

try:
    from textual_image.widget import Image
except Exception:
    Image = None

# Eine Zeile, die nur aus einem Bild-Link besteht: ![Alt](pfad)
# Leerzeichen im Pfad sind erlaubt, optional in <spitzen Klammern>.
IMAGE_LINE = re.compile(r"^\s*!\[[^\]]*\]\(<?([^)>]+)>?\)\s*$")

LIGHT_THEME = Theme(
    name="notiz-light",
    primary="#5a5a5a",
    secondary="#7a7a7a",
    accent="#3a3a3a",
    foreground="#1f1f1f",
    background="#f5f5f5",
    surface="#ffffff",
    panel="#ececec",
    success="#4a4a4a",
    warning="#6a6a6a",
    error="#8b3a3a",
    dark=False,
)

EDITOR_THEME = TextAreaTheme(
    name="notiz-light",
    base_style=Style(color="#1f1f1f", bgcolor="#ffffff"),
    gutter_style=Style(color="#b5b5b5", bgcolor="#f5f5f5"),
    cursor_style=Style(color="#ffffff", bgcolor="#1f1f1f"),
    cursor_line_style=Style(bgcolor="#f2f2f2"),
    cursor_line_gutter_style=Style(color="#8a8a8a", bgcolor="#f2f2f2"),
    selection_style=Style(bgcolor="#dcdcdc"),
    bracket_matching_style=Style(bgcolor="#e4e4e4", bold=True),
    syntax_styles={
        "heading": Style(color="#111111", bold=True),
        "bold": Style(color="#1f1f1f", bold=True),
        "italic": Style(color="#1f1f1f", italic=True),
        "link": Style(color="#4a4a4a", underline=True),
        "inline_code": Style(color="#333333", bgcolor="#efefef"),
        "punctuation.special": Style(color="#9a9a9a"),
        "punctuation.delimiter": Style(color="#9a9a9a"),
        "punctuation.bracket": Style(color="#9a9a9a"),
        "string": Style(color="#4a4a4a"),
        "comment": Style(color="#9a9a9a", italic=True),
    },
)

TABLE_SNIPPET = (
    "\n| Spalte 1 | Spalte 2 |\n"
    "|----------|----------|\n"
    "|          |          |\n\n"
)

IMAGE_SNIPPET = "\n![Beschreibung](bild.png)\n"


class NotizApp(App):
    CSS = """
    #editor {
        width: 1fr;
    }
    #preview {
        width: 1fr;
        background: $surface;
        border-left: solid $panel;
        padding: 0 1;
    }
    #preview.hidden {
        display: none;
    }
    #preview Markdown {
        margin: 0;
        padding: 0;
    }
    .note-image {
        height: 18;
        width: auto;
        margin: 1 0;
    }
    """

    BINDINGS = [
        Binding("ctrl+s", "save", "Speichern"),
        Binding("ctrl+r", "toggle_preview", "Vorschau an/aus"),
        Binding("ctrl+t", "insert_table", "Tabelle einfügen"),
        Binding("ctrl+g", "insert_image", "Bild-Link einfügen"),
        Binding("ctrl+q", "quit_save", "Speichern & Beenden"),
    ]

    def __init__(self, note_path: Path) -> None:
        super().__init__()
        self.note_path = note_path
        self.dirty = False

    # ---------- Aufbau ----------

    def compose(self) -> ComposeResult:
        text = ""
        if self.note_path.exists():
            text = self.note_path.read_text(encoding="utf-8")
        editor = TextArea.code_editor(text, id="editor", soft_wrap=True)
        try:
            editor.language = "markdown"
        except Exception:
            pass
        yield Header()
        with Horizontal():
            yield editor
            yield VerticalScroll(id="preview")
        yield Footer()

    def on_mount(self) -> None:
        self.register_theme(LIGHT_THEME)
        self.theme = "notiz-light"
        editor = self.query_one("#editor", TextArea)
        editor.register_theme(EDITOR_THEME)
        editor.theme = "notiz-light"
        self._update_title()
        self.run_worker(self._render_preview(), exclusive=True, group="preview")

    # ---------- Vorschau ----------

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self.dirty = True
        self._update_title()
        # Debounce: erst rendern, wenn 0.5s nicht getippt wurde
        if getattr(self, "_timer", None):
            self._timer.stop()
        self._timer = self.set_timer(0.5, self._schedule_render)

    def _schedule_render(self) -> None:
        self.run_worker(self._render_preview(), exclusive=True, group="preview")

    async def _render_preview(self) -> None:
        preview = self.query_one("#preview", VerticalScroll)
        text = self.query_one("#editor", TextArea).text
        base = self.note_path.parent

        widgets = []
        buffer: list[str] = []

        def flush() -> None:
            if buffer:
                widgets.append(Markdown("\n".join(buffer)))
                buffer.clear()

        for line in text.splitlines():
            match = IMAGE_LINE.match(line)
            if match and Image is not None and "://" not in match.group(1):
                raw = match.group(1).strip().replace("\\ ", " ")
                img_path = (base / raw).expanduser()
                if img_path.is_file():
                    flush()
                    image = Image(str(img_path))
                    image.add_class("note-image")
                    widgets.append(image)
                    continue
            buffer.append(line)
        flush()

        scroll_y = preview.scroll_y
        await preview.remove_children()
        if widgets:
            await preview.mount(*widgets)
        preview.scroll_to(y=scroll_y, animate=False)

    # ---------- Aktionen ----------

    def action_save(self) -> None:
        text = self.query_one("#editor", TextArea).text
        self.note_path.parent.mkdir(parents=True, exist_ok=True)
        self.note_path.write_text(text, encoding="utf-8")
        self.dirty = False
        self._update_title()
        self._schedule_render()
        self.notify(f"Gespeichert: {self.note_path.name}", timeout=2)

    def action_toggle_preview(self) -> None:
        self.query_one("#preview").toggle_class("hidden")

    def action_insert_table(self) -> None:
        self.query_one("#editor", TextArea).insert(TABLE_SNIPPET)

    def action_insert_image(self) -> None:
        self.query_one("#editor", TextArea).insert(IMAGE_SNIPPET)

    def action_quit_save(self) -> None:
        if self.dirty:
            self.action_save()
        self.exit()

    def _update_title(self) -> None:
        marker = " ●" if self.dirty else ""
        self.title = f"notiz – {self.note_path.name}{marker}"


def resolve_note_path(arg: str) -> Path:
    path = Path(arg).expanduser()
    if not path.suffix:
        path = path.with_suffix(".md")
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()
    return path


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else "Notizen.md"
    NotizApp(resolve_note_path(arg)).run()


if __name__ == "__main__":
    main()
