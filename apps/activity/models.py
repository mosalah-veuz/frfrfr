from django.db import models
from django.conf import settings


class ActivityLog(models.Model):
    ACTION_CHOICES = [
        ('login',              'Admin Login'),
        ('logout',             'Admin Logout'),
        ('login_failed',       'Login Failed'),
        ('ticket_create',      'Ticket Created'),
        ('ticket_delete',      'Ticket Deleted'),
        ('ticket_view',        'Ticket Viewed'),
        ('registration_view',  'Registration Viewed'),
        ('payment_created',    'Payment Order Created'),
        ('payment_verified',   'Payment Verified'),
        ('payment_failed',     'Payment Failed'),
    ]

    actor     = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='activity_logs'
    )
    action    = models.CharField(max_length=50, choices=ACTION_CHOICES)
    # Human-readable target e.g. "Ticket #3 - VIP Pass"
    target    = models.CharField(max_length=300, blank=True)
    # Extra structured context
    metadata  = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes  = [
            models.Index(fields=['actor', 'timestamp']),
            models.Index(fields=['action']),
        ]

    def __str__(self):
        actor = self.actor.username if self.actor else 'system'
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {actor} — {self.action}"
