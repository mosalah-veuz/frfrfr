from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()


class AdminLoginForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'autocomplete': 'username', 'placeholder': 'Username'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password', 'placeholder': 'Password'})
    )


class UserProfileForm(forms.ModelForm):
    first_name = forms.CharField(
        max_length=150,
        required=True,
        label="First Name"
    )
    last_name = forms.CharField(
        max_length=150,
        required=True,
        label="Last Name"
    )
    email = forms.EmailField(
        required=True,
        label="Email Address"
    )
    phone = forms.CharField(
        max_length=20,
        required=True,
        label="Phone Number"
    )

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        from apps.registrations.forms import clean_international_phone
        return clean_international_phone(phone, required=True)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            try:
                self.fields['phone'].initial = self.instance.profile.phone
            except Exception:
                pass

    def save(self, commit=True):
        user = super().save(commit=commit)
        phone = self.cleaned_data.get('phone', '')
        if commit:
            from .models import UserProfile
            profile, created = UserProfile.objects.get_or_create(user=user)
            profile.phone = phone
            profile.save()
        return user
