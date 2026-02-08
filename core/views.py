from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from games.models import Game

from .forms import SignUpForm
from .rendering import render_page


@login_required
def home(request):
    recent_games = Game.objects.filter(created_by=request.user)[:5]
    return render_page(request, "core/home.html", {"recent_games": recent_games})


def signup(request):
    if request.user.is_authenticated:
        return redirect("core:home")

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("core:home")
    else:
        form = SignUpForm()

    return render_page(request, "registration/signup.html", {"form": form})
