"""State machine shared by the desktop application and headless tests."""
from collections import deque
from dataclasses import dataclass
from math import isfinite

from .gestures import classify

MODES = ("Pointer", "Media", "Shortcuts", "Keyboard", "Drawing", "Presentation")
ACTIONS = ("None", "Left click", "Right click", "Double click", "Play / pause",
           "Volume up", "Volume down", "Switch app", "Next slide", "Previous slide", "Shortcut")
DEFAULTS = {
    "Pointer": {"middle pinch": "Right click", "ring pinch": "Double click"},
    "Media": {"pinch": "Play / pause", "thumb up": "Volume up", "thumb down": "Volume down"},
    "Shortcuts": {"pinch": "Shortcut", "middle pinch": "Switch app"},
    "Presentation": {"pinch": "Next slide", "middle pinch": "Previous slide"},
}


@dataclass(frozen=True)
class Command:
    name: str
    value: object = None


class Engine:
    def __init__(self):
        self.mode = "Pointer"
        self.side = "Auto"
        self.sensitivity = 1.0
        self.smoothing = 0.65
        self.cooldown = 0.38
        self.bindings = {}
        self.shortcuts = {}
        self.center = (0.5, 0.5)
        self.samples = deque(maxlen=24)
        self.calibrating = True
        self.reset()

    def reset(self):
        release = [Command("drag end")] if getattr(self, "dragging", False) else []
        if self.calibrating:
            self.samples.clear()
        self.dragging = False
        self.ready = False
        self.owner = None
        self.pose = "unknown"
        self.candidate = "unknown"
        self.since = 0.0
        self.last_action = float("-inf")
        self.fired = False
        self.pinch_consumed = False
        self.anchor = None
        self.position = None
        return release + [Command("stroke end")]

    def calibrate(self):
        self.samples.clear()
        self.calibrating = True
        return self.reset()

    def step(self, hands, now, captured):
        if not isfinite(captured) or not 0 <= now - captured < 0.27:
            return self.reset(), None, "Tracking paused"
        eligible = [h for h in hands if h.score >= 0.65 and len(h.landmarks) == 21
                    and (self.side == "Auto" or h.side == self.side)]
        if not eligible:
            return self.reset(), None, "Tracking paused"
        if self.owner:
            matching = [h for h in eligible if h.side == self.owner]
            if len(matching) != 1:
                return self.reset(), None, "Tracking paused"
            hand = matching[0]
        else:
            hand = max(eligible, key=lambda h: h.score)
        self.owner = hand.side
        recognized = classify(hand, self.candidate)
        if recognized == "unknown":
            return self.reset(), hand, recognized
        if recognized != self.candidate:
            self.candidate, self.since = recognized, now
        stable = now - self.since
        commands = []
        # Release immediately, even while the new pose is being debounced.
        if recognized != "pinch" and self.dragging:
            self.dragging = False
            commands.append(Command("drag end"))
        if self.mode == "Drawing" and recognized != "pinch":
            commands.append(Command("stroke end"))
        if stable < 0.085:
            return commands, hand, recognized
        previous = self.pose
        if recognized != previous:
            self.pose = recognized
            self.fired = False
            self.anchor = None

        x, y, _ = hand.landmarks[8]
        if self.calibrating:
            if recognized == "point":
                self.samples.append((x, y))
                if len(self.samples) == self.samples.maxlen:
                    self.center = tuple(min(0.72, max(0.28, sorted(axis)[len(axis) // 2]))
                                        for axis in zip(*self.samples))
                    self.calibrating = False
            else:
                self.samples.clear()
            return commands, hand, recognized
        if not self.ready:
            self.ready = recognized == "point" and stable >= 0.22
            return commands, hand, recognized

        if self.mode in ("Pointer", "Keyboard", "Drawing") and recognized in ("point", "pinch"):
            if recognized == "point" or self.dragging or self.mode == "Drawing" or self.position is None:
                if recognized == "pinch" and self.mode == "Drawing":
                    x, y, _ = ((a + b) / 2 for a, b in zip(hand.landmarks[4], hand.landmarks[8]))
                target = tuple(min(1., max(0., 0.5 + (v - c) * self.sensitivity / span))
                               for v, c, span in zip((x, y), self.center, (0.55, 0.48)))
                self.position = target if self.position is None else tuple(
                    a * self.smoothing + b * (1 - self.smoothing) for a, b in zip(self.position, target)
                )
            commands.append(Command("cursor", self.position))

        can_fire = not self.fired and now - self.last_action >= self.cooldown
        override = self.bindings.get((self.mode, recognized))
        if override is not None:
            if can_fire:
                self._fire(commands, override, now)
        elif self.mode == "Pointer" and recognized == "pinch":
            if can_fire and stable >= 0.42:
                self.dragging = True
                self._fire(commands, "drag start", now)
        elif self.mode == "Pointer" and previous == "pinch" and recognized == "point":
            # A released short pinch clicks only if it never reached the drag threshold.
            if not self.pinch_consumed and now - self.last_action >= self.cooldown:
                self._fire(commands, "Left click", now)
                commands.insert(0, commands.pop())
        elif self.mode == "Pointer" and recognized == "two fingers":
            scroll_y = (hand.landmarks[8][1] + hand.landmarks[12][1]) / 2
            if self.anchor is None:
                self.anchor = scroll_y
            delta = scroll_y - self.anchor
            if abs(delta) >= 0.022 and now - self.last_action >= 0.09:
                commands.append(Command("scroll", min(5, int(abs(delta) / 0.015)) * (1 if delta < 0 else -1)))
                self.anchor, self.last_action = scroll_y, now
        elif self.mode == "Keyboard" and recognized == "pinch" and can_fire:
            self._fire(commands, "keyboard select", now)
        elif self.mode == "Drawing" and recognized == "pinch":
            commands.append(Command("stroke", self.position))
        elif can_fire and recognized in DEFAULTS.get(self.mode, {}):
            self._fire(commands, DEFAULTS[self.mode][recognized], now)

        if recognized == "pinch" and previous != "pinch":
            self.pinch_consumed = override is not None
        if self.dragging:
            self.pinch_consumed = True
        return commands, hand, recognized

    def _fire(self, commands, action, now):
        self.fired = True
        if action != "None":
            self.last_action = now
            value = None
            if action == "keyboard select":
                value = self.position
            elif action == "Shortcut":
                value = self.shortcuts.get((self.mode, self.pose))
            commands.append(Command(action, value))
