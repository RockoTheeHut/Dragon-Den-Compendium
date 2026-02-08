from django.conf import settings


def ui_settings(request):
    return {
        "openai_model_options": settings.OPENAI_MODEL_OPTIONS,
        "openai_default_model": settings.OPENAI_DEFAULT_MODEL,
        "is_openai_configured": bool(settings.OPENAI_API_KEY and settings.OPENAI_DEFAULT_MODEL),
    }
