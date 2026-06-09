from django.http import HttpResponseRedirect
from django.urls import reverse


def axes_lockout_handler(request, credentials, *args, **kwargs):
    """Custom lockout response — return to login with error."""
    return HttpResponseRedirect(reverse('admin_login') + '?locked=1')
