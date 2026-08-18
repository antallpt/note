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

    print("OK: Editor, Vorschau, Tabelle und Bild funktionieren")


asyncio.run(main())
