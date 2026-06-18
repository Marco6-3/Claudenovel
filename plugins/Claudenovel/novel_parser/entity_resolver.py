"""Alias-aware entity matching utilities.

The parser analyzes arbitrary web novels, so a stable entity layer cannot rely
only on jieba's person-name guesses. This module keeps entity matching
deterministic: explicit aliases are normalized to canonical names, longer terms
win over prefix fragments, and overlapping matches are counted once.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence


AliasMap = Dict[str, List[str]]


@dataclass(frozen=True)
class EntityMatch:
    start: int
    end: int
    canonical: str
    text: str


def clean_alias_map(aliases: Mapping[str, Sequence[str]] | None) -> AliasMap:
    """Return a normalized alias map with empty/duplicate/self aliases removed."""
    if not aliases:
        return {}
    cleaned: AliasMap = {}
    for canonical, raw_aliases in aliases.items():
        canonical = str(canonical).strip()
        if not canonical:
            continue
        seen = {canonical}
        values: List[str] = []
        for alias in raw_aliases or []:
            alias = str(alias).strip()
            if not alias or alias in seen:
                continue
            seen.add(alias)
            values.append(alias)
        cleaned[canonical] = values
    return cleaned


def merge_alias_maps(*maps: Mapping[str, Sequence[str]] | None) -> AliasMap:
    """Merge alias maps, giving later maps ownership of duplicate surface terms."""
    merged: AliasMap = {}
    for aliases in maps:
        for canonical, values in clean_alias_map(aliases).items():
            # A later canonical claim should not remain as another entity's alias.
            for owner in list(merged):
                if owner != canonical and canonical in merged[owner]:
                    merged[owner] = [item for item in merged[owner] if item != canonical]
            merged.setdefault(canonical, [])
            seen = {canonical, *merged[canonical]}
            for alias in values:
                # If an earlier automatic discovery promoted this alias to its
                # own canonical entity, the later explicit alias map wins.
                if alias in merged and alias != canonical:
                    del merged[alias]
                for owner in list(merged):
                    if owner != canonical and alias in merged[owner]:
                        merged[owner] = [item for item in merged[owner] if item != alias]
                if alias not in seen:
                    merged[canonical].append(alias)
                    seen.add(alias)
    return merged


def load_alias_map(path: Path) -> AliasMap:
    """Load a JSON alias map from disk.

    Accepted formats:
    - {"陈汉升": ["小陈", "陈董"]}
    - {"aliases": {"陈汉升": ["小陈", "陈董"]}}
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "aliases" in data and isinstance(data["aliases"], dict):
        data = data["aliases"]
    if not isinstance(data, dict):
        raise ValueError(f"Alias config must be a JSON object: {path}")
    return clean_alias_map(data)


def alias_terms(aliases: Mapping[str, Sequence[str]] | None) -> list[tuple[str, str]]:
    """Return (term, canonical) pairs sorted for longest-first regex matching."""
    terms: list[tuple[str, str]] = []
    for canonical, values in clean_alias_map(aliases).items():
        for term in [canonical, *values]:
            if len(term) < 2:
                continue
            terms.append((term, canonical))
    # Prefer longer terms at the same position, then stable lexical order.
    terms = sorted(set(terms), key=lambda item: (-len(item[0]), item[0], item[1]))
    return terms


def _compile_pattern(aliases: Mapping[str, Sequence[str]] | None) -> re.Pattern[str] | None:
    terms = alias_terms(aliases)
    if not terms:
        return None
    return re.compile("|".join(re.escape(term) for term, _ in terms))


def find_entity_matches(
    text: str,
    aliases: Mapping[str, Sequence[str]] | None,
) -> list[EntityMatch]:
    """Find non-overlapping canonical entity mentions in reading order."""
    terms = dict(alias_terms(aliases))
    pattern = _compile_pattern(aliases)
    if pattern is None:
        return []
    matches: list[EntityMatch] = []
    for match in pattern.finditer(text):
        term = match.group(0)
        canonical = terms.get(term)
        if canonical is None:
            continue
        matches.append(EntityMatch(match.start(), match.end(), canonical, term))
    return matches


def count_entity_mentions(
    text: str,
    aliases: Mapping[str, Sequence[str]] | None,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for match in find_entity_matches(text, aliases):
        counts[match.canonical] = counts.get(match.canonical, 0) + 1
    return counts


def ordered_unique_entities(
    text: str,
    aliases: Mapping[str, Sequence[str]] | None,
) -> list[str]:
    seen = set()
    ordered: list[str] = []
    for match in find_entity_matches(text, aliases):
        if match.canonical in seen:
            continue
        seen.add(match.canonical)
        ordered.append(match.canonical)
    return ordered


def expand_focus_entities(
    focus_entities: Iterable[str],
    aliases: Mapping[str, Sequence[str]] | None,
) -> list[str]:
    """Expand canonical focus names with known aliases for evidence retrieval."""
    alias_map = clean_alias_map(aliases)
    expanded: list[str] = []
    seen = set()
    for name in focus_entities:
        candidates = [name]
        for canonical, values in alias_map.items():
            if name == canonical or name in values:
                candidates = [canonical, *values]
                break
        for candidate in candidates:
            if candidate and candidate not in seen:
                expanded.append(candidate)
                seen.add(candidate)
    return expanded
