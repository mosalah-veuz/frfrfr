from django import forms
from .models import Ticket


class TicketForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name_locked = bool(
            self.instance
            and self.instance.pk
            and self.instance.registration_items.exists()
        )
        if self.name_locked:
            self.fields['name'].disabled = True
            self.fields['name'].help_text = (
                'Ticket name is locked because existing registrations reference it.'
            )

    class Meta:
        model  = Ticket
        fields = [
            'name', 'ticket_type', 'price',
            'quantity_type', 'total_quantity', 'duplicate_email'
        ]
        widgets = {
            'name':           forms.TextInput(attrs={'placeholder': 'e.g. General Admission'}),
            'price':          forms.NumberInput(attrs={'min': '0', 'step': '0.01'}),
            'total_quantity': forms.NumberInput(attrs={'min': '1'}),
        }

    def clean(self):
        cleaned = super().clean()
        ticket_type   = cleaned.get('ticket_type')
        price         = cleaned.get('price')
        quantity_type = cleaned.get('quantity_type')
        total_quantity = cleaned.get('total_quantity')

        if self.name_locked:
            cleaned['name'] = self.instance.name
        if ticket_type == 'free' and price and price > 0:
            self.add_error('price', 'Free tickets must have price 0.')
        if ticket_type == 'paid' and (not price or price <= 0):
            self.add_error('price', 'Paid tickets require a price greater than 0.')
        if quantity_type == 'limited' and not total_quantity:
            self.add_error('total_quantity', 'Enter quantity for limited tickets.')
        if (
            self.instance
            and self.instance.pk
            and quantity_type == 'limited'
            and total_quantity
            and total_quantity < self.instance.sold_count
        ):
            self.add_error(
                'total_quantity',
                f'Quantity cannot be lower than already sold count ({self.instance.sold_count}).'
            )

        return cleaned
