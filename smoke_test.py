"""Smoke-Test: App starten, Vorschau prüfen, Tippen + Speichern simulieren."""

import asyncio
from pathlib import Path

from textual.widgets import Markdown, TextArea

from app import NotizApp


async def main() -> None:
    note = Path(__file__).parent / "beispiel" / "Beispiel.md"
    app = NotizApp(note)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause(1.0)

        md_widgets = app.query(Markdown)
        assert md_widgets, "Vorschau enthaelt keine Markdown-Widgets"

        images = [w for w in app.query("#preview *") if "note-image" in w.classes]
        assert images, "Vorschau enthaelt kein Bild-Widget"

        editor = app.query_one("#editor", TextArea)
        editor.insert("\n\nNeuer Testabsatz.\n")
        await pilot.pause(1.0)
        assert app.dirty, "Editor-Aenderung wurde nicht als dirty markiert"

        app.action_insert_table()
        await pilot.pause(1.0)
        assert "| Spalte 1 |" in editor.text

        app.action_toggle_preview()
        assert app.query_one("#preview").has_class("hidden")
        app.action_toggle_preview()

        # Tabellen erweitern/verkleinern: Cursor in die eingefuegte Tabelle setzen
        lines = editor.text.splitlines()
        header_row = next(i for i, l in enumerate(lines) if l.lstrip().startswith("| Spalte 1"))
        editor.move_cursor((header_row + 2, 2))
        before_lines = editor.document.line_count
        app.action_add_table_row()
        assert editor.document.line_count == before_lines + 1, "Zeile wurde nicht angefuegt"

        header_before = editor.document.get_line(header_row).count("|")
        editor.move_cursor((header_row + 2, 2))
        app.action_add_table_column()
        assert editor.document.get_line(header_row).count("|") == header_before + 1, "Spalte wurde nicht angefuegt"
        app.action_remove_table_column()
        assert editor.document.get_line(header_row).count("|") == header_before, "Spalte wurde nicht entfernt"
        rows_before = editor.document.line_count
        app.action_remove_table_row()
        assert editor.document.line_count == rows_before - 1, "Zeile wurde nicht entfernt"

        # Ausserhalb einer Tabelle: nur Warnung, keine Aenderung
        editor.move_cursor((0, 0))
        text_before = editor.text
        app.action_add_table_row()
        assert editor.text == text_before, "Aktion ausserhalb der Tabelle veraenderte den Text"

        # Bild-Drop: Pfad-Paste auf der Ctrl+G-Zeile wird zum Link
        img = (Path(__file__).parent / "beispiel" / "diagramm.png").resolve()
        end_row = editor.document.line_count - 1
        editor.move_cursor((end_row, len(editor.document.get_line(end_row))))
        app.action_insert_image()
        escaped = str(img).replace(" ", "\\ ")
        handled = app.handle_image_drop(editor, escaped)
        assert handled, "Bildpfad wurde nicht als Drop erkannt"
        row = editor.cursor_location[0]
        line = editor.document.get_line(row)
        assert line == "![diagramm](diagramm.png)", f"Unerwartete Zeile: {line!r}"

        # Kein Bildpfad -> normales Einfuegen bleibt zustaendig
        assert not app.handle_image_drop(editor, "einfach nur text")

    print("OK: Editor, Vorschau, Tabellen-Shortcuts und Bild-Drop funktionieren")


asyncio.run(main())
