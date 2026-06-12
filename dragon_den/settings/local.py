import os

# Local development defaults; must land before base.py reads the environment
# so the strong-SECRET_KEY enforcement stays scoped to non-debug deployments.
os.environ.setdefault("DEBUG", "true")

from .base import *  # noqa: E402,F401,F403

DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
