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
| Ctrl+N  | Tabellenzeile hinzufügen        |
| Ctrl+O  | Tabellenzeile entfernen         |
| Ctrl+B  | Tabellenspalte hinzufügen       |
| Ctrl+F  | Tabellenspalte entfernen        |
| Ctrl+G  | Bild-Link einfügen              |
| Ctrl+P  | Befehlspalette (Textual)        |

Die Tabellen-Kürzel wirken auf die Tabelle, in der der Cursor gerade steht.
Die Vorschau aktualisiert sich zusätzlich automatisch ~0,5 s nach der letzten
Eingabe.

Alle Kürzel sind auch mit Cmd statt Ctrl hinterlegt — das funktioniert aber
nur in Terminals, die Cmd an Programme durchreichen (Ghostty, kitty, WezTerm).
Apple Terminal behält Cmd-Kürzel für sich (Cmd+Q würde das Terminal beenden).

## Tabellen

Ctrl+T fügt ein leeres Tabellen-Gerüst ein (der Cursor landet in der ersten
Zelle), Ctrl+N/O/B/F ändern Zeilen und Spalten. Tabellen werden beim Schreiben
**automatisch bündig ausgerichtet** — ~0,5 s nach der letzten Eingabe; der
Cursor bleibt dabei in seiner Zelle.

## Bilder

Ein Bild erscheint in der Vorschau, wenn sein Link allein auf einer Zeile steht:
`![Beschreibung](diagramm.png)` — Pfade relativ zur Notiz-Datei.

Am schnellsten: **Bilddatei aus dem Finder ins Terminal ziehen.** Der Pfad wird
erkannt und automatisch in einen Markdown-Link umgewandelt — egal ob das
Terminal den Drop als Paste-Event oder als getippten Text übergibt (dann greift
die Umwandlung ~0,5 s später). Landet der Pfad auf einer `![…](…)`-Zeile
(z.B. frisch per Ctrl+G erzeugt), wird deren Platzhalter ersetzt, sonst wird ein
Link an Ort und Stelle eingefügt. Auch von Hand getippte Pfade zu existierenden
Bildern werden so verlinkt. Liegt das Bild im Ordner der Notiz, wird der Link
automatisch relativ.

Die Darstellungsqualität hängt vom Terminal ab: Apple Terminal zeigt
Pixelblöcke, kitty/Ghostty/iTerm2/WezTerm zeigen scharfe Grafiken
(Kitty-Graphics-Protokoll bzw. Sixel).

## Entwicklung

Einstieg: `app.py`. Beispielnotiz: `beispiel/Beispiel.md`.
Smoke-Test: `./.venv/bin/python smoke_test.py`
