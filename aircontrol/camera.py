"""Camera supervision with native inference isolated from the desktop process."""
from dataclasses import dataclass
from multiprocessing import get_context
from pathlib import Path
from threading import Lock
from time import monotonic

from PySide6.QtCore import QThread, Signal

from .gestures import EDGES, Hand

MODEL = Path(__file__).resolve().parents[1] / "assets" / "hand_landmarker.task"


@dataclass
class Frame:
    image: object
    hands: tuple
    timestamp: float
    fps: float


def make_detector():
    import mediapipe as mp

    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(
            model_asset_path=str(MODEL), delegate=mp.tasks.BaseOptions.Delegate.CPU,
        ),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=0.6,
        min_hand_presence_confidence=0.6,
        min_tracking_confidence=0.6,
    )
    return mp.tasks.vision.HandLandmarker.create_from_options(options)


def process_frame(detector, bgr, timestamp_ms, *, overlay=True):
    import cv2
    import mediapipe as mp

    # Four channels also support the macOS GPU buffer format used by MediaPipe.
    rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGBA)
    result = detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGBA, data=rgba), timestamp_ms)
    height, width = bgr.shape[:2]
    rgb = cv2.flip(cv2.cvtColor(rgba, cv2.COLOR_RGBA2RGB), 1)
    hands = []
    for points, categories in zip(result.hand_landmarks, result.handedness):
        if not categories or len(points) != 21:
            continue
        category = categories[0]
        hand = Hand(category.category_name, category.score,
                    tuple((1 - p.x, p.y, p.z) for p in points), width / height)
        hands.append(hand)
        if overlay:
            pixels = [(int(x * width), int(y * height)) for x, y, _ in hand.landmarks]
            for a, b in EDGES:
                cv2.line(rgb, pixels[a], pixels[b], (55, 213, 232), 2, cv2.LINE_AA)
            for point in pixels:
                cv2.circle(rgb, point, 4, (195, 251, 255), -1, cv2.LINE_AA)
    return rgb, tuple(hands)


def capture(index, connection, stop):
    camera = None
    try:
        import cv2

        with make_detector() as detector:
            if stop.is_set():
                return
            camera = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
            if not camera.isOpened():
                raise RuntimeError("Camera unavailable. Check Camera permissions or close apps using it.")
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            last_ms, last_time, fps = -1, monotonic(), 0.
            while not stop.is_set():
                valid, bgr = camera.read()
                captured = monotonic()
                if not valid:
                    raise RuntimeError("Camera stopped supplying frames. Try starting the camera again.")
                last_ms = max(last_ms + 1, int(captured * 1000))
                rgb, hands = process_frame(detector, bgr, last_ms)
                stamp = monotonic()
                fps = fps * 0.87 + 0.13 / max(0.001, stamp - last_time)
                last_time = stamp
                connection.send(Frame(rgb, hands, captured, fps))
    except Exception as exc:
        if not stop.is_set():
            connection.send(str(exc))
    finally:
        if camera is not None:
            camera.release()
        connection.close()


class Camera(QThread):
    failed = Signal(str)

    def __init__(self, index=0):
        super().__init__()
        self.index = index
        self.lock = Lock()
        self.latest = None

    def take(self):
        with self.lock:
            frame, self.latest = self.latest, None
        return frame

    def run(self):
        worker = stop = reader = writer = None
        failure = None
        try:
            context = get_context("spawn")
            reader, writer = context.Pipe(duplex=False)
            stop = context.Event()
            worker = context.Process(target=capture, args=(self.index, writer, stop), daemon=True)
            worker.start()
            writer.close()
            deadline = monotonic() + 45
            while not self.isInterruptionRequested():
                if reader.poll(0.05):
                    payload = reader.recv()
                    if isinstance(payload, str):
                        failure = payload
                        break
                    deadline = monotonic() + 5
                    with self.lock:
                        self.latest = payload
                elif not worker.is_alive():
                    failure = "Tracking process closed. Start the camera to retry."
                    break
                elif monotonic() > deadline:
                    failure = "Camera startup or tracking timed out. Start the camera to retry."
                    break
        except (EOFError, ConnectionError):
            failure = "Tracking process disconnected. Start the camera to retry."
        except Exception as exc:
            failure = str(exc)
        finally:
            if stop is not None:
                stop.set()
            # Closing the pipe also wakes a child that is blocked writing a frame.
            if reader is not None:
                reader.close()
            if writer is not None:
                writer.close()
            if worker is not None and worker.pid is not None:
                worker.join(1.5)
                if worker.is_alive():
                    worker.kill()
                    worker.join()
                worker.close()
        if failure and not self.isInterruptionRequested():
            self.failed.emit(failure)
