from django.urls import path
from . import views

urlpatterns = [
    # Public
    path('',                      views.portal,             name='portal'),
    path('checkout/',             views.checkout,           name='checkout'),
    path('register/',             views.register,           name='register'),
    path('confirm/<int:pk>/',     views.confirmation,       name='confirmation'),
    # Admin
    path('panel/registrations/', views.registration_list, name='registration_list'),
]

