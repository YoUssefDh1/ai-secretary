"""
Terminal interface for the AI receptionist.

Default mode is the full booking-capable receptionist (talks AND manages the
real Google Calendar):

    python cli.py

Other modes:
    python cli.py --raw           # plain conversation only, no calendar
    python cli.py --raw --show-intent

Commands while chatting:
    /reset   start a fresh conversation
    /state   (default mode) show the collected booking details — handy for debugging
    /quit    exit
"""

import argparse

from app import config

CYAN = "\033[36m"
DIM = "\033[2m"
RESET = "\033[0m"
NAME = config.BUSINESS["receptionist_name"]


def run_raw(show_intent: bool) -> None:
    from app.brain import Receptionist, detect_intent

    bot = Receptionist()
    print(f"{CYAN}{NAME}:{RESET} ", end="")
    bot.greeting()
    while True:
        try:
            user = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            return
        if not user:
            continue
        if user.lower() in ("/quit", "/exit"):
            print("Goodbye!")
            return
        if user.lower() == "/reset":
            bot = Receptionist()
            print(f"\n{DIM}--- new conversation ---{RESET}\n")
            print(f"{CYAN}{NAME}:{RESET} ", end="")
            bot.greeting()
            continue
        if show_intent:
            print(f"{DIM}[detected intent: {detect_intent(user)}]{RESET}")
        print(f"\n{CYAN}{NAME}:{RESET} ", end="")
        bot.reply(user)


def run_booking() -> None:
    from app.dialog import BookingDialog

    print(f"{DIM}Connecting to Google Calendar...{RESET}")
    bot = BookingDialog()
    print(f"{CYAN}{NAME}:{RESET} {bot.greeting()}")
    while True:
        try:
            user = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            return
        if not user:
            continue
        if user.lower() in ("/quit", "/exit"):
            print("Goodbye!")
            return
        if user.lower() == "/reset":
            bot = BookingDialog(calendar=bot.calendar)
            print(f"\n{DIM}--- new conversation ---{RESET}\n")
            print(f"{CYAN}{NAME}:{RESET} {bot.greeting()}")
            continue
        if user.lower() == "/state":
            print(f"{DIM}{bot.state}{RESET}")
            continue
        print(f"{CYAN}{NAME}:{RESET} {bot.respond(user)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="AI receptionist")
    parser.add_argument("--raw", action="store_true",
                        help="plain conversation only, no calendar")
    parser.add_argument("--show-intent", action="store_true",
                        help="(raw mode) print detected intent each turn")
    args = parser.parse_args()

    print(f"{DIM}Model: {config.CHAT_MODEL} | Business: {config.BUSINESS['name']}")
    print(f"Type /reset to restart, /quit to exit.{RESET}\n")

    if args.raw:
        run_raw(args.show_intent)
    else:
        run_booking()


if __name__ == "__main__":
    main()
