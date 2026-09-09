"""Normalize the account API without exposing addresses or payment details."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
import re
from zoneinfo import ZoneInfo

NZ = ZoneInfo("Pacific/Auckland")


def timestamp(value):
    if not value or value.startswith("0001-"):
        return None
    result = datetime.fromisoformat(value)
    return result.replace(tzinfo=NZ) if result.tzinfo is None else result.astimezone(NZ)


def bag_name(subscription):
    name = subscription.get("product", {}).get("productName", "My Food Bag")
    return re.sub(r"\s+(?:Choice\s+)?for\s+\d+\s+people.*$", "", name, flags=re.I).strip()


@dataclass
class Delivery:
    key: str
    bag: str
    start: datetime
    end: datetime
    title: str
    price: Decimal | None
    status: str | None
    paid: bool | None
    virtual: bool
    tracking: dict
    promos: list | None
    recipes: list
    deadline: datetime | None
    discount: Decimal | None
    meal_names: list[str | None] = field(default_factory=list)

    def attributes(self):
        return {"delivery_date": self.start.date().isoformat(), "window_end": self.end.isoformat(),
                "delivery_id": self.key, "status": self.status, "provisional": self.virtual,
                "recipes": self.recipes,
                "promo_items": self.promos,
                "tracking_url": self.tracking.get("trackingLink"),
                "courier": self.tracking.get("courier"),
                "estimated_delivery_window": self.tracking.get("estimatedDeliveryDateTime")}

    def description(self):
        parts = [self.bag, self.status or "", "Provisional delivery" if self.virtual else "",
                 f"Delivery window: {self.start:%H:%M}–{self.end:%H:%M} (Pacific/Auckland)"]
        if self.price is not None:
            parts.append(f"Total after promotions: NZ${self.price:.2f}")
        parts += self.recipes
        if self.promos:
            parts.append("Promotional items: " + ", ".join(p["name"] for p in self.promos))
        if self.tracking.get("trackingNumber"):
            parts.append("Tracking: " + str(self.tracking["trackingNumber"]))
        return "\n".join(p for p in parts if p)


def normalize(subscription, order, summary=None, selection=None, tracking=None):
    if order.get("isSkipped") or (order.get("orderStatus") or {}).get("styleTreatment", "").lower() in ("cancelled", "canceled", "skipped"):
        return None
    slot = order.get("deliveryDate") or {}
    day = timestamp(slot.get("actualDeliveryDate"))
    if day is None:
        return None
    start = timestamp(day.date().isoformat() + "T" + (slot.get("actualDeliveryStartTime") or "00:00:00"))
    end_time = slot.get("actualDeliveryEndTime")
    end = timestamp(day.date().isoformat() + "T" + end_time) if end_time else start + timedelta(days=1)
    if end <= start:
        end += timedelta(days=1)
    summary = summary or {}
    product_name = summary.get("primaryProductName") or order.get("primaryProduct", {}).get("marketingName", "")
    match = re.search(r"(\d+)\s+Nights?\s+For\s+(\d+)", product_name, re.I)
    recipes = (selection or {}).get("recipes", [])
    people_match = re.search(r"for\s+(\d+)\s+people", product_name, re.I)
    people = int(match[2]) if match else int(people_match[1]) if people_match else None
    meals = int(match[1]) if match else sum(r.get("quantity", 1) for r in recipes) or None
    # Selection timestamps establish meal order, not the date to eat them.
    # Keep API order for ties and place undated selections last.
    def selection_time(recipe):
        try:
            return float(recipe.get("timeStamp") or float("inf"))
        except (TypeError, ValueError):
            return float("inf")

    meal_names = [r.get("recipeName") for r in sorted(recipes, key=selection_time)
                  for _ in range(max(0, r.get("quantity", 1)))]
    if meals:
        meal_names = meal_names[:meals]
    title = f"{meals} meals for {people} people" if meals and people else "Meal delivery" + (f" for {people} people" if people else "")
    virtual = bool(order.get("isVirtual"))
    raw_price = summary.get("total")
    if raw_price is None and not virtual:
        raw_price = order.get("totalCost")
    price = Decimal(str(raw_price)).quantize(Decimal("0.01")) if raw_price is not None else None
    # Only confirmed order summaries establish whether complimentary extras exist.
    promos = None
    if summary:
        promos = []
        seen = set()
        for item in summary.get("extras", []) + summary.get("products", []):
            name = item.get("productName")
            if name and name != summary.get("primaryProductName") and item.get("price") == 0 and item.get("quantity", 1) > 0 and name not in seen:
                seen.add(name)
                promos.append({"name": name, "quantity": item.get("quantity", 1), "price": 0})
    deadline = timestamp(order.get("orderActions", {}).get("canChangeMeals", {}).get("effectiveUntilActual"))
    discount = summary.get("promoDiscount")
    return Delivery(str(order.get("orderKey") or order.get("deliveryId")), bag_name(subscription), start, end, title,
                    price, (order.get("orderStatus") or {}).get("badgeText"), summary.get("paid", order.get("isPaid")),
                    virtual, tracking or {}, promos, [r["recipeName"] for r in recipes if r.get("recipeName")],
                    deadline, Decimal(str(discount)) if discount is not None else None, meal_names)


def current(deliveries, now=None):
    now = now or datetime.now(NZ)
    # Keep today's delivery selected through midnight, even after the window ends.
    return next((d for d in sorted(deliveries, key=lambda d: d.start) if d.start.date() >= now.astimezone(NZ).date()), None)
