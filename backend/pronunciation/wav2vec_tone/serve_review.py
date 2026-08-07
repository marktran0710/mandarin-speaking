"""Serve the alignment review page over localhost.

A plain file:// page cannot reliably load the audio -- Chrome treats local
files as opaque origins and blocks them. Serving the backend directory over
HTTP makes both the extracted segments and the original utterances resolve,
and costs one command.

    python -m pronunciation.wav2vec_tone.serve_review
"""

from __future__ import annotations

import argparse
import http.server
import socketserver
import sys
import webbrowser
from functools import partial
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
PAGE = "pronunciation/wav2vec_tone/data/review.html"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument("--round", default="1",
                        help="1, 2, ... or 'padding'")
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    name = ("review.html" if args.round == "1"
            else "review_padding.html" if args.round == "padding"
            else "review_binary.html" if args.round == "binary"
            else "review_binpad.html" if args.round == "binpad"
            else f"review_round{args.round}.html")
    page = PAGE.replace("review.html", name)
    if not (BACKEND / page).exists():
        sys.exit(f"{page} not found — run prepare_human_review --round "
                 f"{args.round} first.")

    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(BACKEND))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", args.port), handler) as server:
        url = f"http://127.0.0.1:{args.port}/{page}"
        print(f"serving {BACKEND}")
        print(f"open: {url}")
        print("\nJudge ALIGNMENT only: does the clip contain the intended syllable?")
        print("Keys: a = segment, s = full utterance, 1/2/3 = good/questionable/wrong.")
        print("Progress autosaves in the browser; click Download when finished,")
        target = ("data/ompal_binpad_human_review.csv"
                  if args.round == "binpad"
                  else "data/ompal_binary_human_review.csv"
                  if args.round == "binary"
                  else "data/ompal_padding_human_review.csv"
                  if args.round == "padding"
                  else "data/ompal_alignment_human_review"
                       + ("" if args.round == "1" else f"_round{args.round}")
                       + ".csv")
        print(f"then put the CSV at {target}")
        print("\nCtrl+C to stop.")
        if not args.no_open:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")


if __name__ == "__main__":
    main()
