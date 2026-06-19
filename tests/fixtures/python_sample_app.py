from django.urls import path
from fastapi import APIRouter, FastAPI
from flask import Flask

import requests as http_requests


app = FastAPI()
router = APIRouter()
flask_app = Flask(__name__)


@app.get("/health")
def health_check():
    return {"ok": True}


@router.post("/orders/{order_id}")
async def create_order(order_id: str):
    if order_id:
        save_order(order_id)
    elif fallback_enabled():
        queue_order(order_id)
    else:
        raise ValueError("missing order id")
    return {"id": order_id}


@flask_app.route("/legacy", methods=["GET", "POST"])
def legacy_checkout():
    response = http_requests.get("https://example.invalid/status")
    return response.status_code


class CheckoutView:
    @classmethod
    def as_view(cls):
        return cls()


urlpatterns = [
    path("checkout/", CheckoutView.as_view(), name="checkout"),
]

