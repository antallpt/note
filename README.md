# notiz

Markdown-Notizen im Terminal: Editor links (normale Navigation, kein Vim),
Live-Vorschau rechts mit gerenderten Tabellen und Bildern. Gebaut mit
[Textual](https://textual.textualize.io).

![Screenshot](docs/screenshot.png)

## Installation

```sh
git clone https://github.com/antallpt/notiz.git
cd notiz
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

## Starten

```sh
./note vorlesung-01     # öffnet vorlesung-01.md – wird angelegt, falls nicht vorhanden
./note pfad/zur/datei.md
./note                  # öffnet ./Notizen.md
```

Ohne Dateiendung wird automatisch `.md` angehängt.

Praktisch: Alias in `~/.zshrc` eintragen, dann funktioniert `note datei`
aus jedem Verzeichnis:

```sh
alias note='"/pfad/zu/notiz/note"'
```

## Tastenkürzel

| Kürzel  | Aktion                          |
|---------|---------------------------------|
| Ctrl+S  | Speichern (rendert die Vorschau neu) |
| Ctrl+Q  | Speichern & Beenden             |
| Ctrl+R  | Vorschau ein-/ausblenden        |
| Ctrl+T  | Tabellen-Gerüst einfügen        |
| Ctrl+G  | Bild-Link einfügen              |
| Ctrl+P  | Befehlspalette (Textual)        |

Die Vorschau aktualisiert sich zusätzlich automatisch ~0,5 s nach der letzten
Eingabe.

## Bilder

Ein Bild erscheint in der Vorschau, wenn sein Link allein auf einer Zeile steht:
`![Beschreibung](diagramm.png)` — Pfade relativ zur Notiz-Datei.

Die Darstellungsqualität hängt vom Terminal ab: Apple Terminal zeigt
Pixelblöcke, kitty/Ghostty/iTerm2/WezTerm zeigen scharfe Grafiken
(Kitty-Graphics-Protokoll bzw. Sixel).

## Entwicklung

Einstieg: `app.py`. Beispielnotiz: `beispiel/Beispiel.md`.
Smoke-Test: `./.venv/bin/python smoke_test.py`
