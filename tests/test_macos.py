import sys
import unittest
from unittest.mock import patch

from aircontrol.engine import Command


@unittest.skipUnless(sys.platform == "darwin", "Quartz requires macOS")
class NativeEventTests(unittest.TestCase):
    def test_accessibility_calls_use_application_services(self):
        try:
            from aircontrol import macos
        except ModuleNotFoundError as exc:
            self.skipTest(f"Install the macOS dependencies ({exc.name})")
        self.assertIsInstance(macos.MacInput.trusted(), bool)
        with patch.object(macos, "AXIsProcessTrustedWithOptions", return_value=False) as request:
            self.assertFalse(macos.MacInput.request_access())
            request.assert_called_once_with({macos.kAXTrustedCheckOptionPrompt: True})

    def test_construct_events_without_posting_to_macos(self):
        try:
            from aircontrol.macos import MacInput, q
        except ModuleNotFoundError as exc:
            self.skipTest(f"Install the macOS dependencies to exercise Quartz ({exc.name})")
        native = MacInput()
        native.location = lambda: (300, 300)
        with patch.object(q, "CGEventPost") as post:
            for action, expected in (
                ("Left click", 2), ("Right click", 2), ("Double click", 4),
                ("Volume up", 2), ("Volume down", 2), ("Play / pause", 2),
                ("Switch app", 2), ("Next slide", 2), ("Previous slide", 2),
                ("Shortcut", 2), ("drag start", 1), ("drag end", 1),
            ):
                with self.subTest(action=action):
                    native.execute(Command(action))
                    self.assertEqual(post.call_count, expected)
                    self.assertTrue(all(event.args[1] is not None for event in post.call_args_list))
                    post.reset_mock()
            native.execute(Command("scroll", 2))
            native.execute(Command("type", "A"))
            native.execute(Command("Shortcut", "Cmd+Shift+K"))
            self.assertEqual(post.call_count, 5)
            self.assertFalse(native.dragging)
