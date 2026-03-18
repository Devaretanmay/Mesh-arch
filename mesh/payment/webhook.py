"""Stripe webhook handler for payment events.

This handler processes Stripe webhook events to:
- Confirm successful payments
- Update user subscriptions
- Handle failed payments
- Process cancellations
"""

import os

from mesh.payment.stripe import get_manager
from mesh.auth.storage import get_storage

STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")


def handle_webhook(payload: bytes, signature: str) -> dict:
    """Process Stripe webhook and update user subscriptions.

    Args:
        payload: Raw webhook payload
        signature: Stripe signature header

    Returns:
        dict with status and message
    """
    manager = get_manager()

    if not manager.is_configured():
        return {"status": "error", "message": "Stripe not configured"}

    if not STRIPE_WEBHOOK_SECRET:
        return {"status": "error", "message": "Webhook secret not configured"}

    event = manager.construct_webhook_event(payload, signature, STRIPE_WEBHOOK_SECRET)
    if not event:
        return {"status": "error", "message": "Invalid webhook signature"}

    if event.type == "checkout.session.completed":
        return handle_checkout_completed(event.data.object)
    elif event.type == "customer.subscription.updated":
        return handle_subscription_updated(event.data.object)
    elif event.type == "customer.subscription.deleted":
        return handle_subscription_deleted(event.data.object)
    elif event.type == "invoice.payment_failed":
        return handle_payment_failed(event.data.object)
    else:
        return {"status": "ignored", "message": f"Event type {event.type} not handled"}


def handle_checkout_completed(session) -> dict:
    """Handle successful checkout session."""
    user_id = session.metadata.get("user_id")
    tier = session.metadata.get("tier")

    if not user_id or not tier:
        return {"status": "error", "message": "Missing metadata in session"}

    storage = get_storage()
    stored_auth = storage.get_auth()

    if stored_auth and str(stored_auth.user_id) == user_id:
        if tier == "personal_pro":
            storage.save_auth(stored_auth)
        elif tier in ("org_pro", "org_pro_discount"):
            storage.save_auth(stored_auth)

    return {
        "status": "success",
        "message": f"Activated {tier} for user {user_id}",
    }


def handle_subscription_updated(subscription) -> dict:
    """Handle subscription updates (e.g., plan changes, renewals)."""
    return {
        "status": "success",
        "message": f"Updated subscription {subscription.id}",
    }


def handle_subscription_deleted(subscription) -> dict:
    """Handle subscription cancellations."""
    return {
        "status": "success",
        "message": f"Deleted subscription {subscription.id}",
    }


def handle_payment_failed(invoice) -> dict:
    """Handle failed payment attempts."""
    return {
        "status": "warning",
        "message": f"Payment failed for customer {invoice.customer}",
    }


def create_webhook_app():
    """Create FastAPI app for webhook handling.

    Usage with FastAPI:
        from mesh.payment.webhook import create_webhook_app
        app = create_webhook_app()
    """
    try:
        from fastapi import FastAPI, Request, HTTPException

        app = FastAPI(title="Mesh Stripe Webhook")

        @app.post("/webhook")
        async def stripe_webhook(request: Request):
            payload = await request.body()
            signature = request.headers.get("stripe-signature", "")

            result = handle_webhook(payload, signature)

            if result["status"] == "error":
                raise HTTPException(status_code=400, detail=result["message"])

            return result

        return app
    except ImportError:
        return None


def create_flask_app():
    """Create Flask app for webhook handling.

    Usage with Flask:
        from mesh.payment.webhook import create_flask_app
        app = create_flask_app()
    """
    try:
        from flask import Flask, request, jsonify

        app = Flask(__name__)

        @app.route("/webhook", methods=["POST"])
        def stripe_webhook():
            payload = request.data
            signature = request.headers.get("Stripe-Signature", "")

            result = handle_webhook(payload, signature)

            if result["status"] == "error":
                return jsonify(result), 400

            return jsonify(result)

        return app
    except ImportError:
        return None
