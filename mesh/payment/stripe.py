"""Stripe payment integration for Mesh Pro subscriptions."""

import os
from dataclasses import dataclass
from typing import Optional

import stripe

PRICE_PERSONAL_PRO = "price_personal_pro_monthly"
PRICE_ORG_PRO = "price_org_pro_monthly"
PRICE_ORG_PRO_DISCOUNT = "price_org_pro_discount_monthly"

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")


@dataclass
class CheckoutSession:
    url: str
    session_id: str


@dataclass
class SubscriptionInfo:
    subscription_id: str
    customer_id: str
    status: str
    current_period_end: int


class StripeManager:
    def __init__(self, api_key: Optional[str] = None):
        if api_key:
            stripe.api_key = api_key

    def is_configured(self) -> bool:
        return bool(stripe.api_key)

    def create_checkout_session(
        self,
        price_id: str,
        user_id: str,
        user_email: str,
        success_url: str,
        cancel_url: str,
        metadata: Optional[dict] = None,
    ) -> Optional[CheckoutSession]:
        if not self.is_configured():
            return None

        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                payment_method_types=["card"],
                line_items=[{"price": price_id, "quantity": 1}],
                customer_email=user_email,
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    "user_id": user_id,
                    **(metadata or {}),
                },
            )
            return CheckoutSession(url=session.url, session_id=session.id)
        except stripe.error.StripeError:
            return None

    def create_personal_pro_checkout(
        self,
        user_id: str,
        user_email: str,
        success_url: str = "https://mesh-arch.com/success",
        cancel_url: str = "https://mesh-arch.com/cancel",
    ) -> Optional[CheckoutSession]:
        return self.create_checkout_session(
            price_id=PRICE_PERSONAL_PRO,
            user_id=user_id,
            user_email=user_email,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"tier": "personal_pro"},
        )

    def create_org_pro_checkout(
        self,
        user_id: str,
        user_email: str,
        org_name: str,
        discount: bool = False,
        success_url: str = "https://mesh-arch.com/success",
        cancel_url: str = "https://mesh-arch.com/cancel",
    ) -> Optional[CheckoutSession]:
        price_id = PRICE_ORG_PRO_DISCOUNT if discount else PRICE_ORG_PRO
        return self.create_checkout_session(
            price_id=price_id,
            user_id=user_id,
            user_email=user_email,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "tier": "org_pro_discount" if discount else "org_pro",
                "org_name": org_name,
            },
        )

    def get_subscription(self, subscription_id: str) -> Optional[SubscriptionInfo]:
        if not self.is_configured():
            return None

        try:
            sub = stripe.Subscription.retrieve(subscription_id)
            return SubscriptionInfo(
                subscription_id=sub.id,
                customer_id=sub.customer,
                status=sub.status,
                current_period_end=sub.current_period_end,
            )
        except stripe.error.StripeError:
            return None

    def cancel_subscription(self, subscription_id: str) -> bool:
        if not self.is_configured():
            return False

        try:
            stripe.Subscription.delete(subscription_id)
            return True
        except stripe.error.StripeError:
            return False

    def construct_webhook_event(
        self, payload: bytes, signature: str, webhook_secret: str
    ) -> Optional[stripe.Event]:
        if not self.is_configured():
            return None

        try:
            return stripe.Webhook.construct_event(payload, signature, webhook_secret)
        except stripe.error.SignatureVerificationError:
            return None


def get_manager() -> StripeManager:
    return StripeManager()
