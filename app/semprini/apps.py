from django.apps import AppConfig


class SempriniConfig(AppConfig):
    name = "semprini"
    verbose_name = "Semprini"

    def ready(self):
        from . import puput_sitemap

        puput_sitemap.install()
