"""Quartz input and documented macOS permission and hotkey APIs."""
import ctypes as c

from ApplicationServices import AXIsProcessTrusted, AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
from AVFoundation import (
    AVCaptureDevice, AVMediaTypeVideo, AVAuthorizationStatusAuthorized,
    AVAuthorizationStatusNotDetermined,
)
from AppKit import NSEvent, NSSystemDefined
import Quartz as q

KEYS = dict(zip("asdfhgzxcvbqwertyuiopljknm", (0, 1, 2, 3, 4, 5, 6, 7, 8, 9,
             11, 12, 13, 14, 15, 17, 16, 32, 34, 31, 35, 37, 38, 40, 45, 46)))
KEYS.update(dict(zip("1234567890", (18, 19, 20, 21, 23, 22, 26, 28, 25, 29))))
KEYS.update(tab=48, space=49, enter=36, escape=53, left=123, right=124, down=125, up=126, backspace=51)
MODIFIERS = {"cmd": q.kCGEventFlagMaskCommand, "shift": q.kCGEventFlagMaskShift,
             "ctrl": q.kCGEventFlagMaskControl, "option": q.kCGEventFlagMaskAlternate}


def parse_shortcut(value):
    parts = [part.strip().lower() for part in value.split("+")]
    modifiers = parts[:-1]
    if (not modifiers or parts[-1] not in KEYS or len(modifiers) != len(set(modifiers))
            or any(part not in MODIFIERS for part in modifiers)):
        raise ValueError("Use a modifier and a supported key, for example Cmd+Shift+P.")
    if set(modifiers) == {"ctrl", "option", "cmd"} and parts[-1] == "escape":
        raise ValueError("This shortcut is reserved for the emergency stop.")
    return KEYS[parts[-1]], sum(MODIFIERS[part] for part in modifiers)


def camera_permission(callback):
    status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeVideo)
    if status == AVAuthorizationStatusNotDetermined:
        AVCaptureDevice.requestAccessForMediaType_completionHandler_(AVMediaTypeVideo, callback)
    else:
        callback(status == AVAuthorizationStatusAuthorized)


class MacInput:
    def __init__(self):
        self.dragging = False
        self.shortcut = parse_shortcut("Cmd+Space")

    @staticmethod
    def trusted():
        return bool(AXIsProcessTrusted())

    @staticmethod
    def request_access():
        return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True}))

    @staticmethod
    def location():
        return q.CGEventGetLocation(q.CGEventCreate(None))

    @staticmethod
    def mouse(kind, point, button=q.kCGMouseButtonLeft, count=0):
        event = q.CGEventCreateMouseEvent(None, kind, point, button)
        if count:
            q.CGEventSetIntegerValueField(event, q.kCGMouseEventClickState, count)
        q.CGEventPost(q.kCGHIDEventTap, event)

    def release(self):
        if self.dragging:
            self.dragging = False
            self.mouse(q.kCGEventLeftMouseUp, self.location())

    @staticmethod
    def key(code, flags=0, character=None):
        for down in (True, False):
            event = q.CGEventCreateKeyboardEvent(None, code, down)
            if character:
                q.CGEventKeyboardSetUnicodeString(event, len(character.encode("utf-16-le")) // 2, character)
            q.CGEventSetFlags(event, flags)
            q.CGEventPost(q.kCGHIDEventTap, event)

    @staticmethod
    def media(code):
        for state in (0xA, 0xB):
            event = NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
                NSSystemDefined, (0, 0), state << 8, 0, 0, None, 8, (code << 16) | (state << 8), -1,
            )
            q.CGEventPost(q.kCGHIDEventTap, event.CGEvent())

    def execute(self, command):
        name, value = command.name, command.value
        if name == "cursor":
            bounds = q.CGDisplayBounds(q.CGMainDisplayID())
            x, y = value
            point = (bounds.origin.x + x * (bounds.size.width - 1),
                     bounds.origin.y + y * (bounds.size.height - 1))
            self.mouse(q.kCGEventLeftMouseDragged if self.dragging else q.kCGEventMouseMoved, point)
        elif name == "drag start":
            self.dragging = True
            self.mouse(q.kCGEventLeftMouseDown, self.location(), count=1)
        elif name == "drag end":
            self.release()
        elif name == "scroll":
            event = q.CGEventCreateScrollWheelEvent(None, q.kCGScrollEventUnitLine, 1, value)
            q.CGEventPost(q.kCGHIDEventTap, event)
        elif name in ("Left click", "Right click", "Double click"):
            right = name == "Right click"
            down, up, button = ((q.kCGEventRightMouseDown, q.kCGEventRightMouseUp, q.kCGMouseButtonRight)
                                if right else (q.kCGEventLeftMouseDown, q.kCGEventLeftMouseUp, q.kCGMouseButtonLeft))
            point = self.location()
            for count in range(1, 3 if name == "Double click" else 2):
                self.mouse(down, point, button, count)
                self.mouse(up, point, button, count)
        elif name in ("Volume up", "Volume down", "Play / pause"):
            self.media({"Volume up": 0, "Volume down": 1, "Play / pause": 16}[name])
        elif name == "Shortcut":
            self.key(*(parse_shortcut(value) if value else self.shortcut))
        elif name == "Switch app":
            self.key(KEYS["tab"], MODIFIERS["cmd"])
        elif name in ("Next slide", "Previous slide"):
            self.key(KEYS["right" if name == "Next slide" else "left"])
        elif name == "type":
            if value in ("Backspace", "Enter"):
                self.key(KEYS[value.lower()])
            elif len(value) == 1:
                self.key(0, character=value)
            else:
                raise ValueError("Invalid virtual keyboard key.")


class EventType(c.Structure):
    _fields_ = [("category", c.c_uint32), ("kind", c.c_uint32)]


class HotKeyID(c.Structure):
    _fields_ = [("signature", c.c_uint32), ("id", c.c_uint32)]


class EmergencyHotkey:
    """Register Ctrl+Option+Cmd+Escape without capturing arbitrary keyboard input."""

    def __init__(self, stop):
        self.handler = c.c_void_p()
        self.hotkey = c.c_void_p()
        self.carbon = c.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")
        callback = c.CFUNCTYPE(c.c_int32, c.c_void_p, c.c_void_p, c.c_void_p)
        self.carbon.GetApplicationEventTarget.restype = c.c_void_p
        self.carbon.InstallEventHandler.argtypes = [
            c.c_void_p, callback, c.c_uint32, c.POINTER(EventType), c.c_void_p, c.POINTER(c.c_void_p),
        ]
        self.carbon.RegisterEventHotKey.argtypes = [
            c.c_uint32, c.c_uint32, HotKeyID, c.c_void_p, c.c_uint32, c.POINTER(c.c_void_p),
        ]
        self.carbon.UnregisterEventHotKey.argtypes = [c.c_void_p]
        self.carbon.RemoveEventHandler.argtypes = [c.c_void_p]
        self.carbon.GetEventParameter.argtypes = [
            c.c_void_p, c.c_uint32, c.c_uint32, c.c_void_p, c.c_uint32, c.c_void_p, c.c_void_p,
        ]
        identifier = HotKeyID(int.from_bytes(b"ACAI", "big"), 1)

        @callback
        def handle(_, event, __):
            received = HotKeyID()
            result = self.carbon.GetEventParameter(
                event, int.from_bytes(b"----", "big"), int.from_bytes(b"hkid", "big"),
                None, c.sizeof(received), None, c.byref(received),
            )
            if result or (received.signature, received.id) != (identifier.signature, identifier.id):
                return -9874
            stop()
            return 0

        self.callback = handle  # Keep the native callback alive for the registration.
        target = self.carbon.GetApplicationEventTarget()
        event_type = EventType(int.from_bytes(b"keyb", "big"), 6)
        result = self.carbon.InstallEventHandler(target, handle, 1, c.byref(event_type), None, c.byref(self.handler))
        if not result:
            result = self.carbon.RegisterEventHotKey(53, (1 << 8) | (1 << 11) | (1 << 12),
                                                     identifier, target, 0, c.byref(self.hotkey))
        self.ready = result == 0
        if not self.ready:
            self.close()

    def close(self):
        if self.hotkey:
            self.carbon.UnregisterEventHotKey(self.hotkey)
            self.hotkey = c.c_void_p()
        if self.handler:
            self.carbon.RemoveEventHandler(self.handler)
            self.handler = c.c_void_p()
