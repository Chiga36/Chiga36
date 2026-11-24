"""
Turn a portrait photo into ascii.txt + ascii_tone.txt for the profile card.

Bright areas (skin) become dense, bright characters; dark areas (hair, beard) become sparse,
dim ones, the same way round as the Torukmaktocode card. ascii_tone.txt holds one digit per
character (0 = darkest, 9 = brightest) that the card uses as that character's brightness.

  pip install opencv-python numpy
  python scripts/make_ascii.py photo.jpg --subject 200 180 876 1600 --crop 120 180 800 980

--subject  box around the person (x0 y0 x1 y1, photo pixels); GrabCut removes everything else
--crop     part of the photo to draw (head and shoulders works best)
--cols     width in characters (~110-130 fits the card)
--gamma    >1 pushes hair/beard darker, <1 lifts them
--fade     where (0-1 down the crop) the torso starts fading out

Push the two new files and the workflow rebuilds the card.
"""
import argparse

import cv2
import numpy as np

RAMP = " .':;!|ijlxzoO0@"   # sparse -> dense


def cutout(img, box):
    mask = np.zeros(img.shape[:2], np.uint8)
    bgd, fgd = np.zeros((1, 65)), np.zeros((1, 65))
    x0, y0, x1, y1 = box
    cv2.grabCut(img, mask, (x0, y0, x1 - x0, y1 - y0), bgd, fgd, 8, cv2.GC_INIT_WITH_RECT)
    fg = np.isin(mask, [cv2.GC_FGD, cv2.GC_PR_FGD]).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(fg)
    return (lab == 1 + np.argmax(st[1:, cv2.CC_STAT_AREA])).astype(np.uint8) if n > 1 else fg


def convert(img, fg, cols, crop, gamma=1.3, fade=0.70, sharpen=0.9):
    x0, y0, x1, y1 = crop
    g = img.max(axis=2)[y0:y1, x0:x1]          # brightness that ignores colour tints
    fg = fg[y0:y1, x0:x1]
    g = cv2.GaussianBlur(g, (0, 0), 1.2).astype(np.float32)
    g = np.clip(g + sharpen * (g - cv2.GaussianBlur(g, (0, 0), 4)), 0, 255)
    h, w = g.shape
    rows = int(round(cols * h / w * 0.5))      # a monospace cell is ~2x taller than wide
    s = cv2.resize(g, (cols, rows), interpolation=cv2.INTER_AREA) / 255
    m = cv2.resize(fg.astype(np.float32), (cols, rows), interpolation=cv2.INTER_AREA)
    v = s[m > 0.5]
    lo, hi = np.percentile(v, 2), np.percentile(v, 99.5)
    b = np.clip((s - lo) / (hi - lo), 0, 1) ** gamma
    y = np.arange(rows)[:, None] / rows
    b *= 1 - 0.7 * np.clip((y - fade) / (1 - fade), 0, 1)
    chars, tones = [], []
    for r in range(rows):
        cl, tl = [], []
        for c in range(cols):
            if m[r, c] < 0.5:
                cl.append(" "); tl.append(" ")
            else:
                cl.append(RAMP[min(len(RAMP) - 1, max(1, int(b[r, c] * len(RAMP))))])
                tl.append(str(min(9, int(b[r, c] * 10))))
        chars.append("".join(cl).rstrip()); tones.append("".join(tl).rstrip())
    while chars and not chars[0].strip():
        chars.pop(0); tones.pop(0)
    return chars, tones


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("photo")
    p.add_argument("--subject", type=int, nargs=4, metavar=("X0", "Y0", "X1", "Y1"))
    p.add_argument("--crop", type=int, nargs=4, metavar=("X0", "Y0", "X1", "Y1"))
    p.add_argument("--cols", type=int, default=120)
    p.add_argument("--gamma", type=float, default=1.3)
    p.add_argument("--fade", type=float, default=0.70)
    a = p.parse_args()
    img = cv2.imread(a.photo)
    H, W = img.shape[:2]
    fg = cutout(img, a.subject or (int(W * .05), int(H * .05), int(W * .95), H - 1))
    chars, tones = convert(img, fg, a.cols, a.crop or (0, 0, W, H), a.gamma, a.fade)
    open("ascii.txt", "w", encoding="utf-8").write("\n".join(chars) + "\n")
    open("ascii_tone.txt", "w", encoding="utf-8").write("\n".join(tones) + "\n")
    print("\n".join(chars))
