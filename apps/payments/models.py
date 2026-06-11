from django.db import models
from django.utils import timezone


class Transaction(models.Model):
    STATUS_CHOICES = [
        ('created',  'Created'),
        ('paid',     'Paid'),
        ('failed',   'Failed'),
        ('refunded', 'Refunded'),
    ]

    METHOD_CHOICES = [
        ('card',        'Card'),
        ('netbanking',  'Net Banking'),
        ('wallet',      'Wallet'),
        ('upi',         'UPI'),
        ('emi',         'EMI'),
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

    # ── Payment method details (populated after payment captured) ──────────────
    payment_method  = models.CharField(
        max_length=20, choices=METHOD_CHOICES, blank=True,
        help_text='Payment method used: card, netbanking, wallet, upi, emi'
    )

    # Card (populated when payment_method = 'card')
    card_network    = models.CharField(max_length=50, blank=True,
                                       help_text='e.g. Visa, MasterCard, RuPay, Amex')
    card_issuer     = models.CharField(max_length=100, blank=True,
                                       help_text='Issuing bank, e.g. HDFC, ICICI')
    card_last4      = models.CharField(max_length=4, blank=True,
                                       help_text='Last 4 digits of the card')
    card_type       = models.CharField(max_length=20, blank=True,
                                       help_text='credit or debit')
    card_name       = models.CharField(max_length=200, blank=True,
                                       help_text='Cardholder name as on card')

    # Net Banking (populated when payment_method = 'netbanking')
    bank            = models.CharField(max_length=50, blank=True,
                                       help_text='Bank code, e.g. HDFC, SBIN')

    # Wallet (populated when payment_method = 'wallet')
    wallet          = models.CharField(max_length=50, blank=True,
                                       help_text='Wallet name, e.g. Paytm, PhonePe')

    # UPI (populated when payment_method = 'upi')
    vpa             = models.CharField(max_length=100, blank=True,
                                       help_text='UPI VPA / address')

    # Razorpay platform fees (in ₹, not paise)
    razorpay_fee    = models.DecimalField(max_digits=10, decimal_places=2,
                                          null=True, blank=True,
                                          help_text='Razorpay processing fee (₹)')
    razorpay_tax    = models.DecimalField(max_digits=10, decimal_places=2,
                                          null=True, blank=True,
                                          help_text='GST on Razorpay fee (₹)')

    # Error details (populated when payment fails)
    error_code          = models.CharField(max_length=100, blank=True)
    error_description   = models.CharField(max_length=500, blank=True)

    class Meta:
        indexes = [models.Index(fields=['razorpay_order_id'])]

    def __str__(self):
        return f"TXN | {self.razorpay_order_id} | {self.status}"

    @property
    def payment_summary(self) -> str:
        """Human-readable one-line description of the payment method used."""
        if self.payment_method == 'card':
            parts = [self.card_network, self.card_type, f"••••{self.card_last4}"]
            if self.card_issuer:
                parts.insert(0, self.card_issuer)
            return ' '.join(p for p in parts if p)
        if self.payment_method == 'upi':
            return f"UPI — {self.vpa}" if self.vpa else 'UPI'
        if self.payment_method == 'netbanking':
            return f"Net Banking — {self.bank}" if self.bank else 'Net Banking'
        if self.payment_method == 'wallet':
            return self.wallet or 'Wallet'
        if self.payment_method == 'emi':
            return f"EMI — {self.bank}" if self.bank else 'EMI'
        return '—'
