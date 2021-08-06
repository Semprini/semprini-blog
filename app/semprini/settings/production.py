from .base import *

DEBUG = False

SECRET_KEY = os.environ.get("SECRET_KEY", "n9*fw(b3yzc3lliu-=-6r9)qvjjj(e_!f@kb-r+mk-+ql)iy!%")
ALLOWED_HOSTS = ['*']
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

try:
    from .local import *
except ImportError:
    pass
