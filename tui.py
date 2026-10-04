import curses
import sys
import time

from timer import Phase, SessionEvent, SessionSettings, WorkSession, format_time


class TerminalTimer:
    labels = (
        "Hours", "Minutes", "Seconds",
        "Short break every (work min)", "Short break length (min)",
        "Long break every (work min)", "Long break length (min)",
    )

    def __init__(self) -> None:
        self.timer = WorkSession(SessionSettings())
        self.values = ["2", "0", "0", "15", "5", "60", "15"]
        self.breaks_enabled = True
        self.selected = 0
        self.replace_value = True
        self.started = False
        self.message = "Set a duration, then press S to start."

    def read_settings(self) -> SessionSettings:
        count = 7 if self.breaks_enabled else 3
        try:
            values = [int(value) for value in self.values[:count]]
        except ValueError:
            raise ValueError("Enter whole numbers in all enabled fields.") from None
        hours, minutes, seconds = values[:3]
        if not (0 <= hours <= 99 and 0 <= minutes <= 59 and 0 <= seconds <= 59):
            raise ValueError("Use hours 0-99 and minutes/seconds 0-59.")
        total = hours * 3600 + minutes * 60 + seconds
        if total == 0:
            raise ValueError("Enter a duration greater than zero.")
        if not self.breaks_enabled:
            return SessionSettings(total_work=total, breaks_enabled=False)
        if any(not 1 <= value <= 5940 for value in values[3:]):
            raise ValueError("Break settings must be between 1 and 5940 minutes.")
        return SessionSettings(
            total_work=total, short_interval=values[3] * 60,
            short_break=values[4] * 60, long_interval=values[5] * 60,
            long_break=values[6] * 60,
        )

    def handle_key(self, key: int, now: float) -> list[SessionEvent]:
        events: list[SessionEvent] = []
        if key in (ord("s"), ord("S"), ord(" ")):
            if self.timer.running:
                events = self.timer.pause(now)
            else:
                if not self.started:
                    try:
                        settings = self.read_settings()
                    except ValueError as error:
                        self.message = str(error)
                        return []
                    self.timer.reset(settings)
                    self.started = True
                self.timer.start(now)
            self.message = ""
        elif key in (ord("p"), ord("P")):
            events = self.timer.pause(now)
        elif key in (ord("r"), ord("R")):
            self.timer.reset()
            self.started = False
            self.message = "Reset. Edit settings or press S to start."
        elif not self.started:
            count = 7 if self.breaks_enabled else 3
            if key in (curses.KEY_DOWN, ord("\t"), curses.KEY_UP, curses.KEY_BTAB):
                direction = -1 if key in (curses.KEY_UP, curses.KEY_BTAB) else 1
                self.selected = (self.selected + direction) % count
                self.replace_value = True
            elif key in (ord("b"), ord("B")):
                self.breaks_enabled = not self.breaks_enabled
                if not self.breaks_enabled:
                    self.selected = min(self.selected, 2)
                self.replace_value = True
            elif ord("0") <= key <= ord("9"):
                value = "" if self.replace_value else self.values[self.selected]
                self.values[self.selected] = (value + chr(key))[:4]
                self.replace_value = False
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                self.values[self.selected] = self.values[self.selected][:-1]
                self.replace_value = False
        return events

    def render(self, screen: curses.window) -> None:
        screen.erase()
        height, width = screen.getmaxyx()
        state = self.timer.phase.value
        if self.timer.phase != Phase.FINISHED:
            state += " - running" if self.timer.running else " - paused" if self.started else " - ready"
        lines = [
            "Countdown Timer",
            state,
            f"Work remaining:  {format_time(self.timer.work_remaining)}",
            f"Notes remaining: {format_time(self.timer.break_remaining)}",
            f"Notes elapsed:   {format_time(self.timer.break_elapsed, round_up=False)}",
            f"Total note time: {format_time(self.timer.total_break_elapsed, round_up=False)}",
            "",
            "Settings (locked until Reset)" if self.started else "Settings (Up/Down or Tab; type digits to replace)",
        ]
        for index, (label, value) in enumerate(zip(self.labels, self.values)):
            marker = ">" if index == self.selected and not self.started else " "
            disabled = " (off)" if index >= 3 and not self.breaks_enabled else ""
            lines.append(f"{marker} {label}: {value}{disabled}")
        lines.extend([
            f"Scheduled note breaks: {'on' if self.breaks_enabled else 'off'} [B]",
            "",
            "S/Space: start/pause/resume  P: pause  R: reset  Q: quit",
            "Alerts use the terminal bell (depends on terminal settings).",
            self.message,
        ])
        if height < len(lines) + 1 or width < 60:
            lines = [
                "Resize terminal to at least 60x21.",
                state,
                f"Work: {format_time(self.timer.work_remaining)}",
                f"Notes: {format_time(self.timer.break_remaining)}",
                "Space: start/pause  R: reset  Q: quit",
                self.message,
            ]
        # Leave the last column unused: curses errors when writing bottom-right.
        for row, text in enumerate(lines[:height]):
            if width > 1:
                screen.addnstr(row, 0, text, width - 1)
        screen.refresh()

    def run(self, screen: curses.window) -> None:
        screen.timeout(100)
        pending_bell: float | None = None
        while True:
            now = time.monotonic()
            events = self.timer.tick(now)
            if self.timer.phase == Phase.FINISHED:
                self.started = False
                self.message = "Session complete! Press S to restart or R to reset."
            self.render(screen)
            key = screen.getch()
            now = time.monotonic()
            if key in (ord("q"), ord("Q"), 27):
                return
            events.extend(self.handle_key(key, now))
            if key in (ord("r"), ord("R")):
                pending_bell = None
                events = []
            if pending_bell is not None and now >= pending_bell:
                curses.beep()
                pending_bell = None
            for event in events:
                if event == SessionEvent.COMPLETED and SessionEvent.BREAK_ENDED in events:
                    continue
                curses.beep()
                if event == SessionEvent.BREAK_ENDED:
                    pending_bell = now + 0.25


def main() -> None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("Terminal mode requires an interactive terminal (stdin and stdout).",
              file=sys.stderr)
        raise SystemExit(1)
    try:
        curses.wrapper(TerminalTimer().run)
    except curses.error as error:
        print(f"Cannot run the terminal timer: {error}. Check TERM and terminal support.",
              file=sys.stderr)
        raise SystemExit(1) from error
