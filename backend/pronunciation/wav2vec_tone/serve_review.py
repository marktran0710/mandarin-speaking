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
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    if not (BACKEND / PAGE).exists():
        sys.exit("review.html not found — run prepare_human_review first.")

    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(BACKEND))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", args.port), handler) as server:
        url = f"http://127.0.0.1:{args.port}/{PAGE}"
        print(f"serving {BACKEND}")
        print(f"open: {url}")
        print("\nJudge ALIGNMENT only: does the clip contain the intended syllable?")
        print("Keys: a = segment, s = full utterance, 1/2/3 = good/questionable/wrong.")
        print("Progress autosaves in the browser; click Download when finished,")
        print("then put the CSV at data/ompal_alignment_human_review.csv")
        print("\nCtrl+C to stop.")
        if not args.no_open:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")


if __name__ == "__main__":
    main()
