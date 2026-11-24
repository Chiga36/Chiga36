"""
Render dark_mode.svg and contributions.svg to 2x PNGs with headless Chromium, so the
README looks the same for every visitor regardless of which fonts they have installed.

  pip install playwright && playwright install --with-deps chromium
  python scripts/svg_to_png.py
"""
import base64
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
FILES = ["dark_mode.svg", "contributions.svg"]


def size(svg):
    m = re.search(r'<svg[^>]*\bwidth="([\d.]+)"[^>]*\bheight="([\d.]+)"', svg)
    return int(float(m.group(1))), int(float(m.group(2)))


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name in FILES:
            svg = (ROOT / name).read_text(encoding="utf-8")
            w, h = size(svg)
            page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
            # inline <svg> (not <img>) so locally installed monospace fonts are used
            page.set_content(f'<html><body style="margin:0;background:#0d1117">{svg}</body></html>')
            page.wait_for_timeout(300)
            page.locator("svg").first.screenshot(path=str(ROOT / name.replace(".svg", ".png")), omit_background=True)
            page.close()
            print("wrote", name.replace(".svg", ".png"), f"{w * 2}x{h * 2}")
        browser.close()


if __name__ == "__main__":
    main()
