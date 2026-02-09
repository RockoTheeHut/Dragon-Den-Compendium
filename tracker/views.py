import re

from django.contrib.auth.decorators import login_required
from django.db.models import F, Max
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from compendium.models import GameObject
from core.rendering import render_page
from games.models import GameObjectInstance

from .forms import AddFromCompendiumForm, AddFromGameInstanceForm, TurnTrackerEntryForm
from .models import StatusEffect, TurnTrackerEntry


def _parse_int(value):
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        match = re.search(r"-?\d+", value)
        if not match:
            return None
        return int(match.group(0))
    if isinstance(value, dict):
        for key in ("value", "max", "current", "hp", "hit_points"):
            parsed = _parse_int(value.get(key))
            if parsed is not None:
                return parsed
    return None


def _extract_hp(data):
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


def _entry_queryset(user):
    return TurnTrackerEntry.objects.filter(user=user).prefetch_related("status_effects").order_by("sort_order", "id")


def _list_context(user):
    entries = _entry_queryset(user)
    return {
        "entries": entries,
        "entry_type_choices": TurnTrackerEntry.EntryType.choices,
        "has_entries": entries.exists(),
    }


def _add_forms_context():
    return {
        "manual_form": TurnTrackerEntryForm(initial={"entry_type": TurnTrackerEntry.EntryType.PLAYER, "is_active": True}),
        "from_compendium_form": AddFromCompendiumForm(initial={"entry_type": TurnTrackerEntry.EntryType.ENEMY, "is_active": True}),
        "from_instance_form": AddFromGameInstanceForm(initial={"entry_type": TurnTrackerEntry.EntryType.ENEMY, "is_active": True}),
    }


def _render_list_region(request, status=200):
    if request.headers.get("HX-Request"):
        return render(request, "tracker/partials/list_region.html", _list_context(request.user), status=status)
    context = {}
    context.update(_list_context(request.user))
    context.update(_add_forms_context())
    return render_page(request, "tracker/dashboard.html", context)


def _normalize_sort_order(user):
    entries = list(TurnTrackerEntry.objects.filter(user=user).order_by("sort_order", "id"))
    for index, entry in enumerate(entries):
        if entry.sort_order != index:
            entry.sort_order = index
            entry.save(update_fields=["sort_order"])


def _create_status_effect_from_post(entry, post_data):
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
    context = {}
    context.update(_list_context(request.user))
    context.update(_add_forms_context())
    return render_page(request, "tracker/dashboard.html", context)


@login_required
@require_POST
def add_entry(request):
    form = TurnTrackerEntryForm(request.POST)
    if form.is_valid():
        max_sort = TurnTrackerEntry.objects.filter(user=request.user).aggregate(max_sort=Max("sort_order")).get("max_sort")
        entry = form.save(commit=False)
        entry.user = request.user
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
        source = form.cleaned_data["source"]
        hp_current_default, hp_max_default = _extract_hp(source.data)
        max_sort = TurnTrackerEntry.objects.filter(user=request.user).aggregate(max_sort=Max("sort_order")).get("max_sort")
        entry = TurnTrackerEntry.objects.create(
            user=request.user,
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
            source_snapshot=source.data,
            sort_order=(max_sort + 1) if max_sort is not None else 0,
        )
        _create_status_effect_from_post(entry, request.POST)
        return _render_list_region(request)

    return _render_list_region(request, status=400)


@login_required
@require_POST
def add_from_game_instance(request):
    form = AddFromGameInstanceForm(request.POST)
    if form.is_valid():
        source = form.cleaned_data["source"]
        hp_current_default, hp_max_default = _extract_hp(source.data)
        max_sort = TurnTrackerEntry.objects.filter(user=request.user).aggregate(max_sort=Max("sort_order")).get("max_sort")
        entry = TurnTrackerEntry.objects.create(
            user=request.user,
            name=(form.cleaned_data.get("name") or "").strip() or source.name,
            entry_type=form.cleaned_data["entry_type"],
            initiative=form.cleaned_data.get("initiative"),
            is_active=form.cleaned_data.get("is_active") if form.cleaned_data.get("is_active") is not None else True,
            notes=form.cleaned_data.get("notes") or "",
            hp_current=form.cleaned_data.get("hp_current") if form.cleaned_data.get("hp_current") is not None else hp_current_default,
            hp_max=form.cleaned_data.get("hp_max") if form.cleaned_data.get("hp_max") is not None else hp_max_default,
            items_text=form.cleaned_data.get("items_text") or "",
            source_kind=TurnTrackerEntry.SourceKind.GAME_INSTANCE,
            source_name=source.name,
            source_snapshot=source.data,
            sort_order=(max_sort + 1) if max_sort is not None else 0,
        )
        _create_status_effect_from_post(entry, request.POST)
        return _render_list_region(request)

    return _render_list_region(request, status=400)


@login_required
@require_GET
def edit_entry_modal(request, entry_id):
    entry = get_object_or_404(TurnTrackerEntry, pk=entry_id, user=request.user)
    form = TurnTrackerEntryForm(instance=entry)
    return render(request, "tracker/partials/edit_entry_modal_content.html", {"entry": entry, "form": form})


@login_required
@require_POST
def edit_entry(request, entry_id):
    entry = get_object_or_404(TurnTrackerEntry, pk=entry_id, user=request.user)
    form = TurnTrackerEntryForm(request.POST, instance=entry)
    if form.is_valid():
        form.save()
        return _render_list_region(request)
    return _render_list_region(request, status=400)


@login_required
@require_POST
def quick_update_entry(request, entry_id):
    entry = get_object_or_404(TurnTrackerEntry, pk=entry_id, user=request.user)
    updated_fields = []

    if "initiative" in request.POST:
        raw = (request.POST.get("initiative") or "").strip()
        if raw == "":
            entry.initiative = None
        else:
            try:
                entry.initiative = int(raw)
            except ValueError:
                return HttpResponseBadRequest("Initiative must be an integer.")
        updated_fields.append("initiative")

    if "hp_current" in request.POST and entry.entry_type != TurnTrackerEntry.EntryType.PLAYER:
        raw = (request.POST.get("hp_current") or "").strip()
        if raw == "":
            entry.hp_current = None
        else:
            try:
                entry.hp_current = int(raw)
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
        entry.save(update_fields=list(dict.fromkeys(updated_fields)))

    return _render_list_region(request)


@login_required
@require_POST
def remove_entry(request, entry_id):
    entry = get_object_or_404(TurnTrackerEntry, pk=entry_id, user=request.user)
    entry.delete()
    _normalize_sort_order(request.user)
    return _render_list_region(request)


@login_required
@require_POST
def toggle_active(request, entry_id):
    entry = get_object_or_404(TurnTrackerEntry, pk=entry_id, user=request.user)
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
    entry = get_object_or_404(TurnTrackerEntry, pk=entry_id, user=request.user)
    TurnTrackerEntry.objects.filter(user=request.user, is_current=True).update(is_current=False)
    entry.is_current = True
    entry.save(update_fields=["is_current"])
    return _render_list_region(request)


@login_required
@require_POST
def reorder_entries(request):
    order = request.POST.get("order", "")
    ids = [int(value) for value in order.split(",") if value.strip().isdigit()]

    entries = {entry.id: entry for entry in TurnTrackerEntry.objects.filter(user=request.user, id__in=ids)}
    for index, entry_id in enumerate(ids):
        entry = entries.get(entry_id)
        if entry is None:
            continue
        if entry.sort_order != index:
            entry.sort_order = index
            entry.save(update_fields=["sort_order"])

    _normalize_sort_order(request.user)
    return _render_list_region(request)


@login_required
@require_POST
def move_up(request, entry_id):
    _normalize_sort_order(request.user)
    entries = list(TurnTrackerEntry.objects.filter(user=request.user).order_by("sort_order", "id"))
    for index, entry in enumerate(entries):
        if entry.id == entry_id and index > 0:
            prev_entry = entries[index - 1]
            entry.sort_order, prev_entry.sort_order = prev_entry.sort_order, entry.sort_order
            entry.save(update_fields=["sort_order"])
            prev_entry.save(update_fields=["sort_order"])
            break
    return _render_list_region(request)


@login_required
@require_POST
def move_down(request, entry_id):
    _normalize_sort_order(request.user)
    entries = list(TurnTrackerEntry.objects.filter(user=request.user).order_by("sort_order", "id"))
    for index, entry in enumerate(entries):
        if entry.id == entry_id and index < len(entries) - 1:
            next_entry = entries[index + 1]
            entry.sort_order, next_entry.sort_order = next_entry.sort_order, entry.sort_order
            entry.save(update_fields=["sort_order"])
            next_entry.save(update_fields=["sort_order"])
            break
    return _render_list_region(request)


@login_required
@require_POST
def advance_turn(request):
    active_entries = list(TurnTrackerEntry.objects.filter(user=request.user, is_active=True).order_by("sort_order", "id"))
    if not active_entries:
        TurnTrackerEntry.objects.filter(user=request.user, is_current=True).update(is_current=False)
        return _render_list_region(request)

    current_entry = TurnTrackerEntry.objects.filter(user=request.user, is_current=True).first()
    if current_entry not in active_entries:
        next_entry = active_entries[0]
    else:
        next_index = (active_entries.index(current_entry) + 1) % len(active_entries)
        next_entry = active_entries[next_index]

    TurnTrackerEntry.objects.filter(user=request.user, is_current=True).update(is_current=False)
    next_entry.is_current = True
    next_entry.save(update_fields=["is_current"])

    StatusEffect.objects.filter(entry__user=request.user, is_running=True, remaining_rounds__gt=0).update(
        remaining_rounds=F("remaining_rounds") - 1
    )
    return _render_list_region(request)


@login_required
@require_POST
def previous_turn(request):
    active_entries = list(TurnTrackerEntry.objects.filter(user=request.user, is_active=True).order_by("sort_order", "id"))
    if not active_entries:
        TurnTrackerEntry.objects.filter(user=request.user, is_current=True).update(is_current=False)
        return _render_list_region(request)

    current_entry = TurnTrackerEntry.objects.filter(user=request.user, is_current=True).first()
    if current_entry not in active_entries:
        prev_entry = active_entries[-1]
    else:
        prev_index = (active_entries.index(current_entry) - 1) % len(active_entries)
        prev_entry = active_entries[prev_index]

    TurnTrackerEntry.objects.filter(user=request.user, is_current=True).update(is_current=False)
    prev_entry.is_current = True
    prev_entry.save(update_fields=["is_current"])
    return _render_list_region(request)


@login_required
@require_POST
def clear_entries(request):
    TurnTrackerEntry.objects.filter(user=request.user).delete()
    return _render_list_region(request)


@login_required
@require_GET
def entry_status_modal(request, entry_id):
    entry = get_object_or_404(TurnTrackerEntry.objects.prefetch_related("status_effects"), pk=entry_id, user=request.user)
    return render(request, "tracker/partials/status_modal_content.html", {"entry": entry})


@login_required
@require_POST
def add_status_effect(request, entry_id):
    entry = get_object_or_404(TurnTrackerEntry, pk=entry_id, user=request.user)
    _create_status_effect_from_post(entry, request.POST)
    return _render_list_region(request)


@login_required
@require_POST
def play_status_effect(request, effect_id):
    effect = get_object_or_404(StatusEffect, pk=effect_id, entry__user=request.user)
    effect.is_running = True
    effect.save(update_fields=["is_running"])
    return _render_list_region(request)


@login_required
@require_POST
def pause_status_effect(request, effect_id):
    effect = get_object_or_404(StatusEffect, pk=effect_id, entry__user=request.user)
    effect.is_running = False
    effect.save(update_fields=["is_running"])
    return _render_list_region(request)


@login_required
@require_POST
def reset_status_effect(request, effect_id):
    effect = get_object_or_404(StatusEffect, pk=effect_id, entry__user=request.user)
    effect.remaining_rounds = effect.duration_rounds
    effect.save(update_fields=["remaining_rounds"])
    return _render_list_region(request)


@login_required
@require_POST
def remove_status_effect(request, effect_id):
    effect = get_object_or_404(StatusEffect, pk=effect_id, entry__user=request.user)
    effect.delete()
    return _render_list_region(request)
