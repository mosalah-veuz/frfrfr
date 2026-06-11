from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'

    def ready(self):
        # django-axes is still fully active for brute-force protection,
        # but its admin models (Access Attempts / Failures / Logs) are
        # unregistered here so they don't clutter the Django admin sidebar.
        try:
            from django.contrib import admin
            from axes.models import AccessAttempt, AccessFailure, AccessLog
            for model in (AccessAttempt, AccessFailure, AccessLog):
                try:
                    admin.site.unregister(model)
                except admin.sites.NotRegistered:
                    pass
        except ImportError:
            pass
