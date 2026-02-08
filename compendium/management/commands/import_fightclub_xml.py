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
}


def _text(value):
    if value is None:
        return ""
    return value.strip()


def _merge_value(target, key, value):
    if key in target:
        if not isinstance(target[key], list):
            target[key] = [target[key]]
        target[key].append(value)
    else:
        target[key] = value


def element_to_dict(element):
    payload = {}
    if element.attrib:
        payload["_attributes"] = dict(element.attrib)

    children = list(element)
    if not children:
        text = _text(element.text)
        if text:
            payload["value"] = text
        return payload

    for child in children:
        if list(child):
            value = element_to_dict(child)
        else:
            value = _text(child.text)
            if child.attrib:
                value = {"value": value, "_attributes": dict(child.attrib)}
        _merge_value(payload, child.tag, value)

    return payload


def normalize_for_hashing(value):
    if isinstance(value, dict):
        return {key: normalize_for_hashing(value[key]) for key in sorted(value.keys())}
    if isinstance(value, list):
        return [normalize_for_hashing(item) for item in value]
    return value


def deterministic_external_id(system, object_type, name, raw_payload):
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
    candidates = [
        _text(element.attrib.get("id")),
        _text(element.attrib.get("uid")),
        _text(element.findtext("id")),
        _text(element.findtext("uid")),
    ]
    for candidate in candidates:
        if candidate:
            return candidate
    return ""


def extract_name(element):
    name = _text(element.findtext("name"))
    if name:
        return name
    return _text(element.attrib.get("name")) or "Unnamed"


def extract_description(element):
    for tag in ("text", "description"):
        value = _text(element.findtext(tag))
        if value:
            return value
    return ""


class Command(BaseCommand):
    help = "Import Fight Club XML content into GameObject rows."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to dnd.xml file")
        parser.add_argument("--system", required=True, help="Game system key, e.g. dnd5e")

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        system = options["system"].strip()

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

        for xml_tag, object_type in OBJECT_TYPE_MAP.items():
            for element in root.findall(f".//{xml_tag}"):
                name = extract_name(element)
                description = extract_description(element)
                payload = element_to_dict(element)

                external_id = extract_external_id(element)
                if not external_id:
                    external_id = deterministic_external_id(system, object_type, name, payload)

                match = GameObject.objects.filter(
                    system=system,
                    object_type=object_type,
                    external_id=external_id,
                ).first()

                if match is None:
                    match = GameObject.objects.filter(
                        system=system,
                        object_type=object_type,
                        name=name,
                    ).first()
                    if match is not None and match.external_id:
                        external_id = match.external_id

                defaults = {
                    "name": name,
                    "description": description,
                    "data": payload,
                    "source": GameObject.SourceType.IMPORTED,
                    "external_id": external_id,
                }

                if match is None:
                    GameObject.objects.create(system=system, object_type=object_type, **defaults)
                    created_count += 1
                else:
                    changed = False
                    for field, value in defaults.items():
                        if getattr(match, field) != value:
                            setattr(match, field, value)
                            changed = True
                    if changed:
                        match.save()
                        updated_count += 1
                    else:
                        skipped_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete. Created={created_count}, Updated={updated_count}, Unchanged={skipped_count}"
            )
        )
