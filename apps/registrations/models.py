from django.db import models
from django.conf import settings
from django.utils import timezone


class Registration(models.Model):
    """
    One transaction. Owned by a guest or a logged-in user.
    contact_* fields = billing contact (may differ from any attendee).
    """
    STATUS_CHOICES = [
        ('pending',    'Pending'),
        ('processing', 'Processing'),
        ('completed',  'Completed'),
        ('failed',     'Failed'),
        ('cancelled',  'Cancelled'),
    ]

    # Optional auth — null means guest checkout
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='registrations'
    )

    # Billing contact — always captured explicitly
    contact_name  = models.CharField(max_length=200)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=20)

    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes  = [
            models.Index(fields=['contact_email']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"REG-{self.id:04d} | {self.contact_name} | {self.status}"

    @property
    def is_guest(self):
        return self.user is None

    @property
    def total_amount(self):
        return sum(item.unit_price for item in self.items.all())

    @property
    def is_incomplete(self):
        """Stale pending/processing registrations older than 30 min."""
        if self.status in ('pending', 'processing'):
            return (timezone.now() - self.created_at).seconds > 1800
        return False


class RegistrationItem(models.Model):
    """
    One attendee–ticket row within a registration.
    Attendee details are stored inline — no separate entity.
    unit_price snapshots the price at time of purchase.
    """
    registration = models.ForeignKey(
        Registration, on_delete=models.CASCADE, related_name='items'
    )
    ticket = models.ForeignKey(
        'tickets.Ticket', on_delete=models.PROTECT, related_name='registration_items'
    )

    # Inline attendee data — no FK, no separate table
    attendee_name  = models.CharField(max_length=200)
    attendee_email = models.EmailField()
    attendee_phone = models.CharField(max_length=20, blank=True)

    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['attendee_email']),
            models.Index(fields=['ticket']),
        ]

    def __str__(self):
        return f"{self.attendee_name} — {self.ticket.name} @ ₹{self.unit_price}"
