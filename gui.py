import sys
import time
import tkinter as tk
from tkinter import ttk

from sounds import SoundPlayer
from timer import Phase, SessionEvent, SessionSettings, WorkSession, format_time


class TimerWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.timer = WorkSession(SessionSettings())
        self.started = False
        self.after_id: str | None = None
        self.duration = [tk.StringVar(value=value) for value in ("2", "0", "0")]
        self.breaks_enabled = tk.BooleanVar(value=True)
        self.break_settings = [
            tk.StringVar(value=value) for value in ("15", "5", "60", "15")
        ]
        self.display = tk.StringVar(value="02:00:00")
        self.break_display = tk.StringVar(value="00:00:00")
        self.break_progress = tk.StringVar(value="Notes elapsed: 00:00:00 | Total: 00:00:00")
        self.status = tk.StringVar(value="Set a duration, then press Start.")
        self.sound_status = tk.StringVar()
        self.sounds = SoundPlayer(root, self.sound_status.set)

        root.title("Countdown Timer")
        root.resizable(False, False)
        frame = ttk.Frame(root, padding=24)
        frame.grid()
        ttk.Label(frame, text="Work time remaining").grid(
            row=0, column=0, columnspan=3
        )
        ttk.Label(frame, textvariable=self.display, font=("Helvetica", 48)).grid(
            row=1, column=0, columnspan=3, pady=(0, 8)
        )
        ttk.Label(frame, text="Note time remaining").grid(
            row=2, column=0, columnspan=3
        )
        ttk.Label(frame, textvariable=self.break_display, font=("Helvetica", 32)).grid(
            row=3, column=0, columnspan=3
        )
        ttk.Label(frame, textvariable=self.break_progress).grid(
            row=4, column=0, columnspan=3, pady=(0, 16)
        )
        self.inputs: list[ttk.Spinbox] = []
        for column, (label, variable, limit) in enumerate(
            zip(("Hours", "Minutes", "Seconds"), self.duration, (99, 59, 59))
        ):
            ttk.Label(frame, text=label).grid(row=5, column=column)
            entry = ttk.Spinbox(
                frame, from_=0, to=limit, width=6, textvariable=variable
            )
            entry.grid(row=6, column=column, padx=6, pady=(4, 16))
            self.inputs.append(entry)

        self.break_toggle = ttk.Checkbutton(
            frame, text="Scheduled note breaks", variable=self.breaks_enabled,
            command=self.configure_inputs,
        )
        self.break_toggle.grid(row=7, column=0, columnspan=3, sticky="w")
        self.break_inputs: list[ttk.Spinbox] = []
        for row, (label, variable) in enumerate(
            zip(
                ("Short break every (work min)", "Short break length (min)",
                 "Long break every (work min)", "Long break length (min)"),
                self.break_settings,
            ),
            start=8,
        ):
            ttk.Label(frame, text=label).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=3
            )
            entry = ttk.Spinbox(frame, from_=1, to=5940, width=6, textvariable=variable)
            entry.grid(row=row, column=2, padx=6, pady=3)
            self.break_inputs.append(entry)

        self.start_button = ttk.Button(frame, text="Start", command=self.start)
        self.start_button.grid(row=12, column=0, padx=4, pady=(16, 0))
        self.pause_button = ttk.Button(
            frame, text="Pause", command=self.pause, state="disabled"
        )
        self.pause_button.grid(row=12, column=1, padx=4, pady=(16, 0))
        ttk.Button(frame, text="Reset", command=self.reset).grid(
            row=12, column=2, padx=4, pady=(16, 0)
        )
        ttk.Label(frame, textvariable=self.status, wraplength=330).grid(
            row=13, column=0, columnspan=3, pady=(16, 0)
        )
        ttk.Label(frame, textvariable=self.sound_status, wraplength=330).grid(
            row=14, column=0, columnspan=3, pady=(4, 0)
        )
        root.protocol("WM_DELETE_WINDOW", self.close)

    def read_duration(self) -> int | None:
        try:
            hours, minutes, seconds = (int(value.get()) for value in self.duration)
        except ValueError:
            self.status.set("Enter whole numbers for hours, minutes, and seconds.")
            return None
        if not (0 <= hours <= 99 and 0 <= minutes <= 59 and 0 <= seconds <= 59):
            self.status.set("Use hours 0-99 and minutes/seconds 0-59.")
            return None
        total = hours * 3600 + minutes * 60 + seconds
        if total == 0:
            self.status.set("Enter a duration greater than zero.")
            return None
        return total

    def read_settings(self) -> SessionSettings | None:
        seconds = self.read_duration()
        if seconds is None:
            return None
        if not self.breaks_enabled.get():
            return SessionSettings(total_work=seconds, breaks_enabled=False)
        try:
            values = [int(variable.get()) for variable in self.break_settings]
        except ValueError:
            self.status.set("Enter whole numbers for the break settings.")
            return None
        if any(not 1 <= value <= 5940 for value in values):
            self.status.set("Break settings must be between 1 and 5940 minutes.")
            return None
        return SessionSettings(
            total_work=seconds, short_interval=values[0] * 60,
            short_break=values[1] * 60, long_interval=values[2] * 60,
            long_break=values[3] * 60,
        )

    def configure_inputs(self) -> None:
        for entry in self.inputs:
            entry.configure(state="disabled" if self.started else "normal")
        self.break_toggle.configure(state="disabled" if self.started else "normal")
        for entry in self.break_inputs:
            entry.configure(
                state="normal" if not self.started and self.breaks_enabled.get()
                else "disabled"
            )

    def start(self) -> None:
        if self.timer.running:
            return
        if not self.started:
            settings = self.read_settings()
            if settings is None:
                return
            self.timer.reset(settings)
            self.started = True
            self.sound_status.set("")
        self.timer.start(time.monotonic())
        self.configure_inputs()
        self.start_button.configure(state="disabled")
        self.pause_button.configure(state="normal")
        self.status.set(self.timer.phase.value)
        self.update()

    def pause(self) -> None:
        if not self.timer.running:
            return
        events = self.timer.pause(time.monotonic())
        self.cancel_update()
        self.render()
        self.play_events(events)
        if self.timer.phase == Phase.FINISHED:
            self.finish()
            return
        self.start_button.configure(text="Resume", state="normal")
        self.pause_button.configure(state="disabled")
        self.status.set(f"{self.timer.phase.value} paused. Resume, or Reset to edit.")

    def reset(self) -> None:
        self.cancel_update()
        self.timer.reset()
        self.started = False
        self.configure_inputs()
        self.sounds.close()
        self.sound_status.set("")
        self.start_button.configure(text="Start", state="normal")
        self.pause_button.configure(state="disabled")
        self.render()
        self.status.set("Set a duration, then press Start.")

    def render(self) -> None:
        self.display.set(format_time(self.timer.work_remaining))
        self.break_display.set(format_time(self.timer.break_remaining))
        elapsed = format_time(self.timer.break_elapsed, round_up=False)
        total = format_time(self.timer.total_break_elapsed, round_up=False)
        self.break_progress.set(f"Notes elapsed: {elapsed} | Total: {total}")

    def play_events(self, events: list[SessionEvent]) -> None:
        for event in events:
            # The break-end sound also marks completion after a final note period.
            if event != SessionEvent.COMPLETED or SessionEvent.BREAK_ENDED not in events:
                self.sounds.play(event)

    def update(self) -> None:
        self.after_id = None
        events = self.timer.tick(time.monotonic())
        self.render()
        self.play_events(events)
        if self.timer.running:
            self.status.set(self.timer.phase.value)
            self.after_id = self.root.after(100, self.update)
        else:
            self.finish()

    def finish(self) -> None:
        self.started = False
        self.configure_inputs()
        self.start_button.configure(text="Start", state="normal")
        self.pause_button.configure(state="disabled")
        self.status.set("Session complete!" if self.timer.settings.breaks_enabled else "Time's up!")

    def cancel_update(self) -> None:
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id = None

    def close(self) -> None:
        self.cancel_update()
        self.sounds.close()
        self.root.destroy()


def main() -> None:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        print(f"Cannot open the timer window: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    TimerWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
