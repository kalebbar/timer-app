import contextlib
import curses
import io
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

from main import main
from timer import Phase, SessionEvent, SessionSettings
from tui import TerminalTimer


class LaunchTests(unittest.TestCase):
    def test_flag_routes_to_terminal(self) -> None:
        with patch("tui.main") as launch:
            main(["--tui"])
        launch.assert_called_once_with()

    def test_default_routes_to_desktop(self) -> None:
        launch = Mock()
        with patch.dict(sys.modules, {"gui": Mock(main=launch)}):
            main([])
        launch.assert_called_once_with()

    def test_help_and_terminal_mode_do_not_import_tkinter(self) -> None:
        script = """
import sys
class NoTk:
    def find_spec(self, fullname, path=None, target=None):
        if fullname in ('tkinter', '_tkinter', 'gui', 'sounds'):
            raise AssertionError('Terminal launch imported ' + fullname)
sys.meta_path.insert(0, NoTk())
from main import main
main()
"""
        for args, code, message in (
            (["--help"], 0, "--tui"),
            (["--tui"], 1, "requires an interactive terminal"),
        ):
            with self.subTest(args=args):
                result = subprocess.run(
                    [sys.executable, "-c", script, *args],
                    input="", capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertIn(message, result.stdout + result.stderr)

    def test_terminal_initialization_failure_is_reported(self) -> None:
        from tui import main as terminal_main

        output = io.StringIO()
        with patch("tui.sys.stdin.isatty", return_value=True), \
                patch("tui.sys.stdout.isatty", return_value=True), \
                patch("tui.curses.wrapper", side_effect=curses.error("bad TERM")), \
                contextlib.redirect_stderr(output), \
                self.assertRaises(SystemExit) as raised:
            terminal_main()
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("bad TERM", output.getvalue())


class TerminalTimerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = TerminalTimer()

    def test_defaults_and_edited_settings(self) -> None:
        self.assertEqual(self.app.read_settings(), SessionSettings())
        self.app.values = ["0", "2", "30", "1", "2", "3", "4"]
        self.assertEqual(
            self.app.read_settings(),
            SessionSettings(total_work=150, short_interval=60, short_break=120,
                            long_interval=180, long_break=240),
        )

    def test_invalid_settings_do_not_start(self) -> None:
        for index, value in ((0, "100"), (1, "60"), (2, "-1"), (3, ""),
                             (4, "0"), (5, "5941"), (6, "abc")):
            with self.subTest(index=index, value=value):
                app = TerminalTimer()
                app.values[index] = value
                app.handle_key(ord("s"), 0)
                self.assertFalse(app.started)
                self.assertFalse(app.timer.running)
                self.assertTrue(app.message)
        self.app.values[:3] = ["0", "0", "0"]
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            self.app.read_settings()

    def test_disabled_break_fields_are_ignored(self) -> None:
        self.app.values[3:] = ["invalid"] * 4
        self.app.handle_key(ord("b"), 0)
        self.app.handle_key(ord("s"), 0)
        self.assertTrue(self.app.timer.running)
        self.assertFalse(self.app.timer.settings.breaks_enabled)

    def test_edit_navigation_and_locking(self) -> None:
        self.app.handle_key(ord("1"), 0)
        self.app.handle_key(ord("2"), 0)
        self.assertEqual(self.app.values[0], "12")
        self.app.handle_key(curses.KEY_BACKSPACE, 0)
        self.assertEqual(self.app.values[0], "1")
        self.app.handle_key(curses.KEY_DOWN, 0)
        self.app.handle_key(ord("5"), 0)
        self.assertEqual(self.app.values[1], "5")
        self.app.handle_key(curses.KEY_BTAB, 0)
        self.assertEqual(self.app.selected, 0)
        self.app.handle_key(ord("s"), 0)
        for key in (ord("9"), curses.KEY_DOWN, ord("b")):
            self.app.handle_key(key, 1)
        self.assertEqual(self.app.values[:2], ["1", "5"])
        self.assertEqual(self.app.selected, 0)
        self.assertTrue(self.app.breaks_enabled)

    def test_work_and_break_pause_resume_and_reset(self) -> None:
        self.app.handle_key(ord("s"), 0)
        self.app.handle_key(ord("p"), 100)
        self.assertEqual(self.app.timer.work_remaining, 7100)
        self.app.handle_key(ord(" "), 1000)
        events = self.app.handle_key(ord("p"), 1800)
        self.assertEqual(events, [SessionEvent.BREAK_STARTED])
        self.assertEqual(self.app.timer.phase, Phase.SHORT_BREAK)
        self.assertFalse(self.app.timer.running)
        self.app.handle_key(ord("s"), 2000)
        self.app.handle_key(ord(" "), 2050)
        self.assertEqual(self.app.timer.break_remaining, 250)
        self.assertEqual(self.app.timer.total_break_elapsed, 50)
        self.app.handle_key(ord("r"), 3000)
        self.assertFalse(self.app.started)
        self.assertFalse(self.app.timer.running)
        self.assertEqual(self.app.timer.work_remaining, 7200)
        self.assertEqual(self.app.timer.total_break_elapsed, 0)

    def test_run_completes_with_double_bell_and_can_restart(self) -> None:
        self.app.values = ["0", "1", "0", "1", "1", "60", "15"]
        screen = Mock()
        screen.getmaxyx.return_value = (24, 80)
        screen.getch.side_effect = [ord("s"), -1, -1, -1, ord("s"), ord("q")]
        with patch("tui.time.monotonic", side_effect=[
            0, 0, 60, 60, 120, 120, 121, 121, 122, 122, 123, 123,
        ]), patch("tui.curses.beep") as beep:
            self.app.run(screen)
        self.assertEqual(beep.call_count, 3)
        self.assertTrue(self.app.timer.running)
        self.assertEqual(self.app.timer.phase, Phase.WORK)
        self.assertEqual(self.app.timer.work_remaining, 59)

    def test_resize_clips_rendering_and_keeps_controls(self) -> None:
        screen = Mock()
        for height, width in ((24, 80), (5, 20), (1, 1)):
            with self.subTest(size=(height, width)):
                screen.reset_mock()
                screen.getmaxyx.return_value = (height, width)
                self.app.render(screen)
                for call in screen.addnstr.call_args_list:
                    row, column, text, limit = call.args
                    self.assertLess(row, height)
                    self.assertEqual(column, 0)
                    self.assertLess(limit, width)


if __name__ == "__main__":
    unittest.main()
