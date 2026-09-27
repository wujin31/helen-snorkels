"""San Diego County beach water quality (sdbeachinfo.com).

sdbeachinfo.com is an OutSystems app. Its map loads every sampling site, with
the current advisory/closure level, from one "screen service" POST. We call
that same endpoint the way the page does: the module version comes from a
GET, and the per-endpoint API version is read from the app's own JavaScript
whenever the server says it changed (i.e. after the county redeploys).

Public government data, fetched once an hour.
"""

from __future__ import annotations

import json
import re
from typing import Any

from snorkel.fetch.base import (
    FetchContext,
    HttpItem,
    Item,
    ItemError,
    RawSnapshot,
    describe_error,
    get_many,
    slug,
)
from snorkel.http import get_with_retry, request_with_retry

BASE = "https://cosdapps.sandiegocounty.gov/sdbeachinfo"
MODULE = "CoSD_Beach_Water_CW/MainFlow/HomeBlockNew"
SITES_ACTION = "ScreenDataSetGetSiteById"
SCREEN_JS = f"{BASE}/scripts/CoSD_Beach_Water_CW.MainFlow.HomeBlockNew.mvc.js"
# OutSystems' fixed CSRF token for anonymous sessions (the page sends the same).
ANONYMOUS_CSRF = "T6C+9iB49TLra4jEsMeSckDMNhQ="

SCREEN_VARIABLES: dict[str, Any] = {
    "ShowDetails": False,
    "MapCenter": "32.9345,-117.2619552",
    "SiteIdAux": "0",
    "ShowDetailsPhone": False,
    "EventTypeId": 0,
    "SitesSelectedTextNort": "",
    "SitesSelectedTextSouth": "",
    "SitesSelectedTextCentral": "",
    "SitesSelectedTextCity": "",
    "isRegionNortActivated": False,
    "isRegionSouthActivated": False,
    "isRegionCentralActivated": False,
    "isCityActivated": False,
    "isLegendActivated": False,
    "Zoom": 9,
    "AuxStruct": {"LocationName": "", "CurrRowNumberOldSelected": 0},
    "SitesSelectedToFilter": "",
    "MapIdAux": "",
    "ZoomCurrent": 0,
    "id": "1",
    "_idInDataFetchStatus": 1,
}


def discover_api_version(ctx: FetchContext, action: str) -> str:
    js = get_with_retry(ctx.client, SCREEN_JS, sleep=ctx.sleep).text
    match = re.search(rf'"{action}",\s*"screenservices/[^"]*{action}",\s*"([^"]+)"', js)
    if not match:
        raise ValueError(f"no API version for {action} in {SCREEN_JS}")
    return match.group(1)


def _post_sites(ctx: FetchContext, module_version: str, api_version: str) -> dict[str, Any]:
    body = {
        "versionInfo": {"moduleVersion": module_version, "apiVersion": api_version},
        "viewName": "MainFlow.Home",
        "screenData": {"variables": SCREEN_VARIABLES},
        "inputParameters": {},
    }
    response = request_with_retry(
        ctx.client,
        "POST",
        f"{BASE}/screenservices/{MODULE}/{SITES_ACTION}",
        headers={
            "X-CSRFToken": ANONYMOUS_CSRF,
            "OutSystems-Client-Env": "browser",
            "Content-Type": "application/json; charset=UTF-8",
        },
        content=json.dumps(body).encode(),
        sleep=ctx.sleep,
    )
    return response.json()


def capture_county(ctx: FetchContext) -> list[Item]:
    try:
        module_version = get_with_retry(
            ctx.client, f"{BASE}/moduleservices/moduleversioninfo", sleep=ctx.sleep
        ).json()["versionToken"]
        api_version = str(ctx.params.get("api_version") or discover_api_version(ctx, SITES_ACTION))
        data = _post_sites(ctx, module_version, api_version)
        info = data.get("versionInfo", {})
        if info.get("hasApiVersionChanged") or "data" not in data:
            api_version = discover_api_version(ctx, SITES_ACTION)
            data = _post_sites(ctx, module_version, api_version)
        sites = data["data"]["List"]["List"]
        if not isinstance(sites, list) or not sites:
            raise ValueError("county response has no sites")
    except Exception as exc:
        return [ItemError(error=describe_error(exc), url=BASE, variant="sites")]
    return [
        RawSnapshot(
            content=json.dumps(data).encode(),
            ext="json",
            url=f"{BASE}/screenservices/{MODULE}/{SITES_ACTION}",
            variant="sites",
            meta={"sites": len(sites), "api_version": api_version},
        )
    ]


def _ext(url: str) -> str:
    return "json" if url.split("?")[0].endswith(".json") else "html"


def capture_pages(ctx: FetchContext) -> list[Item]:
    urls = [str(u) for u in ctx.require("urls")]
    items = [HttpItem(url=u, ext=_ext(u), variant=slug(u.split("://", 1)[-1])) for u in urls]
    return get_many(ctx, items)
