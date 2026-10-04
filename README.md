# Desktop countdown timer

A local Python work timer with scheduled note-taking breaks and
Start, Pause/Resume, and Reset controls. Separate displays show work time
remaining, note time remaining, elapsed time in the current note period,
and total note time. Timers use a monotonic clock.

## Work and note schedule

The default goal is **2 hours of actual work**, with:

- A **5-minute note break every 15 minutes of accumulated work**.
- A **15-minute note break every hour of accumulated work**, replacing
  the coinciding short break.
- Automatic return to work after each break.
- A final **15-minute note period after reaching 2 hours of work**,
  then complete shutdown of the countdown (the window stays open).

Breaks never count toward the work goal. The default schedule takes
**3 hours overall**: 2 hours of work, six 5-minute breaks, and two
15-minute breaks, including the final note period.

You can edit the work goal and all four break settings before starting.
Intervals are measured in work time; break settings use whole minutes.
When a custom work goal ends exactly at a scheduled break boundary,
that final break is taken before completion. Goals ending between
boundaries finish directly, without adding an unscheduled break.
Long breaks take priority whenever both intervals coincide.

On macOS, **Glass** marks the start of notes and **Ping** marks the end,
using the built-in `afplay` player without blocking the window. Sound failures
are shown in the window. On other platforms or when native sounds are missing,
the window reports that it uses one system bell for break start and two for
break end. Audibility depends on system sound settings.

Uncheck **Scheduled note breaks** for the original plain countdown behavior.

## Setup and run

Requires Python 3.13+ with Tkinter and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run python main.py
```

uv creates or reuses the project-local `.venv`. There are no third-party
dependencies: the UI uses Python's standard-library Tkinter. If your Python
installation lacks Tkinter, install a Python distribution with Tk support
or your platform's matching Tk package; Tkinter is not installed with pip/uv.

All settings are locked once the session starts. Pause freezes whichever
timer is active (work or notes); a manual pause does not count as note time.
Resume continues that same phase. Reset stops the session, clears note
progress, restores the last started work goal, and unlocks the fields.
Start after completion begins a new session. Closing the window exits
the application and stops any sounds it started.

Delayed UI updates do not skip note periods: a full break starts when
the work boundary is detected, and work resumes when its end is detected.
This can extend wall-clock duration if the computer sleeps.

## Tests

```sh
uv run python -m unittest discover -v
```

The tests cover the exact 2-hour schedule, independent work/note counters,
manual pause/resume, final notes, late updates, input validation, and sound
routing/failures. Desktop control tests use Tkinter and explicitly skip when
no graphical display is available; scheduler and sound tests need no display.