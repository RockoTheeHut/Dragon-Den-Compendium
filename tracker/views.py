import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F, Max
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from compendium.models import GameObject
from core.rendering import render_page
from games.models import GameObjectInstance

from .forms import AddFromCompendiumForm, AddFromGameInstanceForm, StatusEffectForm, TurnTrackerEntryForm
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


def _build_context(user, **overrides):
    context = {
        "entries": _entry_queryset(user),
        "manual_form": TurnTrackerEntryForm(initial={"entry_type": TurnTrackerEntry.EntryType.PLAYER, "is_active": True}),
        "from_compendium_form": AddFromCompendiumForm(initial={"entry_type": TurnTrackerEntry.EntryType.ENEMY, "is_active": True}),
        "from_instance_form": AddFromGameInstanceForm(initial={"entry_type": TurnTrackerEntry.EntryType.ENEMY, "is_active": True}),
        "entry_type_choices": TurnTrackerEntry.EntryType.choices,
    }
    context.update(overrides)
    return context


def _render_tracker(request, status=200, **overrides):
    context = _build_context(request.user, **overrides)
    if request.headers.get("HX-Request"):
        return render(request, "tracker/partials/tracker_content.html", context=context, status=status)
    return render_page(request, "tracker/dashboard.html", context=context)


def _normalize_sort_order(user):
    entries = list(TurnTrackerEntry.objects.filter(user=user).order_by("sort_order", "id"))
    for index, entry in enumerate(entries):
        if entry.sort_order != index:
            entry.sort_order = index
            entry.save(update_fields=["sort_order"])


@login_required
def dashboard(request):
    return _render_tracker(request)


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
        messages.success(request, "Tracker entry added.")
        return _render_tracker(request)

    messages.error(request, "Could not add tracker entry.")
    return _render_tracker(request, status=400, manual_form=form)


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
        messages.success(request, f"Added {entry.entry_type} from monster '{source.name}'.")
        return _render_tracker(request)

    messages.error(request, "Could not create entry from monster.")
    return _render_tracker(request, status=400, from_compendium_form=form)


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
        messages.success(request, f"Added {entry.entry_type} from game object '{source.name}'.")
        return _render_tracker(request)

    messages.error(request, "Could not create entry from game object instance.")
    return _render_tracker(request, status=400, from_instance_form=form)


@login_required
@require_POST
def remove_entry(request, entry_id):
    entry = get_object_or_404(TurnTrackerEntry, pk=entry_id, user=request.user)
    entry.delete()
    _normalize_sort_order(request.user)
    messages.success(request, "Tracker entry removed.")
    return _render_tracker(request)


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
    return _render_tracker(request)


@login_required
@require_POST
def set_current(request, entry_id):
    entry = get_object_or_404(TurnTrackerEntry, pk=entry_id, user=request.user)
    TurnTrackerEntry.objects.filter(user=request.user, is_current=True).update(is_current=False)
    entry.is_current = True
    entry.save(update_fields=["is_current"])
    return _render_tracker(request)


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
    return _render_tracker(request)


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
    return _render_tracker(request)


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
    return _render_tracker(request)


@login_required
@require_POST
def advance_turn(request):
    active_entries = list(TurnTrackerEntry.objects.filter(user=request.user, is_active=True).order_by("sort_order", "id"))
    if not active_entries:
        TurnTrackerEntry.objects.filter(user=request.user, is_current=True).update(is_current=False)
        return _render_tracker(request)

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
    return _render_tracker(request)


@login_required
@require_POST
def add_status_effect(request, entry_id):
    entry = get_object_or_404(TurnTrackerEntry, pk=entry_id, user=request.user)
    form = StatusEffectForm(request.POST)
    if form.is_valid():
        form.save_for_entry(entry)
    return _render_tracker(request)


@login_required
@require_POST
def play_status_effect(request, effect_id):
    effect = get_object_or_404(StatusEffect, pk=effect_id, entry__user=request.user)
    effect.is_running = True
    effect.save(update_fields=["is_running"])
    return _render_tracker(request)


@login_required
@require_POST
def pause_status_effect(request, effect_id):
    effect = get_object_or_404(StatusEffect, pk=effect_id, entry__user=request.user)
    effect.is_running = False
    effect.save(update_fields=["is_running"])
    return _render_tracker(request)


@login_required
@require_POST
def reset_status_effect(request, effect_id):
    effect = get_object_or_404(StatusEffect, pk=effect_id, entry__user=request.user)
    effect.remaining_rounds = effect.duration_rounds
    effect.save(update_fields=["remaining_rounds"])
    return _render_tracker(request)


@login_required
@require_POST
def remove_status_effect(request, effect_id):
    effect = get_object_or_404(StatusEffect, pk=effect_id, entry__user=request.user)
    effect.delete()
    return _render_tracker(request)
