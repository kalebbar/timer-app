import tkinter as tk
import unittest
from unittest.mock import Mock, call, patch

from sounds import SoundPlayer
from timer import SessionEvent


class SoundPlayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Mock(spec=tk.Tk)
        self.report = Mock()
        self.player = SoundPlayer(self.root, self.report)

    def test_start_and_end_use_different_native_sounds(self) -> None:
        self.player.executable = "/usr/bin/afplay"
        with patch("sounds.Path.is_file", return_value=True), \
                patch("sounds.subprocess.Popen") as popen:
            self.player.play(SessionEvent.BREAK_STARTED)
            self.player.play(SessionEvent.BREAK_ENDED)
        arguments = [item.args[0] for item in popen.call_args_list]
        self.assertEqual(arguments[0][-1], "/System/Library/Sounds/Glass.aiff")
        self.assertEqual(arguments[1][-1], "/System/Library/Sounds/Ping.aiff")
        self.root.bell.assert_not_called()

    def test_fallback_patterns_are_distinct_and_reported(self) -> None:
        self.player.executable = None
        self.root.after.return_value = "bell"
        self.player.play(SessionEvent.BREAK_STARTED)
        self.root.after.assert_not_called()
        self.player.play(SessionEvent.BREAK_ENDED)
        self.root.after.assert_called_once_with(250, self.player.second_bell)
        self.player.second_bell()
        self.assertEqual(self.root.bell.call_count, 3)
        self.assertEqual(self.player.bell_ids, [])
        self.assertIn("unavailable", self.report.call_args.args[0])

    def test_process_launch_errors_are_visible(self) -> None:
        self.player.executable = "/usr/bin/afplay"
        with patch("sounds.Path.is_file", return_value=True), \
                patch("sounds.subprocess.Popen", side_effect=OSError("unavailable")):
            self.player.play(SessionEvent.BREAK_STARTED)
        self.report.assert_called_once_with("Could not play sound: unavailable")
        self.assertEqual(self.player.processes, [])

    def test_playback_errors_are_visible_and_process_is_reaped(self) -> None:
        process = Mock()
        process.poll.return_value = 1
        process.returncode = 1
        process.communicate.return_value = (None, "audio device failed\n")
        self.player.processes = [process]
        self.player.check_processes()
        self.report.assert_called_once_with("Sound playback failed: audio device failed")
        self.assertEqual(self.player.processes, [])
        process.communicate.assert_called_once()

    def test_close_cancels_callbacks_and_stops_only_owned_processes(self) -> None:
        self.player.after_id = "poll"
        self.player.bell_ids = ["bell"]
        process = Mock()
        process.poll.return_value = None
        self.player.processes = [process]
        self.player.close()
        self.assertEqual(self.root.after_cancel.call_args_list, [call("poll"), call("bell")])
        process.terminate.assert_called_once()
        process.communicate.assert_called_once_with(timeout=1)
        self.assertEqual(self.player.processes, [])


if __name__ == "__main__":
    unittest.main()
