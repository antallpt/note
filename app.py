#!/usr/bin/env python3
"""notiz – Markdown-Notizen im Terminal.

Editor links (normale Navigation, kein Vim), Live-Vorschau rechts
mit gerenderten Tabellen und Bildern.

Aufruf:  note [datei]   – ohne Endung wird .md angehängt,
                          die Datei wird angelegt, falls sie fehlt.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

from rich.style import Style
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.theme import Theme
from textual.widgets import Footer, Header, Markdown, Static, TextArea
from textual.widgets.text_area import Selection, TextAreaTheme

def _import_image_widget():
    """Importiert textual-image; auf Apple Terminal ohne Terminal-Abfragen.

    textual-image schickt beim Import Sixel-/Kitty-Grafikabfragen ans
    Terminal. Apple Terminal versteht sie nicht und druckt die Kitty-Abfrage
    als Text ('Gi=…'), der nach dem Beenden im Verlauf steht. Da Apple
    Terminal ohnehin kein Grafikprotokoll kann, schlucken wir die Abfragen
    dort und landen direkt beim Halfcell-Rendering.
    """
    # Warnungen von textual-image (z.B. Zellgrößen-Fallback) nie auf stderr
    # ausgeben – sie würden nach dem Beenden im Terminal-Verlauf stehen.
    ti_logger = logging.getLogger("textual_image")
    ti_logger.addHandler(logging.NullHandler())
    ti_logger.propagate = False

    if (
        os.environ.get("TERM_PROGRAM") == "Apple_Terminal"
        and sys.__stdout__ is not None
        and sys.__stdout__.isatty()
    ):

        class _QuietTTY(io.TextIOBase):
            """Schluckt Schreibzugriffe (Escape-Abfragen), reicht aber den
            echten Terminal-Deskriptor durch, damit ioctl-Abfragen wie die
            Zellgröße weiterhin funktionieren."""

            def __init__(self, fd: int) -> None:
                self._fd = fd

            def write(self, s: str) -> int:
                return len(s)

            def flush(self) -> None:
                return None

            def isatty(self) -> bool:
                return True

            def fileno(self) -> int:
                return self._fd

        real_stdout = sys.__stdout__
        sys.__stdout__ = _QuietTTY(real_stdout.fileno())
        try:
            from textual_image.renderable import Image as renderable
            from textual_image.widget import Image as widget
        finally:
            sys.__stdout__ = real_stdout
        return renderable, widget
    from textual_image.renderable import Image as renderable
    from textual_image.widget import Image as widget
    return renderable, widget


try:
    _ImageRenderable, Image = _import_image_widget()
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
        "punctuation.special": Style(color="#7a7a7a"),
        "punctuation.delimiter": Style(color="#7a7a7a"),
        "punctuation.bracket": Style(color="#7a7a7a"),
        "string": Style(color="#4a4a4a"),
        "comment": Style(color="#7a7a7a", italic=True),
    },
)

TABLE_SNIPPET = (
    "\n|     |     |\n"
    "|-----|-----|\n"
    "|     |     |\n"
)

CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]

HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title><style>
@page {{ margin: 1.5cm; }}
body {{ font-family: -apple-system, 'Helvetica Neue', sans-serif; color: #1f1f1f;
       max-width: 720px; margin: 0 auto; line-height: 1.5; font-size: 11pt; }}
h1 {{ font-size: 1.5em; }}
h2 {{ font-size: 1.25em; }}
h3 {{ font-size: 1.1em; }}
h1, h2, h3 {{ color: #111111; margin: 0.8em 0 0.35em; break-after: avoid; }}
p {{ margin: 0.4em 0; }}
table {{ border-collapse: collapse; margin: 0.7em 0; break-inside: avoid; }}
th, td {{ border: 1px solid #9a9a9a; padding: 0.3em 0.6em; text-align: left; }}
th {{ background: #f0f0f0; }}
img {{ max-width: 100%; max-height: 10cm; width: auto; height: auto;
      display: block; margin: 0.5em 0; break-inside: avoid; }}
code {{ background: #f2f2f2; padding: 0.1em 0.3em; border-radius: 3px; }}
pre {{ break-inside: avoid; }}
pre code {{ display: block; padding: 0.8em; overflow-x: auto; }}
blockquote {{ border-left: 3px solid #c0c0c0; margin-left: 0; padding-left: 1em; color: #4a4a4a; }}
</style></head><body>
{body}
</body></html>
"""


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
    * {
        scrollbar-size-vertical: 1;
        scrollbar-size-horizontal: 1;
        scrollbar-color: #c4c4c4;
        scrollbar-color-hover: #a4a4a4;
        scrollbar-color-active: #848484;
        scrollbar-background: $surface;
        scrollbar-background-hover: $surface;
        scrollbar-background-active: $surface;
        scrollbar-corner-color: $surface;
    }
    #panes {
        border: solid #7a7a7a;
        background: $surface;
    }
    #editor {
        width: 1fr;
        border: none;
        background: $surface;
    }
    #editor:focus {
        border: none;
    }
    #preview {
        width: 1fr;
        background: $surface;
        border-left: solid #7a7a7a;
        padding: 0 1;
    }
    #preview.hidden {
        display: none;
    }
    #preview Markdown {
        margin: 0;
        padding: 0;
    }
    Toast {
        width: auto;
        min-width: 20;
        max-width: 50%;
        padding: 0 1;
        margin: 0 1 0 0;
        background: $surface;
        color: $foreground;
        border: solid #7a7a7a;
    }
    Toast.-information, Toast.-warning, Toast.-error {
        border: solid #7a7a7a;
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
        Binding("ctrl+l,super+l", "toggle_pdf", "PDF"),
        Binding("ctrl+q,super+q", "quit_save", "Beenden"),
    ]

    def __init__(self, note_path: Path) -> None:
        super().__init__()
        self.note_path = note_path
        self.dirty = False
        self.pdf_live = False
        self._picking = False

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
        with Horizontal(id="panes"):
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
        if not self.is_running:
            return
        editor = self._editor()
        self._auto_link_images(editor)
        self._format_table(editor)
        self.run_worker(self._render_preview(), exclusive=True, group="preview")

    async def _render_preview(self) -> None:
        try:
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
        except Exception:
            # Beim Beenden kann die Vorschau bereits abgebaut sein –
            # dann still aussteigen statt mit Traceback zu crashen.
            pass

    # ---------- Aktionen ----------

    def action_save(self) -> None:
        self._save()
        self._schedule_render()
        if self.pdf_live:
            self.run_worker(self._export_pdf(open_after=False), exclusive=True, group="pdf")
        self.notify(f"Gespeichert: {self.note_path.name}", timeout=2)

    def _save(self) -> None:
        text = self.query_one("#editor", TextArea).text
        self.note_path.parent.mkdir(parents=True, exist_ok=True)
        self.note_path.write_text(text, encoding="utf-8")
        self.dirty = False
        self._update_title()

    def action_toggle_preview(self) -> None:
        self.query_one("#preview").toggle_class("hidden")

    def action_insert_table(self) -> None:
        editor = self._editor()
        row = editor.cursor_location[0]
        editor.insert(TABLE_SNIPPET)
        # Cursor in die erste Zelle der neuen Tabelle
        editor.move_cursor((row + 1, 2))

    def action_insert_image(self) -> None:
        """Öffnet den Finder-Dateidialog und verlinkt das gewählte Bild."""
        if self._picking:
            return
        self.run_worker(self._pick_image(), group="pick")

    async def _pick_image(self) -> None:
        self._picking = True
        try:
            script = (
                'set p to POSIX path of (choose file of type {"public.image"} '
                'with prompt "Bild für die Notiz auswählen")\n'
                "return p"
            )
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await proc.communicate()
            self._refocus_terminal()
            if proc.returncode != 0:
                return  # Dialog abgebrochen
            path = Path(out.decode().strip())
            if path.is_file():
                self._insert_image_link(self._editor(), path)
        finally:
            self._picking = False

    @staticmethod
    def _refocus_terminal() -> None:
        """Holt das Terminal nach einem Dialog wieder in den Vordergrund."""
        term_apps = {"Apple_Terminal": "Terminal", "iTerm.app": "iTerm"}
        app_name = term_apps.get(os.environ.get("TERM_PROGRAM", ""))
        if app_name:
            subprocess.Popen(
                ["osascript", "-e", f'tell application "{app_name}" to activate'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )

    # ---------- PDF-Vorschau ----------

    def action_toggle_pdf(self) -> None:
        """Live-PDF an/aus: erzeugt die PDF-Datei neben der Notiz und öffnet
        sie in der Vorschau-App; bei jedem Speichern wird sie aktualisiert."""
        self.pdf_live = not self.pdf_live
        if self.pdf_live:
            self.notify("PDF-Vorschau an – aktualisiert sich bei jedem Speichern", timeout=3)
            self.run_worker(self._export_pdf(open_after=True), exclusive=True, group="pdf")
        else:
            self.notify("PDF-Vorschau aus", timeout=2)

    def _md_for_export(self, text: str) -> str:
        """Bildpfade URL-tauglich machen (Leerzeichen etc. encodieren)."""
        lines = []
        for line in text.splitlines():
            match = IMAGE_LINE.match(line)
            if match and "://" not in match.group(2):
                raw = match.group(2).strip().replace("\\ ", " ")
                lines.append(f"![{match.group(1)}]({quote(raw, safe='/')})")
            else:
                lines.append(line)
        return "\n".join(lines)

    async def _export_pdf(self, open_after: bool) -> None:
        chrome = next((p for p in CHROME_PATHS if Path(p).is_file()), None)
        if chrome is None:
            self.pdf_live = False
            self.notify(
                "PDF-Export braucht Chrome/Chromium – nicht gefunden",
                severity="error", timeout=5,
            )
            return
        import markdown as md

        body = md.markdown(
            self._md_for_export(self._editor().text),
            extensions=["tables", "fenced_code"],
        )
        html = HTML_TEMPLATE.format(title=self.note_path.stem, body=body)
        html_path = self.note_path.parent / (self.note_path.stem + ".preview.html")
        pdf_path = self.note_path.with_suffix(".pdf")
        html_path.write_text(html, encoding="utf-8")
        try:
            proc = await asyncio.create_subprocess_exec(
                chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={pdf_path}", str(html_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
        finally:
            html_path.unlink(missing_ok=True)
        if proc.returncode != 0 or not pdf_path.is_file():
            self.notify("PDF-Export fehlgeschlagen", severity="error", timeout=4)
            return
        use_skim = Path("/Applications/Skim.app").exists()
        if open_after:
            viewer = "Skim" if use_skim else "Preview"
            subprocess.Popen(["open", "-a", viewer, str(pdf_path)])
        elif self.pdf_live and not use_skim:
            self._refresh_preview_app(pdf_path)

    @staticmethod
    def _refresh_preview_app(pdf_path: Path) -> None:
        """Preview.app lädt geänderte PDFs erst neu, wenn es aktiviert wird –
        kurz nach vorn holen und den Fokus ans Terminal zurückgeben.
        `open -a` aktiviert zuverlässig und braucht keine Automation-Rechte.
        (Skim braucht das alles nicht, es lädt Änderungen selbst nach.)"""
        term = {"Apple_Terminal": "Terminal", "iTerm.app": "iTerm"}.get(
            os.environ.get("TERM_PROGRAM", "")
        )
        if term is None:
            return
        pdf = shlex.quote(str(pdf_path))
        subprocess.Popen(
            ["/bin/sh", "-c", f"open -a Preview {pdf}; sleep 0.45; open -a {term}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

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
            self._save()
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
