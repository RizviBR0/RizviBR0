"""Refresh the profile cards from GitHub's public repositories and calendar."""

import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen


USER = "RizviBR0"
ASSETS = Path(__file__).resolve().parents[1] / "assets"
DAY = timedelta(days=1)


def fetch(url, headers=None):
    request = Request(url, headers={"User-Agent": "RizviBR0-profile", **(headers or {})})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def public_repositories():
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    repos = {}
    page = 1
    while True:
        url = f"https://api.github.com/users/{USER}/repos?type=owner&per_page=100&page={page}"
        batch = json.loads(fetch(url, headers))
        repos.update((repo["id"], repo["language"]) for repo in batch if not repo["fork"])
        if len(batch) < 100:
            return repos.values()
        page += 1


class Calendar(HTMLParser):
    """Join the public calendar's dated cells to their accessible count labels."""

    def __init__(self):
        super().__init__()
        self.dates = {}
        self.counts = {}
        self.tooltip = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "td" and "data-date" in attrs:
            self.dates[attrs["id"]] = attrs["data-date"]
        if tag == "tool-tip":
            self.tooltip = attrs.get("for")

    def handle_data(self, data):
        if self.tooltip:
            match = re.match(r"\s*(No|[\d,]+) contributions? on ", data)
            if match:
                raw = match[1]
                self.counts[self.tooltip] = 0 if raw == "No" else int(raw.replace(",", ""))

    def handle_endtag(self, tag):
        if tag == "tool-tip":
            self.tooltip = None


def contributions(end):
    dates = [end - i * DAY for i in reversed(range(84))]
    by_date = {}
    # GitHub serves a calendar year per dated request, even across year boundaries.
    for year in range(dates[0].year, end.year + 1):
        url = f"https://github.com/users/{USER}/contributions?from={year}-01-01&to={year}-12-31"
        calendar = Calendar()
        calendar.feed(fetch(url, {"Accept-Language": "en-US"}))
        by_date.update((calendar.dates[key], count) for key, count in calendar.counts.items()
                       if key in calendar.dates)
    # Missing data must fail the refresh so the last successful cards stay visible.
    return [by_date[date.isoformat()] for date in dates]


def card(title, description, body):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="372" height="196" viewBox="0 0 372 196" role="img" aria-labelledby="title desc">
  <title id="title">{escape(title)}</title>
  <desc id="desc">{escape(description)}</desc>
  <style>
    text {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #f2f5ff }}
    .muted {{ fill: #b2bfd6; font-size: 13px }}
  </style>
  <rect x=".5" y=".5" width="371" height="195" rx="12" fill="#0d1628" stroke="#35435e"/>
  <text x="20" y="34" font-size="20" font-weight="650">{escape(title)}</text>
{body}
</svg>
'''


def activity_card(days, end):
    start = end - (len(days) - 1) * DAY
    weeks = [sum(days[i:i + 7]) for i in range(0, len(days), 7)]
    peak = max(max(weeks), 1)
    streak = longest = 0
    for count in days:
        streak = streak + 1 if count else 0
        longest = max(longest, streak)
    bars = []
    for index, count in enumerate(weeks):
        height = 71 * count / peak
        bars.append(f'  <rect x="{22 + index * 28}" y="{153 - height:.1f}" '
                    f'width="19" height="{height:.1f}" rx="3" fill="url(#bar)">'
                    f'<title>Week of {start + 7 * index * DAY}: {count}</title></rect>')
    total = sum(weeks)
    detail = f"{total} contributions from {start} to {end}. Weekly totals: {', '.join(map(str, weeks))}."
    body = f'''  <defs>
    <linearGradient id="bar" x2="0" y2="1">
      <stop stop-color="#93b4ff"/><stop offset="1" stop-color="#8883f1"/>
    </linearGradient>
  </defs>
  <text x="352" y="36" text-anchor="end" font-size="28" font-weight="700">{total:,}</text>
  <text x="20" y="56" class="muted">12 weeks · longest streak {longest} {"day" if longest == 1 else "days"}</text>
  <path d="M20 82h332 M20 118h332 M20 154h332" stroke="#29354c" fill="none"/>
{chr(10).join(bars)}
  <text x="20" y="179" class="muted">{start:%d %b %Y}</text>
  <text x="352" y="179" text-anchor="end" class="muted">{end:%d %b %Y}</text>'''
    return card("Contributions", detail, body)


def language_card(repos):
    counts = Counter(name for name in repos if name)
    leaders = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:4]
    rows = []
    for index, (name, count) in enumerate(leaders):
        y = 73 + index * 24
        length = 173 * count / leaders[0][1]
        rows.append(f'  <text x="20" y="{y + 4}" font-size="14">{escape(name)}</text>\n'
                    f'  <rect x="138" y="{y - 4}" width="173" height="8" rx="4" fill="#29354c"/>\n'
                    f'  <rect x="138" y="{y - 4}" width="{length:.1f}" height="8" rx="4" fill="#9aabff"/>\n'
                    f'  <text x="352" y="{y + 4}" text-anchor="end" font-size="14">{count}</text>')
    scope = f"{len(repos)} public repositories · forks excluded"
    detail = ", ".join(f"{name}: {count}" for name, count in leaders)
    body = f'''  <text x="20" y="54" class="muted">Top primary languages by repository count</text>
{chr(10).join(rows)}
  <text x="20" y="179" class="muted">{scope}</text>'''
    return card("Repository languages", f"{scope}. {detail}.", body)


if __name__ == "__main__":
    today = datetime.now(timezone.utc).date()
    activity = activity_card(contributions(today), today)
    languages = language_card(public_repositories())
    (ASSETS / "github-activity.svg").write_text(activity, encoding="utf-8", newline="\n")
    (ASSETS / "github-languages.svg").write_text(languages, encoding="utf-8", newline="\n")
