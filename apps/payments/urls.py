from django.urls import path
from . import views

urlpatterns = [
    path('callback/',  views.payment_callback,  name='payment_callback'),
    path('webhook/',   views.razorpay_webhook,   name='razorpay_webhook'),
]
