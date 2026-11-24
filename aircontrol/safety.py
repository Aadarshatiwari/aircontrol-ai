"""Central authorization gate for all native input events."""

NATIVE_ACTIONS = frozenset({
    "cursor", "drag start", "drag end", "scroll", "Left click", "Right click",
    "Double click", "Play / pause", "Volume up", "Volume down", "Switch app",
    "Next slide", "Previous slide", "Shortcut", "type",
})


class Safety:
    def __init__(self, native):
        self.native = native
        self.armed = False
        self.hotkey_ready = False

    def arm(self):
        self.armed = self.hotkey_ready and self.native.trusted()
        return self.armed

    def pause(self):
        self.native.release()

    def stop(self):
        self.armed = False
        self.pause()

    def dispatch(self, command):
        if command.name not in NATIVE_ACTIONS or not self.armed:
            return False
        if not self.hotkey_ready or not self.native.trusted():
            self.stop()
            return False
        try:
            self.native.execute(command)
        except Exception:
            self.stop()
            raise
        return True
