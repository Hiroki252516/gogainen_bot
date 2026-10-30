from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from markdown_it import MarkdownIt


GLOSSARY_PATH = Path(__file__).resolve().parents[1] / "seed/content/learning_glossary_v2.yml"
GLOSSARY_VERSION = "learning-glossary-v2"


def _normalized(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


@dataclass(frozen=True)
class GlossaryEntry:
    id: str
    term: str
    definition: str
    aliases: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class LearningGlossary:
    version: str
    sha256: str
    entries: tuple[GlossaryEntry, ...]
    excluded_aliases: tuple[re.Pattern[str], ...]


def parse_learning_glossary(content: Any) -> LearningGlossary:
    if not isinstance(content, dict) or content.get("version") != GLOSSARY_VERSION:
        raise ValueError("learning glossary version is invalid")
    raw_entries = content.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError("learning glossary entries must be a non-empty list")
    entries = []
    ids: set[str] = set()
    aliases: set[str] = set()

    def alias_pattern(alias: Any) -> re.Pattern[str]:
        if not isinstance(alias, str) or not alias.strip() or alias != alias.strip():
            raise ValueError("learning glossary alias must be non-empty and trimmed")
        normalized = _normalized(alias)
        if normalized in aliases:
            raise ValueError(f"learning glossary alias conflicts: {alias}")
        aliases.add(normalized)
        left = r"(?<![a-z0-9_])" if re.match(r"[a-z0-9_]", normalized) else ""
        right = r"(?![a-z0-9_])" if re.search(r"[a-z0-9_]$", normalized) else ""
        return re.compile(left + re.escape(normalized) + right)

    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise ValueError("learning glossary entry must be an object")
        for key in ("id", "term", "definition"):
            if not isinstance(raw.get(key), str) or not raw[key].strip():
                raise ValueError(f"learning glossary {key} must be non-empty")
        if raw["id"] in ids or not re.fullmatch(r"[a-z][a-z0-9_]*", raw["id"]):
            raise ValueError("learning glossary entry id must be unique and use a stable slug")
        ids.add(raw["id"])
        sources = raw.get("sources")
        if not isinstance(sources, list) or not sources or any(not isinstance(source, str) or not source.strip() for source in sources):
            raise ValueError("learning glossary sources must be non-empty")
        raw_aliases = raw.get("aliases")
        if not isinstance(raw_aliases, list) or not raw_aliases:
            raise ValueError("learning glossary aliases must be non-empty")
        patterns = [alias_pattern(alias) for alias in raw_aliases]
        entries.append(GlossaryEntry(raw["id"], raw["term"], raw["definition"], tuple(patterns)))
    raw_excluded = content.get("excluded_aliases", [])
    if not isinstance(raw_excluded, list):
        raise ValueError("learning glossary excluded aliases must be a list")
    excluded = tuple(alias_pattern(alias) for alias in raw_excluded)
    canonical = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return LearningGlossary(content["version"], hashlib.sha256(canonical.encode("utf-8")).hexdigest(), tuple(entries), excluded)


@lru_cache(maxsize=1)
def load_learning_glossary() -> LearningGlossary:
    return parse_learning_glossary(yaml.safe_load(GLOSSARY_PATH.read_text(encoding="utf-8")))


def glossary_snapshot(message: str) -> dict[str, Any]:
    glossary = load_learning_glossary()
    # Parse displayed text so Markdown link destinations and HTML are not vocabulary.
    blocks = []
    for token in MarkdownIt("commonmark").parse(message):
        if token.type == "inline":
            blocks.append("".join(
                "\n" if child.type in {"softbreak", "hardbreak"} else child.content
                for child in token.children or []
                if child.type in {"text", "code_inline", "softbreak", "hardbreak"}
            ))
    text = _normalized("\n".join(blocks))
    matches = list(
        (match.start(), -len(match.group()), index, match.end())
        for index, entry in enumerate(glossary.entries)
        for pattern in entry.aliases
        for match in pattern.finditer(text)
    )
    # Excluded compound terms still mask their shorter, registered substrings.
    matches.extend(
        (match.start(), -len(match.group()), -1, match.end())
        for pattern in glossary.excluded_aliases
        for match in pattern.finditer(text)
    )
    matches.sort()
    entries = []
    seen: set[str] = set()
    end = -1
    for start, _, index, match_end in matches:
        if start < end:
            continue
        end = match_end
        if index == -1:
            continue
        entry = glossary.entries[index]
        if entry.id not in seen:
            seen.add(entry.id)
            entries.append({"id": entry.id, "term": entry.term, "definition": entry.definition})
    return {"version": glossary.version, "dictionary_sha256": glossary.sha256, "entries": entries}


def public_glossary(snapshot: Any) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict):
        return None
    return {
        "version": snapshot["version"],
        "entries": [
            {key: entry[key] for key in ("id", "term", "definition")}
            for entry in snapshot["entries"]
        ],
    }


def glossary_reference() -> dict[str, Any]:
    """Return the shared dictionary definitions for an explicitly enabled prompt mode."""
    glossary = load_learning_glossary()
    return {
        "version": glossary.version,
        "entries": [
            {"id": entry.id, "term": entry.term, "definition": entry.definition}
            for entry in glossary.entries
        ],
    }
