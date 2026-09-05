from django.apps import AppConfig


class DevcastConfig(AppConfig):
    name = "devcast"
    verbose_name = "Devcast"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import conf

        if conf.puput_integration():
            from .integrations import puput

            puput.install()
