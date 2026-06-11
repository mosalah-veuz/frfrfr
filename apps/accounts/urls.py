from django.urls import path
from . import views

urlpatterns = [
    # Admin URLs
    path('panel/login/',     views.admin_login,     name='admin_login'),
    path('panel/logout/',    views.admin_logout,    name='admin_logout'),
    path('panel/dashboard/', views.admin_dashboard,   name='admin_dashboard'),
    path('panel/profile/',   views.profile_view,     name='profile'),

    # Public Authentication URLs
    path('login/',           views.user_login,      name='login'),
    path('signup/',          views.user_signup,     name='signup'),
]

