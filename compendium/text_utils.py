import re

from .models import GameObject


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


def to_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def append_readable_chunks(lines, value, max_chunk_length=260):
    text = clean_text(value)
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
                for index in range(0, len(sentence), max_chunk_length):
                    chunk = sentence[index:index + max_chunk_length].strip()
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


def extract_text_lines(value):
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
            name = clean_text(item.get("name"))
            text = clean_text(item.get("text"))
            if name and text:
                append_readable_chunks(lines, f"{name}: {text}")
            elif text:
                append_readable_chunks(lines, text)
            elif name:
                append_readable_chunks(lines, name)
            return

        append_readable_chunks(lines, item)

    collect(value)
    return lines


def humanize_key(key):
    if not key:
        return ""
    if key in FIELD_LABELS:
        return FIELD_LABELS[key]
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(key))
    normalized = normalized.replace("_", " ").replace("-", " ")
    return normalized.title()


def level_sort_key(level):
    try:
        return int(level)
    except (TypeError, ValueError):
        return 999


def extract_named_entries(value, default_name="Entry", level=""):
    entries = []
    for item in to_list(value):
        if isinstance(item, dict):
            name = clean_text(item.get("name")) or default_name
            text_lines = []
            if "text" in item:
                text_lines.extend(extract_text_lines(item.get("text")))
            elif "value" in item:
                text_lines.extend(extract_text_lines(item.get("value")))

            for key, nested_value in item.items():
                if key in {"_attributes", "name", "text", "value"}:
                    continue
                nested_lines = extract_text_lines(nested_value)
                if nested_lines:
                    text_lines.append(f"{humanize_key(key)}: {'; '.join(nested_lines)}")

            if name or text_lines:
                entries.append(
                    {
                        "name": name or default_name,
                        "text_lines": text_lines,
                        "level": level,
                        "attributes": item.get("_attributes") if isinstance(item.get("_attributes"), dict) else {},
                    }
                )
            continue

        cleaned = clean_text(item)
        if cleaned:
            entries.append({"name": default_name, "text_lines": [cleaned], "level": level, "attributes": {}})

    return entries


def build_section(title, entries):
    compact = len(entries) <= 1 and all(len(" ".join(entry.get("text_lines", []))) < 180 for entry in entries)
    return {
        "title": title,
        "entries": entries,
        "use_disclosure": not compact,
    }


def extract_monster_attacks(data):
    raw_actions = data.get("action")
    action_entries = []
    for action in extract_named_entries(raw_actions, default_name="Attack"):
        text = " ".join(action["text_lines"]).lower()
        attack_expr = clean_text((action.get("attributes") or {}).get("attack"))
        is_attack = bool(attack_expr) or "weapon attack" in text or "spell attack" in text or "attack:" in text
        action_entries.append({"name": action["name"], "text_lines": action["text_lines"], "is_attack": is_attack})

    attack_entries = [entry for entry in action_entries if entry["is_attack"]]
    return attack_entries if attack_entries else action_entries


def detect_subclass_name(feature_name, known_subclasses):
    feature_name = clean_text(feature_name)
    if not feature_name:
        return ""

    parenthetical_match = re.search(r"\(([^()]+)\)\s*$", feature_name)
    if parenthetical_match:
        return clean_text(parenthetical_match.group(1))

    if ":" in feature_name:
        prefix, suffix = [part.strip() for part in feature_name.split(":", 1)]
        if prefix in known_subclasses:
            return prefix
        if prefix in SUBCLASS_PREFIXES:
            return suffix

    return ""


def extract_class_sections(data):
    autolevel_entries = to_list(data.get("autolevel"))
    abilities_by_level = {}
    options_by_level = {}
    progression_by_level = {}
    subclass_map = {}
    known_subclasses = set()

    for level_entry in autolevel_entries:
        if not isinstance(level_entry, dict):
            continue
        level = clean_text((level_entry.get("_attributes") or {}).get("level")) or "?"

        slot_text = clean_text(level_entry.get("slots"))
        if slot_text:
            progression_by_level.setdefault(level, []).append(
                {"name": "Spell Slots", "text_lines": [slot_text], "level": level}
            )

        for counter_value in to_list(level_entry.get("counter")):
            if isinstance(counter_value, dict):
                counter_name = clean_text(counter_value.get("name")) or "Counter"
                counter_text = clean_text(counter_value.get("value"))
                reset_code = clean_text(counter_value.get("reset")).upper()
                text_lines = [counter_text] if counter_text else []
                reset_label = COUNTER_RESET_LABELS.get(reset_code, "")
                if reset_label:
                    text_lines.append(f"Reset: {reset_label}")
                progression_by_level.setdefault(level, []).append(
                    {"name": counter_name, "text_lines": text_lines, "level": level}
                )
                continue

            cleaned_counter = clean_text(counter_value)
            if cleaned_counter:
                progression_by_level.setdefault(level, []).append(
                    {"name": "Counter", "text_lines": [cleaned_counter], "level": level}
                )

        for feature in extract_named_entries(level_entry.get("feature"), default_name="Feature", level=level):
            optional = clean_text((feature.get("attributes") or {}).get("optional")).upper() == "YES"
            if not optional:
                abilities_by_level.setdefault(level, []).append(feature)
                continue

            subclass_name = detect_subclass_name(feature.get("name"), known_subclasses)
            if subclass_name:
                known_subclasses.add(subclass_name)
                subclass_map.setdefault(subclass_name, []).append(feature)
            else:
                options_by_level.setdefault(level, []).append(feature)

    class_ability_levels = [
        {"level": level, "features": abilities_by_level[level]}
        for level in sorted(abilities_by_level.keys(), key=level_sort_key)
    ]
    class_option_levels = [
        {"level": level, "features": options_by_level[level]}
        for level in sorted(options_by_level.keys(), key=level_sort_key)
    ]
    class_progression_levels = [
        {"level": level, "features": progression_by_level[level]}
        for level in sorted(progression_by_level.keys(), key=level_sort_key)
    ]

    class_subclasses = []
    for subclass_name in sorted(subclass_map.keys()):
        features = sorted(subclass_map[subclass_name], key=lambda feature: level_sort_key(feature.get("level")))
        class_subclasses.append({"name": subclass_name, "features": features})

    return class_ability_levels, class_subclasses, class_option_levels, class_progression_levels


def extract_additional_sections(data, consumed_keys):
    entries = []
    for key, value in data.items():
        if key in consumed_keys or key == "name":
            continue
        text_lines = extract_text_lines(value)
        if text_lines:
            entries.append({"name": humanize_key(key), "text_lines": text_lines, "level": "", "attributes": {}})

    return build_section("Additional Details", entries) if entries else None


def build_preview_context(game_object):
    data = game_object.data if isinstance(game_object.data, dict) else {}
    object_type = game_object.object_type
    description_lines = extract_text_lines(data.get("text")) or extract_text_lines(game_object.description)

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
        attacks = extract_monster_attacks(data)
        traits = extract_named_entries(data.get("trait"), default_name="Trait")
        reactions = extract_named_entries(data.get("reaction"), default_name="Reaction")
        legendary_actions = extract_named_entries(data.get("legendary"), default_name="Legendary Action")
        if traits:
            object_sections.append(build_section("Traits", traits))
            consumed_keys.add("trait")
        if reactions:
            object_sections.append(build_section("Reactions", reactions))
            consumed_keys.add("reaction")
        if legendary_actions:
            object_sections.append(build_section("Legendary Actions", legendary_actions))
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
        class_ability_levels, class_subclasses, class_option_levels, class_progression_levels = extract_class_sections(data)
    elif object_type == GameObject.ObjectType.RACE:
        summary_pairs = [
            ("Size", data.get("size")),
            ("Speed", data.get("speed")),
            ("Ability Bonuses", data.get("ability")),
            ("Spell Ability", data.get("spellAbility")),
            ("Proficiencies", data.get("proficiency")),
        ]
        consumed_keys.update({"size", "speed", "ability", "spellAbility", "proficiency"})
        traits = extract_named_entries(data.get("trait"), default_name="Trait")
        if traits:
            object_sections.append(build_section("Traits", traits))
            consumed_keys.add("trait")
    elif object_type == GameObject.ObjectType.FEAT:
        summary_pairs = [("Prerequisite", data.get("prerequisite"))]
        consumed_keys.update({"prerequisite"})
        modifiers = extract_named_entries(data.get("modifier"), default_name="Modifier")
        if modifiers:
            object_sections.append(build_section("Modifiers", modifiers))
            consumed_keys.add("modifier")
    elif object_type == GameObject.ObjectType.BACKGROUND:
        summary_pairs = [("Proficiencies", data.get("proficiency"))]
        consumed_keys.update({"proficiency"})
        traits = extract_named_entries(data.get("trait"), default_name="Trait")
        if traits:
            object_sections.append(build_section("Traits", traits))
            consumed_keys.add("trait")
    elif object_type == GameObject.ObjectType.CONDITION:
        summary_pairs = [("Impact", data.get("impact")), ("Ends When", data.get("ends_when"))]
        consumed_keys.update({"impact", "ends_when", "effects", "levels", "source_reference"})
        effects = extract_named_entries(data.get("effects"), default_name="Effect")
        levels = extract_named_entries(data.get("levels"), default_name="Level")
        if effects:
            object_sections.append(build_section("Effects", effects))
        if levels:
            object_sections.append(build_section("Exhaustion Levels", levels))
    else:
        summary_pairs = [
            ("Type", object_type),
            ("System", game_object.system),
            ("Source", game_object.source),
        ]

    normalized_summary = []
    for label, value in summary_pairs:
        cleaned = clean_text(value)
        if cleaned:
            normalized_summary.append((label, cleaned))

    additional_section = extract_additional_sections(data, consumed_keys)
    if additional_section:
        object_sections.append(additional_section)

    return {
        "description_lines": description_lines,
        "summary_pairs": normalized_summary,
        "attacks": attacks,
        "object_sections": object_sections,
        "class_ability_levels": class_ability_levels,
        "class_subclasses": class_subclasses,
        "class_option_levels": class_option_levels,
        "class_progression_levels": class_progression_levels,
    }
