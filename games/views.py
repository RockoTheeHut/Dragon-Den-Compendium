from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from core.rendering import render_page

from compendium.models import GameObject

from .forms import GameForm, GameObjectInstanceEditForm
from .models import Game, GameObjectInstance


@login_required
def game_list(request):
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

    games = Game.objects.select_related("created_by")
    return render_page(request, "games/game_list.html", {"games": games, "form": form})


@login_required
def game_detail(request, pk):
    game = get_object_or_404(Game.objects.select_related("created_by"), pk=pk)
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
    if game.created_by != request.user and not request.user.is_staff:
        return HttpResponseForbidden("Only the creator can delete this game.")

    game.delete()
    messages.success(request, "Game deleted.")
    return redirect("games:list")


@login_required
@require_POST
def add_object_to_game(request, game_id, object_id):
    game = get_object_or_404(Game, pk=game_id)
    base = get_object_or_404(GameObject, pk=object_id)

    GameObjectInstance.objects.create(
        game=game,
        base_object=base,
        name=base.name,
        object_type=base.object_type,
        description=base.description,
        data=base.data,
    )
    messages.success(request, f"Added '{base.name}' to {game.title}.")

    next_url = request.POST.get("next")
    if next_url:
        return redirect(next_url)
    return redirect("games:detail", pk=game.pk)


@login_required
@require_POST
def edit_instance(request, game_id, instance_id):
    game = get_object_or_404(Game, pk=game_id)
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
    game = get_object_or_404(Game, pk=game_id)
    instance = get_object_or_404(GameObjectInstance, pk=instance_id, game=game)
    instance.delete()
    messages.success(request, "Game object removed.")
    return redirect("games:detail", pk=game.pk)
