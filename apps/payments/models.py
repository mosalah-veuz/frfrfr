from django.db import models
from django.utils import timezone


class Transaction(models.Model):
    STATUS_CHOICES = [
        ('created',  'Created'),
        ('paid',     'Paid'),
        ('failed',   'Failed'),
        ('refunded', 'Refunded'),
    ]

    registration        = models.OneToOneField(
        'registrations.Registration',
        on_delete=models.CASCADE,
        related_name='transaction'
    )
    razorpay_order_id   = models.CharField(max_length=100, unique=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True)
    razorpay_signature  = models.CharField(max_length=500, blank=True)
    amount              = models.DecimalField(max_digits=10, decimal_places=2)
    currency            = models.CharField(max_length=10, default='INR')
    status              = models.CharField(max_length=20, choices=STATUS_CHOICES, default='created')
    created_at          = models.DateTimeField(auto_now_add=True)
    verified_at         = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['razorpay_order_id'])]

    def __str__(self):
        return f"TXN | {self.razorpay_order_id} | {self.status}"
