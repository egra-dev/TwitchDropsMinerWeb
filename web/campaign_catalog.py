from __future__ import annotations

import asyncio
import copy
import logging
import os
import shutil
import time
from typing import Any

logger = logging.getLogger("web_interface")
_CACHE_TTL_SECONDS = 600
_cache: list[dict[str, Any]] = []
_cache_time = 0.0
_cache_lock: asyncio.Lock | None = None


class PublicCampaignCatalogError(RuntimeError):
    pass


async def get_public_campaigns() -> list[dict[str, Any]]:
    """Scrape Twitch's public campaign catalog, returning a cached snapshot."""
    global _cache_lock, _cache_time, _cache

    if _cache_lock is None:
        _cache_lock = asyncio.Lock()

    async with _cache_lock:
        if _cache_time and time.monotonic() - _cache_time < _CACHE_TTL_SECONDS:
            return copy.deepcopy(_cache)

        try:
            campaigns = await _scrape_campaign_page()
        except (PublicCampaignCatalogError, OSError) as exc:
            logger.warning("Failed to scrape Twitch's public campaign catalog: %s", exc)
            if _cache_time:
                logger.warning("Using cached public campaign catalog after scrape failure")
                return copy.deepcopy(_cache)
            if isinstance(exc, PublicCampaignCatalogError):
                raise
            raise PublicCampaignCatalogError(
                "Could not scrape Twitch's public campaign catalog"
            ) from exc

        if campaigns:
            _cache = campaigns
            _cache_time = time.monotonic()
            logger.info("Loaded %d campaigns from Twitch's public catalog", len(campaigns))
        elif not _cache:
            _cache_time = time.monotonic()
            logger.info("Twitch's public campaign catalog is empty")
        else:
            logger.warning(
                "Twitch's public campaign page returned no campaigns; keeping cached data"
            )
            _cache_time = time.monotonic()
        return copy.deepcopy(_cache)


async def _scrape_campaign_page() -> list[dict[str, Any]]:
    try:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise PublicCampaignCatalogError(
            "Playwright is missing; install the project requirements"
        ) from exc

    executable_path = (
        os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )
    launch_options: dict[str, Any] = {
        "headless": True,
        "args": ["--disable-dev-shm-usage"],
    }
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        launch_options["args"].append("--no-sandbox")
    if executable_path:
        launch_options["executable_path"] = executable_path

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(**launch_options)
            try:
                page = await browser.new_page()
                page.set_default_timeout(10_000)
                response = await page.goto(
                    "https://www.twitch.tv/drops/campaigns",
                    wait_until="domcontentloaded",
                    timeout=30_000,
                )
                if response is None or response.status >= 400:
                    status = response.status if response is not None else "no response"
                    raise PublicCampaignCatalogError(
                        f"Twitch campaign page returned HTTP {status}"
                    )
                await page.wait_for_timeout(6_000)

                previous_height = 0
                stable_height_count = 0
                for _ in range(8):
                    height = await page.evaluate("document.body.scrollHeight")
                    if height == previous_height:
                        stable_height_count += 1
                        if stable_height_count == 2:
                            break
                    else:
                        stable_height_count = 0
                    previous_height = height
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(750)

                campaigns = await page.evaluate(
                    """() => {
                    let state = window.__APOLLO_STATE__ || {};
                    if (!Object.keys(state).length && window.__APOLLO_CLIENT__) {
                        try {
                            state = window.__APOLLO_CLIENT__.cache.extract();
                        } catch (_) {}
                    }

                    const output = [];
                    const seen = new Set();
                    const resolve = (value) => {
                        let current = value;
                        for (let depth = 0; depth < 5 && current?.__ref; depth++) {
                            current = state[current.__ref];
                        }
                        return current;
                    };
                    const add = (campaign) => {
                        if (!campaign.id || seen.has(campaign.id)) return;
                        if (!campaign.name || !campaign.game) return;
                        seen.add(campaign.id);
                        output.push(campaign);
                    };

                    for (const [key, value] of Object.entries(state)) {
                        if (!value || typeof value !== 'object') continue;
                        const type = value.__typename || '';
                        if (
                            !type.includes('DropCampaign') &&
                            !key.startsWith('DropCampaign:')
                        ) continue;
                        const game = resolve(value.game) || {};
                        const id = value.id || key.split(':').slice(1).join(':');
                        add({
                            id,
                            name: value.name || value.title || '',
                            game: game.displayName || game.name || '',
                            image_url: game.boxArtURL || game.boxArtUrl || '',
                            start_time: value.startAt || value.startsAt || null,
                            end_time: value.endAt || value.endsAt || null,
                            status: value.status || null
                        });
                    }

                    for (const anchor of document.querySelectorAll('a[href*="/drops/campaigns/"]')) {
                        const url = new URL(anchor.href);
                        const idMatch = url.pathname.match(/\\/drops\\/campaigns\\/([^/]+)/);
                        if (!idMatch) continue;

                        let card = anchor;
                        for (let depth = 0; depth < 6 && card.parentElement; depth++) {
                            card = card.parentElement;
                            if (card.querySelector('img[alt]') && card.textContent.trim().length > 20) break;
                        }
                        const gameImage = card.querySelector('img[alt]');
                        const categoryLink = card.querySelector('a[href*="/directory/category/"]');
                        const game = gameImage?.alt?.trim() || categoryLink?.textContent?.trim() || '';
                        const cardText = card.textContent.toLowerCase();
                        const headings = [...card.querySelectorAll('h1,h2,h3,h4')]
                            .map((heading) => heading.textContent.trim())
                            .filter((text) => text && text !== game);
                        const name = headings[0] || anchor.textContent.trim();
                        if (!game || !name) continue;

                        add({
                            id: decodeURIComponent(idMatch[1]),
                            name,
                            game,
                            image_url: gameImage.currentSrc || gameImage.src || '',
                            start_time: null,
                            end_time: null,
                            status: cardText.includes('upcoming') ? 'UPCOMING' : null
                        });
                    }
                    return output;
                    }"""
                )
                if not isinstance(campaigns, list) or any(
                    not isinstance(campaign, dict) for campaign in campaigns
                ):
                    raise PublicCampaignCatalogError(
                        "Twitch's public campaign page returned an invalid catalog"
                    )
                return campaigns
            finally:
                await browser.close()
    except PlaywrightError as exc:
        raise PublicCampaignCatalogError(
            "Could not scrape Twitch's public campaign page"
        ) from exc
