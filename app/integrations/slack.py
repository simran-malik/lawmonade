"""Send a Slack message through an Incoming Webhook. No extra packages needed.

notify("3 new deadlines found, 1 needs review")
"""
import json
import urllib.request

from app.config import settings
from app.log import get

LOG = get("slack")


def notify(text: str, webhook_url: str | None = None) -> bool:
    url = webhook_url or settings.slack_webhook_url
    if not url:
        LOG.info("[send.slack] not set up; would send %d characters", len(text))
        return False
    req = urllib.request.Request(url, data=json.dumps({"text": text}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status == 200
