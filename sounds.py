import shutil
import subprocess
import sys
import tkinter as tk
from collections.abc import Callable
from pathlib import Path

from timer import SessionEvent


class SoundPlayer:
    def __init__(self, root: tk.Tk, report: Callable[[str], None]) -> None:
        self.root = root
        self.report = report
        self.processes: list[subprocess.Popen[str]] = []
        self.after_id: str | None = None
        self.bell_ids: list[str] = []
        self.executable = shutil.which("afplay") if sys.platform == "darwin" else None
        self.files = {
            SessionEvent.BREAK_STARTED: Path("/System/Library/Sounds/Glass.aiff"),
            SessionEvent.BREAK_ENDED: Path("/System/Library/Sounds/Ping.aiff"),
        }

    def play(self, event: SessionEvent) -> None:
        if event == SessionEvent.COMPLETED:
            self.root.bell()
            return
        sound = self.files[event]
        if self.executable is None or not sound.is_file():
            self.report("Native sounds unavailable: break start = 1 bell, end = 2 bells.")
            self.root.bell()
            if event == SessionEvent.BREAK_ENDED:
                self.bell_ids.append(self.root.after(250, self.second_bell))
            return
        try:
            process = subprocess.Popen(
                [self.executable, str(sound)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        except OSError as error:
            self.report(f"Could not play sound: {error}")
            return
        self.processes.append(process)
        if self.after_id is None:
            self.after_id = self.root.after(100, self.check_processes)

    def second_bell(self) -> None:
        self.bell_ids.pop(0)
        self.root.bell()

    def check_processes(self) -> None:
        self.after_id = None
        active: list[subprocess.Popen[str]] = []
        for process in self.processes:
            if process.poll() is None:
                active.append(process)
                continue
            _, error = process.communicate()
            if process.returncode != 0:
                self.report(f"Sound playback failed: {error.strip()}")
        self.processes = active
        if active:
            self.after_id = self.root.after(100, self.check_processes)

    def close(self) -> None:
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        for after_id in self.bell_ids:
            self.root.after_cancel(after_id)
        self.bell_ids.clear()
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
            try:
                process.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
        self.processes.clear()
