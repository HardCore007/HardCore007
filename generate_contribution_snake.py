"""Render the repository owner's GitHub contribution calendar as an SVG snake."""

import json
import os
from itertools import accumulate, pairwise
from math import dist
from pathlib import Path
from urllib.request import Request, urlopen


LEVELS = ("NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE")
QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks { contributionDays { weekday contributionLevel } }
      }
    }
  }
}
"""


def fetch_weeks():
    request = Request(
        os.environ["GITHUB_GRAPHQL_URL"],
        data=json.dumps({"query": QUERY, "variables": {"login": os.environ["GITHUB_REPOSITORY_OWNER"]}}).encode(),
        headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=30) as response:
        result = json.load(response)
    if result.get("errors") or not result.get("data", {}).get("user"):
        raise RuntimeError(f"Could not read the GitHub contribution calendar: {result.get('errors', [])}")
    return result["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]


def render(weeks):
    if not weeks or len(weeks) > 54:
        raise ValueError("Unexpected contribution calendar width")

    size = 18
    offset = 10
    duration = 30
    width = 1120
    x0 = (width - size * (len(weeks) - 1)) // 2
    y0 = 59
    levels = {
        (column, day["weekday"]): LEVELS.index(day["contributionLevel"])
        for column, week in enumerate(weeks)
        for day in week["contributionDays"]
    }

    # Start with the most recent week and alternate up and down the columns.
    route = [
        (column, row)
        for i, column in enumerate(reversed(range(len(weeks))))
        for row in (range(6, -1, -1) if i % 2 == 0 else range(7))
    ]
    centers = [(x0 + size * column, y0 + size * row) for column, row in route]
    points = [(width + 120, centers[0][1]), *centers, (-120, centers[-1][1])]
    distances = list(accumulate(dist(a, b) for a, b in pairwise(points)))
    length = distances[-1]
    path = "M" + " L".join(f"{x} {y}" for x, y in points)

    grid = []
    active = []
    for cell, (x, y), travel in zip(route, centers, distances):
        if cell not in levels:
            continue
        rect = f'<rect x="{x - 6}" y="{y - 6}" width="12" height="12" rx="2"'
        grid.append(rect + ' class="level-0"/>')
        if levels[cell]:
            active.append(
                rect + f' class="level-{levels[cell]}"><animate class="motion" attributeName="opacity" '
                f'values="1;0;0" keyTimes="0;{travel / length:.6f};1" calcMode="discrete" '
                f'dur="{duration}s" repeatCount="indefinite"/></rect>'
            )

    snake = []
    for index in reversed(range(8)):
        start = duration * offset * index / length
        head = '<circle cx="2.6" cy="-2.7" r="1.1"/><circle cx="2.6" cy="2.7" r="1.1"/>' if index == 0 else ''
        snake.append(
            f'<g><rect x="-6" y="-5.5" width="12" height="11" rx="{4 if index == 0 else 3}" '
            f'fill="var(--snake)" opacity="{1 - .075 * index:.3f}"/>{head}'
            f'<animateMotion path="{path}" rotate="auto" dur="{duration}s" begin="{start:.4f}s" repeatCount="indefinite"/></g>'
        )

    static_active = [shape.split("><animate", 1)[0] + "/>" for shape in active]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="221" viewBox="0 0 {width} 221" role="img" aria-labelledby="title">
  <title id="title">Animated snake eating squares from the GitHub contribution calendar</title>
  <style>
    :root {{ --surface: #0d1714; --header: #12251c; --edge: #345246; --text: #c1d5c8; --snake: #b4fa83;
      --zero: #1c2e27; --one: #296747; --two: #32936a; --three: #5fc786; --four: #9af2a3; }}
    @media (prefers-color-scheme: light) {{ :root {{ --surface: #f4f9f3; --header: #e8f1e8; --edge: #90ad9a;
      --text: #33594b; --snake: #286719; --zero: #dce9dd; --one: #a8d5ae; --two: #70b881; --three: #3b985d; --four: #226c3d; }} }}
    .level-0 {{ fill: var(--zero); }} .level-1 {{ fill: var(--one); }} .level-2 {{ fill: var(--two); }}
    .level-3 {{ fill: var(--three); }} .level-4 {{ fill: var(--four); }}
    .still {{ display: none; }}
    @media (prefers-reduced-motion: reduce) {{ .animated {{ display: none; }} .still {{ display: inline; }} }}
  </style>
  <defs><clipPath id="frame"><rect x="1" y="1" width="1118" height="219" rx="17"/></clipPath></defs>
  <g clip-path="url(#frame)">
    <rect width="1120" height="221" fill="var(--surface)"/>
    <rect width="1120" height="35" fill="var(--header)"/>
    <path d="M0 35.5H1120 M0 188.5H1120" stroke="var(--edge)"/>
    <g font-family="ui-monospace, Consolas, monospace" font-size="15" fill="var(--text)" letter-spacing="1">
      <text x="24" y="23">$ github activity</text>
      <text x="1096" y="23" text-anchor="end">LAST 12 MONTHS</text>
      <text x="24" y="210">NEWEST WEEK → OLDEST WEEK</text>
      <text x="952" y="210" text-anchor="end">LESS</text>
      <text x="1096" y="210" text-anchor="end">MORE</text>
    </g>
    {' '.join(f'<rect x="{966 + 15 * n}" y="198" width="11" height="11" rx="2" class="level-{n}"/>' for n in range(5))}
    {' '.join(grid)}
    <g class="still">{' '.join(static_active)}</g>
    <g class="animated">{' '.join(active)}
      <svg x="0" y="37" width="1120" height="150" viewBox="0 37 1120 150" overflow="hidden">
        {' '.join(snake)}
      </svg>
    </g>
  </g>
  <rect x="1" y="1" width="1118" height="219" rx="17" fill="none" stroke="var(--edge)" stroke-width="2"/>
</svg>
'''


if __name__ == "__main__":
    Path("contribution-snake.svg").write_text(render(fetch_weeks()), encoding="utf-8")
