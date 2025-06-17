from django.apps import AppConfig

class XaridorlarConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'xaridorlar'

    def ready(self):
        import xaridorlar.signals