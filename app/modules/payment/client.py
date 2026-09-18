"""
Stripe Checkout Session endpoint for subscription plans.

Given a plan_id from your /plans list, this creates a Stripe Checkout
Session in "subscription" mode and returns the URL to redirect the user to.

Setup required before this works:
1. In the Stripe Dashboard (Test mode) -> Products, create a Product +
   recurring monthly Price for each ACTIVE plan below (Starter $29,
   Professional $79, Agency $199).
2. Copy each Price ID (looks like "price_1AbCdEfGhIjKlMnOp") into
   PLAN_CODE_TO_STRIPE_PRICE below, matching the plan's "code" field.
3. Set STRIPE_SECRET_KEY as an environment variable (test key, starts
   with sk_test_).
"""

import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import stripe
from dotenv import load_dotenv
import os
load_dotenv()

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

router = APIRouter()

# --- Your plans, as returned by your /plans endpoint ---------------------
# In production this should come from your database (or the same source
# your /plans endpoint reads from) instead of being hardcoded here.
PLANS = [
    {
        "id": "3c2c4c8d-7e50-4fcb-bec6-4ea379b2959b",
        "code": "starter",
        "name": "Starter",
        "price": "29.00",
        "currency": "USD",
        "is_active": True,
    },
    {
        "id": "67d1cd7f-7e31-43e0-a963-d462b8c3eeec",
        "code": "professional",
        "name": "Professional",
        "price": "79.00",
        "currency": "USD",
        "is_active": False,
    },
    {
        "id": "1979ce94-a65d-4de3-8da2-d2103dccd279",
        "code": "agency",
        "name": "Agency",
        "price": "199.00",
        "currency": "USD",
        "is_active": False,
    },
]

# --- Map each plan's code to the Stripe Price ID you create in Stripe ----
# Fill these in once you've created the matching Prices in the Dashboard.
PLAN_CODE_TO_STRIPE_PRICE = {
    "starter": "price_REPLACE_WITH_STARTER_PRICE_ID",
    "professional": "price_REPLACE_WITH_PROFESSIONAL_PRICE_ID",
    "agency": "price_REPLACE_WITH_AGENCY_PRICE_ID",
}


class CreateCheckoutSessionRequest(BaseModel):
    plan_id: str        # the "id" field from your /plans list, e.g. the Starter UUID
    user_id: str         # your internal user ID -- used to match the webhook back to this user
    success_url: str      # where Stripe redirects on successful payment
    cancel_url: str       # where Stripe redirects if the user cancels


def _find_plan(plan_id: str):
    for plan in PLANS:
        if plan["id"] == plan_id:
            return plan
    return None


@router.post("/create-checkout-session")
def create_checkout_session(payload: CreateCheckoutSessionRequest):
    plan = _find_plan(payload.plan_id)
    print(f"=========================plan found:{ plan}=========================") 
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    if not plan["is_active"]:
        raise HTTPException(status_code=400, detail=f"Plan '{plan['name']}' is not currently available")

    price_id = PLAN_CODE_TO_STRIPE_PRICE.get(plan["code"])
    if not price_id or price_id.startswith("price_REPLACE"):
        raise HTTPException(
            status_code=500,
            detail=f"No Stripe Price configured for plan '{plan['code']}' yet",
        )

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            # {CHECKOUT_SESSION_ID} is a literal placeholder Stripe fills in itself
            success_url=payload.success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=payload.cancel_url,
            client_reference_id=payload.user_id,
            metadata={
                "user_id": payload.user_id,
                "plan_id": plan["id"],
                "plan_code": plan["code"],
            },
        )
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    
    print("-======== checkout session created =======")
    return {"checkout_url": session.url, "session_id": session.id}