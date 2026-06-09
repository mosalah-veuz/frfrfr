from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .utils import log_action


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    log_action('login', actor=user, target=user.username, request=request)


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    log_action('logout', actor=user, target=user.username if user else '', request=request)


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request, **kwargs):
    log_action(
        'login_failed',
        target=credentials.get('username', ''),
        metadata={'reason': 'Invalid credentials'},
        request=request
    )
