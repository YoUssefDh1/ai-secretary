"""
Test tool for the Google Calendar integration (Phase 2).

Usage (use `py`, not `python`):

    py calendar_cli.py auth                         # log in / verify access
    py calendar_cli.py slots 2026-06-18             # free slots that day
    py calendar_cli.py book "Youssef" "teeth cleaning" 2026-06-18 14:00
    py calendar_cli.py list                         # upcoming appointments
    py calendar_cli.py find "Youssef"               # find someone's bookings
    py calendar_cli.py cancel <event_id>            # cancel by id (from list/find)
"""

import datetime as dt
import sys

from app.calendar_service import CalendarService, SlotUnavailable, TZ


def _parse_dt(date_str: str, time_str: str) -> dt.datetime:
    naive = dt.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    return naive.replace(tzinfo=TZ)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1

    cmd = argv[0]
    cal = CalendarService()

    if cmd == "auth":
        print("Authenticated OK. Calendar access is working.")

    elif cmd == "slots":
        date = dt.date.fromisoformat(argv[1])
        slots = cal.free_slots(date)
        if not slots:
            print(f"No free slots on {date:%A %d %B} (closed or fully booked).")
        else:
            print(f"Free slots on {date:%A %d %B}:")
            for s in slots:
                print(f"  {s:%H:%M}")

    elif cmd == "book":
        name, service, date_str, time_str = argv[1], argv[2], argv[3], argv[4]
        start = _parse_dt(date_str, time_str)
        try:
            ev = cal.book(name, service, start)
            print(f"Booked: {ev['summary']} on {start:%A %d %B at %H:%M}")
            print(f"  event id: {ev['id']}")
        except SlotUnavailable as e:
            print(f"Cannot book: {e}")

    elif cmd == "list":
        events = cal.upcoming()
        if not events:
            print("No upcoming appointments.")
        for ev in events:
            start = ev["start"].get("dateTime", ev["start"].get("date"))
            print(f"  {start}  {ev.get('summary', '(no title)')}  [{ev['id']}]")

    elif cmd == "find":
        events = cal.find_by_name(argv[1])
        if not events:
            print(f"No appointments found for '{argv[1]}'.")
        for ev in events:
            start = ev["start"].get("dateTime", ev["start"].get("date"))
            print(f"  {start}  {ev.get('summary', '(no title)')}  [{ev['id']}]")

    elif cmd == "cancel":
        cal.cancel(argv[1])
        print("Cancelled.")

    else:
        print(__doc__)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
