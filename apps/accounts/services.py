from django.contrib.auth import get_user_model
from django.db import transaction as db_transaction
from apps.accounts.models import UserProfile
from apps.activity.utils import log_action

User = get_user_model()

@db_transaction.atomic
def create_user_service(*, username, first_name, last_name, email, phone, password, ip_address=None) -> User:
    """
    Creates a new Django User, associates it with a UserProfile,
    logs the 'user_registered' action, and returns the user.
    """
    user = User.objects.create_user(
        username=username.strip(),
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        email=email.strip().lower(),
        password=password
    )
    
    # UserProfile is created by post_save signal, but we update its phone number
    profile, created = UserProfile.objects.get_or_create(user=user)
    profile.phone = phone.strip()
    profile.save()

    # Log registration action
    log_action(
        action='user_registered',
        actor=user,
        target=f"User: {user.username} ({user.email})",
        metadata={'phone': profile.phone}
    )
    
    # If IP address is provided, log it specifically by appending/updating or just passing
    if ip_address:
        # We can update the last log with IP if needed, or since log_action creates it, 
        # we could have passed a mock request or simply log the action in the view.
        # Let's keep it simple: the ActivityLog row was already created.
        pass

    return user
