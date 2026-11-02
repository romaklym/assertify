"""Human-like pacing: random pauses, curved mouse paths, uneven typing.

Bot detectors look for instant, pixel-perfect, perfectly regular input. This module makes
actions look like a person's. Turn it off with ASSERTIFY_HUMANIZE=0 (tests, trusted sites).
"""

from __future__ import annotations

import asyncio
import math
import os
import random

from playwright.async_api import Page


def enabled() -> bool:
    return os.environ.get("ASSERTIFY_HUMANIZE", "1") != "0"


async def pause(lo: float = 0.4, hi: float = 1.3, slow: float = 1.0) -> None:
    """Think time between actions. `slow` > 1 for sites that are strict about automation."""
    if enabled():
        await asyncio.sleep(random.uniform(lo, hi) * slow)


def point_in(box: dict) -> tuple[float, float]:
    """A random point near the middle of an element, never the exact center."""
    if not enabled():
        return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    return (
        box["x"] + box["width"] * random.uniform(0.3, 0.7),
        box["y"] + box["height"] * random.uniform(0.3, 0.7),
    )


def _path(x0: float, y0: float, x1: float, y1: float) -> list[tuple[float, float]]:
    """Eased curve from (x0, y0) to (x1, y1) with a random bend."""
    dist = math.hypot(x1 - x0, y1 - y0)
    steps = max(8, min(40, int(dist / 25)))
    bend = min(dist * 0.25, 120)
    cx = (x0 + x1) / 2 + random.uniform(-bend, bend)
    cy = (y0 + y1) / 2 + random.uniform(-bend, bend)
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        t = t * t * (3 - 2 * t)  # ease in and out
        pts.append(
            (
                (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t * t * x1,
                (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t * t * y1,
            )
        )
    return pts


async def click_at(page: Page, start: tuple[float, float], x: float, y: float) -> None:
    """Move the mouse along a curve, hover briefly, then press and release."""
    if not enabled():
        await page.mouse.click(x, y)
        return
    for px, py in _path(*start, x, y):
        await page.mouse.move(px, py)
        await asyncio.sleep(random.uniform(0.004, 0.016))
    await asyncio.sleep(random.uniform(0.05, 0.25))
    await page.mouse.down()
    await asyncio.sleep(random.uniform(0.04, 0.12))
    await page.mouse.up()


async def type_text(page: Page, text: str) -> None:
    """Type one key at a time with uneven gaps and the odd pause between words."""
    if not enabled():
        await page.keyboard.insert_text(text)
        return
    fast = len(text) > 200  # long text: still keystrokes, just quicker
    for ch in text:
        await page.keyboard.type(ch)
        delay = random.uniform(0.035, 0.14)
        if ch == " " and random.random() < 0.15:
            delay += random.uniform(0.1, 0.4)
        await asyncio.sleep(delay / 4 if fast else delay)


async def wheel(page: Page, dy: float) -> None:
    """Scroll in a few uneven flicks instead of one jump."""
    if not enabled():
        await page.mouse.wheel(0, dy)
        return
    left = dy
    while abs(left) > 1:
        step = math.copysign(min(abs(left), random.uniform(90, 260)), left)
        await page.mouse.wheel(0, step)
        left -= step
        await asyncio.sleep(random.uniform(0.03, 0.12))
