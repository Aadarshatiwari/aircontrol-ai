import unittest

from aircontrol.engine import Command, Engine
from aircontrol.gestures import Hand, classify
from aircontrol.safety import Safety


def hand_as(pose="point", side="Right", score=0.98, dx=0, dy=0):
    points = [(0.50, 0.70, 0)] * 21
    points[1:5] = [(0.44, 0.68, 0), (0.41, 0.64, 0), (0.36, 0.62, 0), (0.32, 0.61, 0)]
    active = {"point": (8,), "two fingers": (8, 12), "open palm": (8, 12, 16, 20)}.get(pose, ())
    for tip, x in zip((8, 12, 16, 20), (0.40, 0.49, 0.58, 0.66)):
        ys = (0.53, 0.45, 0.38, 0.32) if tip in active else (0.53, 0.48, 0.54, 0.58)
        points[tip - 3:tip + 1] = [(x, y, 0) for y in ys]
    if pose in ("pinch", "middle pinch", "ring pinch"):
        tip = {"pinch": 8, "middle pinch": 12, "ring pinch": 16}[pose]
        x, y, _ = points[tip]
        points[4] = (x, y + 0.005, 0)
    elif pose in ("thumb up", "thumb down"):
        points[4] = (0.40, 0.48 if pose == "thumb up" else 0.79, 0)
    return Hand(side, score, tuple(((1 - x if side == "Left" else x) + dx, y + dy, z) for x, y, z in points))


class RecognitionTests(unittest.TestCase):
    def test_every_pose_for_both_hands(self):
        for side in ("Left", "Right"):
            for pose in ("point", "two fingers", "open palm", "pinch", "middle pinch",
                         "ring pinch", "fist", "thumb up", "thumb down"):
                with self.subTest(side=side, pose=pose):
                    self.assertEqual(classify(hand_as(pose, side)), pose)

    def test_invalid_coordinates(self):
        self.assertEqual(classify(Hand("Left", 1, ((float("nan"), 0, 0),) * 21)), "unknown")
        self.assertEqual(classify(Hand("Left", 1, ())), "unknown")


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine()
        self.engine.calibrating = False
        self.arm_frames()

    def arm_frames(self):
        self.names(0)
        self.names(0.23)

    def names(self, t, pose="point", **kwargs):
        return [command.name for command in self.engine.step([hand_as(pose, **kwargs)], t, t)[0]]

    def test_debounce_short_pinch_and_single_click(self):
        self.names(0.30, "pinch")
        self.names(0.34)
        self.assertNotIn("Left click", self.names(0.44))
        self.names(0.50, "pinch")
        self.names(0.60, "pinch")
        self.names(0.64)
        self.assertIn("Left click", self.names(0.75))
        self.assertNotIn("Left click", self.names(0.90))

    def test_drag_releases_before_pose_debounce(self):
        self.names(0.4, "pinch")
        self.names(0.5, "pinch")
        self.assertIn("drag start", self.names(0.85, "pinch"))
        self.assertIn("drag end", self.names(0.90))
        self.assertNotIn("Left click", self.names(1.02))

    def test_lost_stale_and_reacquired_hand(self):
        self.names(0.4, "pinch")
        self.names(0.5, "pinch")
        self.names(0.85, "pinch")
        self.assertIn(Command("drag end"), self.engine.step([], 0.9, 0.9)[0])
        self.assertFalse(self.engine.ready)
        self.names(1.1, "pinch")
        self.assertNotIn("drag start", self.names(1.7, "pinch"))
        self.names(2.0)
        self.names(2.24)
        self.assertIn("cursor", self.names(2.3))
        self.engine.step([hand_as()], 3, 2.5)
        self.assertFalse(self.engine.ready)

    def test_controls_are_scoped_to_one_hand(self):
        self.assertIn("cursor", self.names(0.31))
        self.assertNotIn("cursor", self.names(0.4, side="Left"))
        self.assertFalse(self.engine.ready)
        self.engine.side = "Right"
        self.assertIsNone(self.engine.step([hand_as(side="Left")], 1, 1)[1])

    def test_calibration_is_automatic(self):
        self.engine.calibrate()
        for i in range(28):
            self.names(i / 30, dx=0.15, dy=0.15)
        self.assertFalse(self.engine.calibrating)
        self.assertAlmostEqual(self.engine.center[0], 0.55)
        self.assertAlmostEqual(self.engine.center[1], 0.47)

    def test_scroll_is_rate_limited(self):
        self.names(0.4, "two fingers")
        self.names(0.51, "two fingers")
        self.assertIn("scroll", self.names(0.55, "two fingers", dy=-0.05))
        self.assertNotIn("scroll", self.names(0.60, "two fingers", dy=-0.10))

    def test_modes_and_one_shot_bindings(self):
        for mode, action in (("Media", "Play / pause"), ("Shortcuts", "Shortcut"),
                             ("Presentation", "Next slide"), ("Keyboard", "keyboard select"),
                             ("Drawing", "stroke")):
            with self.subTest(mode=mode):
                self.engine.mode = mode
                self.engine.reset()
                self.arm_frames()
                self.names(0.4, "pinch")
                self.assertIn(action, self.names(0.51, "pinch"))
                if mode != "Drawing":
                    self.assertNotIn(action, self.names(1, "pinch"))
        self.engine.bindings["Drawing", "open palm"] = "Switch app"
        self.names(1.2, "open palm")
        self.assertIn("Switch app", self.names(1.31, "open palm"))


    def test_custom_shortcut_and_cooldown(self):
        self.engine.mode = "Shortcuts"
        self.engine.bindings["Shortcuts", "open palm"] = "Shortcut"
        self.engine.shortcuts["Shortcuts", "open palm"] = "Cmd+Shift+K"
        self.names(0.40, "open palm")
        commands, _, _ = self.engine.step([hand_as("open palm")], 0.51, 0.51)
        self.assertEqual(commands, [Command("Shortcut", "Cmd+Shift+K")])
        self.names(0.55, "middle pinch")
        self.assertNotIn("Switch app", self.names(0.66, "middle pinch"))
        self.assertIn("Switch app", self.names(0.91, "middle pinch"))


class NativeSpy:
    allowed = False
    fail = False

    def __init__(self):
        self.commands = []
        self.releases = 0

    def trusted(self):
        return self.allowed

    def execute(self, command):
        if self.fail:
            raise RuntimeError("input failed")
        self.commands.append(command)

    def release(self):
        self.releases += 1


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.native = NativeSpy()
        self.gate = Safety(self.native)

    def test_simulation_permissions_and_hotkey_gate(self):
        command = Command("Left click")
        self.assertFalse(self.gate.dispatch(command))
        self.native.allowed = True
        self.assertFalse(self.gate.arm())
        self.gate.hotkey_ready = True
        self.native.allowed = False
        self.assertFalse(self.gate.arm())
        self.native.allowed = True
        self.assertTrue(self.gate.arm())
        self.assertFalse(self.gate.dispatch(Command("arbitrary")))
        self.assertTrue(self.gate.dispatch(command))
        self.native.allowed = False
        self.assertFalse(self.gate.dispatch(command))
        self.gate.stop()
        self.assertFalse(self.gate.armed)
        self.assertEqual(self.native.commands, [command])
        self.assertEqual(self.native.releases, 2)

    def test_dispatch_failure_disarms(self):
        self.native.allowed = self.gate.hotkey_ready = True
        self.gate.arm()
        self.native.fail = True
        with self.assertRaises(RuntimeError):
            self.gate.dispatch(Command("drag start"))
        self.assertFalse(self.gate.armed)
        self.assertEqual(self.native.releases, 1)
