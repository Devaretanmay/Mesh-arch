"""Payment processor."""

from api.routes import get_user_profile, get_order_from_payment


class PaymentProcessor:
    """Process payments."""

    def __init__(self):
        self.api_base = "https://api.example.com"

    def process(self, order):
        """Process a payment."""
        user_id = order.get("user_id")
        profile = get_user_profile(user_id)

        return {
            "status": "paid",
            "user": profile,
        }


def process_payment(order):
    """Process payment for order."""
    processor = PaymentProcessor()
    return processor.process(order)


def refund_payment(transaction_id: str):
    """Refund a payment."""
    return {"status": "refunded", "id": transaction_id}


def get_payment_status(transaction_id: str) -> dict:
    """Get payment status."""
    return {"transaction_id": transaction_id, "status": "completed"}


def get_order_details(payment_id: str) -> dict:
    """Get order details from payment - creates circular dep with api module."""
    order = get_order_from_payment(payment_id)
    return order


def cancel_payment(transaction_id: str) -> dict:
    """Cancel payment."""
    return {"transaction_id": transaction_id, "cancelled": True}


def process_refund(transaction_id: str, amount: float) -> dict:
    """Process refund."""
    return {"transaction_id": transaction_id, "refunded": amount}
