import re
import phonenumbers
from django import forms
from django.core.exceptions import ValidationError
from apps.tickets.models import Ticket


PHONE_RE = re.compile(r'^\+?[\d\s\-]{7,15}$')


def clean_international_phone(phone_str, required=True):
    phone_str = (phone_str or '').strip()
    if not phone_str:
        if required:
            raise ValidationError('Phone number is required.')
        return ''
    
    try:
        # If it doesn't start with '+', parse with IN default region
        if not phone_str.startswith('+'):
            parsed_num = phonenumbers.parse(phone_str, 'IN')
        else:
            parsed_num = phonenumbers.parse(phone_str, None)
            
        if not phonenumbers.is_valid_number(parsed_num):
            raise ValidationError('Enter a valid phone number.')
            
        return phonenumbers.format_number(parsed_num, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        raise ValidationError('Enter a valid phone number.')


class ContactForm(forms.Form):
    first_name = forms.CharField(max_length=100, error_messages={'required': 'First name is required.'})
    last_name  = forms.CharField(max_length=100, required=False)
    email      = forms.EmailField(error_messages={'required': 'Your email is required.'})
    phone      = forms.CharField(max_length=20)

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        return clean_international_phone(phone, required=self.fields['phone'].required)

    def clean_email(self):
        return self.cleaned_data['email'].lower().strip()


class AttendeeForm(forms.Form):
    first_name = forms.CharField(max_length=100, error_messages={'required': 'First name is required.'})
    last_name  = forms.CharField(max_length=100, required=False)
    email      = forms.EmailField()
    phone      = forms.CharField(max_length=20)

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        return clean_international_phone(phone, required=True)

    def clean_email(self):
        return self.cleaned_data['email'].lower().strip()


class RegistrationItemForm(forms.Form):
    ticket_id = forms.IntegerField()

    def clean_ticket_id(self):
        tid = self.cleaned_data['ticket_id']
        try:
            return Ticket.objects.get(id=tid, is_active=True)
        except Ticket.DoesNotExist:
            raise forms.ValidationError('This ticket is no longer available.')
