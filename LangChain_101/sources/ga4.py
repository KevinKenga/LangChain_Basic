"""Google Analytics 4: yesterday's product page views per item name.

Needs GA4_PROPERTY_ID and GOOGLE_APPLICATION_CREDENTIALS (service-account JSON path) in .env.
Raises SourceUnavailable when configuration is missing or the API call fails.
"""
import os
from datetime import date

from sources import SourceUnavailable


def fetch_product_views(day: date) -> dict[str, int]:
    """Return {item_name: items_viewed} for the given day."""
    prop = os.getenv("GA4_PROPERTY_ID")
    creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not prop or not creds:
        raise SourceUnavailable("GA4_PROPERTY_ID / GOOGLE_APPLICATION_CREDENTIALS not set in .env")
    if not os.path.isfile(creds):
        raise SourceUnavailable(f"credentials file not found: {creds}")

    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest

        client = BetaAnalyticsDataClient()
        req = RunReportRequest(
            property=f"properties/{prop}",
            dimensions=[Dimension(name="itemName")],
            metrics=[Metric(name="itemsViewed")],
            date_ranges=[DateRange(start_date=day.isoformat(), end_date=day.isoformat())],
            limit=1000,
        )
        resp = client.run_report(req)
    except Exception as exc:  # GA4 raises google.api_core errors of many types
        raise SourceUnavailable(f"GA4 request failed: {exc}") from exc

    views: dict[str, int] = {}
    for row in resp.rows:
        name = row.dimension_values[0].value or "unknown"
        views[name] = views.get(name, 0) + int(row.metric_values[0].value or 0)
    return views
