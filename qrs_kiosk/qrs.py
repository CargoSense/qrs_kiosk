"""What the QRS server says about a sticker: its label and applets, or nothing."""

import logging

import aiohttp

log = logging.getLogger(__name__)


async def describe(url, http):
    try:
        async with http.get(url, headers={"accept": "application/json"}, timeout=aiohttp.ClientTimeout(total=15)) as res:
            if res.status != 200:
                return None
            body = await res.json(content_type=None)
    except (aiohttp.ClientError, ValueError, TimeoutError) as e:
        log.warning("could not describe %s: %s", url, e)
        return None
    sensor = body.get("sensor") or {}
    return {
        "url": url,
        "label": sensor.get("label") or "",
        "brand": (body.get("branding") or {}).get("name"),
        "applets": [a.get("title") or a.get("name") for a in body.get("applets") or []],
    }
