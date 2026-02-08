from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from games.models import Game

from .models import TurnEntry


def _active_entries(game):
    return list(game.turn_entries.filter(is_active=True).order_by("sort_order", "id"))


@transaction.atomic
def _set_current(game, entry):
    game.turn_entries.filter(is_current=True).update(is_current=False)
    if entry is not None:
        entry.is_current = True
        entry.save(update_fields=["is_current"])


@login_required
@require_POST
def set_current(request, game_id, entry_id):
    game = get_object_or_404(Game, pk=game_id)
    entry = get_object_or_404(TurnEntry, pk=entry_id, game=game)
    _set_current(game, entry)
    return redirect("games:detail", pk=game.id)


@login_required
@require_POST
def next_turn(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    entries = _active_entries(game)
    if not entries:
        _set_current(game, None)
        return redirect("games:detail", pk=game.id)

    current = game.turn_entries.filter(is_current=True).first()
    if current not in entries:
        _set_current(game, entries[0])
        return redirect("games:detail", pk=game.id)

    index = entries.index(current)
    next_entry = entries[(index + 1) % len(entries)]
    _set_current(game, next_entry)
    return redirect("games:detail", pk=game.id)


@login_required
@require_POST
def previous_turn(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    entries = _active_entries(game)
    if not entries:
        _set_current(game, None)
        return redirect("games:detail", pk=game.id)

    current = game.turn_entries.filter(is_current=True).first()
    if current not in entries:
        _set_current(game, entries[0])
        return redirect("games:detail", pk=game.id)

    index = entries.index(current)
    previous_entry = entries[(index - 1) % len(entries)]
    _set_current(game, previous_entry)
    return redirect("games:detail", pk=game.id)


@login_required
@require_POST
def remove_entry(request, game_id, entry_id):
    game = get_object_or_404(Game, pk=game_id)
    entry = get_object_or_404(TurnEntry, pk=entry_id, game=game)
    was_current = entry.is_current
    entry.delete()

    if was_current:
        next_entry = game.turn_entries.filter(is_active=True).order_by("sort_order", "id").first()
        _set_current(game, next_entry)

    return redirect("games:detail", pk=game.id)


@login_required
@require_POST
def reorder_entries(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    order = request.POST.get("order", "")
    ids = [int(value) for value in order.split(",") if value.strip().isdigit()]

    entries = {entry.id: entry for entry in game.turn_entries.filter(id__in=ids)}
    for index, entry_id in enumerate(ids):
        entry = entries.get(entry_id)
        if entry is None:
            continue
        if entry.sort_order != index:
            entry.sort_order = index
            entry.save(update_fields=["sort_order"])

    return redirect("games:detail", pk=game.id)


@login_required
@require_POST
def toggle_active(request, game_id, entry_id):
    game = get_object_or_404(Game, pk=game_id)
    entry = get_object_or_404(TurnEntry, pk=entry_id, game=game)
    entry.is_active = not entry.is_active
    if not entry.is_active and entry.is_current:
        entry.is_current = False
        entry.save(update_fields=["is_active", "is_current"])
    else:
        entry.save(update_fields=["is_active"])
    return redirect("games:detail", pk=game.id)
