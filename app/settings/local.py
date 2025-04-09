import os
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(PROJECT_DIR)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "sem2",
        "USER": "semprini",
        "PASSWORD": "01974a1974",
        "HOST": "192.168.1.102",
        "PORT": "5432",
    }
}

