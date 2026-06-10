# EventHub — Event Registration System

## Setup

```bash
# 1. Create virtual environment
python -m venv venv
 
venv\Scripts\activate
 # shell: source venv/bin/activate 

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — add your SECRET_KEY and Razorpay keys

# 4. Run migrations
python manage.py migrate

# 5. Create admin user
python create_admin.py

# 6. Run server
python manage.py runserver
```

## URLs

| URL | Description |
|-----|-------------|
| `/` | Public registration portal |
| `/confirm/<id>/` | Registration confirmation page |
| `/payment/callback/` | Razorpay payment callback (AJAX POST) |
| `/payment/webhook/` | Razorpay server webhook |
| `/admin-portal/login/` | Admin login |
| `/admin-portal/dashboard/` | Admin dashboard |
| `/admin-portal/tickets/` | Ticket management |
| `/admin-portal/registrations/` | Registration management |
| `/admin-portal/activity/` | Activity logs |

## Default Admin Credentials
- Username: `admin`
- Password: `admin@123`
- **Change these before any deployment**

## Architecture

```
Registration (billing contact, optional user)
  └── RegistrationItem (junction: one attendee × one ticket)
        ├── Attendee   (standalone entity, identified by email)
        └── Ticket     (soft-deleted, price snapshot on item)

Transaction (1:1 with Registration, Razorpay refs)
ActivityLog (append-only audit trail)
```

## Key Design Decisions

- **Attendee as entity**: `get_or_create` by email — reusable across events
- **Price snapshot**: `unit_price` on RegistrationItem captures price at purchase time
- **Soft delete**: Tickets with completed registrations are deactivated, not deleted
- **Idempotent payments**: Webhook + callback both safe to call multiple times
- **Email dedup per ticket**: Checked against `Attendee` model, not contact email
- **Race conditions**: `select_for_update()` on quota check inside `atomic()`
- **Guest checkout**: `user` FK is nullable — no forced account creation

## Razorpay Test Setup
1. Create account at https://razorpay.com
2. Get test Key ID and Secret from Dashboard → Settings → API Keys
3. Add to `.env`
4. Use test card: 4111 1111 1111 1111, any future date, any CVV


.\venv\Scripts\celery.exe -A config worker --loglevel=info -P solo
.\venv\Scripts\celery.exe -A config beat --loglevel=info
"# frfrfr" 
