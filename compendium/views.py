import re
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
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
                lines.append(f"{name}: {text}")
            elif text:
                lines.append(text)
            elif name:
                lines.append(name)
            return

        cleaned = _clean_text(item)
        if cleaned:
            lines.append(cleaned)

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


def _apply_search_filters(queryset, request):
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

    sort = request.GET.get("sort")
    if sort == "favorites":
        favorites = Favorite.objects.filter(user=request.user, game_object=OuterRef("pk"))
        queryset = queryset.annotate(is_favorite=Exists(favorites)).order_by("-is_favorite", "object_type", "name")
    else:
        queryset = queryset.order_by("object_type", "name")

    return queryset.distinct(), {
        "q": query,
        "object_type": object_type,
        "tag": tag_id,
        "favorites": "1" if favorites_only else "0",
        "sort": sort or "",
    }


@login_required
def object_list(request):
    objects = GameObject.objects.prefetch_related("tags")
    objects, active_filters = _apply_search_filters(objects, request)
    tags = Tag.objects.order_by("name")
    favorites = set(Favorite.objects.filter(user=request.user).values_list("game_object_id", flat=True))
    paginator = Paginator(objects, 100)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)
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
    game_object = get_object_or_404(GameObject.objects.prefetch_related("tags"), pk=pk)
    form = GameObjectEditForm(instance=game_object)
    games = Game.objects.order_by("title")
    is_favorite = Favorite.objects.filter(user=request.user, game_object=game_object).exists()

    context = {
        "game_object": game_object,
        "form": form,
        "games": games,
        "is_favorite": is_favorite,
    }
    return render_page(request, "compendium/object_detail.html", context)


@login_required
@require_GET
def object_preview_modal(request, pk):
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

    games = Game.objects.order_by("title")
    is_favorite = Favorite.objects.filter(user=request.user, game_object=game_object).exists()
    context = {
        "game_object": game_object,
        "form": form,
        "games": games,
        "is_favorite": is_favorite,
    }
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
        .prefetch_related("tags")
        .order_by("name")[:8]
    )
    return render_page(request, "compendium/partials/search_preview.html", {"objects": objects})


@login_required
@require_GET
def quick_search_redirect(request):
    query = request.GET.get("q", "").strip()
    if not query:
        return redirect("compendium:list")
    return redirect(f"/compendium/?q={query}")


@login_required
@require_POST
def remove_tag(request, pk):
    tag = get_object_or_404(Tag, pk=pk)
    if tag.is_system_tag and not request.user.is_staff:
        return HttpResponseBadRequest("System tags can only be deleted by staff users.")
    tag.delete()
    messages.success(request, "Tag deleted.")
    return redirect("compendium:tags")
