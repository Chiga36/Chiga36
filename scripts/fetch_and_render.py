"""
Profile card + contribution heatmap for github.com/Chiga36.

  python scripts/fetch_and_render.py            # fetch live stats (needs ACCESS_TOKEN or GITHUB_TOKEN), then render
  python scripts/fetch_and_render.py --offline  # render from data/stats.json without calling the API

Writes dark_mode.svg and contributions.svg. Then run scripts/svg_to_png.py for the PNGs the README shows.
Edit the PROFILE block below to change what the card says about you.
"""
import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "stats.json"
LOGIN = os.environ.get("USER_NAME", "Chiga36")
TOKEN = os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN")

# ================================================================ edit me ====
PROFILE = [                       # (label, value) lines under the name header
    ("Name", "Chirag Saha"),
    ("Uptime", "{uptime}"),       # filled with the age of the GitHub account
    ("Focus", "Data Science & AI/ML"),
    ("Working on", "ML development"),
    ("Learning", "Data science"),
    ("Stack", "Python, PyTorch, TensorFlow, MySQL"),
]
HIDE_LANGUAGES = {"Jupyter Notebook"}   # notebook outputs inflate byte counts
TOP_LANGUAGES = 6                        # bars shown; the rest go on the "Other" line
PINNED_REPOS = []    # e.g. ["fin-agenti", "IISc-VGA", "document-ai-microservices"]; empty = most recently pushed
# =============================================================================

C = dict(bg="#0d1117", border="#30363d", text="#c9d1d9", dim="#8b949e", rule="#3d444d",
         head="#58a6ff", num="#79c0ff", green="#39d353", repo="#ffa657", faint="#484f58")
# portrait brightness: tone digit 0 (darkest) .. 9 (brightest) from ascii_tone.txt
PORTRAIT_DARK, PORTRAIT_LIGHT = (40, 46, 54), (244, 248, 252)
MONO = "'Consolas', 'Menlo', 'DejaVu Sans Mono', monospace"
CHAR = 0.602  # advance width of a monospace glyph, in em (DejaVu Sans Mono / Consolas ~0.55-0.6)


# ------------------------------------------------------------------- fetch ---
def gql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "User-Agent": f"{LOGIN}-profile"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.load(r)
    if out.get("errors"):
        raise RuntimeError(out["errors"])
    return out["data"]


QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    createdAt
    followers { totalCount }
    following { totalCount }
    contributionsCollection {
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
    }
    repositories(first: 100, after: $cursor, privacy: PUBLIC, ownerAffiliations: OWNER,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        name description isFork stargazerCount pushedAt
        primaryLanguage { name }
        languages(first: 25, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } }
      }
    }
  }
}"""


def fetch():
    cursor, nodes, first = None, [], None
    while True:
        u = gql(QUERY, {"login": LOGIN, "cursor": cursor})["user"]
        first = first or u
        nodes += u["repositories"]["nodes"]
        if not u["repositories"]["pageInfo"]["hasNextPage"]:
            break
        cursor = u["repositories"]["pageInfo"]["endCursor"]

    langs, recent = {}, []
    for r in nodes:
        if r["isFork"]:
            continue
        for e in r["languages"]["edges"]:
            l = langs.setdefault(e["node"]["name"], {"bytes": 0, "color": e["node"]["color"] or C["faint"]})
            l["bytes"] += e["size"]
        recent.append({"name": r["name"], "description": r["description"] or "",
                       "language": (r["primaryLanguage"] or {}).get("name"),
                       "stars": r["stargazerCount"], "pushed_at": r["pushedAt"][:10]})
    cal = first["contributionsCollection"]["contributionCalendar"]
    days = [[d["date"], d["contributionCount"]] for w in cal["weeks"] for d in w["contributionDays"]]
    return {
        "login": LOGIN, "created_at": first["createdAt"], "fetched_at": dt.date.today().isoformat(),
        "public_repos": first["repositories"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in nodes if not r["isFork"]),
        "followers": first["followers"]["totalCount"], "following": first["following"]["totalCount"],
        "languages": langs, "recent_repos": recent,
        "calendar": days, "total_contributions": cal["totalContributions"],
    }


# ----------------------------------------------------------------- helpers ---
def uptime(created_iso, today=None):
    start, today = dt.date.fromisoformat(created_iso[:10]), today or dt.date.today()
    months = (today.year - start.year) * 12 + today.month - start.month - (today.day < start.day)
    y, m = divmod(start.month - 1 + months, 12)
    anchor = dt.date(start.year + y, m + 1, min(start.day, 28))
    days = (today - anchor).days
    p = lambda n, w: f"{n} {w}{'' if n == 1 else 's'}"
    return f"{p(months // 12, 'year')}, {p(months % 12, 'month')}, {p(days, 'day')}"


def streaks(days):
    counts = [c for _, c in sorted(days)]
    longest = run = 0
    for c in counts:
        run = run + 1 if c else 0
        longest = max(longest, run)
    current, i = 0, len(counts) - 1
    if i >= 0 and counts[i] == 0:   # today not counted yet
        i -= 1
    while i >= 0 and counts[i]:
        current, i = current + 1, i - 1
    return current, longest, sum(1 for c in counts if c)


def t(x, y, size, spans, extra=""):
    inner = "".join(f'<tspan fill="{col}">{escape(s)}</tspan>' for s, col in spans)
    return (f'  <text x="{x:.1f}" y="{y:.1f}" font-family="{MONO}" xml:space="preserve" '
            f'font-size="{size}"{extra}>{inner}</text>')


# -------------------------------------------------------------------- card ---
def tone_color(digit):
    t = ((int(digit) + 0.5) / 10) ** 0.75
    return "#" + "".join(f"{round(a + (b - a) * t):02x}" for a, b in zip(PORTRAIT_DARK, PORTRAIT_LIGHT))


def tone_runs(row, tones):
    """Split a portrait row into (text, colour) runs of equal brightness."""
    if not tones:
        return [(row, C["text"])]
    runs, cur, col = [], "", None
    for i, ch in enumerate(row):
        d = tones[i] if i < len(tones) and tones[i].isdigit() else None
        c = tone_color(d) if d is not None else col
        if c != col and cur:
            runs.append((cur, col or C["text"]))
            cur = ""
        cur, col = cur + ch, c
    if cur:
        runs.append((cur, col or C["text"]))
    return runs


def render_card(s, ascii_rows, tone_rows=None):
    width = 1254
    art_fs, art_lh, art_x = 8, 9.6, 28
    info_x = art_x + max(map(len, ascii_rows)) * art_fs * CHAR + 34
    rule_chars = 50

    # ---- build the info column as (kind, payload) rows
    sections = []
    prof = [(k, v.replace("{uptime}", uptime(s["created_at"]))) for k, v in PROFILE]
    kw = max(len(k) for k, _ in prof) + 2
    sections.append((s["login"], [[(f"  {k + ':':<{kw}}", C["dim"]), (v, C["text"])] for k, v in prof]))

    langs = {k: v for k, v in s["languages"].items() if k not in HIDE_LANGUAGES}
    total = sum(v["bytes"] for v in langs.values()) or 1
    ranked = sorted(langs.items(), key=lambda kv: -kv[1]["bytes"])
    shown, rest = ranked[:TOP_LANGUAGES], ranked[TOP_LANGUAGES:]
    top_pct = shown[0][1]["bytes"] / total if shown else 1
    lw = max([len(k) for k, _ in shown] + [5]) + 1
    lang_rows = []
    for name, v in shown:
        pct = v["bytes"] / total
        n = max(0, round(pct / top_pct * 22))
        bar = "█" * n if n else "▏"
        lang_rows.append([(f"  {name:<{lw}}", C["dim"]), (bar, v["color"] or C["faint"]),
                          (f" {pct * 100:.1f}%" if pct >= 0.01 else " <1%", C["text"])])
    if rest:
        lang_rows.append([(f"  {'Other':<{lw}}", C["dim"]), ("▏", C["faint"]),
                          (" " + ", ".join(k for k, _ in rest[:4]), C["text"])])
    sections.append(("Languages", lang_rows))

    joined = dt.date.fromisoformat(s["created_at"][:10]).strftime("%b %Y")
    a, b = str(s["public_repos"]), str(s["followers"])
    col = max(len(a), len(b)) + 2
    sections.append(("GitHub", [
        [("  Repos:      ", C["dim"]), (f"{a:<{col}}", C["num"]), ("|  ", C["rule"]),
         ("Stars:      ", C["dim"]), (str(s["stars"]), C["num"])],
        [("  Followers:  ", C["dim"]), (f"{b:<{col}}", C["num"]), ("|  ", C["rule"]),
         ("Following:  ", C["dim"]), (str(s["following"]), C["num"])],
        [("  Joined:     ", C["dim"]), (joined, C["text"])],
    ]))

    by_name = {r["name"]: r for r in s["recent_repos"]}
    picks = [by_name[n] for n in PINNED_REPOS if n in by_name]
    if not picks:  # default: most recently pushed repos that have code
        picks = [r for r in s["recent_repos"] if r["name"] != s["login"] and r["language"]][:3]
    repo_rows = []
    for r in picks[:3]:
        name = r["name"].strip("-_")
        name = name if len(name) <= 24 else name[:23] + "…"
        when = dt.date.fromisoformat(r["pushed_at"]).strftime("%b %Y")
        desc = r["description"][:34] or f"{r['language']} · updated {when}"
        repo_rows.append([(f"  {name:<25}", C["repo"]), (" " + desc, C["dim"])])
    sections.append(("Top Repos", repo_rows))

    cur, longest, active = streaks(s["calendar"])
    tot = str(s["total_contributions"])
    sections.append(("Activity", [
        [("  Contributions: ", C["dim"]), (tot, C["green"]), ("  |  ", C["rule"]),
         ("Active days: ", C["dim"]), (str(active), C["num"])],
        [("  Streak:        ", C["dim"]), (f"{cur} day{'s' * (cur != 1)}", C["num"]), ("  |  ", C["rule"]),
         ("Longest: ", C["dim"]), (f"{longest} day{'s' * (longest != 1)}", C["num"])],
    ]))

    # ---- lay out vertically
    head_to_row, row_step, gap = 25, 20, 40
    info_h = sum(head_to_row + (len(rows) - 1) * row_step for _, rows in sections) + gap * (len(sections) - 1)
    art_h = (len(ascii_rows) - 1) * art_lh
    height = int(max(info_h, art_h) + 2 * 48)
    art_y = (height - art_h) / 2 + 3
    y = (height - info_h) / 2 + 6

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           f'  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="8" fill="{C["bg"]}" stroke="{C["border"]}"/>']
    tone_rows = tone_rows or []
    for i, row in enumerate(ascii_rows):
        tones = tone_rows[i] if i < len(tone_rows) else ""
        out.append(t(art_x, art_y + i * art_lh, art_fs, tone_runs(row, tones)))
    for si, (title, rows) in enumerate(sections):
        if si:
            y += gap
        label = f" {title} "
        out.append(t(info_x, y, 18, [("──────", C["rule"]), (label, C["head"]),
                                     ("─" * (rule_chars - 6 - len(label)), C["rule"])]))
        for ri, spans in enumerate(rows):
            y_row = y + head_to_row + ri * row_step
            out.append(t(info_x, y_row, 13 if title == "Top Repos" else 14, spans))
        y = y + head_to_row + (len(rows) - 1) * row_step
    out.append("</svg>")
    return "\n".join(out) + "\n"


# ----------------------------------------------------------------- heatmap ---
def render_heatmap(s):
    levels = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
    counts = dict(s["calendar"])
    end = max(dt.date.fromisoformat(d) for d in counts)
    start = end - dt.timedelta(days=(end.weekday() + 1) % 7) - dt.timedelta(weeks=52)  # a Sunday
    nz = sorted(c for c in counts.values() if c)
    q = lambda p: nz[min(len(nz) - 1, int(p * len(nz)))] if nz else 1
    cuts = [q(0.25), q(0.5), q(0.75)]  # quartiles of active days, like GitHub

    def level(c):
        if not c:
            return 0
        return 1 + sum(c > x for x in cuts)

    cell, step, left, top = 11, 14, 38, 58
    weeks = 53
    w, h = left + weeks * step + 16, top + 7 * step + 34
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
         f'font-family="-apple-system, \'Segoe UI\', Helvetica, Arial, sans-serif">',
         '  <defs><linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="#39d353"/>'
         '<stop offset="1" stop-color="#26a641"/></linearGradient>'
         '<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="1.2"/></filter></defs>',
         f'  <rect width="{w}" height="{h}" rx="6" fill="{C["bg"]}"/>',
         f'  <rect width="{w}" height="4" rx="2" fill="url(#g)"/>',
         f'  <text x="12" y="27" fill="#ffffff" font-size="13" font-weight="600">'
         f'{s["total_contributions"]} contributions in the last year</text>']
    last_month, last_label_wk = None, None
    for wk in range(weeks):
        for dow in range(7):
            d = start + dt.timedelta(weeks=wk, days=dow)
            if d > end:
                continue
            if dow == 0 and d.month != last_month:
                # label the first week of each month, skipping one that would crowd the previous label
                stub = wk == 0 and (d + dt.timedelta(weeks=3)).month != d.month  # partial first month
                if not stub and (last_label_wk is None or wk - last_label_wk >= 3):
                    o.append(f'  <text x="{left + wk * step}" y="{top - 8}" fill="{C["dim"]}" font-size="10">{d.strftime("%b")}</text>')
                    last_label_wk = wk
                last_month = d.month
            c = counts.get(d.isoformat(), 0)
            lv = level(c)
            x, y = left + wk * step, top + dow * step
            tip = f"<title>{c} contribution{'s' * (c != 1)} on {d.strftime('%a, %d %b %Y')}</title>"
            if lv:
                o.append(f'  <rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{levels[lv]}" opacity="0.35" filter="url(#glow)"/>')
            o.append(f'  <rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{levels[lv]}">{tip}</rect>')
    for dow, name in [(1, "Mon"), (3, "Wed"), (5, "Fri")]:
        o.append(f'  <text x="4" y="{top + dow * step + 9}" fill="{C["dim"]}" font-size="10">{name}</text>')
    lx, ly = w - 16 - 5 * step - 34, h - 12
    o.append(f'  <text x="{lx - 30}" y="{ly + 9}" fill="{C["dim"]}" font-size="10">Less</text>')
    for i, col in enumerate(levels):
        o.append(f'  <rect x="{lx + i * step}" y="{ly}" width="{cell}" height="{cell}" rx="2" fill="{col}"/>')
    o.append(f'  <text x="{lx + 5 * step + 4}" y="{ly + 9}" fill="{C["dim"]}" font-size="10">More</text>')
    o.append("</svg>")
    return "\n".join(o) + "\n"


def main():
    if "--offline" in sys.argv or not TOKEN:
        print("offline: rendering from", DATA.relative_to(ROOT))
        stats = json.loads(DATA.read_text())
    else:
        stats = fetch()
        DATA.write_text(json.dumps(stats, indent=1))
        print("fetched:", {k: stats[k] for k in ("public_repos", "stars", "followers", "total_contributions")})
    rows = (ROOT / "ascii.txt").read_text(encoding="utf-8").rstrip("\n").split("\n")
    tone_file = ROOT / "ascii_tone.txt"
    tones = tone_file.read_text(encoding="utf-8").rstrip("\n").split("\n") if tone_file.exists() else None
    (ROOT / "dark_mode.svg").write_text(render_card(stats, rows, tones), encoding="utf-8")
    (ROOT / "contributions.svg").write_text(render_heatmap(stats), encoding="utf-8")
    print("wrote dark_mode.svg, contributions.svg")


if __name__ == "__main__":
    main()
