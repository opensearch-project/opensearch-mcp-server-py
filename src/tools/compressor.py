# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Lossless Prompt Compression via Dictionary-Encoding.

Implementation of the hierarchical dictionary-encoding algorithm from:
"Lossless Prompt Compression via Dictionary-Encoding and In-Context Learning"
(arXiv:2604.13066v1)

The algorithm replaces frequently occurring word subsequences with compact
meta-tokens (<M1>, <M2>, ...) and produces a dictionary for lossless
reconstruction. LLMs can learn this dictionary in-context and analyze
compressed data directly.
"""

from __future__ import annotations

import json as _json
import re
import tiktoken
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache


META_TOKEN_PATTERN = re.compile(r'<M\d+>')

_enc = tiktoken.get_encoding('cl100k_base')


@lru_cache(maxsize=8192)
def _count_tokens(text: str) -> int:
    return len(_enc.encode(text))


@dataclass
class CompressionResult:
    """Result of dictionary-encoding compression."""

    compressed_text: str
    dictionary: dict[str, str]  # meta-token -> original subsequence
    original_token_count: int
    compressed_token_count: int  # compressed text + dictionary overhead

    @property
    def compression_ratio(self) -> float:
        """CR = 1 - (compressed + dict) / original."""
        if self.original_token_count == 0:
            return 0.0
        return 1.0 - self.compressed_token_count / self.original_token_count

    def format_dictionary(self) -> str:
        """Format dictionary entries as readable text."""
        lines = []
        for meta, subseq in sorted(self.dictionary.items(), key=lambda x: _meta_sort_key(x[0])):
            lines.append(f'{meta} = {subseq}')
        return '\n'.join(lines)

    def decompress(self) -> str:
        """Reconstruct original text from compressed text + dictionary."""
        text = self.compressed_text
        # Replace longest meta-tokens first to avoid partial matches
        for meta, subseq in sorted(self.dictionary.items(), key=lambda x: -len(x[0])):
            text = text.replace(meta, subseq)
        return text

    def __repr__(self) -> str:  # noqa: D105
        return (
            f'CompressionResult(\n'
            f'  compression_ratio={self.compression_ratio:.1%},\n'
            f'  original_tokens={self.original_token_count},\n'
            f'  compressed_tokens={self.compressed_token_count},\n'
            f'  dictionary_size={len(self.dictionary)}\n'
            f')'
        )


def _meta_sort_key(meta: str) -> int:
    m = re.search(r'\d+', meta)
    return int(m.group()) if m else 0


def _contains_meta_token(tokens: list[str]) -> bool:
    return any(META_TOKEN_PATTERN.fullmatch(t) for t in tokens)


def _apply_replacements(
    tokens: list[str], selected: list[tuple[tuple[str, ...], list[int], str]]
) -> list[str]:
    """Algorithm 3: Replace selected subsequences with meta-tokens."""
    replacement_map: dict[int, str] = {}
    skip_positions: set[int] = set()

    for subseq, positions, meta in selected:
        length = len(subseq)
        for p in positions:
            replacement_map[p] = meta
            skip_positions.update(range(p + 1, p + length))

    result: list[str] = []
    for i in range(len(tokens)):
        if i in replacement_map:
            result.append(replacement_map[i])
        elif i not in skip_positions:
            result.append(tokens[i])

    return result


def _field_level_compress(
    docs: list[dict],
    f_min: int,
    l_max: int = 15,
    text_fields: set[str] | None = None,
    skip_fields: set[str] | None = None,
) -> tuple[list[str], dict[str, str], dict[tuple[str, str], str], set[str], dict]:
    """Shared logic: build field order, dictionary, and value->meta map.

    Hybrid strategy:
      - Keyword/numeric fields: whole-value replacement only.
      - Text fields (from OpenSearch mapping): word-subsequence compression
        scoped per field.

    Args:
        docs: List of flat dicts.
        f_min: Minimum frequency.
        l_max: Maximum subsequence length for text field compression.
        text_fields: Set of field names to treat as text (substring compression).
            If None, all fields use whole-value only.
        skip_fields: Fields to exclude from compression entirely (e.g. numeric
            fields whose values the LLM needs to reason about directly).

    Returns (field_order, dictionary, value_to_meta, text_fields, text_compressed).
    """
    if text_fields is None:
        text_fields = set()
    if skip_fields is None:
        skip_fields = set()

    # --- Collect field names in document order ---
    field_order: list[str] = []
    seen: set[str] = set()
    for doc in docs:
        for key in doc:
            if key not in seen:
                field_order.append(key)
                seen.add(key)

    # --- Serialize all values per field ---
    field_values: dict[str, list[str]] = {f: [] for f in field_order}
    for doc in docs:
        for field in field_order:
            if field not in doc:
                field_values[field].append('')
                continue
            val = doc[field]
            s = val if isinstance(val, str) else _json.dumps(val, separators=(',', ':'))
            field_values[field].append(s)

    # --- Whole-value compression for structured fields ---
    dictionary: dict[str, str] = {}
    value_to_meta: dict[tuple[str, str], str] = {}
    meta_counter = 1

    MIN_TOKEN_SAVINGS = 5

    for field in field_order:
        if field in text_fields or field in skip_fields:
            continue
        counts: Counter[str] = Counter()
        for v in field_values[field]:
            if v:
                counts[v] += 1
        for serialized, freq in counts.most_common():
            if freq < f_min:
                break
            meta = f'<M{meta_counter}>'
            val_tokens = _count_tokens(serialized)
            meta_tokens = _count_tokens(meta)
            # dict entry cost: meta_tokens + val_tokens (for "M# = value" line)
            token_savings = freq * (val_tokens - meta_tokens) - (meta_tokens + val_tokens)
            if token_savings < MIN_TOKEN_SAVINGS:
                continue
            meta_counter += 1
            dictionary[meta] = serialized
            value_to_meta[(field, serialized)] = meta

    # --- Substring compression for text fields ---
    text_compressed: dict[tuple[str, int], str] = {}

    for field in text_fields:
        if field not in field_values:
            continue
        all_values = field_values[field]
        SEP = ' \x00 '
        joined = SEP.join(all_values)
        tokens = joined.split()

        sep_positions: set[int] = set()
        for i, t in enumerate(tokens):
            if t == '\x00':
                sep_positions.add(i)

        field_dict: dict[str, str] = {}
        saved_meta_counter = meta_counter

        max_value_len = max((len(v.split()) for v in all_values if v), default=0)

        for length in range(min(l_max, max_value_len), 1, -1):
            if length > len(tokens):
                continue
            subseq_positions: dict[tuple[str, ...], list[int]] = defaultdict(list)
            for i in range(len(tokens) - length + 1):
                span = set(range(i, i + length))
                if span & sep_positions:
                    continue
                subseq = tuple(tokens[i : i + length])
                if _contains_meta_token(list(subseq)):
                    continue
                subseq_positions[subseq].append(i)

            subseq_positions = {s: ps for s, ps in subseq_positions.items() if len(ps) >= f_min}
            sorted_subseqs = sorted(subseq_positions.items(), key=lambda x: -len(x[1]))

            used: set[int] = set()
            selected: list[tuple[tuple[str, ...], list[int], str]] = []

            for subseq, positions in sorted_subseqs:
                subseq_len = len(subseq)
                valid = []
                occupied: set[int] = set()
                for p in sorted(positions):
                    span = set(range(p, p + subseq_len))
                    if not span & used and not span & occupied:
                        valid.append(p)
                        occupied.update(span)
                if len(valid) < f_min:
                    continue
                f = len(valid)
                subseq_str = ' '.join(subseq)
                meta = f'<M{meta_counter}>'
                val_tokens = _count_tokens(subseq_str)
                meta_tokens = _count_tokens(meta)
                token_savings = f * (val_tokens - meta_tokens) - (meta_tokens + val_tokens)
                if token_savings < MIN_TOKEN_SAVINGS:
                    continue
                meta_counter += 1
                selected.append((subseq, valid, meta))
                field_dict[meta] = subseq_str
                dictionary[meta] = subseq_str
                for p in valid:
                    used.update(range(p, p + subseq_len))

            if selected:
                tokens = _apply_replacements(tokens, selected)
                sep_positions = {i for i, t in enumerate(tokens) if t == '\x00'}

        # Split back into per-doc values
        result_tokens: list[list[str]] = []
        current: list[str] = []
        for t in tokens:
            if t == '\x00':
                result_tokens.append(current)
                current = []
            else:
                current.append(t)
        result_tokens.append(current)

        # Post-hoc validation: verify net token savings for this field.
        field_dict_tokens = sum(_count_tokens(m) + _count_tokens(v) for m, v in field_dict.items())
        orig_tokens = sum(_count_tokens(v) for v in all_values)
        comp_tokens = (
            sum(_count_tokens(' '.join(toks)) for toks in result_tokens) + field_dict_tokens
        )
        if comp_tokens >= orig_tokens:
            for meta in field_dict:
                del dictionary[meta]
            meta_counter = saved_meta_counter
            continue

        for i, toks in enumerate(result_tokens):
            text_compressed[(field, i)] = ' '.join(toks)

    return field_order, dictionary, value_to_meta, text_fields, text_compressed


def compress_docs(
    docs: list[dict],
    f_min: int = 2,
    l_max: int = 15,
    text_fields: set[str] | None = None,
    skip_fields: set[str] | None = None,
) -> CompressionResult:
    """Field-level dictionary-encoding compression for structured documents.

    Hybrid strategy:
      - Keyword/numeric fields: whole-value replacement.
      - Text fields: word-subsequence compression scoped per field.
    Never crosses field or row boundaries.

    Args:
        docs: List of flat dicts (e.g., OpenSearch _source docs).
        f_min: Minimum frequency for a value/pattern to be compressed.
        l_max: Maximum subsequence length for text field compression.
        text_fields: Field names to treat as text (substring compression).
            Typically the 'text' type fields from OpenSearch mapping.
        skip_fields: Fields to exclude from compression entirely (e.g. numeric
            fields whose values the LLM needs to reason about directly).
    """
    import json as _json

    field_order, dictionary, value_to_meta, text_fields, text_compressed = _field_level_compress(
        docs, f_min, l_max, text_fields, skip_fields
    )

    original_lines = []
    compressed_lines = []
    for i, doc in enumerate(docs):
        orig_obj: dict = {}
        comp_obj: dict = {}
        for field in field_order:
            if field not in doc:
                continue
            val = doc[field]
            serialized = val if isinstance(val, str) else _json.dumps(val, separators=(',', ':'))
            orig_obj[field] = val

            if field in text_fields:
                comp_obj[field] = text_compressed.get((field, i), serialized)
            else:
                meta = value_to_meta.get((field, serialized))
                comp_obj[field] = meta if meta is not None else val

        original_lines.append(_json.dumps(orig_obj, separators=(',', ':')))
        compressed_lines.append(_json.dumps(comp_obj, separators=(',', ':')))

    original_text = '\n'.join(original_lines)
    compressed_text = '\n'.join(compressed_lines)

    original_count = _count_tokens(original_text)
    dict_text = '\n'.join(f'{m} = {v}' for m, v in dictionary.items())
    compressed_count = (
        _count_tokens(compressed_text) + _count_tokens(dict_text)
        if dict_text
        else _count_tokens(compressed_text)
    )

    return CompressionResult(
        compressed_text=compressed_text,
        dictionary=dictionary,
        original_token_count=original_count,
        compressed_token_count=compressed_count,
    )


def compress_tsv_docs(
    docs: list[dict],
    f_min: int = 2,
    l_max: int = 15,
    text_fields: set[str] | None = None,
    skip_fields: set[str] | None = None,
) -> CompressionResult:
    """Field-level dictionary-encoding compression outputting TSV format.

    Same hybrid strategy as compress_docs but outputs TSV, which is more
    token-efficient since field names appear only once in the header.

    Args:
        docs: List of flat dicts (e.g., OpenSearch _source docs).
        f_min: Minimum frequency for a value/pattern to be compressed.
        l_max: Maximum subsequence length for text field compression.
        text_fields: Field names to treat as text (substring compression).
        skip_fields: Fields to exclude from compression entirely (e.g. numeric
            fields whose values the LLM needs to reason about directly).
    """
    import json as _json

    field_order, dictionary, value_to_meta, text_fields, text_compressed = _field_level_compress(
        docs, f_min, l_max, text_fields, skip_fields
    )

    def _cell(val, field, doc_idx, use_compression: bool) -> str:
        serialized = val if isinstance(val, str) else _json.dumps(val, separators=(',', ':'))
        if use_compression:
            if field in text_fields:
                c = text_compressed.get((field, doc_idx))
                if c is not None:
                    return c.replace('\t', ' ').replace('\n', ' ')
            else:
                meta = value_to_meta.get((field, serialized))
                if meta is not None:
                    return meta
        return serialized.replace('\t', ' ').replace('\n', ' ')

    header = '\t'.join(field_order)

    orig_rows = [header]
    comp_rows = [header]
    for i, doc in enumerate(docs):
        orig_cells = []
        comp_cells = []
        for field in field_order:
            val = doc.get(field, '')
            orig_cells.append(_cell(val, field, i, False))
            comp_cells.append(_cell(val, field, i, True))
        orig_rows.append('\t'.join(orig_cells))
        comp_rows.append('\t'.join(comp_cells))

    original_text = '\n'.join(orig_rows)
    compressed_text = '\n'.join(comp_rows)

    original_count = _count_tokens(original_text)
    dict_text = '\n'.join(f'{m} = {v}' for m, v in dictionary.items())
    compressed_count = (
        _count_tokens(compressed_text) + _count_tokens(dict_text)
        if dict_text
        else _count_tokens(compressed_text)
    )

    return CompressionResult(
        compressed_text=compressed_text,
        dictionary=dictionary,
        original_token_count=original_count,
        compressed_token_count=compressed_count,
    )
