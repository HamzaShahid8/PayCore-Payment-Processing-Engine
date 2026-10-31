# Stripe Test Mode Backend

Django REST Framework API for fixed-price, one-time Stripe Checkout payments.
The backend determines every amount; clients submit only a plan identifier.

## Plans

| Plan | Amount | Stripe amount |
|---|---:|---:|
| `basic` | $10 | 1,000 cents |
| `standard` | $510 | 51,000 cents |
| `premium` | $1,000 | 100,000 cents |
| `enterprise` | $3,257 | 325,700 cents |

## Local setup

Use Python 3.10 or later. From this directory:

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and set a strong `DJANGO_SECRET_KEY`, test
   Stripe keys, success/cancel URLs, and PostgreSQL connection settings.
4. Run `python manage.py migrate`.
5. Start the API with `python manage.py runserver`.

The application uses PostgreSQL by default with the database name
`stripetestmode`. Set `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` in
`.env` for your PostgreSQL instance, or provide a PostgreSQL `DATABASE_URL`
instead. Django tests use SQLite when run without `DATABASE_URL`. For Vercel,
configure `DATABASE_URL` to use a persistent PostgreSQL database; the
serverless filesystem is ephemeral.
The deployment also requires `DJANGO_SECRET_KEY`, `STRIPE_SECRET_KEY`,
`STRIPE_WEBHOOK_SECRET`, `STRIPE_SUCCESS_URL`, and `STRIPE_CANCEL_URL`.
Set `ALLOWED_HOSTS` to a comma-separated list that includes your deployed
domain. Set Stripe keys to Test Mode values while testing.

## API

### Create a Checkout Session

`POST /api/create-checkout-session`

Request:

```json
{
  "plan": "basic"
}
```

Successful response (`201`):

```json
{
  "success": true,
  "session_id": "cs_test_xxxxx",
  "checkout_url": "https://checkout.stripe.com/xxxxx"
}
```

Invalid or missing plans return `400`; Stripe API failures return `502`.
No amount field is accepted or used.

### Stripe webhook

`POST /api/stripe/webhook`

Configure Stripe to send events to this URL and subscribe to
`checkout.session.completed`. The API verifies `Stripe-Signature` against the
unmodified request body with `STRIPE_WEBHOOK_SECRET`, persists each event ID
once, and marks a matching payment paid only when Stripe reports
`payment_status == "paid"`. Duplicate events are acknowledged without applying
their effects again.

The `Payment` and `StripeWebhookEvent` tables are created by Django migrations.
Checkout attempts are stored as pending before calling Stripe; successful
webhooks update their status and retain the Checkout Session, Payment Intent,
and customer email.

## Django admin

Create an admin account with `python manage.py createsuperuser`, then sign in
at `/admin/`. Payments and Stripe webhook events are available as read-only
records; payment status cannot be changed through the admin.

## Tests

Run the API test suite with:

```powershell
python manage.py test payments
```

Tests cover all fixed prices, invalid input, method errors, signature rejection,
paid and unpaid completion events, and duplicate event delivery. Stripe calls
are mocked; use Stripe Test Mode and the Stripe CLI to exercise an end-to-end
test payment against a running server:

```powershell
stripe listen --forward-to localhost:8000/api/stripe/webhook
```

Set the printed `whsec_...` value as `STRIPE_WEBHOOK_SECRET`. Use a Stripe test
card such as `4242 4242 4242 4242` with any future expiry and CVC.

## Vercel

Set the Vercel project root to this `backend` directory. `vercel.json` routes
requests through `api/index.py` into Django's WSGI application. Run migrations
against the configured persistent PostgreSQL database as part of deployment
operations; do not rely on SQLite or local files in the serverless runtime.
