#!/usr/bin/env python3
"""notiz – Markdown-Notizen im Terminal.

Editor links (normale Navigation, kein Vim), Live-Vorschau rechts
mit gerenderten Tabellen und Bildern.

Aufruf:  note [datei]   – ohne Endung wird .md angehängt,
                          die Datei wird angelegt, falls sie fehlt.
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from rich.style import Style
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.theme import Theme
from textual.widgets import Footer, Header, Markdown, Static, TextArea
from textual.widgets.text_area import Selection, TextAreaTheme

try:
    from textual_image.renderable import Image as _ImageRenderable
    from textual_image.widget import Image
except Exception:
    Image = None

if Image is not None:

    class NoteImage(Image, Renderable=_ImageRenderable):
        """Vorschau-Bild; Klick öffnet die Datei in voller Qualität."""

        def __init__(self, path: Path) -> None:
            super().__init__(str(path))
            self._img_path = path
            self.tooltip = "Klicken: Bild in voller Qualität öffnen"

        def on_click(self, event: events.Click) -> None:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, str(self._img_path)])

else:
    NoteImage = None

# Eine Zeile, die nur aus einem Bild-Link besteht: ![Titel](pfad)
# Leerzeichen im Pfad sind erlaubt, optional in <spitzen Klammern>.
IMAGE_LINE = re.compile(r"^\s*!\[([^\]]*)\]\(<?([^)>]+)>?\)\s*$")
IMAGE_LINK = re.compile(r"^(\s*)!\[([^\]]*)\]\([^)]*\)\s*$")
TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
SEP_CELL = re.compile(r":?-+:?")

# Formate, die PIL/textual-image sicher rendern kann
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

# Ein nackter Bildpfad im Text, z.B. per Drag & Drop aus dem Finder getippt.
# Leerzeichen u.ä. kommen von Apple Terminal backslash-escaped an.
BARE_IMAGE_PATH = re.compile(
    r"(?:\\.|[^\s|()\[\]<>])+\.(?:png|jpe?g|gif|webp|bmp)", re.IGNORECASE
)
MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")

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
    "\n|     |     |\n"
    "|-----|-----|\n"
    "|     |     |\n"
)

IMAGE_SNIPPET = "\n![Beschreibung](bild.png)"


class NoteEditor(TextArea):
    """TextArea, die gedroppte Bilddateien als Markdown-Link einfügt."""

    async def _on_paste(self, event: events.Paste) -> None:
        app = self.app
        if isinstance(app, NotizApp) and app.handle_image_drop(self, event.text):
            event.stop()
            return
        await super()._on_paste(event)


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
        margin: 1 0 0 0;
    }
    .image-caption {
        color: $secondary;
        text-style: italic;
        margin: 0 0 1 0;
    }
    """

    # super+X = Cmd-Taste; funktioniert nur in Terminals, die Cmd durchreichen
    # (Ghostty, kitty, WezTerm) – Apple Terminal fängt Cmd selbst ab.
    BINDINGS = [
        Binding("ctrl+s,super+s", "save", "Speichern"),
        Binding("ctrl+r,super+r", "toggle_preview", "Vorschau"),
        Binding("ctrl+t,super+t", "insert_table", "Tabelle"),
        Binding("ctrl+n,super+n", "add_table_row", "+Zeile"),
        Binding("ctrl+o,super+o", "remove_table_row", "−Zeile"),
        Binding("ctrl+b,super+b", "add_table_column", "+Spalte"),
        Binding("ctrl+f,super+f", "remove_table_column", "−Spalte"),
        Binding("ctrl+g,super+g", "insert_image", "Bild"),
        Binding("ctrl+q,super+q", "quit_save", "Beenden"),
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
        editor = NoteEditor.code_editor(text, id="editor", soft_wrap=True)
        try:
            editor.language = "markdown"
        except Exception:
            pass
        # Vorschau darf keinen Fokus bekommen, sonst landen Tastatur-
        # eingaben (auch Drag & Drop-Pfade) nicht im Editor.
        preview = VerticalScroll(id="preview")
        preview.can_focus = False
        yield Header()
        with Horizontal():
            yield editor
            yield preview
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
        editor = self._editor()
        self._auto_link_images(editor)
        self._format_table(editor)
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
            if match and Image is not None and "://" not in match.group(2):
                raw = match.group(2).strip().replace("\\ ", " ")
                img_path = (base / raw).expanduser()
                if img_path.is_file() and img_path.suffix.lower() in IMAGE_EXTS:
                    flush()
                    image = NoteImage(img_path)
                    image.add_class("note-image")
                    widgets.append(image)
                    title = match.group(1).strip()
                    if title:
                        widgets.append(Static(title, classes="image-caption"))
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
        editor = self._editor()
        row = editor.cursor_location[0]
        editor.insert(TABLE_SNIPPET)
        # Cursor in die erste Zelle der neuen Tabelle
        editor.move_cursor((row + 1, 2))

    def action_insert_image(self) -> None:
        """Fügt ein Bild ein: kopierte Datei oder Screenshot aus der
        Zwischenablage; sonst die Link-Vorlage."""
        editor = self._editor()
        clip_file = self._clipboard_file_path()
        if clip_file is not None and clip_file.suffix.lower() in IMAGE_EXTS:
            self._insert_image_link(editor, clip_file)
            self.notify(f"Verlinkt: {clip_file.name}", timeout=3)
            return
        dest_dir = self.note_path.parent / "bilder"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"bild-{datetime.now():%Y%m%d-%H%M%S}.png"
        if self._clipboard_png_to(dest):
            self._insert_image_link(editor, dest)
            self.notify(f"Screenshot gespeichert: bilder/{dest.name}", timeout=3)
            return
        try:
            dest_dir.rmdir()  # nur entfernen, wenn leer angelegt
        except OSError:
            pass
        editor.insert(IMAGE_SNIPPET)

    @staticmethod
    def _clipboard_file_path() -> Path | None:
        """Pfad einer im Finder kopierten Datei, sonst None."""
        try:
            result = subprocess.run(
                ["osascript", "-e", "POSIX path of (the clipboard as «class furl»)"],
                capture_output=True, text=True, timeout=3,
            )
        except Exception:
            return None
        if result.returncode != 0:
            return None
        path = Path(result.stdout.strip())
        return path if path.is_file() else None

    @staticmethod
    def _clipboard_png_to(dest: Path) -> bool:
        """Schreibt Bilddaten aus der Zwischenablage (z.B. Screenshot) als PNG."""
        script = (
            f'set outFile to (open for access POSIX file "{dest}" with write permission)\n'
            "try\n"
            "    write (the clipboard as «class PNGf») to outFile\n"
            "    close access outFile\n"
            "on error\n"
            "    close access outFile\n"
            "    error\n"
            "end try\n"
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script], capture_output=True, timeout=5
            )
        except Exception:
            result = None
        ok = (
            result is not None
            and result.returncode == 0
            and dest.is_file()
            and dest.stat().st_size > 0
        )
        if not ok and dest.exists():
            dest.unlink()
        return ok

    def _insert_image_link(self, editor: TextArea, path: Path) -> None:
        path = path.resolve()
        try:
            link = str(path.relative_to(self.note_path.parent.resolve()))
        except ValueError:
            link = str(path)
        row, col = editor.cursor_location
        line = editor.document.get_line(row)
        prefix = "" if not line.strip() else "\n"
        editor.insert(f"{prefix}![{path.stem}]({link})")
        if prefix:
            self._select_title(editor, row + 1, 2, path.stem)
        else:
            self._select_title(editor, row, col + 2, path.stem)

    # ---------- Tabellen ----------

    def _editor(self) -> TextArea:
        return self.query_one("#editor", TextArea)

    def _table_bounds(self, editor: TextArea) -> tuple[int, int] | None:
        doc = editor.document
        row = editor.cursor_location[0]
        if not TABLE_ROW.match(doc.get_line(row)):
            return None
        start = row
        while start > 0 and TABLE_ROW.match(doc.get_line(start - 1)):
            start -= 1
        end = row
        while end < doc.line_count - 1 and TABLE_ROW.match(doc.get_line(end + 1)):
            end += 1
        return start, end

    def _table_or_warn(self, editor: TextArea) -> tuple[int, int] | None:
        bounds = self._table_bounds(editor)
        if bounds is None:
            self.notify("Cursor steht in keiner Tabelle", severity="warning", timeout=3)
        return bounds

    @staticmethod
    def _cells(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]

    @classmethod
    def _is_separator(cls, line: str) -> bool:
        cells = cls._cells(line)
        return bool(cells) and all(SEP_CELL.fullmatch(c) for c in cells)

    def action_add_table_row(self) -> None:
        editor = self._editor()
        if (bounds := self._table_or_warn(editor)) is None:
            return
        start, end = bounds
        cols = len(self._cells(editor.document.get_line(start)))
        last = editor.document.get_line(end)
        editor.insert("\n|" + "   |" * cols, (end, len(last)))
        self._format_table(editor)

    def action_remove_table_row(self) -> None:
        editor = self._editor()
        if self._table_or_warn(editor) is None:
            return
        doc = editor.document
        row = editor.cursor_location[0]
        if row + 1 < doc.line_count:
            editor.replace("", (row, 0), (row + 1, 0))
        elif row > 0:
            editor.replace("", (row - 1, len(doc.get_line(row - 1))), (row, len(doc.get_line(row))))
        else:
            editor.replace("", (row, 0), (row, len(doc.get_line(row))))

    def _change_table_columns(self, delta: int) -> None:
        editor = self._editor()
        if (bounds := self._table_or_warn(editor)) is None:
            return
        start, end = bounds
        doc = editor.document
        lines = [doc.get_line(i) for i in range(start, end + 1)]
        if delta < 0 and len(self._cells(lines[0])) <= 1:
            self.notify("Nur noch eine Spalte", severity="warning", timeout=3)
            return
        new_lines = []
        for line in lines:
            stripped = line.rstrip()
            if not stripped.endswith("|"):
                stripped += " |"
            if delta > 0:
                stripped += "---|" if self._is_separator(stripped) else "   |"
            else:
                body = stripped[:-1]
                stripped = body[: body.rfind("|") + 1]
            new_lines.append(stripped)
        editor.replace("\n".join(new_lines), (start, 0), (end, len(lines[-1])))
        self._format_table(editor)

    def action_add_table_column(self) -> None:
        self._change_table_columns(1)

    def action_remove_table_column(self) -> None:
        self._change_table_columns(-1)

    @staticmethod
    def _cell_cursor(line: str, col: int) -> tuple[int, int]:
        """Liefert (Zellenindex, Offset im Zelleninhalt) für eine Cursorspalte."""
        pipes = [i for i, ch in enumerate(line) if ch == "|"]
        if not pipes:
            return 0, 0
        cell = 0
        for n, p in enumerate(pipes):
            if col > p:
                cell = n
        cell = min(cell, len(pipes) - 1)
        inner_start = pipes[cell] + 1
        inner_end = pipes[cell + 1] if cell + 1 < len(pipes) else len(line)
        inner = line[inner_start:inner_end]
        lead = len(inner) - len(inner.lstrip())
        offset = min(max(0, col - inner_start - lead), len(inner.strip()))
        return cell, offset

    def _format_table(self, editor: TextArea) -> None:
        """Richtet die Tabelle unter dem Cursor bündig aus; Cursor bleibt in seiner Zelle."""
        bounds = self._table_bounds(editor)
        if bounds is None:
            return
        start, end = bounds
        doc = editor.document
        lines = [doc.get_line(i) for i in range(start, end + 1)]
        rows = [self._cells(line) for line in lines]
        seps = [self._is_separator(line) for line in lines]
        ncols = max(len(r) for r in rows)
        widths = [3] * ncols
        for r, sep in zip(rows, seps):
            if sep:
                continue
            for i, cell in enumerate(r):
                widths[i] = max(widths[i], len(cell))
        new_lines = []
        for r, sep in zip(rows, seps):
            if sep:
                cells = []
                for i in range(ncols):
                    spec = r[i] if i < len(r) else "---"
                    left = ":" if spec.startswith(":") else ""
                    right = ":" if spec.endswith(":") and len(spec) > 1 else ""
                    cells.append(left + "-" * (widths[i] + 2 - len(left) - len(right)) + right)
                new_lines.append("|" + "|".join(cells) + "|")
            else:
                cells = [(r[i] if i < len(r) else "").ljust(widths[i]) for i in range(ncols)]
                new_lines.append("| " + " | ".join(cells) + " |")
        if new_lines == lines:
            return
        row, col = editor.cursor_location
        cell, offset = self._cell_cursor(lines[row - start], col)
        editor.replace("\n".join(new_lines), (start, 0), (end, len(lines[-1])))
        new_line = new_lines[row - start]
        pipes = [i for i, ch in enumerate(new_line) if ch == "|"]
        if pipes:
            cell = min(cell, len(pipes) - 1)
            editor.move_cursor((row, min(pipes[cell] + 2 + offset, len(new_line))))

    def _auto_link_images(self, editor: TextArea) -> None:
        """Wandelt einen nackten Bildpfad auf der Cursor-Zeile in einen Markdown-Link um.

        Fängt Drag & Drop auch dann ab, wenn das Terminal den Pfad als
        Tastatureingabe statt als Paste-Event liefert.
        """
        row = editor.cursor_location[0]
        line = editor.document.get_line(row)
        link_spans = [m.span() for m in MD_IMAGE.finditer(line)]
        for match in BARE_IMAGE_PATH.finditer(line):
            if any(s <= match.start() < e for s, e in link_spans):
                continue
            raw = re.sub(r"\\(.)", r"\1", match.group(0))
            path = Path(raw).expanduser()
            if not path.is_absolute():
                path = self.note_path.parent / path
            if not path.is_file():
                continue
            path = path.resolve()
            try:
                link = str(path.relative_to(self.note_path.parent.resolve()))
            except ValueError:
                link = str(path)
            rest = line[: match.start()] + line[match.end():]
            template = re.fullmatch(r"(\s*)!\[([^\]]*)\]\(bild\.png\)\s*", rest)
            if template:
                desc = template.group(2)
                if desc in ("", "Beschreibung"):
                    desc = path.stem
                new_line = f"{template.group(1)}![{desc}]({link})"
                desc_col = len(template.group(1)) + 2
            else:
                desc = path.stem
                new_line = f"{line[: match.start()]}![{desc}]({link}){line[match.end():]}"
                desc_col = match.start() + 2
            editor.replace(new_line, (row, 0), (row, len(line)))
            self._select_title(editor, row, desc_col, desc)
            return

    # ---------- Bild per Drag & Drop ----------

    def on_paste(self, event: events.Paste) -> None:
        """Sicherheitsnetz: Paste/Drop, der nicht im fokussierten Editor landete."""
        editor = self._editor()
        if editor.has_focus:
            return  # NoteEditor hat das Event bereits verarbeitet
        if not self.handle_image_drop(editor, event.text):
            editor.insert(event.text)
        event.stop()

    def handle_image_drop(self, editor: TextArea, pasted: str) -> bool:
        """Verwandelt einen gedroppten Bild-Dateipfad in einen Markdown-Link.

        Gibt False zurück, wenn der Text kein Pfad zu einer Bilddatei ist –
        dann greift das normale Einfügen.
        """
        text = pasted.strip()
        if not text:
            return False
        candidate = re.sub(r"\\(.)", r"\1", text.splitlines()[0].strip().strip("'\""))
        path = Path(candidate).expanduser()
        if path.suffix.lower() not in IMAGE_EXTS or not path.is_file():
            return False
        path = path.resolve()
        try:
            link = str(path.relative_to(self.note_path.parent.resolve()))
        except ValueError:
            link = str(path)
        row = editor.cursor_location[0]
        line = editor.document.get_line(row)
        match = IMAGE_LINK.match(line)
        if match:
            desc = match.group(2)
            if desc in ("", "Beschreibung"):
                desc = path.stem
            editor.replace(f"{match.group(1)}![{desc}]({link})", (row, 0), (row, len(line)))
            self._select_title(editor, row, len(match.group(1)) + 2, desc)
        else:
            row, col = editor.cursor_location
            editor.insert(f"![{path.stem}]({link})")
            self._select_title(editor, row, col + 2, path.stem)
        return True

    @staticmethod
    def _select_title(editor: TextArea, row: int, col: int, title: str) -> None:
        """Markiert den Bildtitel, damit er direkt überschrieben werden kann."""
        editor.selection = Selection((row, col), (row, col + len(title)))

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
