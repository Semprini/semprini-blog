import os
from .base import *

DEBUG = False

# SECURITY WARNING: define the correct hosts in production!
ALLOWED_HOSTS = ["*"]


def _split_env_list(name, default):
    value = os.environ.get(name)
    if not value:
        return default
    return [item.strip() for item in value.replace(",", " ").split() if item.strip()]

CSRF_TRUSTED_ORIGINS = _split_env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    [
        "http://localhost:8000",
        "https://semprini.me",
        "https://www.semprini.me",
    ],
)

CORS_ORIGIN_WHITELIST = _split_env_list(
    "DJANGO_CORS_ORIGIN_WHITELIST",
    CSRF_TRUSTED_ORIGINS,
)

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

SECRET_KEY = os.environ.get('SECRET_KEY')

STATIC_URL = "https://s3.ap-southeast-2.amazonaws.com/semprini.me/static/"
MEDIA_URL = "https://s3.ap-southeast-2.amazonaws.com/semprini.me/media/"
