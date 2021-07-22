from .base import *

DEBUG = False

SECRET_KEY = "n9*fw(b3yzc3lliu-=-6r9)qvjjj(e_!f@kb-r+mk-+ql)iy!%"
ALLOWED_HOSTS = ['*']

try:
    from .local import *
except ImportError:
    pass
