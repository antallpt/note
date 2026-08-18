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
        assert app.query(".image-caption"), "Bildunterschrift fehlt in der Vorschau"

        editor = app.query_one("#editor", TextArea)
        editor.insert("\n\nNeuer Testabsatz.\n")
        await pilot.pause(1.0)
        assert app.dirty, "Editor-Aenderung wurde nicht als dirty markiert"

        app.action_insert_table()
        header_row = editor.cursor_location[0]
        assert editor.document.get_line(header_row).startswith("|"), "Tabellen-Geruest fehlt"
        await pilot.pause(1.0)

        app.action_toggle_preview()
        assert app.query_one("#preview").has_class("hidden")
        app.action_toggle_preview()
        assert not app.query_one("#preview").can_focus, "Vorschau darf keinen Fokus nehmen"

        # Tabellen erweitern/verkleinern: Cursor in die eingefuegte Tabelle setzen
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

        # Bild-Drop via Paste-Event: Pfad auf einer Vorlagen-Zeile wird zum Link
        img = (Path(__file__).parent / "beispiel" / "diagramm.png").resolve()
        escaped = str(img).replace(" ", "\\ ")
        editor.load_text("![Beschreibung](bild.png)")
        assert app.handle_image_drop(editor, escaped), "Bildpfad wurde nicht als Drop erkannt"
        row = editor.cursor_location[0]
        line = editor.document.get_line(row)
        assert line == "![diagramm](diagramm.png)", f"Unerwartete Zeile: {line!r}"

        # Kein Bildpfad -> normales Einfuegen bleibt zustaendig
        assert not app.handle_image_drop(editor, "einfach nur text")

        # Drop, der als Tastatureingabe ankommt: Auto-Link auf der Cursor-Zeile
        editor.load_text("Notiz dazu: " + escaped)
        editor.move_cursor((0, 5))
        app._auto_link_images(editor)
        line = editor.document.get_line(0)
        assert line == "Notiz dazu: ![diagramm](diagramm.png)", f"Unerwartet: {line!r}"
        assert editor.selected_text == "diagramm", "Titel ist nach Auto-Link nicht markiert"

        # ... und auf der Ctrl+G-Zeile ersetzt er den Platzhalter komplett
        editor.load_text("![Beschreibung](bild.png)" + escaped)
        editor.move_cursor((0, 0))
        app._auto_link_images(editor)
        line = editor.document.get_line(0)
        assert line == "![diagramm](diagramm.png)", f"Unerwartet: {line!r}"

        # Direktes Verlinken (Zwischenablage-Pfad): eigene Zeile unter Text
        editor.load_text("Text davor")
        editor.move_cursor((0, 10))
        app._insert_image_link(editor, img)
        line = editor.document.get_line(1)
        assert line == "![diagramm](diagramm.png)", f"Unerwartet: {line!r}"

        # Live-Autoformat: unordentliche Tabelle wird buendig ausgerichtet
        editor.load_text("| Spalte 1 | Hallo |Hallo   |\n|----------|---|---|\n|  | test | test |")
        editor.move_cursor((2, 3))
        app._format_table(editor)
        lines2 = editor.text.splitlines()
        assert lines2[0] == "| Spalte 1 | Hallo | Hallo |", lines2[0]
        assert lines2[1] == "|----------|-------|-------|", lines2[1]
        assert lines2[2] == "|          | test  | test  |", lines2[2]
        assert editor.cursor_location == (2, 2), editor.cursor_location

        # Undo/Redo mit Ctrl+Z / Ctrl+Y
        editor.load_text("abc")
        editor.move_cursor((0, 3))
        await pilot.press("x")
        assert editor.text == "abcx"
        await pilot.press("ctrl+z")
        assert editor.text == "abc", "Ctrl+Z hat nicht rueckgaengig gemacht"
        await pilot.press("ctrl+y")
        assert editor.text == "abcx", "Ctrl+Y hat nicht wiederhergestellt"

        # PDF-Export (nur wenn ein Chrome-Browser vorhanden ist)
        from app import CHROME_PATHS
        if any(Path(p).is_file() for p in CHROME_PATHS):
            editor.load_text(note.read_text(encoding="utf-8"))
            await app._export_pdf(open_after=False)
            pdf = note.with_suffix(".pdf")
            assert pdf.is_file() and pdf.stat().st_size > 1000, "PDF wurde nicht erzeugt"
            data = pdf.read_bytes()
            pages = data.count(b"/Type /Page") - data.count(b"/Type /Pages")
            assert pages == 1, f"Beispielnotiz sollte auf eine PDF-Seite passen, hat {pages}"
            pdf.unlink()

        # Speichern & Beenden darf keinen Worker-Crash ausloesen
        editor.load_text(note.read_text(encoding="utf-8"))
        assert app.dirty
        app.action_quit_save()
        await pilot.pause(0.3)

    print("OK: Editor, Vorschau, Tabellen-Shortcuts, Autoformat und Bild-Drop funktionieren")


asyncio.run(main())
