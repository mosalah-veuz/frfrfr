from django.db import models
from django.core.exceptions import ValidationError


class Ticket(models.Model):
    TICKET_TYPE_CHOICES   = [('free', 'Free'), ('paid', 'Paid')]
    QUANTITY_TYPE_CHOICES = [('limited', 'Limited'), ('unlimited', 'Unlimited')]

    name          = models.CharField(max_length=200, unique=True)
    ticket_type   = models.CharField(max_length=10, choices=TICKET_TYPE_CHOICES)
    price         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantity_type = models.CharField(max_length=10, choices=QUANTITY_TYPE_CHOICES)
    # null = unlimited; only set when quantity_type = 'limited'
    total_quantity    = models.PositiveIntegerField(null=True, blank=True)
    # False = block duplicate emails for this ticket
    duplicate_email   = models.BooleanField(
        default=False,
        help_text='Allow the same email to register multiple times for this ticket'
    )
    is_active     = models.BooleanField(default=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes  = [models.Index(fields=['is_active'])]

    def __str__(self):
        return f"{self.name} ({self.get_ticket_type_display()})"

    def clean(self):
        # Price must be 0 for free tickets
        if self.ticket_type == 'free' and self.price != 0:
            raise ValidationError({'price': 'Free tickets must have a price of 0.'})
        # Price required for paid tickets
        if self.ticket_type == 'paid' and (self.price is None or self.price <= 0):
            raise ValidationError({'price': 'Paid tickets must have a price greater than 0.'})
        # Quantity required for limited tickets
        if self.quantity_type == 'limited' and self.total_quantity is None:
            raise ValidationError({'total_quantity': 'Enter a quantity for limited tickets.'})
        # Unlimited tickets should not have a quantity
        if self.quantity_type == 'unlimited':
            self.total_quantity = None

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def sold_count(self):
        if hasattr(self, 'annotated_sold_count'):
            return self.annotated_sold_count
        from apps.registrations.models import RegistrationItem
        from django.db.models import Q
        from django.utils import timezone

        now = timezone.now()
        active_payment_cutoff = now - timezone.timedelta(minutes=15)
        recent_pending_cutoff = now - timezone.timedelta(minutes=2)

        result = RegistrationItem.objects.filter(
            ticket=self
        ).filter(
            Q(registration__status='completed') |
            # Case 1: Pending registration with a transaction created within the payment window (15 mins)
            Q(
                registration__status='pending',
                registration__transaction__status='created',
                registration__created_at__gte=active_payment_cutoff
            ) |
            # Case 2: Pending registration created in the last 2 minutes, which is in the middle of creating its order/transaction
            Q(
                registration__status='pending',
                registration__transaction__isnull=True,
                registration__created_at__gte=recent_pending_cutoff
            )
        ).count()
        return result

    @property
    def available_count(self):
        if self.quantity_type == 'unlimited':
            return None
        return max(0, self.total_quantity - self.sold_count)

    @property
    def is_sold_out(self):
        if self.quantity_type == 'unlimited':
            return False
        return self.available_count == 0
