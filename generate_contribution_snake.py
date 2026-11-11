"""Render the repository owner's GitHub contribution calendar as an SVG snake."""

import json
import os
from itertools import accumulate, pairwise
from math import dist
from pathlib import Path
from random import Random
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


def randomized_route(columns, rng, from_right):
    """Cover the calendar once by mixing row and column sweeps of varying widths."""
    ordered_columns = list(range(columns - 1, -1, -1) if from_right else range(columns))
    ordered_rows = list(range(7))
    if rng.choice((True, False)):
        ordered_rows.reverse()

    route = []
    start = 0
    while start < columns:
        strip = ordered_columns[start:start + rng.choice((2, 3, 4))]
        if rng.choice((True, False)):
            for i, row in enumerate(ordered_rows):
                route.extend((column, row) for column in (strip if i % 2 == 0 else strip[::-1]))
        else:
            for i, column in enumerate(strip):
                route.extend((column, row) for row in (ordered_rows if i % 2 == 0 else ordered_rows[::-1]))

        if ordered_rows[0] != route[-1][1]:
            ordered_rows.reverse()
        start += len(strip)

    return route


def food_for_round(route, blank_cells, rng):
    # Spread pellets along the route so there is food to chase throughout the round.
    candidates = [cell for cell in route if cell in blank_cells]
    count = min(9, len(candidates))
    return {
        rng.choice(candidates[i * len(candidates) // count:(i + 1) * len(candidates) // count])
        for i in range(count)
    }


def eating_animation(cell, timings, visible_rounds, duration):
    """Show a square at the start of its round and hide it when the head reaches it."""
    initial = int(0 in visible_rounds)
    events = [(0, initial)]
    for index, (start, visits) in enumerate(timings):
        if index not in visible_rounds:
            continue
        if index:
            events.append((start, 1))
        events.append((visits[cell], 0))
    events.append((1, initial))
    values = ";".join(str(value) for _, value in events)
    times = ";".join(f"{time:.8f}" for time, _ in events)
    return (
        f'<animate attributeName="opacity" values="{values}" keyTimes="{times}" '
        f'calcMode="discrete" dur="{duration}s" repeatCount="indefinite"/>'
    )


def render(weeks, rng=None):
    if not weeks or len(weeks) > 54:
        raise ValueError("Unexpected contribution calendar width")

    rng = rng if rng is not None else Random()
    rounds = range(3)
    size = 18
    offset = 10
    duration = 24 * len(rounds)
    width = 1120
    x0 = (width - size * (len(weeks) - 1)) // 2
    y0 = 59
    levels = {
        (column, day["weekday"]): LEVELS.index(day["contributionLevel"])
        for column, week in enumerate(weeks)
        for day in week["contributionDays"]
    }

    def center(cell):
        column, row = cell
        return x0 + size * column, y0 + size * row

    blank_cells = {cell for cell, level in levels.items() if level == 0}
    pellets_by_round = []
    paths = []
    rounds_by_distance = []
    length = 0
    for index in rounds:
        from_right = index % 2 == 0
        route = randomized_route(len(weeks), rng, from_right)
        pellets_by_round.append(food_for_round(route, blank_cells, rng))
        entry, exit = (width + 120, -120) if from_right else (-120, width + 120)
        centers = [center(cell) for cell in route]
        points = [(entry, centers[0][1]), *centers, (exit, centers[-1][1])]
        segments = (dist(a, b) for a, b in pairwise(points))
        distances = list(accumulate(segments, initial=length))
        rounds_by_distance.append((length, dict(zip(route, distances[1:]))))
        length = distances[-1]
        paths.append("M" + " L".join(f"{x} {y}" for x, y in points))

    timings = [
        (start / length, {cell: value / length for cell, value in visits.items()})
        for start, visits in rounds_by_distance
    ]

    grid = []
    active = []
    static_active = []
    for cell, level in sorted(levels.items()):
        x, y = center(cell)
        rect = f'<rect x="{x - 6}" y="{y - 6}" width="12" height="12" rx="2"'
        grid.append(rect + ' class="level-0"/>')
        if level:
            rect += f' class="level-{level}"'
            static_active.append(rect + '/>')
            active.append(rect + '>' + eating_animation(cell, timings, rounds, duration) + '</rect>')

    for cell in sorted(set().union(*pellets_by_round)):
        visible_rounds = [index for index in rounds if cell in pellets_by_round[index]]
        x, y = center(cell)
        active.append(
            f'<circle cx="{x}" cy="{y}" r="4" fill="var(--food)" opacity="{int(0 in visible_rounds)}">'
            + eating_animation(cell, timings, visible_rounds, duration) + '</circle>'
        )

    snake = []
    for index in reversed(range(8)):
        start = duration * offset * index / length
        head = '<circle cx="2.6" cy="-2.7" r="1.1"/><circle cx="2.6" cy="2.7" r="1.1"/>' if index == 0 else ''
        snake.append(
            f'<g><rect x="-6" y="-5.5" width="12" height="11" rx="{4 if index == 0 else 3}" '
            f'fill="var(--snake)" opacity="{1 - .075 * index:.3f}"/>{head}'
            f'<animateMotion rotate="auto" dur="{duration}s" begin="{start:.4f}s" repeatCount="indefinite">'
            '<mpath href="#snake-route"/></animateMotion></g>'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="221" viewBox="0 0 {width} 221" role="img" aria-labelledby="title">
  <title id="title">Snake eating contribution squares and food that respawns each round</title>
  <style>
    :root {{ --surface: #0d1714; --header: #12251c; --edge: #345246; --text: #c1d5c8; --snake: #b4fa83; --food: #ffd26d;
      --zero: #1c2e27; --one: #296747; --two: #32936a; --three: #5fc786; --four: #9af2a3; }}
    @media (prefers-color-scheme: light) {{ :root {{ --surface: #f4f9f3; --header: #e8f1e8; --edge: #90ad9a;
      --text: #33594b; --snake: #286719; --food: #a15a00; --zero: #dce9dd; --one: #a8d5ae; --two: #70b881; --three: #3b985d; --four: #226c3d; }} }}
    .level-0 {{ fill: var(--zero); }} .level-1 {{ fill: var(--one); }} .level-2 {{ fill: var(--two); }}
    .level-3 {{ fill: var(--three); }} .level-4 {{ fill: var(--four); }}
    .still {{ display: none; }}
    @media (prefers-reduced-motion: reduce) {{ .animated {{ display: none; }} .still {{ display: inline; }} }}
  </style>
  <defs>
    <clipPath id="frame"><rect x="1" y="1" width="1118" height="219" rx="17"/></clipPath>
    <path id="snake-route" d="{' '.join(paths)}"/>
  </defs>
  <g clip-path="url(#frame)">
    <rect width="1120" height="221" fill="var(--surface)"/>
    <rect width="1120" height="35" fill="var(--header)"/>
    <path d="M0 35.5H1120 M0 188.5H1120" stroke="var(--edge)"/>
    <g font-family="ui-monospace, Consolas, monospace" font-size="15" fill="var(--text)" letter-spacing="1">
      <text x="24" y="23">$ github activity</text>
      <text x="1096" y="23" text-anchor="end">LAST 12 MONTHS</text>
      <text class="animated" x="40" y="210">FOOD RESPAWNS EACH ROUND</text>
      <text class="still" x="24" y="210">PUBLIC CONTRIBUTION CALENDAR</text>
      <text x="952" y="210" text-anchor="end">LESS</text>
      <text x="1096" y="210" text-anchor="end">MORE</text>
    </g>
    <circle class="animated" cx="27" cy="205" r="4" fill="var(--food)"/>
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
