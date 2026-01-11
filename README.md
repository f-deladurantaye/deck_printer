# MTG Deck Printer

Generate printable PDFs of Magic: The Gathering cards from a deck list using Scryfall.

## Overview

This small utility fetches card images from Scryfall, tiles them into Letter-sized pages, and writes a printable PDF. It also attempts to include tokens referenced by cards.

## Requirements

- Python 3.10+ (3.11 recommended)
- System packages: Git, a C compiler for some wheel builds (if needed)
- Python packages: pandas, scrython, numpy, opencv-python, requests, fpdf, pyfzf, einops, tqdm

Install into an isolated virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If you don't have a `requirements.txt`, install the essentials:

```bash
pip install pandas scrython numpy opencv-python requests fpdf pyfzf einops tqdm
```

## Quick Start

1. Prepare a deck file (CSV recommended) and place it under the `decks/` directory.
2. Run the interactive picker and choose your deck file:

```bash
python src/main.py
```

The script will fetch images and produce a PDF alongside your deck file (same name, `.pdf` suffix).

## CLI Options

- `--no-tokens`: Do not include tokens on generated sheets. By default the script will attempt to find tokens referenced by cards and include them.
- `--token`, `-t`: Add a specific token to include. Accepts a Scryfall URL, a `set/number` pair, or a card name. This option can be provided multiple times.

Examples:

```bash
# Add a token by Scryfall URL
python src/main.py --token https://scryfall.com/card/tm3c/24/construct

# Add multiple tokens by set/number or name
python src/main.py -t tm3c/24 -t "Construct"

# Skip automatic token discovery but still include user-specified tokens
python src/main.py --no-tokens -t tm3c/24
```

Notes:

- If `--no-tokens` is set but `--token` is provided, user-specified tokens are still included (the script prints a notice).
- Deck entries in the `name` column may also be Scryfall URLs (e.g. `https://scryfall.com/card/tm3c/24/construct`) or `set/number` (e.g. `tm3c/24`); the script will resolve those to the correct card and fetch by id.

## Deck file format

CSV is preferred and should include a header row with `name` and `count` columns.

Example `decks/azlask.csv`:

```csv
name,count
"Otharri, Suns' Glory",1
"Eldrazi Confluence",1
"Adrix and Nev, Twinasters",1
```

Plain text formats are also supported (space-separated count and name per line).

## File picker behavior

- The interactive file picker only searches for `.csv`, `.txt`, and `.tsv` files.
- Directories that look like virtual environments (names containing `venv`, e.g. `.venv`, `venv`) are excluded from traversal so your virtualenv won't be scanned.

## Troubleshooting

- Ambiguous card names: If Scryfall returns an error like "Too many cards match ambiguous name", update the `name` entry in your deck CSV to be more specific (include set name or more words).
- Missing images: Network issues or Scryfall rate limits may cause fetches to fail. Retry after a short pause.

## License

See the `LICENSE` file in this repository.

## Windows Instructions

To be able to execute the script on Windows, run the following commands in PowerShell:

```powershell
Set-ExecutionPolicy Unrestricted -Scope Process
iwr -useb get.scoop.sh | iex
scoop install fzf
Install-Module -Name PSFzf -Scope CurrentUser -Force
```

## Author

Francis de Ladurantaye
