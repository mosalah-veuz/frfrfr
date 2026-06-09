# EventHub — Project Business Logic & Architecture Description

This document details the business logic, constraints, models, and workflows of the EventHub event ticketing and registration application.

---

## 1. System Components & Models

### Accounts (`apps.accounts`)
- Manages authentication and user sessions.
- Staff/Admin users can access the administrative backend panel (`/admin-portal/`).
- Regular public users register as guests or logged-in users.

### Tickets (`apps.tickets`)
Stores details for different entry/seat categories.
- **`ticket_type`**: `free` or `paid`.
  - *Constraint*: Free tickets must have a price of `0`. Paid tickets must have a price greater than `0`.
- **`quantity_type`**: `limited` or `unlimited`.
  - *Constraint*: Limited tickets require `total_quantity` to be specified. Unlimited tickets default `total_quantity` to `None`.
- **`duplicate_email`**: Boolean flag.
  - *Constraint*: If `True`, the same email address can register multiple times for this ticket. If `False`, email reuse is blocked.
- **`is_active`**: Boolean flag. Only active tickets are listed in the public portal.

### Registrations (`apps.registrations`)
Represents the purchase order and attendee database.
- **`Registration`**: Represents the billing contact/transaction level.
  - Contains fields: `contact_name`, `contact_email`, `contact_phone`.
  - `status`: `pending`, `processing`, `completed`, `failed`, `cancelled`.
- **`RegistrationItem`**: Represents one attendee seat under a specific ticket category.
  - Contains inline attendee details: `attendee_name`, `attendee_email`, `attendee_phone`.
  - Snapshots `unit_price` at the time of order placement to isolate historic registrations from pricing updates.

### Payments (`apps.payments`)
Handles billing integrations.
- Integrates with **Razorpay**.
- Creates a `Transaction` row pointing to a Razorpay `order_id`.
- Validates signatures client-side and server-side on callback.
- Exposes a server-to-server webhook callback to handle asynchronous capture notifications (`payment.captured` or `payment.failed`) from Razorpay.

### Activity Logs (`apps.activity`)
- Logs audit actions (e.g. `payment_created`, `payment_verified`, `registration_view`) for administrative monitoring.

---

## 2. Public Registration & Validation Workflows

### Step 1: Portal Selection (Homepage)
- The user selects ticket types via a popup modal.
- Active ticket selections are displayed as full-width horizontal sections.
- The user enters attendee details for each ticket category.
- **Dry-Run Validation (Pre-Checkout)**:
  - When the user clicks **Proceed to Checkout**, an AJAX POST request containing the selected tickets and attendee lists is sent to `/register/` with a `dry_run: true` flag.
  - The server validates the following constraints and returns precise errors:
    1. **Form Presence**: Attendee Name and Email must not be blank. Email must match a valid address format.
    2. **Local Duplicate Constraint**: If `ticket.duplicate_email` is `False`, the attendee list in the ticket group must not contain duplicate emails. If `True`, duplicates are permitted.
    3. **Event-Wide Duplicate Constraint**: If `ticket.duplicate_email` is `False`, attendee emails are compared against all completed registrations. If any match, registration is blocked.
    4. **Quota Constraint**: If `ticket.quantity_type` is `limited`, the quantity must not exceed the remaining quota (`total_quantity - sold_count`).
  - If validation passes, the selection is stored in `sessionStorage` and the user is redirected to `/checkout/`.

### Step 2: Checkout & Placement
- The checkout page retrieves the cart from `sessionStorage` and displays a detailed summary.
- The user enters billing details (`contact_name`, `contact_email`, `contact_phone`).
- The user clicks **Confirm & Complete Registration** which posts the final payload to `/register/` (without `dry_run` flag):
  - **Double-Submission Guard**: If a registration with the same contact email is already in `pending` status and was created within the last 5 minutes, the server intercepts the request and returns the existing registration order instead of duplicating.
  - **Paid Tickets**: If total > 0, the server creates a Razorpay payment order and initiates the Razorpay Checkout SDK popup. On payment success, it verifies the signature and marks status as `completed`.
  - **Free Tickets**: If total = 0, the transaction completes immediately, is marked `completed` in the DB, and redirects to the confirmation page.
