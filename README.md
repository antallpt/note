# note

Markdown notes in the terminal: editor on the left (regular navigation, no vim),
live preview on the right with rendered tables and images, live PDF export.
Built with [Textual](https://textual.textualize.io).

![Screenshot](docs/screenshot.png)

## Installation

Runs on **macOS, Linux and Windows**. Requirements: Python 3.10+.
For the PDF export you need a Chromium browser — on Windows the preinstalled
Edge is enough, on Linux `chromium`/`google-chrome`, on macOS
Chrome/Brave/Edge. For the image dialog (Ctrl+G) on Linux: `zenity` (GNOME)
or `kdialog` (KDE) — usually preinstalled.

**1. Clone the repository and install the dependencies:**

macOS / Linux:

```sh
git clone https://github.com/antallpt/note.git
cd note
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

Windows (PowerShell):

```powershell
git clone https://github.com/antallpt/note.git
cd note
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

**2. Set up the `note` command:**

macOS / Linux — add an alias to your shell config (run this inside the cloned
folder; use `~/.bashrc` instead of `~/.zshrc` for Bash):

```sh
echo "alias note='\"$PWD/note\"'" >> ~/.zshrc
source ~/.zshrc
```

Windows — add the project folder to your PATH (once, PowerShell inside the
cloned folder):

```powershell
[Environment]::SetEnvironmentVariable("Path", "$env:Path;$PWD", "User")
```

After that, `note` works in every new terminal (Windows automatically uses
`note.cmd`).

**3. Try it out** — open the sample note:

```sh
note beispiel/Beispiel.md
```

## Usage

The `note` command works from any directory:

```sh
note lecture-01        # opens lecture-01.md – created if it doesn't exist
note os/chapter-2.md   # subfolders are created as needed
note                   # opens ./Notizen.md
```

Without a file extension, `.md` is appended automatically. Without the alias,
`./note file` always works directly from the project folder.

## Keyboard shortcuts

| Shortcut | Action                          |
|---------|----------------------------------|
| Ctrl+S  | Save (re-renders the preview)    |
| Ctrl+Q  | Save & quit                      |
| Ctrl+R  | Toggle the preview               |
| Ctrl+T  | Insert a table skeleton          |
| Ctrl+N  | Add a table row                  |
| Ctrl+O  | Remove a table row               |
| Ctrl+B  | Add a table column               |
| Ctrl+F  | Remove a table column            |
| Ctrl+G  | Pick an image via the file dialog |
| Ctrl+L  | Toggle the live PDF preview      |
| Ctrl+Z / Ctrl+Y | Undo / redo              |
| Ctrl+P  | Command palette (Textual)        |

The table shortcuts act on the table the cursor is currently in. The preview
also refreshes automatically ~0.5 s after the last keystroke.

All shortcuts are additionally bound with Cmd instead of Ctrl — but that only
works in terminals that pass Cmd through to programs (Ghostty, kitty, WezTerm).
Apple Terminal keeps Cmd shortcuts for itself (Cmd+Q would quit the terminal).

## Tables

Ctrl+T inserts an empty table skeleton (the cursor lands in the first cell),
Ctrl+N/O/B/F change rows and columns. Tables are **aligned automatically
while you write** — ~0.5 s after the last keystroke; the cursor stays in its
cell.

## Images

An image appears in the preview when its link sits alone on a line:
`![Description](diagram.png)` — paths are relative to the note file.

**Ctrl+G opens the native file dialog** (macOS: Finder, Linux:
zenity/kdialog, Windows: Explorer) — pick an image and it gets linked at the
cursor position (on its own line, with the title selected).

**Drag & drop from Finder** and hand-typed paths to existing images are also
converted into links automatically (~0.5 s after typing). If the image sits in
the note's folder, the link is made relative.

After linking, the **title is selected** (prefilled with the file name) —
just start typing to replace it; right arrow keeps it. The title appears in
the preview as a caption below the image.

Rendering quality depends on the terminal: Apple Terminal and older Windows
terminals don't support a graphics protocol, so images are rendered there as
colored pixel blocks — **clicking an image in the preview opens it in full
quality in the default image viewer.**
kitty/Ghostty/iTerm2/WezTerm (and Windows Terminal from 1.22 via Sixel)
display images sharply right away.

## Live PDF preview

**Ctrl+L** creates a PDF next to the note (same name, `.pdf`) and opens it in
the system's PDF viewer. While the PDF preview is on, the PDF is regenerated
on every save (Ctrl+S) — the viewer reloads it automatically. Tables and
images are rendered in full quality.

The export uses an installed Chrome/Chromium/Brave/Edge as the PDF renderer
(headless; on Windows the preinstalled Edge is picked up automatically). The
PDF is also ready to hand in or share as-is. On Linux, Evince (GNOME) and
Okular (KDE) reload changed PDFs on their own; on Windows, SumatraPDF is
recommended for that.

The PDF uses a graded gray palette (Tailwind "Neutral" scale, WCAG AA
checked): main title dark gray (#262626), subheadings graded (#404040,
#525252), body text light gray (#737373), table header as an intermediate
step (#525252 on #f5f5f5) with zebra stripes, subtle gray bullet points.

macOS only: since Preview.app reloads changed PDFs only when it gains focus,
the app briefly nudges the window after each export and immediately hands
focus back to the terminal (short flicker). It becomes completely
flicker-free with [Skim](https://skim-app.sourceforge.io)
(`brew install --cask skim`): if Skim is installed, the app uses it
automatically — enable automatic reloading on file changes in Skim's
settings under "Sync".

## Development

Entry point: `app.py`. Sample note: `beispiel/Beispiel.md`.
Smoke test: `./.venv/bin/python smoke_test.py`
