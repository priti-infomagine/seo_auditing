import os
import stripe

client = stripe.StripeClient(os.environ["STRIPE_PUBLISHABLE_KEY"])