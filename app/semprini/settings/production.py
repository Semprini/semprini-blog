import os
from .base import *

DEBUG = True

# SECURITY WARNING: define the correct hosts in production!
ALLOWED_HOSTS = ["*"]

CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8000',
    'https://www.semprini.me'
]

CORS_ORIGIN_WHITELIST = [
    'http://localhost:8000',
    'https://www.semprini.me'
]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

SECRET_KEY = os.environ.get('SECRET_KEY')
STATIC_URL = "https://s3.ap-southeast-2.amazonaws.com/semprini.me/static/"
MEDIA_URL = "https://s3.ap-southeast-2.amazonaws.com/semprini.me/media/"

try:
    from .local import *
except ImportError:
    pass
