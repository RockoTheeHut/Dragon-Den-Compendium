import re
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Case, Exists, IntegerField, OuterRef, Prefetch, Value, When
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET, require_POST

from core.rendering import render_page
from games.models import Game

from .forms import GameObjectCreateForm, GameObjectEditForm, TagForm
from .models import Favorite, GameObject, Tag


FIELD_LABELS = {
    "ac": "Armor Class",
    "cha": "CHA",
    "conditionImmune": "Condition Immunities",
    "con": "CON",
    "cr": "Challenge",
    "dex": "DEX",
    "dmg1": "Damage",
    "dmgType": "Damage Type",
    "hd": "Hit Die",
    "hp": "Hit Points",
    "int": "INT",
    "numSkills": "Skill Choices",
    "spellAbility": "Primary Ability",
    "str": "STR",
    "wis": "WIS",
}

SUBCLASS_PREFIXES = {
    "Arcane Tradition",
    "Artificer Specialist",
    "Bard College",
    "Divine Domain",
    "Druid Circle",
    "Martial Archetype",
    "Monastic Tradition",
    "Otherworldly Patron",
    "Primal Path",
    "Ranger Archetype",
    "Roguish Archetype",
    "Sacred Oath",
    "Sorcerous Origin",
}

COUNTER_RESET_LABELS = {
    "S": "Short Rest",
    "L": "Long Rest",
    "D": "Daily",
}

REFERENCE_OBJECT_TYPES = [
    GameObject.ObjectType.SPELL,
    GameObject.ObjectType.ITEM,
    GameObject.ObjectType.MONSTER,
    GameObject.ObjectType.CONDITION,
    GameObject.ObjectType.CLASS,
    GameObject.ObjectType.RACE,
    GameObject.ObjectType.FEAT,
    GameObject.ObjectType.BACKGROUND,
]

KEY_RULE_SENTENCE_PATTERN = re.compile(
    r"\b(\d+|gp|sp|cp|pp|hour|hours|minute|minutes|day|days|round|rounds|level|levels|slot|slots|rest|rests|cost|costs|maximum|minimum|must|can't|cannot)\b",
    flags=re.IGNORECASE,
)
INLINE_LIST_HINT_PATTERN = re.compile(r"\b(for example|such as|the following)\b", flags=re.IGNORECASE)
WORD_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
KEY_TERM_EMPHASIS = ["spellbook", "cantrip", "spell level", "prepared spells"]
OBJECT_TYPE_SORT_ORDER = [
    GameObject.ObjectType.CLASS,
    GameObject.ObjectType.FEAT,
    GameObject.ObjectType.ITEM,
    GameObject.ObjectType.MONSTER,
    GameObject.ObjectType.CONDITION,
    GameObject.ObjectType.SPELL,
    GameObject.ObjectType.RACE,
    GameObject.ObjectType.BACKGROUND,
    GameObject.ObjectType.CHARACTER,
    GameObject.ObjectType.NPC,
    GameObject.ObjectType.MISC,
]


def _to_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _clean_text(value):
    if value is None:
        return ""
    text = str(value).strip()
    return text


def _append_readable_chunks(lines, value, max_chunk_length=260):
    text = _clean_text(value)
    if not text:
        return

    paragraph_blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    if not paragraph_blocks:
        paragraph_blocks = [text]

    for block in paragraph_blocks:
        normalized = re.sub(r"\s+", " ", block).strip()
        if len(normalized) <= max_chunk_length:
            lines.append(normalized)
            continue

        sentence_parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", normalized) if part.strip()]
        if len(sentence_parts) <= 1:
            sentence_parts = [part.strip() for part in re.split(r";\s+", normalized) if part.strip()]
        if len(sentence_parts) <= 1:
            sentence_parts = [part.strip() for part in re.split(r",\s+", normalized) if part.strip()]
        if len(sentence_parts) <= 1:
            sentence_parts = [normalized]

        current = ""
        for sentence in sentence_parts:
            if len(sentence) > max_chunk_length:
                if current:
                    lines.append(current)
                    current = ""
                for i in range(0, len(sentence), max_chunk_length):
                    chunk = sentence[i:i + max_chunk_length].strip()
                    if chunk:
                        lines.append(chunk)
                continue

            if not current:
                current = sentence
                continue

            if len(current) + 1 + len(sentence) <= max_chunk_length:
                current = f"{current} {sentence}"
            else:
                lines.append(current)
                current = sentence

        if current:
            lines.append(current)


def _extract_text_lines(value):
    lines = []

    def collect(item):
        if item is None:
            return
        if isinstance(item, list):
            for child in item:
                collect(child)
            return
        if isinstance(item, dict):
            if "text" in item:
                collect(item.get("text"))
                return
            if "value" in item:
                collect(item.get("value"))
                return
            name = _clean_text(item.get("name"))
            text = _clean_text(item.get("text"))
            if name and text:
                _append_readable_chunks(lines, f"{name}: {text}")
            elif text:
                _append_readable_chunks(lines, text)
            elif name:
                _append_readable_chunks(lines, name)
            return

        _append_readable_chunks(lines, item)

    collect(value)
    return lines


def _humanize_key(key):
    if not key:
        return ""
    if key in FIELD_LABELS:
        return FIELD_LABELS[key]
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(key))
    normalized = normalized.replace("_", " ").replace("-", " ")
    return normalized.title()


def _level_sort_key(level):
    try:
        return int(level)
    except (TypeError, ValueError):
        return 999


def _extract_named_entries(value, default_name="Entry", level=""):
    entries = []
    for item in _to_list(value):
        if isinstance(item, dict):
            name = _clean_text(item.get("name")) or default_name
            text_lines = []
            if "text" in item:
                text_lines.extend(_extract_text_lines(item.get("text")))
            elif "value" in item:
                text_lines.extend(_extract_text_lines(item.get("value")))

            for key, nested_value in item.items():
                if key in {"_attributes", "name", "text", "value"}:
                    continue
                nested_lines = _extract_text_lines(nested_value)
                if nested_lines:
                    text_lines.append(f"{_humanize_key(key)}: {'; '.join(nested_lines)}")

            if not name and not text_lines:
                continue

            entries.append(
                {
                    "name": name or default_name,
                    "text_lines": text_lines,
                    "level": level,
                    "attributes": item.get("_attributes") if isinstance(item.get("_attributes"), dict) else {},
                }
            )
            continue

        cleaned = _clean_text(item)
        if not cleaned:
            continue
        entries.append({"name": default_name, "text_lines": [cleaned], "level": level, "attributes": {}})

    return entries


def _build_section(title, entries):
    compact = len(entries) <= 1 and all(len(" ".join(entry.get("text_lines", []))) < 180 for entry in entries)
    return {
        "title": title,
        "entries": entries,
        "use_disclosure": not compact,
    }


def _extract_monster_attacks(data):
    raw_actions = data.get("action")
    action_entries = []
    for action in _extract_named_entries(raw_actions, default_name="Attack"):
        text = " ".join(action["text_lines"]).lower()
        attack_expr = _clean_text((action.get("attributes") or {}).get("attack"))
        is_attack = bool(attack_expr) or "weapon attack" in text or "spell attack" in text or "attack:" in text
        action_entries.append({"name": action["name"], "text_lines": action["text_lines"], "is_attack": is_attack})

    attack_entries = [entry for entry in action_entries if entry["is_attack"]]
    return attack_entries if attack_entries else action_entries


def _detect_subclass_name(feature_name, known_subclasses):
    feature_name = _clean_text(feature_name)
    if not feature_name:
        return ""

    parenthetical_match = re.search(r"\(([^()]+)\)\s*$", feature_name)
    if parenthetical_match:
        return _clean_text(parenthetical_match.group(1))

    if ":" in feature_name:
        prefix, suffix = [part.strip() for part in feature_name.split(":", 1)]
        if prefix in known_subclasses:
            return prefix
        if prefix in SUBCLASS_PREFIXES:
            return suffix

    return ""


def _extract_class_sections(data):
    autolevel_entries = _to_list(data.get("autolevel"))
    abilities_by_level = {}
    options_by_level = {}
    progression_by_level = {}
    subclass_map = {}
    known_subclasses = set()

    for level_entry in autolevel_entries:
        if not isinstance(level_entry, dict):
            continue
        level = _clean_text((level_entry.get("_attributes") or {}).get("level")) or "?"

        slot_text = _clean_text(level_entry.get("slots"))
        if slot_text:
            progression_by_level.setdefault(level, []).append(
                {"name": "Spell Slots", "text_lines": [slot_text], "level": level}
            )

        for counter_value in _to_list(level_entry.get("counter")):
            if isinstance(counter_value, dict):
                counter_name = _clean_text(counter_value.get("name")) or "Counter"
                counter_text = _clean_text(counter_value.get("value"))
                reset_code = _clean_text(counter_value.get("reset")).upper()
                text_lines = [counter_text] if counter_text else []
                reset_label = COUNTER_RESET_LABELS.get(reset_code, "")
                if reset_label:
                    text_lines.append(f"Reset: {reset_label}")
                progression_by_level.setdefault(level, []).append(
                    {"name": counter_name, "text_lines": text_lines, "level": level}
                )
                continue

            cleaned_counter = _clean_text(counter_value)
            if cleaned_counter:
                progression_by_level.setdefault(level, []).append(
                    {"name": "Counter", "text_lines": [cleaned_counter], "level": level}
                )

        for feature in _extract_named_entries(level_entry.get("feature"), default_name="Feature", level=level):
            optional = _clean_text((feature.get("attributes") or {}).get("optional")).upper() == "YES"
            if not optional:
                abilities_by_level.setdefault(level, []).append(feature)
                continue

            subclass_name = _detect_subclass_name(feature.get("name"), known_subclasses)
            if subclass_name:
                known_subclasses.add(subclass_name)
                subclass_map.setdefault(subclass_name, []).append(feature)
            else:
                options_by_level.setdefault(level, []).append(feature)

    class_ability_levels = [
        {"level": level, "features": abilities_by_level[level]}
        for level in sorted(abilities_by_level.keys(), key=_level_sort_key)
    ]
    class_option_levels = [
        {"level": level, "features": options_by_level[level]}
        for level in sorted(options_by_level.keys(), key=_level_sort_key)
    ]
    class_progression_levels = [
        {"level": level, "features": progression_by_level[level]}
        for level in sorted(progression_by_level.keys(), key=_level_sort_key)
    ]

    class_subclasses = []
    for subclass_name in sorted(subclass_map.keys()):
        features = sorted(subclass_map[subclass_name], key=lambda feature: _level_sort_key(feature.get("level")))
        class_subclasses.append({"name": subclass_name, "features": features})

    return class_ability_levels, class_subclasses, class_option_levels, class_progression_levels


def _extract_additional_sections(data, consumed_keys):
    entries = []
    for key, value in data.items():
        if key in consumed_keys or key == "name":
            continue
        text_lines = _extract_text_lines(value)
        if not text_lines:
            continue
        entries.append({"name": _humanize_key(key), "text_lines": text_lines, "level": "", "attributes": {}})

    return _build_section("Additional Details", entries) if entries else None


def _build_preview_context(game_object):
    data = game_object.data if isinstance(game_object.data, dict) else {}
    object_type = game_object.object_type
    description_lines = _extract_text_lines(data.get("text")) or _extract_text_lines(game_object.description)

    summary_pairs = []
    attacks = []
    object_sections = []
    class_ability_levels = []
    class_subclasses = []
    class_option_levels = []
    class_progression_levels = []
    consumed_keys = {"name", "text"}

    if object_type == GameObject.ObjectType.MONSTER:
        summary_pairs = [
            ("Size", data.get("size")),
            ("Type", data.get("type")),
            ("Alignment", data.get("alignment")),
            ("Armor Class", data.get("ac")),
            ("Hit Points", data.get("hp")),
            ("Speed", data.get("speed")),
            ("STR", data.get("str")),
            ("DEX", data.get("dex")),
            ("CON", data.get("con")),
            ("INT", data.get("int")),
            ("WIS", data.get("wis")),
            ("CHA", data.get("cha")),
            ("Challenge", data.get("cr")),
            ("Senses", data.get("senses")),
            ("Languages", data.get("languages")),
        ]
        consumed_keys.update({"size", "type", "alignment", "ac", "hp", "speed", "str", "dex", "con", "int", "wis", "cha", "cr", "senses", "languages", "action"})
        attacks = _extract_monster_attacks(data)
        traits = _extract_named_entries(data.get("trait"), default_name="Trait")
        reactions = _extract_named_entries(data.get("reaction"), default_name="Reaction")
        legendary_actions = _extract_named_entries(data.get("legendary"), default_name="Legendary Action")
        if traits:
            object_sections.append(_build_section("Traits", traits))
            consumed_keys.add("trait")
        if reactions:
            object_sections.append(_build_section("Reactions", reactions))
            consumed_keys.add("reaction")
        if legendary_actions:
            object_sections.append(_build_section("Legendary Actions", legendary_actions))
            consumed_keys.add("legendary")
    elif object_type == GameObject.ObjectType.SPELL:
        summary_pairs = [
            ("Level", data.get("level")),
            ("School", data.get("school")),
            ("Casting Time", data.get("time")),
            ("Range", data.get("range")),
            ("Components", data.get("components")),
            ("Duration", data.get("duration")),
            ("Classes", data.get("classes")),
            ("Ritual", data.get("ritual")),
            ("Roll", data.get("roll")),
        ]
        consumed_keys.update({"level", "school", "time", "range", "components", "duration", "classes", "ritual", "roll"})
    elif object_type == GameObject.ObjectType.ITEM:
        summary_pairs = [
            ("Item Type", data.get("type")),
            ("Value", data.get("value")),
            ("Weight", data.get("weight")),
            ("Damage", data.get("dmg1")),
            ("Damage Type", data.get("dmgType")),
            ("Armor Class", data.get("ac")),
            ("Range", data.get("range")),
            ("Properties", data.get("property")),
        ]
        consumed_keys.update({"type", "value", "weight", "dmg1", "dmgType", "ac", "range", "property"})
    elif object_type == GameObject.ObjectType.CLASS:
        summary_pairs = [
            ("Hit Die", data.get("hd")),
            ("Primary Ability", data.get("spellAbility")),
            ("Skill Choices", data.get("numSkills")),
            ("Armor", data.get("armor")),
            ("Weapons", data.get("weapons")),
            ("Tools", data.get("tools")),
            ("Starting Wealth", data.get("wealth")),
            ("Proficiencies", data.get("proficiency")),
        ]
        consumed_keys.update({"hd", "spellAbility", "numSkills", "armor", "weapons", "tools", "wealth", "proficiency", "autolevel"})
        class_ability_levels, class_subclasses, class_option_levels, class_progression_levels = _extract_class_sections(data)
    elif object_type == GameObject.ObjectType.RACE:
        summary_pairs = [
            ("Size", data.get("size")),
            ("Speed", data.get("speed")),
            ("Ability Bonuses", data.get("ability")),
            ("Spell Ability", data.get("spellAbility")),
            ("Proficiencies", data.get("proficiency")),
        ]
        consumed_keys.update({"size", "speed", "ability", "spellAbility", "proficiency"})
        traits = _extract_named_entries(data.get("trait"), default_name="Trait")
        if traits:
            object_sections.append(_build_section("Traits", traits))
            consumed_keys.add("trait")
    elif object_type == GameObject.ObjectType.FEAT:
        summary_pairs = [
            ("Prerequisite", data.get("prerequisite")),
        ]
        consumed_keys.update({"prerequisite"})
        modifiers = _extract_named_entries(data.get("modifier"), default_name="Modifier")
        if modifiers:
            object_sections.append(_build_section("Modifiers", modifiers))
            consumed_keys.add("modifier")
    elif object_type == GameObject.ObjectType.BACKGROUND:
        summary_pairs = [
            ("Proficiencies", data.get("proficiency")),
        ]
        consumed_keys.update({"proficiency"})
        traits = _extract_named_entries(data.get("trait"), default_name="Trait")
        if traits:
            object_sections.append(_build_section("Traits", traits))
            consumed_keys.add("trait")
    elif object_type == GameObject.ObjectType.CONDITION:
        summary_pairs = [
            ("Impact", data.get("impact")),
            ("Ends When", data.get("ends_when")),
        ]
        consumed_keys.update({"impact", "ends_when", "effects", "levels", "source_reference"})
        effects = _extract_named_entries(data.get("effects"), default_name="Effect")
        levels = _extract_named_entries(data.get("levels"), default_name="Level")
        if effects:
            object_sections.append(_build_section("Effects", effects))
        if levels:
            object_sections.append(_build_section("Exhaustion Levels", levels))
    else:
        summary_pairs = [
            ("Type", object_type),
            ("System", game_object.system),
            ("Source", game_object.source),
        ]

    normalized_summary = []
    for label, value in summary_pairs:
        cleaned = _clean_text(value)
        if cleaned:
            normalized_summary.append((label, cleaned))

    additional_section = _extract_additional_sections(data, consumed_keys)
    if additional_section:
        object_sections.append(additional_section)

    return {
        "game_object": game_object,
        "description_lines": description_lines,
        "summary_pairs": normalized_summary,
        "attacks": attacks,
        "object_sections": object_sections,
        "class_ability_levels": class_ability_levels,
        "class_subclasses": class_subclasses,
        "class_option_levels": class_option_levels,
        "class_progression_levels": class_progression_levels,
    }


def _collect_preview_text_lines(preview_context):
    lines = []
    lines.extend(preview_context.get("description_lines", []))
    lines.extend(value for _, value in preview_context.get("summary_pairs", []))

    for attack in preview_context.get("attacks", []):
        lines.append(_clean_text(attack.get("name")))
        lines.extend(_to_list(attack.get("text_lines")))

    for section in preview_context.get("object_sections", []):
        lines.append(_clean_text(section.get("title")))
        for entry in section.get("entries", []):
            lines.append(_clean_text(entry.get("name")))
            lines.extend(_to_list(entry.get("text_lines")))

    for level in preview_context.get("class_ability_levels", []):
        for feature in level.get("features", []):
            lines.append(_clean_text(feature.get("name")))
            lines.extend(_to_list(feature.get("text_lines")))

    for subclass in preview_context.get("class_subclasses", []):
        lines.append(_clean_text(subclass.get("name")))
        for feature in subclass.get("features", []):
            lines.append(_clean_text(feature.get("name")))
            lines.extend(_to_list(feature.get("text_lines")))

    for level in preview_context.get("class_option_levels", []):
        for feature in level.get("features", []):
            lines.append(_clean_text(feature.get("name")))
            lines.extend(_to_list(feature.get("text_lines")))

    for level in preview_context.get("class_progression_levels", []):
        for feature in level.get("features", []):
            lines.append(_clean_text(feature.get("name")))
            lines.extend(_to_list(feature.get("text_lines")))

    return [line for line in (_clean_text(line) for line in lines) if line]


def _build_related_reference_groups(game_object, preview_context):
    text_lines = _collect_preview_text_lines(preview_context)
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
        name = _clean_text(candidate_name)
        if not name:
            continue

        simple_name = re.sub(r"[^a-z0-9]+", "", name.lower())
        if len(simple_name) < 4:
            continue

        lowered_name = name.lower()
        if not _is_reference_candidate(corpus_tokens, lowered_name):
            continue

        if lowered_name not in corpus:
            continue

        if not _contains_whole_phrase(corpus, lowered_name):
            continue

        bucket = grouped.get(candidate_object_type)
        max_items = 24 if candidate_object_type == GameObject.ObjectType.CONDITION else 12
        if bucket is None or len(bucket) >= max_items:
            continue
        bucket.append({"id": candidate_id, "name": name})

    result = []
    for object_type in REFERENCE_OBJECT_TYPES:
        items = grouped.get(object_type) or []
        if not items:
            continue
        result.append(
            {
                "object_type": object_type,
                "label": object_type_labels.get(object_type, object_type.title()),
                "items": items,
            }
        )
    return result


def _is_reference_candidate(corpus_tokens, lowered_name):
    name_tokens = [token for token in WORD_TOKEN_PATTERN.findall(lowered_name) if len(token) >= 3]
    if not name_tokens:
        return False
    return all(token in corpus_tokens for token in name_tokens)


def _contains_whole_phrase(corpus, phrase):
    start = 0
    phrase_length = len(phrase)
    while True:
        index = corpus.find(phrase, start)
        if index == -1:
            return False
        end = index + phrase_length
        before_ok = index == 0 or not corpus[index - 1].isalnum()
        after_ok = end == len(corpus) or not corpus[end].isalnum()
        if before_ok and after_ok:
            return True
        start = index + 1


def _build_reference_lookup(related_reference_groups):
    lookup = {}
    for group in related_reference_groups:
        for item in group.get("items", []):
            key = _clean_text(item.get("name")).lower()
            object_id = item.get("id")
            if key and object_id and key not in lookup:
                lookup[key] = object_id
    return lookup


def _compile_reference_pattern(reference_lookup):
    if not reference_lookup:
        return None
    names = sorted(reference_lookup.keys(), key=len, reverse=True)
    if not names:
        return None
    pattern = r"(?<![A-Za-z0-9])(" + "|".join(re.escape(name) for name in names) + r")(?![A-Za-z0-9])"
    return re.compile(pattern, flags=re.IGNORECASE)


def _split_sentences(text):
    cleaned = _clean_text(text)
    if not cleaned:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]


def _extract_key_rules_and_bullets(raw_lines):
    key_rules = []
    bullets = []

    def append_unique(target, value):
        candidate = _clean_text(value)
        if candidate and candidate not in target:
            target.append(candidate)

    for raw_line in raw_lines:
        line = _clean_text(raw_line)
        if not line:
            continue

        for sentence in _split_sentences(line):
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


def _group_lines_for_dropdowns(raw_lines, html_lines, group_size=3):
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


def _format_plain_segment_with_emphasis(segment, seen_terms):
    text = _clean_text(segment)
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
    after = _format_plain_segment_with_emphasis(text[next_match.end():], seen_terms)
    return mark_safe(f"{before}{highlighted}{after}")


def _linkify_text_line(text, reference_lookup, pattern, seen_terms=None):
    cleaned = _clean_text(text)
    if not cleaned:
        return ""
    if pattern is None:
        return _format_plain_segment_with_emphasis(cleaned, seen_terms)

    parts = []
    last_index = 0
    for match in pattern.finditer(cleaned):
        start, end = match.span()
        object_id = reference_lookup.get(match.group(0).lower())
        if object_id is None:
            continue
        if start > last_index:
            parts.append(_format_plain_segment_with_emphasis(cleaned[last_index:start], seen_terms))
        parts.append(
            format_html(
                '<button class="compendium-inline-ref" type="button" onclick="openCompendiumPreviewModal({})">{}</button>',
                object_id,
                match.group(0),
            )
        )
        last_index = end

    if last_index < len(cleaned):
        parts.append(_format_plain_segment_with_emphasis(cleaned[last_index:], seen_terms))

    if not parts:
        return _format_plain_segment_with_emphasis(cleaned, seen_terms)
    return mark_safe("".join(str(part) for part in parts))


def _apply_inline_reference_links(preview_context, reference_lookup, pattern):
    description_seen_terms = set()
    preview_context["description_lines_html"] = [
        _linkify_text_line(line, reference_lookup, pattern, description_seen_terms)
        for line in preview_context.get("description_lines", [])
    ]

    for attack in preview_context.get("attacks", []):
        seen_terms = set()
        attack["text_lines_html"] = [
            _linkify_text_line(line, reference_lookup, pattern, seen_terms) for line in attack.get("text_lines", [])
        ]

    for section in preview_context.get("object_sections", []):
        for entry in section.get("entries", []):
            seen_terms = set()
            entry["text_lines_html"] = [
                _linkify_text_line(line, reference_lookup, pattern, seen_terms) for line in entry.get("text_lines", [])
            ]

    for level in preview_context.get("class_ability_levels", []):
        for feature in level.get("features", []):
            seen_terms = set()
            feature["text_lines_html"] = [
                _linkify_text_line(line, reference_lookup, pattern, seen_terms) for line in feature.get("text_lines", [])
            ]

    for subclass in preview_context.get("class_subclasses", []):
        for feature in subclass.get("features", []):
            seen_terms = set()
            feature["text_lines_html"] = [
                _linkify_text_line(line, reference_lookup, pattern, seen_terms) for line in feature.get("text_lines", [])
            ]

    for level in preview_context.get("class_option_levels", []):
        for feature in level.get("features", []):
            seen_terms = set()
            feature["text_lines_html"] = [
                _linkify_text_line(line, reference_lookup, pattern, seen_terms) for line in feature.get("text_lines", [])
            ]

    for level in preview_context.get("class_progression_levels", []):
        for feature in level.get("features", []):
            seen_terms = set()
            feature["text_lines_html"] = [
                _linkify_text_line(line, reference_lookup, pattern, seen_terms) for line in feature.get("text_lines", [])
            ]


def _build_dropdown_payload(title, raw_lines, html_lines, dropdown_id, is_open, reference_lookup, pattern):
    key_rules, bullets = _extract_key_rules_and_bullets(raw_lines)
    key_rules_html = [
        _linkify_text_line(sentence, reference_lookup, pattern, seen_terms=set()) for sentence in key_rules
    ]
    bullets_html = [
        _linkify_text_line(item, reference_lookup, pattern, seen_terms=set()) for item in bullets
    ]
    return {
        "id": dropdown_id,
        "title": title,
        "paragraphs_html": html_lines,
        "key_rules_html": key_rules_html,
        "bullets_html": bullets_html,
        "is_open": is_open,
    }


def _build_rules_sections(preview_context, reference_lookup, pattern):
    sections = []

    def get_or_create_section(title):
        for section in sections:
            if section["title"] == title:
                return section
        section = {"title": title, "dropdowns": []}
        sections.append(section)
        return section

    def add_entry_dropdowns(section_title, entry_title, raw_lines, html_lines, split_groups=False, group_size=3):
        clean_raw = [line for line in (_clean_text(line) for line in raw_lines) if line]
        clean_html = [line for line in html_lines if _clean_text(line)]
        if not clean_raw or not clean_html:
            return
        if split_groups:
            groups = _group_lines_for_dropdowns(clean_raw, clean_html, group_size=group_size)
        else:
            groups = [{"raw": clean_raw, "html": clean_html}]
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
            raw_lines = [line for line in (_clean_text(line) for line in block.get("raw_lines", [])) if line]
            html_lines = [line for line in block.get("html_lines", []) if _clean_text(line)]
            if not raw_lines or not html_lines:
                continue
            clean_blocks.append(
                {
                    "title": _clean_text(block.get("title")) or "Details",
                    "raw_lines": raw_lines,
                    "html_lines": html_lines,
                }
            )
        if not clean_blocks:
            return
        section = get_or_create_section(section_title)
        section["dropdowns"].append(
            {
                "entry_title": entry_title,
                "entry_blocks": clean_blocks,
            }
        )

    for attack in preview_context.get("attacks", []):
        add_entry_dropdowns("Attacks", attack.get("name") or "Attack", attack.get("text_lines", []), attack.get("text_lines_html", []))

    for level in preview_context.get("class_ability_levels", []):
        level_label = level.get("level") or "?"
        blocks = []
        for feature in level.get("features", []):
            feature_name = _clean_text(feature.get("name"))
            blocks.append(
                {
                    "title": feature_name or "Feature",
                    "raw_lines": feature.get("text_lines", []),
                    "html_lines": feature.get("text_lines_html", []),
                }
            )
        add_grouped_dropdown("Class Abilities", f"Level {level_label}", blocks)

    for subclass in preview_context.get("class_subclasses", []):
        subclass_name = subclass.get("name") or "Subclass"
        blocks = []
        for feature in subclass.get("features", []):
            level_label = feature.get("level") or "?"
            feature_name = _clean_text(feature.get("name"))
            heading = f"Level {level_label}: {feature_name}" if feature_name else f"Level {level_label}"
            blocks.append(
                {
                    "title": heading,
                    "raw_lines": feature.get("text_lines", []),
                    "html_lines": feature.get("text_lines_html", []),
                }
            )
        add_grouped_dropdown("Subclasses", subclass_name, blocks)

    for level in preview_context.get("class_option_levels", []):
        level_label = level.get("level") or "?"
        blocks = []
        for feature in level.get("features", []):
            feature_name = _clean_text(feature.get("name"))
            blocks.append(
                {
                    "title": feature_name or "Option",
                    "raw_lines": feature.get("text_lines", []),
                    "html_lines": feature.get("text_lines_html", []),
                }
            )
        add_grouped_dropdown("Class Options", f"Level {level_label}", blocks)

    for level in preview_context.get("class_progression_levels", []):
        level_label = level.get("level") or "?"
        blocks = []
        for feature in level.get("features", []):
            feature_name = _clean_text(feature.get("name"))
            blocks.append(
                {
                    "title": feature_name or "Progression",
                    "raw_lines": feature.get("text_lines", []),
                    "html_lines": feature.get("text_lines_html", []),
                }
            )
        add_grouped_dropdown("Class Progression", f"Level {level_label}", blocks)

    for section in preview_context.get("object_sections", []):
        section_title = section.get("title") or "Details"
        for entry in section.get("entries", []):
            add_entry_dropdowns(
                section_title,
                entry.get("name") or "Entry",
                entry.get("text_lines", []),
                entry.get("text_lines_html", []),
            )

    add_entry_dropdowns(
        "Details",
        "Overview",
        preview_context.get("description_lines", []),
        preview_context.get("description_lines_html", []),
    )

    payload_sections = []
    for section_index, section in enumerate(sections):
        dropdowns = []
        for dropdown_index, source in enumerate(section["dropdowns"]):
            dropdown_id = f"rules-{section_index + 1}-{dropdown_index + 1}"
            if source.get("entry_blocks"):
                blocks = []
                for block in source["entry_blocks"]:
                    key_rules, bullets = _extract_key_rules_and_bullets(block["raw_lines"])
                    key_rules_html = [
                        _linkify_text_line(sentence, reference_lookup, pattern, seen_terms=set())
                        for sentence in key_rules
                    ]
                    bullets_html = [
                        _linkify_text_line(item, reference_lookup, pattern, seen_terms=set())
                        for item in bullets
                    ]
                    blocks.append(
                        {
                            "title": block["title"],
                            "paragraphs_html": block["html_lines"],
                            "key_rules_html": key_rules_html,
                            "bullets_html": bullets_html,
                        }
                    )
                dropdowns.append(
                    {
                        "id": dropdown_id,
                        "title": source["entry_title"],
                        "blocks": blocks,
                        "is_open": False,
                    }
                )
            else:
                dropdowns.append(
                    _build_dropdown_payload(
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


def _with_object_type_sort_order(queryset):
    whens = [
        When(object_type=object_type, then=Value(index))
        for index, object_type in enumerate(OBJECT_TYPE_SORT_ORDER)
    ]
    return queryset.annotate(
        object_type_order=Case(
            *whens,
            default=Value(len(OBJECT_TYPE_SORT_ORDER)),
            output_field=IntegerField(),
        )
    )


def _apply_search_filters(queryset, request):
    """Apply list filters/sorting and return both queryset and serialized filter state."""
    query = request.GET.get("q", "").strip()
    object_type = request.GET.get("object_type", "").strip()
    tag_id = request.GET.get("tag", "").strip()
    favorites_only = request.GET.get("favorites") == "1"

    if query:
        queryset = queryset.filter(name__icontains=query)

    if object_type:
        queryset = queryset.filter(object_type=object_type)

    if tag_id.isdigit():
        queryset = queryset.filter(tags__id=int(tag_id))

    if favorites_only:
        queryset = queryset.filter(favorited_by__user=request.user)

    queryset = _with_object_type_sort_order(queryset)
    sort = request.GET.get("sort")
    if sort == "favorites":
        favorites = Favorite.objects.filter(user=request.user, game_object=OuterRef("pk"))
        queryset = queryset.annotate(is_favorite=Exists(favorites)).order_by("-is_favorite", "object_type_order", "name")
    else:
        queryset = queryset.order_by("object_type_order", "name")

    return queryset.distinct(), {
        "q": query,
        "object_type": object_type,
        "tag": tag_id,
        "favorites": "1" if favorites_only else "0",
        "sort": sort or "",
    }


@login_required
def object_list(request):
    """Paginated compendium list with tag/favorite metadata for the current page."""
    objects = (
        GameObject.objects.only("id", "name", "object_type", "system", "source")
        .prefetch_related(Prefetch("tags", queryset=Tag.objects.only("id", "name", "color").order_by("name")))
    )
    objects, active_filters = _apply_search_filters(objects, request)
    tags = Tag.objects.only("id", "name").order_by("name")
    paginator = Paginator(objects, 100)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)
    page_object_ids = [item.id for item in page_obj.object_list]
    favorites = set(
        Favorite.objects.filter(user=request.user, game_object_id__in=page_object_ids).values_list("game_object_id", flat=True)
    )
    scroll_query = urlencode(active_filters)

    context = {
        "objects": page_obj.object_list,
        "tags": tags,
        "favorites": favorites,
        "object_type_choices": GameObject.ObjectType.choices,
        "active_filters": active_filters,
        "page_obj": page_obj,
        "has_next": page_obj.has_next(),
        "next_page_number": page_obj.next_page_number() if page_obj.has_next() else None,
        "scroll_query": scroll_query,
    }

    if request.headers.get("HX-Request") and request.GET.get("append") == "1":
        return render(request, "compendium/partials/object_rows.html", context)
    return render_page(request, "compendium/object_list.html", context)


@login_required
def object_create(request):
    if request.method == "POST":
        form = GameObjectCreateForm(request.POST)
        if form.is_valid():
            game_object = form.save()
            messages.success(request, "Game object created.")
            return redirect("compendium:object_detail", pk=game_object.pk)
    else:
        form = GameObjectCreateForm(initial={"system": "dnd5e"})

    return render_page(request, "compendium/object_create.html", {"form": form})


@login_required
def object_detail(request, pk):
    """Full object detail page with parsed rules/preview context."""
    game_object = get_object_or_404(GameObject.objects.prefetch_related("tags"), pk=pk)
    form = GameObjectEditForm(instance=game_object)
    context = _build_object_detail_context(game_object=game_object, form=form, user=request.user)
    return render_page(request, "compendium/object_detail.html", context)


@login_required
@require_GET
def object_preview_modal(request, pk):
    """Lightweight preview content loaded into the shared modal shell."""
    game_object = get_object_or_404(GameObject, pk=pk)
    context = _build_preview_context(game_object)
    return render(request, "compendium/partials/object_preview_modal_content.html", context)


@login_required
@require_POST
def object_edit(request, pk):
    game_object = get_object_or_404(GameObject, pk=pk)
    form = GameObjectEditForm(request.POST, instance=game_object)
    if form.is_valid():
        form.save()
        messages.success(request, "Game object updated.")
        return redirect("compendium:object_detail", pk=pk)

    context = _build_object_detail_context(game_object=game_object, form=form, user=request.user)
    return render_page(request, "compendium/object_detail.html", context)


@login_required
@require_POST
def toggle_favorite(request, pk):
    game_object = get_object_or_404(GameObject, pk=pk)
    favorite, created = Favorite.objects.get_or_create(user=request.user, game_object=game_object)
    if not created:
        favorite.delete()

    if request.headers.get("HX-Request"):
        is_favorite = created
        return render_page(
            request,
            "compendium/partials/favorite_button.html",
            {"game_object": game_object, "is_favorite": is_favorite},
        )
    return redirect("compendium:object_detail", pk=pk)


@login_required
def tag_list(request):
    if request.method == "POST":
        form = TagForm(request.POST)
        if form.is_valid():
            tag = form.save(commit=False)
            if not tag.is_system_tag:
                tag.created_by = request.user
            tag.save()
            messages.success(request, "Tag saved.")
            return redirect("compendium:tags")
    else:
        form = TagForm(initial={"system": "dnd5e", "color": "#4A90E2"})

    tags = Tag.objects.order_by("system", "name")
    return render_page(request, "compendium/tag_list.html", {"form": form, "tags": tags})


@login_required
@require_POST
def tag_update(request, pk):
    tag = get_object_or_404(Tag, pk=pk)
    form = TagForm(request.POST, instance=tag)
    if form.is_valid():
        updated = form.save(commit=False)
        if not updated.is_system_tag:
            updated.created_by = request.user
        updated.save()
        messages.success(request, "Tag updated.")
    else:
        messages.error(request, "Could not update tag.")
    return redirect("compendium:tags")


@login_required
@require_GET
def search_preview(request):
    query = request.GET.get("q", "").strip()
    if not query:
        return render_page(request, "compendium/partials/search_preview.html", {"objects": []})

    objects = (
        GameObject.objects.filter(name__icontains=query)
        .only("id", "name", "object_type")
        .prefetch_related(Prefetch("tags", queryset=Tag.objects.only("id", "name", "color").order_by("name")))
        .order_by("name")[:8]
    )
    return render_page(request, "compendium/partials/search_preview.html", {"objects": objects})


@login_required
@require_GET
def quick_search_redirect(request):
    query = request.GET.get("q", "").strip()
    if not query:
        return redirect("compendium:list")
    return redirect(f"{reverse('compendium:list')}?{urlencode({'q': query})}")


@login_required
@require_POST
def remove_tag(request, pk):
    tag = get_object_or_404(Tag, pk=pk)
    if tag.is_system_tag:
        return HttpResponseBadRequest("System tags cannot be deleted.")
    tag.delete()
    messages.success(request, "Tag deleted.")
    return redirect("compendium:tags")


def _build_object_detail_context(game_object, form, user):
    """Assemble reusable detail context for both GET detail and invalid edit POST."""
    preview_context = _build_preview_context(game_object)
    related_reference_groups = _build_related_reference_groups(game_object, preview_context)
    reference_lookup = _build_reference_lookup(related_reference_groups)
    reference_pattern = _compile_reference_pattern(reference_lookup)
    _apply_inline_reference_links(preview_context, reference_lookup, reference_pattern)
    rules_sections = _build_rules_sections(preview_context, reference_lookup, reference_pattern)
    return {
        "game_object": game_object,
        "form": form,
        "games": Game.objects.only("id", "title").order_by("title"),
        "is_favorite": Favorite.objects.filter(user=user, game_object=game_object).exists(),
        "related_reference_groups": related_reference_groups,
        "rules_sections": rules_sections,
        **preview_context,
    }
