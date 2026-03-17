"""API routes."""

from auth.middleware import get_current_user
from payments.processor import process_payment, get_order_details


def get_user_profile(user_id: int):
    """Get user profile."""
    user = {"id": user_id, "name": "Test User"}
    return user


def create_order(user_id: int, items: list):
    """Create an order."""
    order = {"user_id": user_id, "items": items}
    return order


def handle_request(request):
    """Handle incoming request."""
    user = get_current_user(request)
    if not user:
        return {"error": "Unauthorized"}

    order = create_order(user["id"], request.get("items", []))
    result = process_payment(order)

    return {"status": "success", "order": order, "payment": result}


def get_order_from_payment(payment_id: str):
    """Get order from payment - creates circular dep with payments module."""
    order_details = get_order_details(payment_id)
    return order_details


def update_order_status(order_id: int, status: str):
    """Update order status."""
    return {"order_id": order_id, "status": status}


def cancel_order(order_id: int):
    """Cancel order."""
    return {"order_id": order_id, "cancelled": True}
