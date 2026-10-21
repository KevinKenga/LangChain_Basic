"""Shopify Admin API: yesterday's units and revenue per product.

Needs SHOPIFY_STORE (e.g. yourstore.myshopify.com) and SHOPIFY_ACCESS_TOKEN in .env.
Raises SourceUnavailable when credentials are missing or the API call fails.
"""
import os
import re
from datetime import datetime

import requests

from sources import SourceUnavailable

API_VERSION = "2024-10"


def _next_page_url(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        m = re.search(r'<([^>]+)>;\s*rel="next"', part)
        if m:
            return m.group(1)
    return None


def fetch_product_sales(start: datetime, end: datetime) -> dict[str, dict]:
    """Return {product_title: {"units": int, "revenue": float}} for orders created in [start, end)."""
    store = os.getenv("SHOPIFY_STORE")
    token = os.getenv("SHOPIFY_ACCESS_TOKEN")
    if not store or not token:
        raise SourceUnavailable("SHOPIFY_STORE / SHOPIFY_ACCESS_TOKEN not set in .env")

    url = f"https://{store}/admin/api/{API_VERSION}/orders.json"
    params = {
        "status": "any",
        "created_at_min": start.isoformat(),
        "created_at_max": end.isoformat(),
        "limit": 250,
        "fields": "id,created_at,cancelled_at,line_items",
    }
    headers = {"X-Shopify-Access-Token": token}

    sales: dict[str, dict] = {}
    try:
        while url:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            for order in resp.json().get("orders", []):
                if order.get("cancelled_at"):
                    continue
                for item in order.get("line_items", []):
                    title = item.get("title") or "unknown"
                    row = sales.setdefault(title, {"units": 0, "revenue": 0.0})
                    qty = int(item.get("quantity") or 0)
                    row["units"] += qty
                    row["revenue"] += qty * float(item.get("price") or 0)
            url = _next_page_url(resp.headers.get("Link"))
            params = None  # the next-page URL already carries its query
    except requests.RequestException as exc:
        raise SourceUnavailable(f"Shopify request failed: {exc}") from exc
    return sales
