from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.rendering import render_page

from .forms import EncounterForm, GameForm, GameObjectInstanceEditForm, GamePlayerForm
from .models import Encounter, Game, GameObjectInstance, GamePlayer


ACTIVE_TRACKER_ENCOUNTER_SESSION_KEY = "active_tracker_encounter_id"
LAST_GAME_SESSION_KEY = "last_open_game_id"


def _is_game_owner(user, game):
    """Single ownership gate used by all game detail/mutation views."""
    return bool(user and user.is_authenticated and game.created_by_id == user.id)


def _get_owned_game_or_forbidden(request, pk, action="edit"):
    """Fetch a game and enforce ownership in one place.

    Returns (game, None) for the owner, (None, 403 response) otherwise.
    """
    game = get_object_or_404(Game.objects.select_related("created_by"), pk=pk)
    if not _is_game_owner(request.user, game):
        return None, HttpResponseForbidden(f"Only the creator can {action} this game.")
    return game, None


@login_required
def game_list(request):
    """Create/list games that belong to the requesting user."""
    if request.method == "POST":
        form = GameForm(request.POST)
        if form.is_valid():
            game = form.save(commit=False)
            game.created_by = request.user
            game.save()
            request.session[LAST_GAME_SESSION_KEY] = game.pk
            messages.success(request, "Game created.")
            return redirect("games:detail", pk=game.pk)
    else:
        form = GameForm()

    if request.method == "GET" and request.GET.get("all") != "1":
        last_game_id = request.session.get(LAST_GAME_SESSION_KEY)
        if last_game_id:
            last_game = Game.objects.filter(pk=last_game_id, created_by=request.user).first()
            if last_game is not None:
                return redirect("games:detail", pk=last_game.pk)
            request.session.pop(LAST_GAME_SESSION_KEY, None)

    games = Game.objects.select_related("created_by").filter(created_by=request.user)
    return render_page(request, "games/game_list.html", {"games": games, "form": form})


@login_required
def game_detail(request, pk):
    """Show one game with players and encounters."""
    game, forbidden = _get_owned_game_or_forbidden(request, pk, action="view")
    if forbidden:
        return forbidden
    request.session[LAST_GAME_SESSION_KEY] = game.pk
    players = game.players.order_by("name", "id")
    encounters = game.encounters.order_by("-updated_at", "-id")

    return render_page(
        request,
        "games/game_detail.html",
        {
            "game": game,
            "players": players,
            "encounters": encounters,
            "player_form": GamePlayerForm(),
            "encounter_form": EncounterForm(),
        },
    )


@login_required
@require_POST
def delete_game(request, pk):
    game, forbidden = _get_owned_game_or_forbidden(request, pk, action="delete")
    if forbidden:
        return forbidden

    if request.session.get(LAST_GAME_SESSION_KEY) == game.pk:
        request.session.pop(LAST_GAME_SESSION_KEY, None)
    game.delete()
    messages.success(request, "Game deleted.")
    return redirect("games:list")


@login_required
@require_POST
def edit_instance(request, game_id, instance_id):
    """Update an instance that belongs to a game owned by the current user."""
    game, forbidden = _get_owned_game_or_forbidden(request, game_id, action="edit")
    if forbidden:
        return forbidden
    instance = get_object_or_404(GameObjectInstance, pk=instance_id, game=game)
    form = GameObjectInstanceEditForm(request.POST, instance=instance)
    if form.is_valid():
        form.save()
        messages.success(request, "Game object updated.")
    else:
        messages.error(request, "Could not update game object.")
    return redirect("games:detail", pk=game.pk)


@login_required
@require_POST
def remove_instance(request, game_id, instance_id):
    """Delete an instance that belongs to a game owned by the current user."""
    game, forbidden = _get_owned_game_or_forbidden(request, game_id, action="edit")
    if forbidden:
        return forbidden
    instance = get_object_or_404(GameObjectInstance, pk=instance_id, game=game)
    instance.delete()
    messages.success(request, "Game object removed.")
    return redirect("games:detail", pk=game.pk)


@login_required
@require_POST
def create_encounter(request, game_id):
    game, forbidden = _get_owned_game_or_forbidden(request, game_id, action="edit")
    if forbidden:
        return forbidden

    form = EncounterForm(request.POST)
    if form.is_valid():
        encounter = form.save(commit=False)
        encounter.game = game
        encounter.save()
        messages.success(request, "Encounter created.")
    else:
        messages.error(request, "Could not create encounter.")
    return redirect("games:detail", pk=game.pk)


@login_required
@require_POST
def delete_encounter(request, game_id, encounter_id):
    game, forbidden = _get_owned_game_or_forbidden(request, game_id, action="edit")
    if forbidden:
        return forbidden

    encounter = get_object_or_404(Encounter, pk=encounter_id, game=game)
    encounter.delete()
    messages.success(request, "Encounter deleted.")
    return redirect("games:detail", pk=game.pk)


@login_required
def open_encounter_tracker(request, game_id, encounter_id):
    game, forbidden = _get_owned_game_or_forbidden(request, game_id, action="view")
    if forbidden:
        return forbidden

    encounter = get_object_or_404(Encounter, pk=encounter_id, game=game)
    request.session[LAST_GAME_SESSION_KEY] = game.pk
    request.session[ACTIVE_TRACKER_ENCOUNTER_SESSION_KEY] = encounter.pk
    tracker_url = f"{reverse('tracker:dashboard')}?encounter={encounter.pk}"
    if request.headers.get("HX-Request"):
        response = redirect(tracker_url)
        response["HX-Redirect"] = tracker_url
        return response
    return redirect(tracker_url)


@login_required
@require_POST
def create_player(request, game_id):
    game, forbidden = _get_owned_game_or_forbidden(request, game_id, action="edit")
    if forbidden:
        return forbidden

    form = GamePlayerForm(request.POST)
    if form.is_valid():
        player = form.save(commit=False)
        player.game = game
        player.save()
        messages.success(request, "Player created.")
    else:
        messages.error(request, "Could not create player.")
    return redirect("games:detail", pk=game.pk)


@login_required
@require_POST
def edit_player(request, game_id, player_id):
    game, forbidden = _get_owned_game_or_forbidden(request, game_id, action="edit")
    if forbidden:
        return forbidden

    player = get_object_or_404(GamePlayer, pk=player_id, game=game)
    form = GamePlayerForm(request.POST, instance=player)
    if form.is_valid():
        form.save()
        messages.success(request, "Player updated.")
    else:
        messages.error(request, "Could not update player.")
    return redirect("games:detail", pk=game.pk)


@login_required
@require_POST
def delete_player(request, game_id, player_id):
    game, forbidden = _get_owned_game_or_forbidden(request, game_id, action="edit")
    if forbidden:
        return forbidden

    player = get_object_or_404(GamePlayer, pk=player_id, game=game)
    player.delete()
    messages.success(request, "Player removed.")
    return redirect("games:detail", pk=game.pk)


@login_required
def edit_player_modal(request, game_id, player_id):
    game, forbidden = _get_owned_game_or_forbidden(request, game_id, action="edit")
    if forbidden:
        return forbidden
    player = get_object_or_404(GamePlayer, pk=player_id, game=game)
    form = GamePlayerForm(instance=player)
    return render(request, "games/partials/edit_player_modal_content.html", {"game": game, "player": player, "form": form})
