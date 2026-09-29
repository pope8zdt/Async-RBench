#!/usr/bin/env python3
"""Public helper: read the deterministic listing event feed.

The event feed is a deterministic re-implementation of the environment's
listing stream. Events are appended over a simulated window; reveal them in
arrival order by polling with an increasing --tick and track how many you have
already seen with --since (a cursor = the highest seq you have consumed).

Events carry ``seq`` (delivery order) and ``at`` (simulated arrival time). A
call returns every event with ``since < seq <= tick``.

Usage:
  python3 scripts/read_events.py                          # show the whole feed
  python3 scripts/read_events.py --tick 1                # reveal the first event
  python3 scripts/read_events.py --tick 3 --since 1      # events 2..3
  python3 scripts/read_events.py --since 2               # everything after seq 2
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_FEED = HERE.parent / "event_feed"


def load_meta(feed_dir: Path) -> dict:
    path = feed_dir / "feed_meta.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def load_events(feed_dir: Path) -> list[dict]:
    events = []
    for line in (feed_dir / "feed.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    events.sort(key=lambda event: int(event["seq"]))
    return events


def main() -> int:
    parser = argparse.ArgumentParser(description="Read the deterministic listing event feed")
    parser.add_argument("--feed", default=str(DEFAULT_FEED))
    parser.add_argument("--tick", type=int, default=None,
                        help="reveal events with seq <= tick (default: all events)")
    parser.add_argument("--since", type=int, default=0,
                        help="only reveal events with seq > this cursor (default 0)")
    args = parser.parse_args()
    feed_dir = Path(args.feed)
    events = load_events(feed_dir)
    total = len(events)
    tick = args.tick if args.tick is not None else total
    selected = [event for event in events if args.since < int(event["seq"]) <= tick]
    for event in selected:
        print(json.dumps(event, ensure_ascii=False, sort_keys=True))
    meta = load_meta(feed_dir)
    print(
        f"[event_feed] total_events={total} window_minutes={meta.get('window_minutes')} "
        f"revealed_so_far={tick} delivered={len(selected)} (since {args.since})",
        file=__import__("sys").stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
