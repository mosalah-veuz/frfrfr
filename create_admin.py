"""
Run this once to create the admin user:
  python create_admin.py
"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "admin")
email    = os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@eventhub.com")
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "admin")

if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username=username, email=email, password=password)
    print(f"Superuser created - username: {username}")
else:
    print(f"Superuser '{username}' already exists.")
