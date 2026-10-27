from decimal import Decimal

from django import template

from planner.forms import CURRENCY_SYMBOLS
from planner.services.budget import divide_round, to_cents

register = template.Library()


def group_digits(number, currency):
    """Thousands grouping; Indian lakh/crore grouping for INR (mirrors budget.js)."""
    digits = str(number)
    if currency != "INR" or len(digits) <= 3:
        return f"{number:,}"
    head, tail = digits[:-3], digits[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


def format_cents(cents, currency):
    whole = divide_round(abs(int(cents)), 100)
    sign = "−" if cents < 0 and whole else ""
    return f"{sign}{CURRENCY_SYMBOLS.get(currency, currency + ' ')}{group_digits(whole, currency)}"


@register.filter
def money(cents, currency):
    """Render integer minor units, e.g. {{ result.total|money:trip.currency }}."""
    if cents is None or cents == "":
        return ""
    return format_cents(int(cents), currency)


@register.filter
def money_amount(amount, currency):
    """Render a Decimal amount in major units."""
    if amount is None or amount == "":
        return ""
    return format_cents(to_cents(Decimal(str(amount))), currency)


@register.filter
def abs_value(value):
    return abs(value)


@register.filter
def get_item(mapping, key):
    return mapping.get(key) if hasattr(mapping, "get") else None


@register.filter
def times(amount, multiplier):
    return Decimal(str(amount)) * int(multiplier)
