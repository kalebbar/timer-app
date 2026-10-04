import tkinter as tk
import unittest
from unittest.mock import call, patch

from main import TimerWindow, format_time
from timer import Phase, SessionEvent, SessionSettings


class FormattingTests(unittest.TestCase):
    def test_remaining_rounds_up_and_elapsed_rounds_down(self) -> None:
        self.assertEqual(format_time(59.1), "00:01:00")
        self.assertEqual(format_time(59.9, round_up=False), "00:00:59")
        self.assertEqual(format_time(7200), "02:00:00")


class TimerWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Desktop display unavailable: {error}")
        self.root.withdraw()
        self.sound_patch = patch("main.SoundPlayer", autospec=True)
        self.sound_patch.start()
        self.addCleanup(self.sound_patch.stop)
        self.clock_patch = patch("main.time.monotonic", return_value=0.0)
        self.clock = self.clock_patch.start()
        self.addCleanup(self.clock_patch.stop)
        self.app = TimerWindow(self.root)
        self.addCleanup(self.app.close)

    def advance(self, now: float) -> None:
        self.app.cancel_update()
        self.clock.return_value = now
        self.app.update()

    def test_work_break_resume_final_notes_and_distinct_sound_events(self) -> None:
        settings = SessionSettings(total_work=4, short_interval=2, short_break=1,
                                   long_interval=4, long_break=2)
        with patch.object(self.app, "read_settings", return_value=settings):
            self.app.start()
        self.assertEqual(self.app.display.get(), "00:00:04")
        self.advance(2)
        self.assertEqual(self.app.display.get(), "00:00:02")
        self.assertEqual(self.app.break_display.get(), "00:00:01")
        self.assertEqual(self.app.status.get(), "Note break")
        self.advance(3)
        self.assertEqual(self.app.timer.phase, Phase.WORK)
        self.assertIn("Total: 00:00:01", self.app.break_progress.get())
        self.advance(5)
        self.assertEqual(self.app.display.get(), "00:00:00")
        self.assertEqual(self.app.break_display.get(), "00:00:02")
        self.assertTrue(self.app.started)
        self.advance(6)
        self.assertIn("Notes elapsed: 00:00:01", self.app.break_progress.get())
        self.advance(7)
        self.assertEqual(self.app.status.get(), "Session complete!")
        self.assertFalse(self.app.started)
        self.assertIsNone(self.app.after_id)
        self.assertIn("Total: 00:00:03", self.app.break_progress.get())
        self.assertEqual(
            self.app.sounds.play.call_args_list,
            [call(SessionEvent.BREAK_STARTED), call(SessionEvent.BREAK_ENDED),
             call(SessionEvent.BREAK_STARTED), call(SessionEvent.BREAK_ENDED)],
        )

    def test_manual_pause_and_reset_during_break(self) -> None:
        self.app.start()
        self.advance(900)
        self.clock.return_value = 950
        self.app.pause()
        self.assertEqual(self.app.break_display.get(), "00:04:10")
        self.assertEqual(self.app.start_button.cget("text"), "Resume")
        self.assertIsNone(self.app.after_id)
        self.clock.return_value = 2000
        self.app.start()
        self.advance(2100)
        self.assertEqual(self.app.break_display.get(), "00:02:30")
        self.app.reset()
        self.assertEqual(self.app.display.get(), "02:00:00")
        self.assertEqual(self.app.break_display.get(), "00:00:00")
        self.assertFalse(self.app.timer.running)
        self.assertIsNone(self.app.after_id)
        self.assertTrue(all(str(entry.cget("state")) == "normal"
                            for entry in self.app.inputs + self.app.break_inputs))
        self.app.sounds.close.assert_called_once()

    def test_invalid_break_settings_show_error_without_starting(self) -> None:
        for value in ("0", "-1", "abc", "5941"):
            with self.subTest(value=value):
                self.app.break_settings[0].set(value)
                self.app.start()
                self.assertFalse(self.app.timer.running)
                self.assertFalse(self.app.started)
                self.assertIn("break", self.app.status.get().lower())

    def test_disabling_breaks_preserves_plain_timer_and_ignores_break_fields(self) -> None:
        self.app.breaks_enabled.set(False)
        self.app.configure_inputs()
        self.app.break_settings[0].set("invalid")
        for variable, value in zip(self.app.duration, ("0", "0", "1")):
            variable.set(value)
        self.app.start()
        self.advance(1)
        self.assertEqual(self.app.status.get(), "Time's up!")
        self.app.sounds.play.assert_called_once_with(SessionEvent.COMPLETED)
        self.assertTrue(all(str(entry.cget("state")) == "disabled"
                            for entry in self.app.break_inputs))


if __name__ == "__main__":
    unittest.main()
