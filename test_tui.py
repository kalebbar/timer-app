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
        ]), patch("tui.curses.beep") as beep, \
                patch("tui.curses.has_colors", return_value=False):
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
                    row, column, text, limit, style = call.args
                    self.assertLess(row, height)
                    self.assertEqual(column, 0)
                    self.assertLess(limit, width)

    def test_only_running_countdown_is_highlighted_in_both_layouts(self) -> None:
        self.app.running_style = curses.A_BOLD | 256
        screen = Mock()

        def check(active_row: int | None) -> None:
            for size in ((24, 80), (6, 40)):
                screen.reset_mock()
                screen.getmaxyx.return_value = size
                self.app.render(screen)
                for call in screen.addnstr.call_args_list:
                    row, _, _, _, style = call.args
                    self.assertEqual(
                        style, self.app.running_style if row == active_row else 0,
                    )

        check(None)
        self.app.handle_key(ord("s"), 0)
        check(2)
        self.app.handle_key(ord("p"), 100)
        check(None)
        self.app.handle_key(ord("s"), 200)
        check(2)
        self.app.timer.tick(1000)
        check(3)
        self.app.handle_key(ord("p"), 1010)
        check(None)
        self.app.handle_key(ord("s"), 1100)
        check(3)
        self.app.timer.tick(1390)
        check(2)
        self.app.handle_key(ord("r"), 1400)
        check(None)
        self.app.timer.reset(SessionSettings(total_work=1, breaks_enabled=False))
        self.app.timer.start(0)
        self.app.timer.tick(1)
        check(None)

    def test_color_setup_and_monochrome_fallback(self) -> None:
        screen = Mock()
        screen.getmaxyx.return_value = (24, 80)
        screen.getch.return_value = ord("q")
        for colors, default_error, background in (
            (True, None, -1),
            (True, curses.error("unsupported"), curses.COLOR_BLACK),
            (False, None, None),
        ):
            with self.subTest(colors=colors, background=background), \
                    patch("tui.curses.has_colors", return_value=colors), \
                    patch("tui.curses.use_default_colors", side_effect=default_error) as defaults, \
                    patch("tui.curses.init_pair") as init_pair, \
                    patch("tui.curses.color_pair", return_value=256):
                app = TerminalTimer()
                app.run(screen)
                if colors:
                    init_pair.assert_called_once_with(1, curses.COLOR_GREEN, background)
                    self.assertEqual(app.running_style, 256 | curses.A_BOLD)
                    if default_error:
                        self.assertIn("Default background unavailable", app.message)
                else:
                    defaults.assert_not_called()
                    init_pair.assert_not_called()
                    self.assertEqual(app.running_style, curses.A_BOLD)


if __name__ == "__main__":
    unittest.main()
