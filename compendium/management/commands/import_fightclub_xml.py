import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from compendium.models import GameObject


OBJECT_TYPE_MAP = {
    "monster": GameObject.ObjectType.MONSTER,
    "spell": GameObject.ObjectType.SPELL,
    "item": GameObject.ObjectType.ITEM,
    "class": GameObject.ObjectType.CLASS,
    "race": GameObject.ObjectType.RACE,
    "feat": GameObject.ObjectType.FEAT,
    "background": GameObject.ObjectType.BACKGROUND,
    "condition": GameObject.ObjectType.CONDITION,
}


DND5E_CONDITIONS = [
    {
        "name": "Blinded",
        "impact": "A blinded creature cannot see.",
        "effects": [
            "A blinded creature cannot see.",
            "It automatically fails any ability check that requires sight.",
            "Attack rolls against it have advantage, and its own attack rolls have disadvantage.",
        ],
        "ends_when": "The effect causing blindness ends.",
    },
    {
        "name": "Charmed",
        "impact": "A charmed creature is socially influenced by its charmer.",
        "effects": [
            "A charmed creature cannot attack the charmer or target the charmer with harmful abilities or magical effects.",
            "The charmer has advantage on ability checks to interact socially with the charmed creature.",
        ],
        "ends_when": "The effect causing charm ends.",
    },
    {
        "name": "Deafened",
        "impact": "A deafened creature cannot hear.",
        "effects": [
            "A deafened creature cannot hear.",
            "It automatically fails any ability check that requires hearing.",
        ],
        "ends_when": "The effect causing deafness ends.",
    },
    {
        "name": "Exhaustion",
        "impact": "Exhaustion is tracked in cumulative levels and becomes deadly at level 6.",
        "effects": [
            "Exhaustion levels are cumulative.",
            "Some effects reduce exhaustion by one or more levels.",
            "At level 6, the creature dies.",
        ],
        "levels": [
            {"name": "Level 1", "text": "Disadvantage on ability checks."},
            {"name": "Level 2", "text": "Speed halved."},
            {"name": "Level 3", "text": "Disadvantage on attack rolls and saving throws."},
            {"name": "Level 4", "text": "Hit point maximum halved."},
            {"name": "Level 5", "text": "Speed reduced to 0."},
            {"name": "Level 6", "text": "Death."},
        ],
        "ends_when": "Reduced by rest, magic, or specific effects.",
    },
    {
        "name": "Frightened",
        "impact": "A frightened creature struggles while its fear source is visible.",
        "effects": [
            "A frightened creature has disadvantage on ability checks and attack rolls while the source of its fear is within line of sight.",
            "The creature cannot willingly move closer to the source of its fear.",
        ],
        "ends_when": "The effect causing fear ends.",
    },
    {
        "name": "Grappled",
        "impact": "A grappled creature's movement is stopped.",
        "effects": [
            "A grappled creature's speed becomes 0 and it cannot benefit from bonuses to its speed.",
            "The condition ends if the grappler is incapacitated.",
            "The condition also ends if an effect removes the grappled creature from the grappler's reach.",
        ],
        "ends_when": "Escape, forced movement, or grappler incapacitation ends the grapple.",
    },
    {
        "name": "Incapacitated",
        "impact": "An incapacitated creature cannot take meaningful turns.",
        "effects": [
            "An incapacitated creature cannot take actions or reactions.",
        ],
        "ends_when": "The effect causing incapacitation ends.",
    },
    {
        "name": "Invisible",
        "impact": "An invisible creature cannot be seen without special detection.",
        "effects": [
            "An invisible creature is impossible to see without a special sense or magic.",
            "For hiding, the creature is heavily obscured.",
            "Attack rolls against the creature have disadvantage, and the creature's attack rolls have advantage.",
        ],
        "ends_when": "The effect causing invisibility ends.",
    },
    {
        "name": "Paralyzed",
        "impact": "A paralyzed creature is helpless and vulnerable in melee.",
        "effects": [
            "A paralyzed creature is incapacitated and cannot move or speak.",
            "It automatically fails Strength and Dexterity saving throws.",
            "Attack rolls against it have advantage.",
            "Any attack that hits from within 5 feet is a critical hit.",
        ],
        "ends_when": "The effect causing paralysis ends.",
    },
    {
        "name": "Petrified",
        "impact": "A petrified creature is transformed into inert material and immobilized.",
        "effects": [
            "A petrified creature is transformed, along with nonmagical gear, into a solid inanimate substance.",
            "It is incapacitated, cannot move or speak, and is unaware of its surroundings.",
            "Attack rolls against it have advantage, and it automatically fails Strength and Dexterity saving throws.",
            "It has resistance to all damage and is immune to poison and disease.",
        ],
        "ends_when": "The effect causing petrification ends.",
    },
    {
        "name": "Poisoned",
        "impact": "A poisoned creature performs worse across attacks and ability checks.",
        "effects": [
            "A poisoned creature has disadvantage on attack rolls and ability checks.",
        ],
        "ends_when": "The effect causing poison ends.",
    },
    {
        "name": "Prone",
        "impact": "A prone creature is on the ground and less mobile.",
        "effects": [
            "A prone creature's only movement option is to crawl, unless it stands up and ends the condition.",
            "The creature has disadvantage on attack rolls.",
            "An attack roll against the creature has advantage if the attacker is within 5 feet; otherwise the attack roll has disadvantage.",
        ],
        "ends_when": "Standing up or other effects can end the condition.",
    },
    {
        "name": "Restrained",
        "impact": "A restrained creature is held in place and easier to hit.",
        "effects": [
            "A restrained creature's speed becomes 0 and it cannot benefit from bonuses to its speed.",
            "Attack rolls against it have advantage, and its own attack rolls have disadvantage.",
            "It has disadvantage on Dexterity saving throws.",
        ],
        "ends_when": "Escape or removal of the restraining effect ends the condition.",
    },
    {
        "name": "Stunned",
        "impact": "A stunned creature is dazed, immobile, and defenseless.",
        "effects": [
            "A stunned creature is incapacitated, cannot move, and can speak only falteringly.",
            "It automatically fails Strength and Dexterity saving throws.",
            "Attack rolls against it have advantage.",
        ],
        "ends_when": "The effect causing stun ends.",
    },
    {
        "name": "Unconscious",
        "impact": "An unconscious creature is unaware and highly vulnerable.",
        "effects": [
            "An unconscious creature is incapacitated, cannot move or speak, and is unaware of its surroundings.",
            "It drops whatever it is holding and falls prone.",
            "It automatically fails Strength and Dexterity saving throws.",
            "Attack rolls against it have advantage.",
            "Any attack that hits from within 5 feet is a critical hit.",
        ],
        "ends_when": "Damage, successful aid, or the ending effect can restore consciousness.",
    },
]


def _strip_text(value):
    """Trim XML text values while safely handling None."""
    if value is None:
        return ""
    return value.strip()


def _merge_value(target, key, value):
    """Merge repeated XML tags into list values."""
    if key in target:
        if not isinstance(target[key], list):
            target[key] = [target[key]]
        target[key].append(value)
    else:
        target[key] = value


def element_to_dict(element):
    """Convert an XML element tree into a JSON-serializable dictionary."""
    payload = {}
    if element.attrib:
        payload["_attributes"] = dict(element.attrib)

    children = list(element)
    if not children:
        text = _strip_text(element.text)
        if text:
            payload["value"] = text
        return payload

    for child in children:
        if list(child):
            value = element_to_dict(child)
        else:
            value = _strip_text(child.text)
            if child.attrib:
                value = {"value": value, "_attributes": dict(child.attrib)}
        _merge_value(payload, child.tag, value)

    return payload


def normalize_for_hashing(value):
    """Recursively sort dictionaries so payload hashing is stable."""
    if isinstance(value, dict):
        return {key: normalize_for_hashing(value[key]) for key in sorted(value.keys())}
    if isinstance(value, list):
        return [normalize_for_hashing(item) for item in value]
    return value


def deterministic_external_id(system, object_type, name, raw_payload):
    """Build a deterministic ID when source XML has no stable external identifier."""
    fingerprint = {
        "system": system,
        "object_type": object_type,
        "name": name,
        "payload": normalize_for_hashing(raw_payload),
    }
    encoded = json.dumps(fingerprint, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"{system}:{object_type}:{digest}"


def extract_external_id(element):
    """Try multiple common XML ID locations in priority order."""
    candidates = [
        _strip_text(element.attrib.get("id")),
        _strip_text(element.attrib.get("uid")),
        _strip_text(element.findtext("id")),
        _strip_text(element.findtext("uid")),
    ]
    for candidate in candidates:
        if candidate:
            return candidate
    return ""


def extract_name(element):
    """Read primary object name from child tags/attributes."""
    name = _strip_text(element.findtext("name"))
    if name:
        return name
    return _strip_text(element.attrib.get("name")) or "Unnamed"


def extract_description(element):
    """Choose first non-empty description-like field."""
    for tag in ("text", "description"):
        value = _strip_text(element.findtext(tag))
        if value:
            return value
    return ""


def _slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", _strip_text(value).lower()).strip("-")
    return slug or "condition"


def _condition_payload(definition):
    payload = {
        "impact": definition["impact"],
        "effects": list(definition["effects"]),
        "ends_when": definition["ends_when"],
        "text": [definition["impact"]],
        "source_reference": "D&D 5e Core Rules",
    }
    if definition.get("levels"):
        payload["levels"] = definition["levels"]
    return payload


def _upsert_dnd5e_conditions(system):
    if _strip_text(system).lower() != "dnd5e":
        return {"created": 0, "updated": 0, "unchanged": 0, "touched_object_ids": []}

    created_count = 0
    updated_count = 0
    unchanged_count = 0
    touched_object_ids = []

    for definition in DND5E_CONDITIONS:
        name = definition["name"]
        external_id = f"{system}:{GameObject.ObjectType.CONDITION}:{_slugify(name)}"
        defaults = {
            "name": name,
            "description": definition["impact"],
            "data": _condition_payload(definition),
            "source": GameObject.SourceType.OFFICIAL,
            "external_id": external_id,
        }

        existing_object = GameObject.objects.filter(
            system=system,
            object_type=GameObject.ObjectType.CONDITION,
            external_id=external_id,
        ).first()

        if existing_object is None:
            existing_object = GameObject.objects.filter(
                system=system,
                object_type=GameObject.ObjectType.CONDITION,
                name=name,
            ).first()
            if existing_object is not None and existing_object.external_id:
                defaults["external_id"] = existing_object.external_id

        if existing_object is None:
            created = GameObject.objects.create(
                system=system,
                object_type=GameObject.ObjectType.CONDITION,
                **defaults,
            )
            created_count += 1
            touched_object_ids.append(created.pk)
        else:
            changed = False
            for field, value in defaults.items():
                if getattr(existing_object, field) != value:
                    setattr(existing_object, field, value)
                    changed = True
            if changed:
                existing_object.save()
                updated_count += 1
            else:
                unchanged_count += 1
            touched_object_ids.append(existing_object.pk)

    return {
        "created": created_count,
        "updated": updated_count,
        "unchanged": unchanged_count,
        "touched_object_ids": touched_object_ids,
    }


def import_fightclub_xml_path(file_path, system):
    """Import/upsert supported Fight Club XML nodes into GameObject rows."""
    if not isinstance(file_path, Path):
        file_path = Path(file_path)
    system = (system or "").strip()

    if not file_path.exists() or not file_path.is_file():
        raise CommandError(f"File not found: {file_path}")
    if not system:
        raise CommandError("--system is required")

    try:
        root = ET.parse(file_path).getroot()
    except ET.ParseError as exc:
        raise CommandError(f"Invalid XML: {exc}") from exc

    created_count = 0
    updated_count = 0
    skipped_count = 0
    touched_object_ids = []

    for xml_tag, object_type in OBJECT_TYPE_MAP.items():
        for element in root.findall(f".//{xml_tag}"):
            name = extract_name(element)
            description = extract_description(element)
            payload = element_to_dict(element)

            external_id = extract_external_id(element)
            if not external_id:
                external_id = deterministic_external_id(system, object_type, name, payload)

            # Primary match path: stable external ID.
            existing_object = GameObject.objects.filter(
                system=system,
                object_type=object_type,
                external_id=external_id,
            ).first()

            if existing_object is None:
                # Secondary fallback keeps existing objects stable across re-imports.
                existing_object = GameObject.objects.filter(
                    system=system,
                    object_type=object_type,
                    name=name,
                ).first()
                if existing_object is not None and existing_object.external_id:
                    external_id = existing_object.external_id

            defaults = {
                "name": name,
                "description": description,
                "data": payload,
                "source": GameObject.SourceType.IMPORTED,
                "external_id": external_id,
            }

            if existing_object is None:
                created = GameObject.objects.create(system=system, object_type=object_type, **defaults)
                created_count += 1
                touched_object_ids.append(created.pk)
            else:
                changed = False
                for field, value in defaults.items():
                    if getattr(existing_object, field) != value:
                        setattr(existing_object, field, value)
                        changed = True
                if changed:
                    existing_object.save()
                    updated_count += 1
                else:
                    skipped_count += 1
                touched_object_ids.append(existing_object.pk)

    condition_result = _upsert_dnd5e_conditions(system)
    created_count += condition_result["created"]
    updated_count += condition_result["updated"]
    skipped_count += condition_result["unchanged"]
    touched_object_ids.extend(condition_result["touched_object_ids"])

    return {
        "created": created_count,
        "updated": updated_count,
        "unchanged": skipped_count,
        "touched_object_ids": touched_object_ids,
    }


class Command(BaseCommand):
    help = "Import Fight Club XML content into GameObject rows."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to dnd.xml file")
        parser.add_argument("--system", required=True, help="Game system key, e.g. dnd5e")

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        system = options["system"].strip()
        result = import_fightclub_xml_path(file_path=file_path, system=system)

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete. Created={result['created']}, Updated={result['updated']}, Unchanged={result['unchanged']}"
            )
        )
