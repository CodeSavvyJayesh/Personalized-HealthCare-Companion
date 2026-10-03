"""BERT WordPiece tokenizer in pure Python.

Why this exists: the sentiment model only needs `text -> input_ids`. Pulling
in `transformers` (and with it `torch`) for that costs roughly 2.5 GB of
image and several hundred MB of RAM, which is the difference between
fitting a small cloud instance and not. This is the same algorithm as
`BertTokenizer(do_lower_case=True)` — basic tokenization followed by greedy
longest-match-first WordPiece — implemented against the model's own
`vocab.txt`, with no dependencies at all.

Verified against the reference ids for bert-base-uncased in
tests/test_wordpiece.py.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

CLS, SEP, UNK, PAD = "[CLS]", "[SEP]", "[UNK]", "[PAD]"


def _is_whitespace(ch: str) -> bool:
    if ch in (" ", "\t", "\n", "\r"):
        return True
    return unicodedata.category(ch) == "Zs"


def _is_control(ch: str) -> bool:
    if ch in ("\t", "\n", "\r"):
        return False
    return unicodedata.category(ch).startswith("C")


def _is_punctuation(ch: str) -> bool:
    cp = ord(ch)
    # ASCII symbols such as "$" and "^" are not in the Unicode P* classes but
    # BERT treats them as punctuation anyway.
    if 33 <= cp <= 47 or 58 <= cp <= 64 or 91 <= cp <= 96 or 123 <= cp <= 126:
        return True
    return unicodedata.category(ch).startswith("P")


def _is_cjk(cp: int) -> bool:
    return (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0x20000 <= cp <= 0x2A6DF
        or 0x2A700 <= cp <= 0x2B73F
        or 0x2B740 <= cp <= 0x2B81F
        or 0x2B820 <= cp <= 0x2CEAF
        or 0xF900 <= cp <= 0xFAFF
        or 0x2F800 <= cp <= 0x2FA1F
    )


class WordPieceTokenizer:
    def __init__(
        self,
        vocab_path: str | Path,
        *,
        lowercase: bool = True,
        max_chars_per_word: int = 100,
    ) -> None:
        self.vocab: dict[str, int] = {}
        with open(vocab_path, encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                self.vocab[line.rstrip("\n")] = index
        for required in (CLS, SEP, UNK):
            if required not in self.vocab:
                raise ValueError(f"{vocab_path} is not a BERT vocab: no {required}")
        self.lowercase = lowercase
        self.max_chars_per_word = max_chars_per_word
        self.cls_id = self.vocab[CLS]
        self.sep_id = self.vocab[SEP]
        self.unk_id = self.vocab[UNK]
        self.pad_id = self.vocab.get(PAD, 0)

    # ------------------------------------------------------ basic tokenizer
    def _clean(self, text: str) -> str:
        out = []
        for ch in text:
            cp = ord(ch)
            if cp == 0 or cp == 0xFFFD or _is_control(ch):
                continue
            if _is_whitespace(ch):
                out.append(" ")
            elif _is_cjk(cp):
                out.append(f" {ch} ")
            else:
                out.append(ch)
        return "".join(out)

    def _strip_accents(self, token: str) -> str:
        return "".join(
            ch
            for ch in unicodedata.normalize("NFD", token)
            if unicodedata.category(ch) != "Mn"
        )

    def _split_punctuation(self, token: str) -> list[str]:
        pieces: list[str] = []
        current: list[str] = []
        for ch in token:
            if _is_punctuation(ch):
                if current:
                    pieces.append("".join(current))
                    current = []
                pieces.append(ch)
            else:
                current.append(ch)
        if current:
            pieces.append("".join(current))
        return pieces

    def basic_tokenize(self, text: str) -> list[str]:
        tokens: list[str] = []
        for token in self._clean(text).split():
            if self.lowercase:
                token = self._strip_accents(token.lower())
            tokens.extend(self._split_punctuation(token))
        return [t for t in tokens if t]

    # -------------------------------------------------------- wordpiece
    def _wordpiece(self, token: str) -> list[str]:
        if len(token) > self.max_chars_per_word:
            return [UNK]
        pieces: list[str] = []
        start = 0
        while start < len(token):
            end = len(token)
            match = None
            while start < end:
                candidate = token[start:end]
                if start > 0:
                    candidate = "##" + candidate
                if candidate in self.vocab:
                    match = candidate
                    break
                end -= 1
            if match is None:
                return [UNK]  # the whole word is unknown, as in BERT
            pieces.append(match)
            start = end
        return pieces

    def tokenize(self, text: str) -> list[str]:
        tokens: list[str] = []
        for word in self.basic_tokenize(text):
            tokens.extend(self._wordpiece(word))
        return tokens

    def encode(self, text: str, max_length: int = 256) -> list[int]:
        """`[CLS] tokens [SEP]`, truncated to `max_length` ids in total."""
        ids = [self.vocab.get(tok, self.unk_id) for tok in self.tokenize(text)]
        ids = ids[: max(0, max_length - 2)]
        return [self.cls_id, *ids, self.sep_id]
