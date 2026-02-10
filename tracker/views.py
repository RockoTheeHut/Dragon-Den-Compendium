import re

from django.contrib.auth.decorators import login_required
from django.db.models import Case, F, IntegerField, Max, Value, When
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from compendium.models import GameObject
from core.rendering import render_page
from games.models import Encounter, GamePlayer

from .forms import AddFromCompendiumForm, AddFromGamePlayerForm, TurnTrackerEntryForm
from .models import StatusEffect, TurnTrackerEntry

ACTIVE_TRACKER_ENCOUNTER_SESSION_KEY = "active_tracker_encounter_id"


def _parse_int(value):
    """Parse common int-like strings/dicts coming from imported monster data."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        number_match = re.search(r"-?\d+", value)
        if not number_match:
            return None
        return int(number_match.group(0))
    if isinstance(value, dict):
        for key in ("value", "max", "current", "hp", "hit_points"):
            parsed = _parse_int(value.get(key))
            if parsed is not None:
                return parsed
    return None


def _extract_hp(data):
    """Return (current_hp, max_hp) from mixed source shapes."""
    if not isinstance(data, dict):
        return None, None

    current = None
    maximum = None
    current_keys = ("hp_current", "current_hp", "hp", "hit_points")
    max_keys = ("hp_max", "max_hp", "hit_points_max", "hit_points")

    for key in current_keys:
        current = _parse_int(data.get(key))
        if current is not None:
            break

    for key in max_keys:
        maximum = _parse_int(data.get(key))
        if maximum is not None:
            break

    if current is not None and maximum is None:
        maximum = current
    return current, maximum


def _clear_active_encounter(request):
    request.session.pop(ACTIVE_TRACKER_ENCOUNTER_SESSION_KEY, None)


def _get_active_encounter(request):
    raw_id = request.session.get(ACTIVE_TRACKER_ENCOUNTER_SESSION_KEY)
    try:
        encounter_id = int(raw_id)
    except (TypeError, ValueError):
        _clear_active_encounter(request)
        return None
    encounter = Encounter.objects.select_related("game").filter(pk=encounter_id, game__created_by=request.user).first()
    if encounter is None:
        _clear_active_encounter(request)
        return None
    return encounter


def _entry_queryset(user, encounter=None):
    """Canonical tracker ordering and prefetch strategy for list rendering."""
    queryset = TurnTrackerEntry.objects.filter(user=user, encounter=encounter)
    return queryset.prefetch_related("status_effects").order_by("sort_order", "id")


def _scoped_entry_queryset(request):
    encounter = _get_active_encounter(request)
    return _entry_queryset(request.user, encounter=encounter), encounter


def _extract_snapshot_object_id(snapshot):
    if not isinstance(snapshot, dict):
        return None
    raw_value = snapshot.get("_source_object_id")
    try:
        source_id = int(raw_value)
    except (TypeError, ValueError):
        return None
    if source_id <= 0:
        return None
    return source_id


def _resolve_compendium_object_for_entry(entry):
    """Best-effort lookup for the original monster object behind an entry snapshot."""
    if entry.source_kind != TurnTrackerEntry.SourceKind.COMPENDIUM_MONSTER:
        return None

    source_id = _extract_snapshot_object_id(entry.source_snapshot)
    if source_id is not None:
        return GameObject.objects.filter(
            pk=source_id,
            object_type=GameObject.ObjectType.MONSTER,
        ).first()

    if entry.source_name:
        return (
            GameObject.objects.filter(
                object_type=GameObject.ObjectType.MONSTER,
                name=entry.source_name,
            )
            .order_by("id")
            .first()
        )
    return None


def _extract_attack_actions(monster_data):
    """Normalize monster actions into a display-friendly attack list."""
    raw_actions = monster_data.get("action")
    if isinstance(raw_actions, dict):
        action_items = [raw_actions]
    elif isinstance(raw_actions, list):
        action_items = [item for item in raw_actions if isinstance(item, dict)]
    else:
        action_items = []

    normalized = []
    for action in action_items:
        name = str(action.get("name") or "").strip()
        text = str(action.get("text") or "").strip()
        attack_expr = str(action.get("attack") or "").strip()
        if not text and attack_expr:
            text = attack_expr
        if not name:
            name = "Attack"
        normalized.append(
            {
                "name": name,
                "text": text,
                "is_attack": bool(attack_expr) or "attack:" in text.lower() or "weapon attack" in text.lower() or "spell attack" in text.lower(),
            }
        )

    attacks_only = [item for item in normalized if item["is_attack"]]
    return attacks_only if attacks_only else normalized


def _list_context(request):
    entries_queryset, encounter = _scoped_entry_queryset(request)
    return {
        "entries": list(entries_queryset),
        "encounter": encounter,
    }


def _add_forms_context(request):
    encounter = _get_active_encounter(request)
    encounter_game = encounter.game if encounter else None
    return {
        "manual_form": TurnTrackerEntryForm(initial={"entry_type": TurnTrackerEntry.EntryType.PLAYER, "is_active": True}),
        "from_compendium_form": AddFromCompendiumForm(initial={"entry_type": TurnTrackerEntry.EntryType.ENEMY, "is_active": True}),
        "from_player_form": AddFromGamePlayerForm(
            user=request.user,
            game=encounter_game,
            initial={"is_active": True},
        ),
    }


def _render_list_region(request, status=200):
    if request.headers.get("HX-Request"):
        return render(request, "tracker/partials/list_region.html", _list_context(request), status=status)
    return render_page(request, "tracker/dashboard.html", _list_context(request))


def _render_quick_update_response(request, entry):
    if request.headers.get("HX-Request"):
        return render(request, "tracker/partials/quick_update_oob.html", {"entry": entry})
    return _render_list_region(request)


def _normalize_sort_order(user, encounter=None):
    """Ensure contiguous ordering and persist changes in a single bulk update."""
    entries = list(TurnTrackerEntry.objects.filter(user=user, encounter=encounter).order_by("sort_order", "id"))
    updates = []
    for index, entry in enumerate(entries):
        if entry.sort_order != index:
            entry.sort_order = index
            updates.append(entry)
    if updates:
        TurnTrackerEntry.objects.bulk_update(updates, ["sort_order"])


def _create_status_effect_from_post(entry, post_data):
    """Create an optional status effect from add-entry form fields."""
    name = (post_data.get("status_effect_name") or post_data.get("name") or "").strip()
    if not name:
        return

    rounds_raw = (post_data.get("status_effect_rounds") or post_data.get("duration_rounds") or "").strip()
    try:
        duration = int(rounds_raw) if rounds_raw else 1
    except ValueError:
        duration = 1
    duration = max(duration, 1)

    max_sort = entry.status_effects.aggregate(max_sort=Max("sort_order")).get("max_sort")
    StatusEffect.objects.create(
        entry=entry,
        name=name,
        duration_rounds=duration,
        remaining_rounds=duration,
        is_running=True,
        sort_order=(max_sort + 1) if max_sort is not None else 0,
    )


@login_required
def dashboard(request):
    encounter_id = request.GET.get("encounter", "").strip()
    if encounter_id:
        encounter = Encounter.objects.filter(pk=encounter_id, game__created_by=request.user).first()
        if encounter is None:
            return HttpResponseBadRequest("Encounter not found.")
        request.session[ACTIVE_TRACKER_ENCOUNTER_SESSION_KEY] = encounter.pk
    else:
        _clear_active_encounter(request)
    return render_page(request, "tracker/dashboard.html", _list_context(request))


@login_required
@require_GET
def add_entry_modal(request):
    return render(request, "tracker/partials/add_entry_modal_content.html", _add_forms_context(request))


@login_required
@require_POST
def add_entry(request):
    form = TurnTrackerEntryForm(request.POST)
    if form.is_valid():
        encounter = _get_active_encounter(request)
        max_sort = TurnTrackerEntry.objects.filter(user=request.user, encounter=encounter).aggregate(max_sort=Max("sort_order")).get("max_sort")
        entry = form.save(commit=False)
        entry.user = request.user
        entry.encounter = encounter
        entry.sort_order = (max_sort + 1) if max_sort is not None else 0
        entry.source_kind = TurnTrackerEntry.SourceKind.MANUAL
        entry.save()
        _create_status_effect_from_post(entry, request.POST)
        return _render_list_region(request)

    return _render_list_region(request, status=400)


@login_required
@require_POST
def add_from_compendium(request):
    form = AddFromCompendiumForm(request.POST)
    if form.is_valid():
        encounter = _get_active_encounter(request)
        source = form.cleaned_data["source"]
        hp_current_default, hp_max_default = _extract_hp(source.data)
        source_snapshot = dict(source.data) if isinstance(source.data, dict) else {}
        source_snapshot["_source_object_id"] = source.pk
        max_sort = TurnTrackerEntry.objects.filter(user=request.user, encounter=encounter).aggregate(max_sort=Max("sort_order")).get("max_sort")
        entry = TurnTrackerEntry.objects.create(
            user=request.user,
            encounter=encounter,
            name=(form.cleaned_data.get("name") or "").strip() or source.name,
            entry_type=form.cleaned_data["entry_type"],
            initiative=form.cleaned_data.get("initiative"),
            is_active=form.cleaned_data.get("is_active") if form.cleaned_data.get("is_active") is not None else True,
            notes=form.cleaned_data.get("notes") or "",
            hp_current=form.cleaned_data.get("hp_current") if form.cleaned_data.get("hp_current") is not None else hp_current_default,
            hp_max=form.cleaned_data.get("hp_max") if form.cleaned_data.get("hp_max") is not None else hp_max_default,
            items_text=form.cleaned_data.get("items_text") or "",
            source_kind=TurnTrackerEntry.SourceKind.COMPENDIUM_MONSTER,
            source_name=source.name,
            source_snapshot=source_snapshot,
            sort_order=(max_sort + 1) if max_sort is not None else 0,
        )
        _create_status_effect_from_post(entry, request.POST)
        return _render_list_region(request)

    return _render_list_region(request, status=400)


@login_required
@require_POST
def add_from_game_player(request):
    encounter = _get_active_encounter(request)
    form = AddFromGamePlayerForm(request.POST, user=request.user, game=(encounter.game if encounter else None))
    if form.is_valid():
        source = form.cleaned_data["source"]
        max_sort = TurnTrackerEntry.objects.filter(user=request.user, encounter=encounter).aggregate(max_sort=Max("sort_order")).get("max_sort")
        entry = TurnTrackerEntry.objects.create(
            user=request.user,
            encounter=encounter,
            name=(form.cleaned_data.get("name") or "").strip() or source.name,
            entry_type=TurnTrackerEntry.EntryType.PLAYER,
            initiative=form.cleaned_data.get("initiative"),
            is_active=form.cleaned_data.get("is_active") if form.cleaned_data.get("is_active") is not None else True,
            notes=(form.cleaned_data.get("notes") or "").strip() or source.notes or "",
            source_kind=TurnTrackerEntry.SourceKind.GAME_INSTANCE,
            source_name=source.name,
            source_snapshot={
                "game_player_id": source.pk,
                "ac": source.ac,
                "notes": source.notes,
                "strength": source.strength,
                "dexterity": source.dexterity,
                "constitution": source.constitution,
                "intelligence": source.intelligence,
                "wisdom": source.wisdom,
                "charisma": source.charisma,
            },
            sort_order=(max_sort + 1) if max_sort is not None else 0,
        )
        _create_status_effect_from_post(entry, request.POST)
        return _render_list_region(request)

    return _render_list_region(request, status=400)


@login_required
@require_GET
def edit_entry_modal(request, entry_id):
    entry = get_object_or_404(TurnTrackerEntry, pk=entry_id, user=request.user, encounter=_get_active_encounter(request))
    form = TurnTrackerEntryForm(instance=entry)
    return render(request, "tracker/partials/edit_entry_modal_content.html", {"entry": entry, "form": form})


@login_required
@require_POST
def edit_entry(request, entry_id):
    entry = get_object_or_404(TurnTrackerEntry, pk=entry_id, user=request.user, encounter=_get_active_encounter(request))
    form = TurnTrackerEntryForm(request.POST, instance=entry)
    if form.is_valid():
        form.save()
        return _render_list_region(request)
    return _render_list_region(request, status=400)


@login_required
@require_POST
def quick_update_entry(request, entry_id):
    encounter = _get_active_encounter(request)
    entry = get_object_or_404(
        TurnTrackerEntry.objects.prefetch_related("status_effects"),
        pk=entry_id,
        user=request.user,
        encounter=encounter,
    )
    updated_fields = []

    if "initiative" in request.POST:
        raw_value = (request.POST.get("initiative") or "").strip()
        if raw_value == "":
            entry.initiative = None
        else:
            try:
                entry.initiative = int(raw_value)
            except ValueError:
                return HttpResponseBadRequest("Initiative must be an integer.")
        updated_fields.append("initiative")

    if "hp_current" in request.POST and entry.entry_type != TurnTrackerEntry.EntryType.PLAYER:
        raw_value = (request.POST.get("hp_current") or "").strip()
        if raw_value == "":
            entry.hp_current = None
        else:
            try:
                entry.hp_current = int(raw_value)
            except ValueError:
                return HttpResponseBadRequest("HP must be an integer.")
        updated_fields.append("hp_current")

    if "is_active" in request.POST:
        entry.is_active = request.POST.get("is_active") in {"1", "true", "True", "on"}
        updated_fields.append("is_active")
        if not entry.is_active and entry.is_current:
            entry.is_current = False
            updated_fields.append("is_current")

    if updated_fields:
        # Keep update_fields deterministic and deduplicated.
        entry.save(update_fields=list(dict.fromkeys(updated_fields)))

    return _render_quick_update_response(request, entry)


@login_required
@require_POST
def remove_entry(request, entry_id):
    encounter = _get_active_encounter(request)
    entry = get_object_or_404(TurnTrackerEntry, pk=entry_id, user=request.user, encounter=encounter)
    entry.delete()
    _normalize_sort_order(request.user, encounter=encounter)
    return _render_list_region(request)


@login_required
@require_POST
def toggle_active(request, entry_id):
    entry = get_object_or_404(TurnTrackerEntry, pk=entry_id, user=request.user, encounter=_get_active_encounter(request))
    entry.is_active = not entry.is_active
    if not entry.is_active and entry.is_current:
        entry.is_current = False
        entry.save(update_fields=["is_active", "is_current"])
    else:
        entry.save(update_fields=["is_active"])
    return _render_list_region(request)


@login_required
@require_POST
def set_current(request, entry_id):
    encounter = _get_active_encounter(request)
    entry = get_object_or_404(TurnTrackerEntry, pk=entry_id, user=request.user, encounter=encounter)
    TurnTrackerEntry.objects.filter(user=request.user, encounter=encounter, is_current=True).update(is_current=False)
    entry.is_current = True
    entry.save(update_fields=["is_current"])
    return _render_list_region(request)


@login_required
@require_POST
def reorder_entries(request):
    encounter = _get_active_encounter(request)
    order = request.POST.get("order", "")
    ids = [int(value) for value in order.split(",") if value.strip().isdigit()]

    position_by_id = {entry_id: index for index, entry_id in enumerate(ids)}
    entries = list(TurnTrackerEntry.objects.filter(user=request.user, encounter=encounter, id__in=ids))
    updates = []
    for entry in entries:
        new_position = position_by_id.get(entry.id)
        if new_position is None or entry.sort_order == new_position:
            continue
        entry.sort_order = new_position
        updates.append(entry)
    if updates:
        TurnTrackerEntry.objects.bulk_update(updates, ["sort_order"])

    _normalize_sort_order(request.user, encounter=encounter)
    return _render_list_region(request)


@login_required
@require_POST
def move_up(request, entry_id):
    encounter = _get_active_encounter(request)
    _normalize_sort_order(request.user, encounter=encounter)
    entry = get_object_or_404(TurnTrackerEntry, pk=entry_id, user=request.user, encounter=encounter)
    if entry.sort_order > 0:
        prev_entry = TurnTrackerEntry.objects.filter(user=request.user, encounter=encounter, sort_order=entry.sort_order - 1).first()
        if prev_entry is not None:
            TurnTrackerEntry.objects.filter(pk__in=[entry.pk, prev_entry.pk]).update(
                sort_order=Case(
                    When(pk=entry.pk, then=Value(prev_entry.sort_order)),
                    When(pk=prev_entry.pk, then=Value(entry.sort_order)),
                    output_field=IntegerField(),
                )
            )
    return _render_list_region(request)


@login_required
@require_POST
def move_down(request, entry_id):
    encounter = _get_active_encounter(request)
    _normalize_sort_order(request.user, encounter=encounter)
    entry = get_object_or_404(TurnTrackerEntry, pk=entry_id, user=request.user, encounter=encounter)
    next_entry = TurnTrackerEntry.objects.filter(user=request.user, encounter=encounter, sort_order=entry.sort_order + 1).first()
    if next_entry is not None:
        TurnTrackerEntry.objects.filter(pk__in=[entry.pk, next_entry.pk]).update(
            sort_order=Case(
                When(pk=entry.pk, then=Value(next_entry.sort_order)),
                When(pk=next_entry.pk, then=Value(entry.sort_order)),
                output_field=IntegerField(),
            )
        )
    return _render_list_region(request)


@login_required
@require_POST
def advance_turn(request):
    encounter = _get_active_encounter(request)
    active_entries = list(TurnTrackerEntry.objects.filter(user=request.user, encounter=encounter, is_active=True).order_by("sort_order", "id"))
    if not active_entries:
        TurnTrackerEntry.objects.filter(user=request.user, encounter=encounter, is_current=True).update(is_current=False)
        return _render_list_region(request)

    current_entry = TurnTrackerEntry.objects.filter(user=request.user, encounter=encounter, is_current=True).first()
    if current_entry not in active_entries:
        next_entry = active_entries[0]
    else:
        next_index = (active_entries.index(current_entry) + 1) % len(active_entries)
        next_entry = active_entries[next_index]

    TurnTrackerEntry.objects.filter(user=request.user, encounter=encounter, is_current=True).update(is_current=False)
    next_entry.is_current = True
    next_entry.save(update_fields=["is_current"])

    StatusEffect.objects.filter(
        entry__user=request.user,
        entry__encounter=encounter,
        is_running=True,
        remaining_rounds__gt=0,
    ).update(
        remaining_rounds=F("remaining_rounds") - 1
    )
    return _render_list_region(request)


@login_required
@require_POST
def previous_turn(request):
    encounter = _get_active_encounter(request)
    active_entries = list(TurnTrackerEntry.objects.filter(user=request.user, encounter=encounter, is_active=True).order_by("sort_order", "id"))
    if not active_entries:
        TurnTrackerEntry.objects.filter(user=request.user, encounter=encounter, is_current=True).update(is_current=False)
        return _render_list_region(request)

    current_entry = TurnTrackerEntry.objects.filter(user=request.user, encounter=encounter, is_current=True).first()
    if current_entry not in active_entries:
        prev_entry = active_entries[-1]
    else:
        prev_index = (active_entries.index(current_entry) - 1) % len(active_entries)
        prev_entry = active_entries[prev_index]

    TurnTrackerEntry.objects.filter(user=request.user, encounter=encounter, is_current=True).update(is_current=False)
    prev_entry.is_current = True
    prev_entry.save(update_fields=["is_current"])
    return _render_list_region(request)


@login_required
@require_POST
def clear_entries(request):
    TurnTrackerEntry.objects.filter(user=request.user, encounter=_get_active_encounter(request)).delete()
    return _render_list_region(request)


@login_required
@require_GET
def entry_status_modal(request, entry_id):
    entry = get_object_or_404(
        TurnTrackerEntry.objects.prefetch_related("status_effects"),
        pk=entry_id,
        user=request.user,
        encounter=_get_active_encounter(request),
    )
    return render(request, "tracker/partials/status_modal_content.html", {"entry": entry})


@login_required
@require_GET
def entry_monster_modal(request, entry_id):
    entry = get_object_or_404(TurnTrackerEntry, pk=entry_id, user=request.user, encounter=_get_active_encounter(request))
    if entry.source_kind != TurnTrackerEntry.SourceKind.COMPENDIUM_MONSTER:
        return HttpResponseBadRequest("Monster stat block is only available for compendium monsters.")

    source_data = entry.source_snapshot if isinstance(entry.source_snapshot, dict) else {}
    if not source_data:
        source_object = _resolve_compendium_object_for_entry(entry)
        source_data = source_object.data if source_object and isinstance(source_object.data, dict) else {}

    context = {
        "entry": entry,
        "monster_name": source_data.get("name") or entry.source_name or entry.name,
        "size": source_data.get("size"),
        "monster_type": source_data.get("type"),
        "alignment": source_data.get("alignment"),
        "armor_class": source_data.get("ac"),
        "hit_points": source_data.get("hp"),
        "speed": source_data.get("speed"),
        "strength": source_data.get("str"),
        "dexterity": source_data.get("dex"),
        "constitution": source_data.get("con"),
        "intelligence": source_data.get("int"),
        "wisdom": source_data.get("wis"),
        "charisma": source_data.get("cha"),
        "skills": source_data.get("skill"),
        "senses": source_data.get("senses"),
        "passive": source_data.get("passive"),
        "languages": source_data.get("languages"),
        "challenge_rating": source_data.get("cr"),
        "attacks": _extract_attack_actions(source_data),
    }
    return render(request, "tracker/partials/monster_modal_content.html", context)


@login_required
@require_GET
def entry_player_modal(request, entry_id):
    entry = get_object_or_404(TurnTrackerEntry, pk=entry_id, user=request.user, encounter=_get_active_encounter(request))
    if entry.source_kind != TurnTrackerEntry.SourceKind.GAME_INSTANCE or entry.entry_type != TurnTrackerEntry.EntryType.PLAYER:
        return HttpResponseBadRequest("Player card is only available for game player entries.")

    source_data = entry.source_snapshot if isinstance(entry.source_snapshot, dict) else {}
    source_player = None
    raw_player_id = source_data.get("game_player_id")
    try:
        player_id = int(raw_player_id)
    except (TypeError, ValueError):
        player_id = None
    if player_id:
        source_player = GamePlayer.objects.filter(pk=player_id, game__created_by=request.user).first()

    def _value(key):
        value = source_data.get(key)
        if value is None and source_player is not None:
            return getattr(source_player, key, None)
        return value

    context = {
        "player_name": entry.name,
        "armor_class": _value("ac"),
        "strength": _value("strength"),
        "dexterity": _value("dexterity"),
        "constitution": _value("constitution"),
        "intelligence": _value("intelligence"),
        "wisdom": _value("wisdom"),
        "charisma": _value("charisma"),
        "notes": _value("notes") or entry.notes,
    }
    return render(request, "tracker/partials/player_modal_content.html", context)


@login_required
@require_POST
def add_status_effect(request, entry_id):
    entry = get_object_or_404(TurnTrackerEntry, pk=entry_id, user=request.user, encounter=_get_active_encounter(request))
    _create_status_effect_from_post(entry, request.POST)
    return _render_list_region(request)


@login_required
@require_POST
def play_status_effect(request, effect_id):
    effect = get_object_or_404(
        StatusEffect,
        pk=effect_id,
        entry__user=request.user,
        entry__encounter=_get_active_encounter(request),
    )
    effect.is_running = True
    effect.save(update_fields=["is_running"])
    return _render_list_region(request)


@login_required
@require_POST
def pause_status_effect(request, effect_id):
    effect = get_object_or_404(
        StatusEffect,
        pk=effect_id,
        entry__user=request.user,
        entry__encounter=_get_active_encounter(request),
    )
    effect.is_running = False
    effect.save(update_fields=["is_running"])
    return _render_list_region(request)


@login_required
@require_POST
def reset_status_effect(request, effect_id):
    effect = get_object_or_404(
        StatusEffect,
        pk=effect_id,
        entry__user=request.user,
        entry__encounter=_get_active_encounter(request),
    )
    effect.remaining_rounds = effect.duration_rounds
    effect.save(update_fields=["remaining_rounds"])
    return _render_list_region(request)


@login_required
@require_POST
def remove_status_effect(request, effect_id):
    effect = get_object_or_404(
        StatusEffect,
        pk=effect_id,
        entry__user=request.user,
        entry__encounter=_get_active_encounter(request),
    )
    effect.delete()
    return _render_list_region(request)
