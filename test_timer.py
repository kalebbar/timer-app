import unittest

from timer import Countdown, Phase, SessionEvent, SessionSettings, WorkSession


class CountdownTests(unittest.TestCase):
    def test_delayed_updates_do_not_cause_drift(self) -> None:
        timer = Countdown(10)
        timer.start(100)
        timer.tick(103.25)
        self.assertEqual(timer.remaining, 6.75)
        timer.tick(112)
        self.assertEqual(timer.remaining, 0)
        self.assertFalse(timer.running)

    def test_pause_and_resume_preserve_remaining_time(self) -> None:
        timer = Countdown(10)
        timer.start(100)
        timer.pause(104)
        timer.tick(200)
        self.assertEqual(timer.remaining, 6)
        self.assertFalse(timer.running)
        timer.start(200)
        timer.tick(205)
        self.assertEqual(timer.remaining, 1)
        timer.tick(206)
        self.assertEqual(timer.remaining, 0)
        self.assertFalse(timer.running)

    def test_start_while_running_does_not_extend_deadline(self) -> None:
        timer = Countdown(10)
        timer.start(100)
        timer.start(105)
        self.assertEqual(timer.deadline, 110)

    def test_reset_stops_and_restores_duration(self) -> None:
        timer = Countdown(10)
        timer.start(100)
        timer.tick(104)
        timer.reset()
        self.assertEqual(timer.remaining, 10)
        self.assertFalse(timer.running)
        timer.reset(20)
        self.assertEqual(timer.duration, 20)
        self.assertEqual(timer.remaining, 20)

    def test_finished_timer_needs_reset_before_restart(self) -> None:
        timer = Countdown(1)
        timer.start(0)
        timer.tick(1)
        timer.start(2)
        self.assertFalse(timer.running)

    def test_invalid_duration_is_rejected(self) -> None:
        for seconds in (0, -1, float("inf"), float("nan")):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                Countdown(seconds)

    def test_invalid_reset_preserves_state(self) -> None:
        timer = Countdown(10)
        timer.start(0)
        with self.assertRaises(ValueError):
            timer.reset(-1)
        self.assertEqual(timer.duration, 10)
        self.assertTrue(timer.running)


class WorkSessionTests(unittest.TestCase):
    def test_two_hour_schedule_includes_final_notes_and_hourly_precedence(self) -> None:
        session = WorkSession(SessionSettings())
        session.start(0)
        now = 0
        for interval in range(1, 9):
            now += 900
            self.assertEqual(session.tick(now), [SessionEvent.BREAK_STARTED])
            long_break = interval % 4 == 0
            duration = 900 if long_break else 300
            self.assertEqual(
                session.phase, Phase.LONG_BREAK if long_break else Phase.SHORT_BREAK
            )
            self.assertEqual(session.work_remaining, 7200 - interval * 900)
            self.assertEqual(session.break_remaining, duration)
            now += duration
            events = session.tick(now)
            self.assertEqual(
                events,
                [SessionEvent.BREAK_ENDED, SessionEvent.COMPLETED]
                if interval == 8 else [SessionEvent.BREAK_ENDED],
            )
        self.assertEqual(now, 10800)
        self.assertEqual(session.total_break_elapsed, 3600)
        self.assertEqual(session.phase, Phase.FINISHED)
        self.assertFalse(session.running)
        self.assertEqual(session.tick(now + 1), [])

    def test_break_freezes_work_and_tracks_elapsed_notes(self) -> None:
        session = WorkSession(SessionSettings())
        session.start(10)
        session.tick(910)
        session.tick(1010)
        self.assertEqual(session.work_remaining, 6300)
        self.assertEqual(session.break_remaining, 200)
        self.assertEqual(session.break_elapsed, 100)
        self.assertEqual(session.total_break_elapsed, 100)
        session.tick(1210)
        session.tick(1220)
        self.assertEqual(session.work_remaining, 6290)
        self.assertEqual(session.break_elapsed, 0)
        self.assertEqual(session.total_break_elapsed, 300)

    def test_manual_pause_preserves_fractional_work_and_schedule(self) -> None:
        session = WorkSession(SessionSettings())
        session.start(0)
        session.pause(100.5)
        self.assertEqual(session.work_remaining, 7099.5)
        self.assertEqual(session.tick(1000), [])
        session.start(1000)
        self.assertEqual(session.tick(1799.5), [SessionEvent.BREAK_STARTED])
        self.assertEqual(session.work_remaining, 6300)

    def test_manual_pause_during_notes_freezes_both_counters(self) -> None:
        session = WorkSession(SessionSettings())
        session.start(0)
        session.tick(900)
        session.pause(1000)
        session.tick(5000)
        self.assertEqual(session.break_remaining, 200)
        self.assertEqual(session.total_break_elapsed, 100)
        self.assertEqual(session.work_remaining, 6300)
        session.start(5000)
        self.assertEqual(session.tick(5200), [SessionEvent.BREAK_ENDED])
        self.assertEqual(session.phase, Phase.WORK)

    def test_pause_at_boundary_pauses_new_break_and_emits_start_once(self) -> None:
        session = WorkSession(SessionSettings())
        session.start(0)
        self.assertEqual(session.pause(900), [SessionEvent.BREAK_STARTED])
        self.assertFalse(session.running)
        self.assertEqual(session.break_remaining, 300)
        self.assertEqual(session.tick(1000), [])

    def test_late_update_does_not_skip_or_shorten_note_period(self) -> None:
        session = WorkSession(SessionSettings())
        session.start(0)
        self.assertEqual(session.tick(5000), [SessionEvent.BREAK_STARTED])
        self.assertEqual(session.work_remaining, 6300)
        self.assertEqual(session.break_remaining, 300)
        self.assertEqual(session.tick(5300), [SessionEvent.BREAK_ENDED])
        self.assertEqual(session.work_remaining, 6300)

    def test_noncoincident_intervals_each_trigger_at_work_boundaries(self) -> None:
        session = WorkSession(
            SessionSettings(total_work=30, short_interval=10, short_break=2,
                            long_interval=15, long_break=3)
        )
        session.start(0)
        for now, phase, work_remaining in (
            (10, Phase.SHORT_BREAK, 20), (17, Phase.LONG_BREAK, 15),
            (25, Phase.SHORT_BREAK, 10), (37, Phase.LONG_BREAK, 0),
        ):
            self.assertEqual(session.tick(now), [SessionEvent.BREAK_STARTED])
            self.assertEqual(session.phase, phase)
            self.assertEqual(session.work_remaining, work_remaining)
            events = session.tick(now + (3 if phase == Phase.LONG_BREAK else 2))
            self.assertIn(SessionEvent.BREAK_ENDED, events)
        self.assertEqual(session.phase, Phase.FINISHED)
        self.assertEqual(session.total_break_elapsed, 10)

    def test_partial_final_interval_finishes_without_unscheduled_break(self) -> None:
        session = WorkSession(SessionSettings(total_work=1000))
        session.start(0)
        session.tick(900)
        session.tick(1200)
        self.assertEqual(session.tick(1300), [SessionEvent.COMPLETED])
        self.assertEqual(session.phase, Phase.FINISHED)
        self.assertEqual(session.work_remaining, 0)

    def test_final_short_boundary_includes_short_note_period(self) -> None:
        session = WorkSession(SessionSettings(total_work=900))
        session.start(0)
        self.assertEqual(session.tick(900), [SessionEvent.BREAK_STARTED])
        self.assertEqual(session.work_remaining, 0)
        self.assertTrue(session.running)
        self.assertEqual(
            session.tick(1200), [SessionEvent.BREAK_ENDED, SessionEvent.COMPLETED]
        )

    def test_plain_countdown_mode_preserves_old_behavior(self) -> None:
        session = WorkSession(SessionSettings(total_work=1000, breaks_enabled=False))
        session.start(0)
        self.assertEqual(session.tick(900), [])
        self.assertEqual(session.work_remaining, 100)
        self.assertEqual(session.tick(1000), [SessionEvent.COMPLETED])
        self.assertEqual(session.total_break_elapsed, 0)

    def test_reset_clears_break_progress_and_restores_work_goal(self) -> None:
        session = WorkSession(SessionSettings())
        session.start(0)
        session.tick(900)
        session.tick(1000)
        session.reset()
        self.assertFalse(session.running)
        self.assertEqual(session.phase, Phase.WORK)
        self.assertEqual(session.work_remaining, 7200)
        self.assertEqual(session.total_break_elapsed, 0)
        session.reset(SessionSettings(total_work=60))
        self.assertEqual(session.work_remaining, 60)

    def test_start_while_running_does_not_extend_interval(self) -> None:
        session = WorkSession(SessionSettings())
        session.start(0)
        session.start(100)
        self.assertEqual(session.tick(900), [SessionEvent.BREAK_STARTED])

    def test_finished_session_cannot_restart_without_reset(self) -> None:
        session = WorkSession(SessionSettings(total_work=1))
        session.start(0)
        session.tick(1)
        session.start(2)
        self.assertFalse(session.running)
        self.assertEqual(session.phase, Phase.FINISHED)

    def test_settings_reject_invalid_values(self) -> None:
        for name in (
            "total_work", "short_interval", "short_break", "long_interval", "long_break"
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                SessionSettings(**{name: 0})


if __name__ == "__main__":
    unittest.main()
