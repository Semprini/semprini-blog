
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "sem4",
        "USER": "semprini",
        "PASSWORD": "01974a1974",
        "HOST": "127.0.0.1",
        "PORT": "5432",
    },  
        "prod": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "sem2",
        "USER": "semprini",
        "PASSWORD": "01974a1974",
        "HOST": "192.168.1.102",
        "PORT": "5432",
    }

}
MEDIA_URL = "https://s3.ap-southeast-2.amazonaws.com/semprini.me/media/"
