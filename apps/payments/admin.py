from django.contrib import admin
from .models import Transaction

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display   = ['razorpay_order_id', 'registration', 'amount', 'status', 'created_at', 'verified_at']
    list_filter    = ['status', 'currency']
    search_fields  = ['razorpay_order_id', 'razorpay_payment_id']
    readonly_fields = ['created_at', 'verified_at']
