import os
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GLib', '2.0')
from gi.repository import GLib, Gst # type: ignore
import threading

# Default devices/pipe; can be overridden via env vars
VIDEO_DEVICE = os.environ.get("VIDEO_DEVICE", "/dev/video0")
AUDIO_DEVICE = os.environ.get("AUDIO_DEVICE", "plughw:1,0")
PIPE_DESC = (
    f"v4l2src device={VIDEO_DEVICE} ! videoconvert ! "
    "textoverlay name=subtitle font-desc=\"Sans 28\" halignment=center valignment=bottom shaded-background=true ! "
    "autovideosink sync=false"
)


class SubDeamon_utils:
    def __init__(self):
        self.name = "SubDeamon_utils"
        self.loop = GLib.MainLoop()
        Gst.init(None)
        self.pipeline = Gst.parse_launch(PIPE_DESC)
        self.sub_overlay = self.pipeline.get_by_name("subtitle")
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect("message", self.on_message)
        self.transcript = ""
        self.lock = threading.Lock()

    def on_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            self.loop.quit()
        elif t == Gst.MessageType.ERROR:
            try:
                err, dbg = message.parse_error()
            except Exception:
                err, dbg = None, None
            print("Gst.Error:", err, dbg)
            self.loop.quit()

    def start_video(self):
        self.pipeline.set_state(Gst.State.PLAYING)
        try:
            self.loop.run()
        finally:
            self.pipeline.set_state(Gst.State.NULL)

    def update_subtitle(self, text: str):
        if self.sub_overlay:
            self.sub_overlay.set_property("text", text)
