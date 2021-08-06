from .base import *

DEBUG = False

SECRET_KEY = os.environ.get("SECRET_KEY", None)
ALLOWED_HOSTS = ['*']
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

try:
    from .local import *
except ImportError:
    pass
