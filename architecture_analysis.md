# EventHub Architectural & Edge Case Analysis

This document provides a detailed architectural review of the EventHub ticketing and registration codebase, identifying critical design flaws, concurrency race conditions, performance bottlenecks, and active bugs.

---

## 1. Critical Bugs & Logic Flaws

### 1.1 Webhook Payment Corruptor (Webhooks active-fail successful payments)
* **Location**: `apps/payments/views.py` (line 101) & `apps/payments/services.py` (lines 90-116)
* **The Flaw**: When the Razorpay server-to-server webhook receives a `payment.captured` event, it calls:
  `confirm_payment(order_id, payment_id, '')`
  Inside `confirm_payment`, it attempts to verify the signature of the payment:
  ```python
  if not verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
      _mark_failed(transaction)
      raise PaymentError("Payment signature verification failed.")
  ```
  Since the webhook passes an empty string (`''`) as the signature, `verify_payment_signature` will execute `compare_digest` with an empty string, which **always fails**.
* **Impact**: If a user completes their payment but closes their browser before redirecting to the frontend success page, the webhook fires to reconcile the transaction. Instead of completing it, it will fail signature verification, **actively mark the transaction and registration as `failed`**, and throw an error. This leaves the user charged but marked as failed in the database.
* **Remediation**: Introduce a `bypass_signature` boolean flag to `confirm_payment` or skip the check if the signature argument is empty, since the webhook payload signature is already verified at the entry point of the view.

### 1.2 Overbroad Double-Submission Guard (State Hijacking)
* **Location**: `apps/registrations/services.py` (lines 120-132)
* **The Flaw**: To guard against double-clicks/submissions, the service checks for any `pending` registration under the same contact email in the last 5 minutes:
  ```python
  recent = Registration.objects.filter(
      contact_email=contact['email'].lower(),
      status='pending',
      created_at__gte=timezone.now() - timezone.timedelta(minutes=5)
  ).first()
  if recent:
      return recent
  ```
* **Impact**: 
  1. **Discarded Ticket/Attendee Changes**: If a user submits a registration, changes their mind during checkout, hits back, updates their ticket types/counts or attendee details, and clicks checkout again within 5 minutes, the system silently discards all their new selections and returns the old pending registration.
  2. **Data Hijacking**: If two different guests attempt to checkout using the same contact/corporate email address (e.g., `info@company.com`) within a 5-minute window, the second user will hijack the first user's pending checkout list and billing details.
* **Remediation**: Guard double-submissions using a unique idempotency key generated in the browser session, or check if the exact items/attendees match before returning the existing registration.

---

## 2. Concurrency & Race Conditions

### 2.1 Database Lock Deadlock Risk (Unsorted row locks)
* **Location**: `apps/registrations/services.py` (line 78)
* **The Flaw**: During the quota validation in `_check_quota`, the system locks tickets sequentially:
  ```python
  for item in items:
      ticket = Ticket.objects.select_for_update().get(id=item['ticket'].id)
  ```
  If Request A locks Ticket #1 and then tries to lock Ticket #2, while Request B locks Ticket #2 and then tries to lock Ticket #1 at the same instant, a **database deadlock** occurs. Postgres/SQLite will terminate one of the transactions.
* **Remediation**: Sort the input ticket IDs before acquiring the lock:
  `ticket_ids = sorted(list({item['ticket'].id for item in items}))` and lock them in ascending order.

### 2.2 Quota Reservation Leak (Unreserved "Pending" registrations)
* **Location**: `apps/registrations/services.py` (lines 83-86) & `apps/tickets/models.py` (lines 53-56)
* **The Flaw**: Quotas are calculated by counting registrations with `status` in `['processing', 'completed']`. However, registrations are initially created as `pending`. 
* **Impact**: If 10 users select the last available ticket type and proceed to checkout simultaneously, the system creates 10 separate `pending` registrations. Since `pending` is not counted as "sold", all 10 users are allowed to proceed to checkout for a ticket type with only 1 slot left. Only when the Razorpay SDK updates the status to `processing` does the slot register as locked, leading to overbooking.
* **Remediation**: The sold count should count `pending` registrations (optionally excluding those that have expired beyond a short time limit like 10-15 minutes).

---

## 3. Performance & N+1 Query Bottlenecks

### 3.1 N+1 Ticket Sold/Available Metrics
* **Location**: `apps/tickets/models.py` (lines 50-69)
* **The Flaw**: Properties like `sold_count`, `available_count`, and `is_sold_out` execute independent SQL queries (`RegistrationItem.objects.filter(...).count()`) inside python property descriptors.
* **Impact**: When rendering a listing page of 10-20 tickets (both in the public portal and the admin tickets dashboard), the template invokes these properties on each loop iteration. This results in **30+ redundant count queries** on a single page request.
* **Remediation**: Implement a selector/manager method to annotate tickets with `sold_count` in a single query (using Django’s `Coalesce` and `Count`), and use those annotations in views rather than database-hitting properties.

---

## 4. Operational & Lifecycle Issues

### 4.1 Lack of Cleanup/Expiration Workflows for Stale Registrations
* **The Flaw**: The system has no celery tasks, background threads, or cron scripts to transition stale `pending` or `processing` registrations to `failed`/`cancelled` status.
* **Impact**: If registrations are counted towards quotas (to prevent overbooking), stale uncompleted checkouts will lock up inventory permanently. If they are not counted (as is currently the case), they create database clutter and lead to disjointed audit logs.
* **Remediation**: Add a Celery task or a manage.py command (scheduled via cron) to clean up and expire any `pending` or `processing` registrations older than 15-30 minutes.
