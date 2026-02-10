import hashlib
import json
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
}


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
