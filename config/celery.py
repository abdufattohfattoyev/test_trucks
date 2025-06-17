import os
from celery import Celery

# Django sozlamalarini o'rnatamiz
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Celery ilovasini yaratamiz
app = Celery('config')

# Django sozlamalaridan Celery sozlamalarini yuklaymiz
app.config_from_object('django.conf:settings', namespace='CELERY')

# Django modellaridagi tasklarni avtomatik topish
app.autodiscover_tasks()  # Loyiha app'lari

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')