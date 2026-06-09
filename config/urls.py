from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('',              include('apps.registrations.urls')),
    path('panel/', include('apps.accounts.urls')),
    path('panel/', include('apps.tickets.urls')),
    path('panel/', include('apps.activity.urls')),
    path('payment/',      include('apps.payments.urls')),
]
