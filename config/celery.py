import os
from celery import Celery

# Set default Django settings module for celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('event_system')

# Use namespace 'CELERY' to read celery configs from settings.py
app.config_from_object('django.conf:settings', namespace='CELERY')

# Automatically discover tasks.py files in all installed apps
app.autodiscover_tasks()
