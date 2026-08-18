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

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Footer, Header, Markdown, TextArea

try:
    from textual_image.widget import Image
except Exception:
    Image = None

# Eine Zeile, die nur aus einem Bild-Link besteht: ![Alt](pfad)
IMAGE_LINE = re.compile(r"^\s*!\[[^\]]*\]\(([^)\s]+)\)\s*$")

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
        border-left: solid $primary;
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
                img_path = (base / match.group(1)).expanduser()
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
