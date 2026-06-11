from django import forms
from .models import Ticket


class TicketForm(forms.ModelForm):
    available_quantity = forms.IntegerField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'min': '0'}),
        label='Tickets Available for Purchase',
        help_text='Number of active tickets available for purchase.'
    )

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
        if self.instance and self.instance.pk:
            if self.instance.quantity_type == 'limited':
                self.initial['available_quantity'] = self.instance.available_count
            else:
                self.initial['available_quantity'] = None

    class Meta:
        model  = Ticket
        fields = [
            'name', 'ticket_type', 'price',
            'quantity_type', 'duplicate_email'
        ]
        widgets = {
            'name':           forms.TextInput(attrs={'placeholder': 'e.g. General Admission'}),
            'price':          forms.NumberInput(attrs={'min': '0', 'step': '0.01'}),
        }

    def clean(self):
        cleaned = super().clean()
        ticket_type   = cleaned.get('ticket_type')
        price         = cleaned.get('price')
        quantity_type = cleaned.get('quantity_type')
        available_quantity = cleaned.get('available_quantity')

        if self.name_locked:
            cleaned['name'] = self.instance.name
        if ticket_type == 'free' and price and price > 0:
            self.add_error('price', 'Free tickets must have price 0.')
        if ticket_type == 'paid' and (not price or price <= 0):
            self.add_error('price', 'Paid tickets require a price greater than 0.')
        if quantity_type == 'limited':
            if available_quantity is None:
                self.add_error('available_quantity', 'Enter quantity for limited tickets.')
            else:
                sold = self.instance.sold_count if (self.instance and self.instance.pk) else 0
                total_qty = sold + available_quantity
                cleaned['total_quantity'] = total_qty
                self.instance.total_quantity = total_qty
        else:
            cleaned['total_quantity'] = None
            self.instance.total_quantity = None

        return cleaned
