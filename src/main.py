import random
import re
import tempfile
import time
from pathlib import Path
import os
import argparse
from urllib.parse import urlparse

import cv2
import numpy as np
import pandas as pd
import requests
import scrython
from einops import rearrange
from fpdf import FPDF
from pyfzf.pyfzf import FzfPrompt
from tqdm import tqdm


def load_deck(path):
    if path.suffix == '.csv':
        deck = pd.read_csv(path)
        # Ensure we have `name` and `count` columns and correct types.
        if set(['name', 'count']).issubset(deck.columns):
            deck = deck[['name', 'count']]
        else:
            deck.columns = ['name', 'count']
        deck['count'] = deck['count'].astype(int)
    else:
        with path.open('r') as file:
            lines = file.read().splitlines()
        cards = [re.split(" ", line, maxsplit=1)
                 for line in lines if line != ""]
        deck = pd.DataFrame(cards, columns=['count', 'name'])
        deck['count'] = deck['count'].astype(int)

    return deck.sort_values(by=['count', 'name'])


def to_json(card_data):
    if isinstance(card_data, dict):
        return card_data
    return card_data.scryfallJson


def process_card(infos, image_list, token_ids, add_tokens=True):
    name = str(infos['name']).strip()

    # If the deck contains a Scryfall URL or a set/number spec, resolve it to an id
    card_data = None
    try:
        if name.startswith('http') or ('/' in name and not name.isdigit()):
            tid = resolve_token_spec(name)
            if tid:
                card_data = to_json(scrython.cards.Id(id=tid))

        if card_data is None:
            card_data = to_json(scrython.cards.Named(fuzzy=name))
    except Exception:
        # Re-raise with more context so caller sees which input failed
        raise

    if card_data['type_line'].startswith('Basic Land'):
        candidates = scrython.cards.Search(q=f"++{infos['name']}").data()
        image_list.extend(
            map(fetch_image, random.sample(candidates, infos['count'])))
    else:
        image = fetch_image(card_data)
        image_list.extend([image] * int(infos['count']))
        if add_tokens:
            token_ids |= get_tokens(card_data)

    time.sleep(0.05)


def process_token(ident, image_list):
    token_data = to_json(scrython.cards.Id(id=ident))
    image_list.extend([fetch_image(token_data)] * 2)


def fetch_image(card_data):
    image_url = card_data['image_uris']['normal']
    img_data = requests.get(image_url, stream=True).raw

    image = np.asarray(bytearray(img_data.read()), dtype="uint8")
    image = cv2.imdecode(image, cv2.IMREAD_COLOR)
    return image


def get_tokens(card_data):
    token_ids = set()
    for part in card_data.get('all_parts', []):
        if part['component'] == 'token':
            token_ids.add(part['id'])

    return token_ids


def tile_in_pages(image_list):
    ROWS_PER_PAGE = COLS_PER_PAGE = 3
    CARDS_PER_PAGE = ROWS_PER_PAGE * COLS_PER_PAGE
    H_INCHES, W_INCHES, PAD_INCHES = 3.48, 2.49, 0.005

    nb_images = len(image_list)
    nb_missing = CARDS_PER_PAGE - (nb_images % CARDS_PER_PAGE)
    img_shape = np.asarray(image_list[0]).shape

    WHITE = 255
    canvas = np.vstack([image_list, np.full([nb_missing, *img_shape], WHITE)])

    padding = np.zeros([len(canvas.shape), 2], dtype=int)
    padding[1, 0] = round(PAD_INCHES / H_INCHES * canvas.shape[1])
    padding[2, 0] = round(PAD_INCHES / W_INCHES * canvas.shape[2])

    canvas = np.pad(canvas, padding, constant_values=WHITE)
    canvas_shape = canvas.shape

    canvas = rearrange(
        canvas, '(p rows cols) h w c -> p (rows h) (cols w) c',
        rows=ROWS_PER_PAGE, cols=COLS_PER_PAGE,
    )

    MISSING_HEIGHT = (11 - H_INCHES * ROWS_PER_PAGE) / H_INCHES * canvas_shape[1]
    MISSING_WIDTH = (8.5 - W_INCHES * COLS_PER_PAGE) / W_INCHES * canvas_shape[2]

    padding = np.zeros([len(canvas.shape), 1], dtype=int)
    padding[1, 0] = round(MISSING_HEIGHT / 2)
    padding[2, 0] = round(MISSING_WIDTH / 2)

    canvas = np.pad(canvas, padding, constant_values=WHITE)
    return canvas


def resolve_token_spec(spec):
    """Resolve a token specifier to a Scryfall card id.

    Accepted formats:
    - Full Scryfall URL: https://scryfall.com/card/{set}/{number}/{name}
    - Short form: "{set}/{number}"
    - Card name: any name passed to Named(fuzzy=...)
    Returns card id (str) on success, else None.
    """
    spec = spec.strip()
    try:
        if spec.startswith('http'):
            parsed = urlparse(spec)
            parts = parsed.path.strip('/').split('/')
            # Expect path like: card/{set}/{number}/{name}
            if len(parts) >= 3 and parts[0] == 'card':
                set_code = parts[1]
                number = parts[2]
                results = scrython.cards.Search(q=f"set:{set_code} number:{number}").data()
                if results:
                    return results[0]['id']
        elif '/' in spec:
            set_code, number = spec.split('/', 1)
            results = scrython.cards.Search(q=f"set:{set_code} number:{number}").data()
            if results:
                return results[0]['id']
        else:
            card = scrython.cards.Named(fuzzy=spec)
            return to_json(card)['id']
    except Exception:
        return None



def generate_pdf(path, canvas):
    with tempfile.TemporaryDirectory() as dirname:
        pdf = FPDF(format='Letter')

        out_dir = Path(dirname)
        for i, page in enumerate(canvas, start=1):
            out_path = (out_dir / f"page_{i}.jpg").as_posix()
            cv2.imwrite(out_path, page)

            pdf.add_page()
            pdf.image(out_path, 0, 0, 215.9, 279.4)

        pdf.output(path.with_suffix(".pdf"), 'F')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate printable PDFs from a deck list")
    parser.add_argument('--no-tokens', action='store_true', help='Do not include tokens on generated sheets')
    parser.add_argument('--token', '-t', action='append', default=[],
                        help='Add a specific token (Scryfall URL, "set/number", or name). Can be provided multiple times.')
    args = parser.parse_args()

    fzf = FzfPrompt()
    # Only look for common deck file extensions and do not descend into virtualenv folders.
    allowed_exts = {'.csv', '.txt', '.tsv'}

    def find_deck_files(root=Path('.'), allowed_exts=allowed_exts):
        for dirpath, dirnames, filenames in os.walk(str(root)):
            # Prevent descending into virtualenv directories named like '.venv', 'venv', etc.
            dirnames[:] = [d for d in dirnames if 'venv' not in d.lower()]
            for fname in filenames:
                p = Path(dirpath) / fname
                if p.suffix.lower() in allowed_exts:
                    yield p

    choices = list(find_deck_files())
    path = Path(fzf.prompt(choices)[0])

    deck = load_deck(path)

    image_list, token_ids = [], set()
    add_tokens = not args.no_tokens

    # Resolve any user-specified token specs and add their ids to token_ids.
    forced_token_ids = set()
    for spec in args.token:
        tid = resolve_token_spec(spec)
        if tid:
            forced_token_ids.add(tid)
        else:
            print(f"Warning: could not resolve token spec: {spec}")

    if forced_token_ids and args.no_tokens:
        print("Note: user-specified tokens will be included despite --no-tokens.")

    token_ids |= forced_token_ids
    for idx, card_infos in tqdm(deck.iterrows(), total=len(deck), desc="Fetching cards"):
        process_card(card_infos, image_list, token_ids, add_tokens=add_tokens)

    # Fetch tokens if either automatic token collection is enabled, or the user specified tokens.
    if (add_tokens and token_ids) or forced_token_ids:
        for ident in tqdm(token_ids, desc="Fetching tokens"):
            process_token(ident, image_list)

    canvas = tile_in_pages(image_list)
    generate_pdf(path, canvas)
