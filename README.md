# Desktop and terminal countdown timer

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

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).
Desktop mode additionally requires Tkinter.

```sh
uv sync
uv run python main.py
```

uv creates or reuses the project-local `.venv`. There are no third-party
dependencies: the UI uses Python's standard-library Tkinter. If your Python
installation lacks Tkinter, install a Python distribution with Tk support
or your platform's matching Tk package; Tkinter is not installed with pip/uv.

### Linux terminal interface

```sh
uv run python main.py --tui
```

Terminal mode uses standard-library `curses`, needs no Tkinter or graphical
display, and requires an interactive terminal. Run without `--tui` for the
original desktop window; `--help` shows launch options.

Use **Up/Down** or **Tab/Shift-Tab** to select a setting, then type digits to
replace its value (Backspace deletes). **B** toggles scheduled breaks.
**S** or **Space** starts, pauses, or resumes; **P** pauses; **R** resets;
**Q**, **Esc**, or **Ctrl-C** exits and restores the terminal. Settings use the
same defaults, units, and limits as the desktop interface and remain locked
until Reset or completion. Use a terminal at least 60 columns by 21 rows for
all settings; smaller terminals show a compact timer view.
The running countdown is **green and bold**: work during work periods, notes
during breaks. Paused, idle, and finished timers are not highlighted. Terminals
without color support use bold alone.

Work and note counters follow the same schedule in both interfaces. Terminal
alerts use one bell for break start/completion and two for break end (without
an extra completion bell after final notes). Audibility depends on terminal
settings. Completion leaves the interface open so you can start again.

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
Terminal tests cover keyboard controls, settings, rendering at small sizes,
alerts, restart, launch routing, and startup without importing Tkinter.