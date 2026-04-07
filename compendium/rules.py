import re

from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

from .models import GameObject
from .text_utils import (
    INLINE_LIST_HINT_PATTERN,
    KEY_RULE_SENTENCE_PATTERN,
    KEY_TERM_EMPHASIS,
    REFERENCE_OBJECT_TYPES,
    WORD_TOKEN_PATTERN,
    clean_text,
)


def collect_preview_text_lines(preview_context):
    lines = []
    lines.extend(preview_context.get("description_lines", []))
    lines.extend(value for _, value in preview_context.get("summary_pairs", []))

    for attack in preview_context.get("attacks", []):
        lines.append(clean_text(attack.get("name")))
        lines.extend(attack.get("text_lines", []))

    for section in preview_context.get("object_sections", []):
        lines.append(clean_text(section.get("title")))
        for entry in section.get("entries", []):
            lines.append(clean_text(entry.get("name")))
            lines.extend(entry.get("text_lines", []))

    for level_key in ("class_ability_levels", "class_option_levels", "class_progression_levels"):
        for level in preview_context.get(level_key, []):
            for feature in level.get("features", []):
                lines.append(clean_text(feature.get("name")))
                lines.extend(feature.get("text_lines", []))

    for subclass in preview_context.get("class_subclasses", []):
        lines.append(clean_text(subclass.get("name")))
        for feature in subclass.get("features", []):
            lines.append(clean_text(feature.get("name")))
            lines.extend(feature.get("text_lines", []))

    return [line for line in (clean_text(line) for line in lines) if line]


def build_related_reference_groups(game_object, preview_context):
    text_lines = collect_preview_text_lines(preview_context)
    if not text_lines:
        return []

    corpus = " ".join(text_lines).lower()
    corpus_tokens = set(WORD_TOKEN_PATTERN.findall(corpus))
    object_type_labels = dict(GameObject.ObjectType.choices)
    grouped = {object_type: [] for object_type in REFERENCE_OBJECT_TYPES}

    candidates = GameObject.objects.filter(
        system=game_object.system,
        object_type__in=REFERENCE_OBJECT_TYPES,
    ).exclude(pk=game_object.pk).values_list("id", "name", "object_type").order_by("name")

    for candidate_id, candidate_name, candidate_object_type in candidates:
        name = clean_text(candidate_name)
        if not name:
            continue
        if len(re.sub(r"[^a-z0-9]+", "", name.lower())) < 4:
            continue

        lowered_name = name.lower()
        name_tokens = [token for token in WORD_TOKEN_PATTERN.findall(lowered_name) if len(token) >= 3]
        if not name_tokens or not all(token in corpus_tokens for token in name_tokens):
            continue
        if lowered_name not in corpus:
            continue

        start = 0
        whole_match = False
        while True:
            index = corpus.find(lowered_name, start)
            if index == -1:
                break
            end = index + len(lowered_name)
            before_ok = index == 0 or not corpus[index - 1].isalnum()
            after_ok = end == len(corpus) or not corpus[end].isalnum()
            if before_ok and after_ok:
                whole_match = True
                break
            start = index + 1
        if not whole_match:
            continue

        bucket = grouped.get(candidate_object_type)
        max_items = 24 if candidate_object_type == GameObject.ObjectType.CONDITION else 12
        if bucket is None or len(bucket) >= max_items:
            continue
        bucket.append({"id": candidate_id, "name": name})

    result = []
    for object_type in REFERENCE_OBJECT_TYPES:
        items = grouped.get(object_type) or []
        if items:
            result.append(
                {
                    "object_type": object_type,
                    "label": object_type_labels.get(object_type, object_type.title()),
                    "items": items,
                }
            )
    return result


def build_reference_lookup(related_reference_groups):
    lookup = {}
    for group in related_reference_groups:
        for item in group.get("items", []):
            key = clean_text(item.get("name")).lower()
            object_id = item.get("id")
            if key and object_id and key not in lookup:
                lookup[key] = object_id
    return lookup


def compile_reference_pattern(reference_lookup):
    if not reference_lookup:
        return None
    names = sorted(reference_lookup.keys(), key=len, reverse=True)
    if not names:
        return None
    return re.compile(
        r"(?<![A-Za-z0-9])(" + "|".join(re.escape(name) for name in names) + r")(?![A-Za-z0-9])",
        flags=re.IGNORECASE,
    )


def split_sentences(text):
    cleaned = clean_text(text)
    if not cleaned:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]


def extract_key_rules_and_bullets(raw_lines):
    key_rules = []
    bullets = []

    def append_unique(target, value):
        candidate = clean_text(value)
        if candidate and candidate not in target:
            target.append(candidate)

    for raw_line in raw_lines:
        line = clean_text(raw_line)
        if not line:
            continue

        for sentence in split_sentences(line):
            if KEY_RULE_SENTENCE_PATTERN.search(sentence):
                append_unique(key_rules, sentence)

        if re.match(r"^(\*|-|•|\d+\.)\s+", line):
            append_unique(bullets, re.sub(r"^(\*|-|•|\d+\.)\s+", "", line))
            continue

        if INLINE_LIST_HINT_PATTERN.search(line) and ":" in line:
            _, remainder = line.split(":", 1)
            remainder = remainder.strip()
            delimiter = ";" if ";" in remainder else ","
            parts = [part.strip(" .") for part in remainder.split(delimiter)]
            parts = [part for part in parts if len(part) > 2]
            if len(parts) >= 2:
                for part in parts:
                    append_unique(bullets, part)

    return key_rules, bullets


def group_lines_for_dropdowns(raw_lines, html_lines, group_size=3):
    groups = []
    current_raw = []
    current_html = []
    for raw_line, html_line in zip(raw_lines, html_lines):
        current_raw.append(raw_line)
        current_html.append(html_line)
        if len(current_raw) >= group_size:
            groups.append({"raw": current_raw, "html": current_html})
            current_raw = []
            current_html = []

    if current_raw:
        groups.append({"raw": current_raw, "html": current_html})
    return groups


def format_plain_segment_with_emphasis(segment, seen_terms):
    text = clean_text(segment)
    if not text:
        return ""
    if seen_terms is None:
        return escape(text)

    next_match = None
    next_term = None
    for term in KEY_TERM_EMPHASIS:
        if term in seen_terms:
            continue
        match = re.search(rf"\b{re.escape(term)}\b", text, flags=re.IGNORECASE)
        if not match:
            continue
        if next_match is None or match.start() < next_match.start():
            next_match = match
            next_term = term

    if next_match is None or next_term is None:
        return escape(text)

    seen_terms.add(next_term)
    before = escape(text[:next_match.start()])
    highlighted = format_html("<strong>{}</strong>", text[next_match.start():next_match.end()])
    after = format_plain_segment_with_emphasis(text[next_match.end():], seen_terms)
    return mark_safe(f"{before}{highlighted}{after}")


def linkify_text_line(text, reference_lookup, pattern, seen_terms=None):
    cleaned = clean_text(text)
    if not cleaned:
        return ""
    if pattern is None:
        return format_plain_segment_with_emphasis(cleaned, seen_terms)

    parts = []
    last_index = 0
    for match in pattern.finditer(cleaned):
        start, end = match.span()
        object_id = reference_lookup.get(match.group(0).lower())
        if object_id is None:
            continue
        if start > last_index:
            parts.append(format_plain_segment_with_emphasis(cleaned[last_index:start], seen_terms))
        parts.append(
            format_html(
                '<button class="compendium-inline-ref" type="button" onclick="openCompendiumPreviewModal({})">{}</button>',
                object_id,
                match.group(0),
            )
        )
        last_index = end

    if last_index < len(cleaned):
        parts.append(format_plain_segment_with_emphasis(cleaned[last_index:], seen_terms))

    if not parts:
        return format_plain_segment_with_emphasis(cleaned, seen_terms)
    return mark_safe("".join(str(part) for part in parts))


def apply_inline_reference_links(preview_context, reference_lookup, pattern):
    description_seen_terms = set()
    preview_context["description_lines_html"] = [
        linkify_text_line(line, reference_lookup, pattern, description_seen_terms)
        for line in preview_context.get("description_lines", [])
    ]

    for attack in preview_context.get("attacks", []):
        seen_terms = set()
        attack["text_lines_html"] = [
            linkify_text_line(line, reference_lookup, pattern, seen_terms) for line in attack.get("text_lines", [])
        ]

    for section in preview_context.get("object_sections", []):
        for entry in section.get("entries", []):
            seen_terms = set()
            entry["text_lines_html"] = [
                linkify_text_line(line, reference_lookup, pattern, seen_terms) for line in entry.get("text_lines", [])
            ]

    for level_key in ("class_ability_levels", "class_option_levels", "class_progression_levels"):
        for level in preview_context.get(level_key, []):
            for feature in level.get("features", []):
                seen_terms = set()
                feature["text_lines_html"] = [
                    linkify_text_line(line, reference_lookup, pattern, seen_terms)
                    for line in feature.get("text_lines", [])
                ]

    for subclass in preview_context.get("class_subclasses", []):
        for feature in subclass.get("features", []):
            seen_terms = set()
            feature["text_lines_html"] = [
                linkify_text_line(line, reference_lookup, pattern, seen_terms)
                for line in feature.get("text_lines", [])
            ]


def build_dropdown_payload(title, raw_lines, html_lines, dropdown_id, is_open, reference_lookup, pattern):
    key_rules, bullets = extract_key_rules_and_bullets(raw_lines)
    key_rules_html = [linkify_text_line(sentence, reference_lookup, pattern, seen_terms=set()) for sentence in key_rules]
    bullets_html = [linkify_text_line(item, reference_lookup, pattern, seen_terms=set()) for item in bullets]
    return {
        "id": dropdown_id,
        "title": title,
        "paragraphs_html": html_lines,
        "key_rules_html": key_rules_html,
        "bullets_html": bullets_html,
        "is_open": is_open,
    }


def build_rules_sections(preview_context, reference_lookup, pattern):
    sections = []

    def get_or_create_section(title):
        for section in sections:
            if section["title"] == title:
                return section
        section = {"title": title, "dropdowns": []}
        sections.append(section)
        return section

    def add_entry_dropdowns(section_title, entry_title, raw_lines, html_lines, split_groups=False, group_size=3):
        clean_raw = [line for line in (clean_text(line) for line in raw_lines) if line]
        clean_html = [line for line in html_lines if clean_text(line)]
        if not clean_raw or not clean_html:
            return
        groups = group_lines_for_dropdowns(clean_raw, clean_html, group_size=group_size) if split_groups else [{"raw": clean_raw, "html": clean_html}]
        section = get_or_create_section(section_title)
        for group in groups:
            section["dropdowns"].append(
                {
                    "entry_title": entry_title,
                    "raw_lines": group["raw"],
                    "html_lines": group["html"],
                }
            )

    def add_grouped_dropdown(section_title, entry_title, entry_blocks):
        clean_blocks = []
        for block in entry_blocks:
            raw_lines = [line for line in (clean_text(line) for line in block.get("raw_lines", [])) if line]
            html_lines = [line for line in block.get("html_lines", []) if clean_text(line)]
            if not raw_lines or not html_lines:
                continue
            clean_blocks.append(
                {
                    "title": clean_text(block.get("title")) or "Details",
                    "raw_lines": raw_lines,
                    "html_lines": html_lines,
                }
            )
        if not clean_blocks:
            return
        get_or_create_section(section_title)["dropdowns"].append({"entry_title": entry_title, "entry_blocks": clean_blocks})

    for attack in preview_context.get("attacks", []):
        add_entry_dropdowns("Attacks", attack.get("name") or "Attack", attack.get("text_lines", []), attack.get("text_lines_html", []))

    for level in preview_context.get("class_ability_levels", []):
        blocks = []
        for feature in level.get("features", []):
            blocks.append(
                {
                    "title": clean_text(feature.get("name")) or "Feature",
                    "raw_lines": feature.get("text_lines", []),
                    "html_lines": feature.get("text_lines_html", []),
                }
            )
        add_grouped_dropdown("Class Abilities", f"Level {level.get('level') or '?'}", blocks)

    for subclass in preview_context.get("class_subclasses", []):
        blocks = []
        for feature in subclass.get("features", []):
            level_label = feature.get("level") or "?"
            feature_name = clean_text(feature.get("name"))
            heading = f"Level {level_label}: {feature_name}" if feature_name else f"Level {level_label}"
            blocks.append(
                {
                    "title": heading,
                    "raw_lines": feature.get("text_lines", []),
                    "html_lines": feature.get("text_lines_html", []),
                }
            )
        add_grouped_dropdown("Subclasses", subclass.get("name") or "Subclass", blocks)

    for level_key, section_title, default_title in (
        ("class_option_levels", "Class Options", "Option"),
        ("class_progression_levels", "Class Progression", "Progression"),
    ):
        for level in preview_context.get(level_key, []):
            blocks = []
            for feature in level.get("features", []):
                blocks.append(
                    {
                        "title": clean_text(feature.get("name")) or default_title,
                        "raw_lines": feature.get("text_lines", []),
                        "html_lines": feature.get("text_lines_html", []),
                    }
                )
            add_grouped_dropdown(section_title, f"Level {level.get('level') or '?'}", blocks)

    for section in preview_context.get("object_sections", []):
        for entry in section.get("entries", []):
            add_entry_dropdowns(
                section.get("title") or "Details",
                entry.get("name") or "Entry",
                entry.get("text_lines", []),
                entry.get("text_lines_html", []),
            )

    add_entry_dropdowns("Details", "Overview", preview_context.get("description_lines", []), preview_context.get("description_lines_html", []))

    payload_sections = []
    for section_index, section in enumerate(sections):
        dropdowns = []
        for dropdown_index, source in enumerate(section["dropdowns"]):
            dropdown_id = f"rules-{section_index + 1}-{dropdown_index + 1}"
            if source.get("entry_blocks"):
                blocks = []
                for block in source["entry_blocks"]:
                    key_rules, bullets = extract_key_rules_and_bullets(block["raw_lines"])
                    key_rules_html = [linkify_text_line(sentence, reference_lookup, pattern, seen_terms=set()) for sentence in key_rules]
                    bullets_html = [linkify_text_line(item, reference_lookup, pattern, seen_terms=set()) for item in bullets]
                    blocks.append(
                        {
                            "title": block["title"],
                            "paragraphs_html": block["html_lines"],
                            "key_rules_html": key_rules_html,
                            "bullets_html": bullets_html,
                        }
                    )
                dropdowns.append({"id": dropdown_id, "title": source["entry_title"], "blocks": blocks, "is_open": False})
            else:
                dropdowns.append(
                    build_dropdown_payload(
                        source["entry_title"],
                        source["raw_lines"],
                        source["html_lines"],
                        dropdown_id,
                        is_open=False,
                        reference_lookup=reference_lookup,
                        pattern=pattern,
                    )
                )
        payload_sections.append({"title": section["title"], "dropdowns": dropdowns})

    return payload_sections
