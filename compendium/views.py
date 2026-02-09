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
