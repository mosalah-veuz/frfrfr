from django.urls import path
from . import views

urlpatterns = [
    path('tickets/',              views.ticket_list,   name='ticket_list'),
    path('tickets/create/',       views.ticket_create, name='ticket_create'),
    path('tickets/<int:pk>/edit/', views.ticket_update, name='ticket_update'),
    path('tickets/<int:pk>/activate/', views.ticket_activate, name='ticket_activate'),
    path('tickets/<int:pk>/delete/', views.ticket_delete, name='ticket_delete'),
]
