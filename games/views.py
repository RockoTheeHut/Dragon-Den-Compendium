from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from core.rendering import render_page

from .forms import GameForm, GameObjectInstanceEditForm
from .models import Game, GameObjectInstance


def _is_game_owner(user, game):
    """Single ownership gate used by all game detail/mutation views."""
    return bool(user and user.is_authenticated and game.created_by_id == user.id)


@login_required
def game_list(request):
    """Create/list games that belong to the requesting user."""
    if request.method == "POST":
        form = GameForm(request.POST)
        if form.is_valid():
            game = form.save(commit=False)
            game.created_by = request.user
            game.save()
            messages.success(request, "Game created.")
            return redirect("games:detail", pk=game.pk)
    else:
        form = GameForm()

    games = Game.objects.select_related("created_by").filter(created_by=request.user)
    return render_page(request, "games/game_list.html", {"games": games, "form": form})


@login_required
def game_detail(request, pk):
    """Show one game and all of its per-campaign object instances."""
    game = get_object_or_404(Game.objects.select_related("created_by"), pk=pk)
    if not _is_game_owner(request.user, game):
        return HttpResponseForbidden("Only the creator can view this game.")
    instances = game.object_instances.select_related("base_object").order_by("name")

    return render_page(
        request,
        "games/game_detail.html",
        {
            "game": game,
            "instances": instances,
        },
    )


@login_required
@require_POST
def delete_game(request, pk):
    game = get_object_or_404(Game, pk=pk)
    if not _is_game_owner(request.user, game):
        return HttpResponseForbidden("Only the creator can delete this game.")

    game.delete()
    messages.success(request, "Game deleted.")
    return redirect("games:list")


@login_required
@require_POST
def edit_instance(request, game_id, instance_id):
    """Update an instance that belongs to a game owned by the current user."""
    game = get_object_or_404(Game, pk=game_id)
    if not _is_game_owner(request.user, game):
        return HttpResponseForbidden("Only the creator can edit this game.")
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
    game = get_object_or_404(Game, pk=game_id)
    if not _is_game_owner(request.user, game):
        return HttpResponseForbidden("Only the creator can edit this game.")
    instance = get_object_or_404(GameObjectInstance, pk=instance_id, game=game)
    instance.delete()
    messages.success(request, "Game object removed.")
    return redirect("games:detail", pk=game.pk)
