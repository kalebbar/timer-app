import math
from dataclasses import dataclass
from enum import Enum


def format_time(seconds: float, *, round_up: bool = True) -> str:
    whole_seconds = math.ceil(seconds) if round_up else math.floor(seconds)
    hours, whole_seconds = divmod(whole_seconds, 3600)
    minutes, whole_seconds = divmod(whole_seconds, 60)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02}"


class Countdown:
    def __init__(self, seconds: float) -> None:
        self.duration = self.validate_duration(seconds)
        self.remaining = self.duration
        self.deadline: float | None = None

    @staticmethod
    def validate_duration(seconds: float) -> float:
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("Duration must be finite and greater than zero.")
        return float(seconds)

    @property
    def running(self) -> bool:
        return self.deadline is not None

    def start(self, now: float) -> None:
        if not self.running and self.remaining > 0:
            self.deadline = now + self.remaining

    def tick(self, now: float) -> None:
        if self.deadline is not None:
            self.remaining = max(0.0, self.deadline - now)
            if self.remaining == 0:
                self.deadline = None

    def pause(self, now: float) -> None:
        self.tick(now)
        self.deadline = None

    def reset(self, seconds: float | None = None) -> None:
        if seconds is not None:
            self.duration = self.validate_duration(seconds)
        self.remaining = self.duration
        self.deadline = None


class Phase(Enum):
    WORK = "Work"
    SHORT_BREAK = "Note break"
    LONG_BREAK = "Hourly note break"
    FINISHED = "Finished"


class SessionEvent(Enum):
    BREAK_STARTED = "break_started"
    BREAK_ENDED = "break_ended"
    COMPLETED = "completed"


@dataclass(frozen=True)
class SessionSettings:
    total_work: int = 7200
    short_interval: int = 900
    short_break: int = 300
    long_interval: int = 3600
    long_break: int = 900
    breaks_enabled: bool = True

    def __post_init__(self) -> None:
        for name in (
            "total_work", "short_interval", "short_break", "long_interval", "long_break"
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive whole number of seconds.")


class WorkSession:
    def __init__(self, settings: SessionSettings) -> None:
        self.settings = settings
        self.reset()

    def reset(self, settings: SessionSettings | None = None) -> None:
        if settings is not None:
            self.settings = settings
        self.phase = Phase.WORK
        self.work_done = 0
        self.completed_break_time = 0.0
        self.work_target = self.next_work_target()
        self.countdown = Countdown(self.work_target)

    @property
    def running(self) -> bool:
        return self.countdown.running

    @property
    def in_break(self) -> bool:
        return self.phase in (Phase.SHORT_BREAK, Phase.LONG_BREAK)

    @property
    def work_remaining(self) -> float:
        if self.phase == Phase.WORK:
            return self.settings.total_work - self.work_target + self.countdown.remaining
        return float(self.settings.total_work - self.work_done)

    @property
    def break_remaining(self) -> float:
        return self.countdown.remaining if self.in_break else 0.0

    @property
    def break_elapsed(self) -> float:
        if self.in_break:
            return self.countdown.duration - self.countdown.remaining
        return 0.0

    @property
    def total_break_elapsed(self) -> float:
        return self.completed_break_time + self.break_elapsed

    def next_work_target(self) -> int:
        if not self.settings.breaks_enabled:
            return self.settings.total_work
        return min(
            self.settings.total_work,
            (self.work_done // self.settings.short_interval + 1)
            * self.settings.short_interval,
            (self.work_done // self.settings.long_interval + 1)
            * self.settings.long_interval,
        )

    def start(self, now: float) -> None:
        if self.phase != Phase.FINISHED:
            self.countdown.start(now)

    def pause(self, now: float) -> list[SessionEvent]:
        events = self.tick(now)
        self.countdown.pause(now)
        return events

    def tick(self, now: float) -> list[SessionEvent]:
        if not self.running:
            return []
        self.countdown.tick(now)
        if self.running:
            return []

        events: list[SessionEvent] = []
        if self.in_break:
            self.completed_break_time += self.countdown.duration
            events.append(SessionEvent.BREAK_ENDED)
        else:
            self.work_done = self.work_target
            if self.settings.breaks_enabled:
                if self.work_done % self.settings.long_interval == 0:
                    self.phase = Phase.LONG_BREAK
                    duration = self.settings.long_break
                elif self.work_done % self.settings.short_interval == 0:
                    self.phase = Phase.SHORT_BREAK
                    duration = self.settings.short_break
                else:
                    duration = None
                if duration is not None:
                    # Start a full break now, even if a UI update arrived late.
                    self.countdown = Countdown(duration)
                    self.countdown.start(now)
                    return [SessionEvent.BREAK_STARTED]

        if self.work_done == self.settings.total_work:
            self.phase = Phase.FINISHED
            return events + [SessionEvent.COMPLETED]

        self.phase = Phase.WORK
        self.work_target = self.next_work_target()
        self.countdown = Countdown(self.work_target - self.work_done)
        self.countdown.start(now)
        return events
