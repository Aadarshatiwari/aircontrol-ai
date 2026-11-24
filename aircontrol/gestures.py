"""Deterministic, hand-relative geometry for MediaPipe's 21 landmarks."""
from dataclasses import dataclass
from math import dist, isfinite

POSES = ("pinch", "middle pinch", "ring pinch", "two fingers", "open palm", "fist", "thumb up", "thumb down")
EDGES = ((0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
         (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15),
         (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (17, 0))


@dataclass(frozen=True)
class Hand:
    side: str
    score: float
    landmarks: tuple[tuple[float, float, float], ...]
    aspect: float = 4 / 3


def classify(hand: Hand, held: str = "") -> str:
    if len(hand.landmarks) != 21 or not all(isfinite(v) for point in hand.landmarks for v in point):
        return "unknown"
    p = [(x * hand.aspect, y, z * hand.aspect) for x, y, z in hand.landmarks]
    scale = max(dist(p[0], p[9]), dist(p[5], p[17]))
    if scale < 0.025:
        return "unknown"
    extended = tuple(
        dist(p[tip], p[0]) > dist(p[tip - 2], p[0]) * 1.17
        and dist(p[tip], p[tip - 3]) > dist(p[tip - 2], p[tip - 3]) * 1.40
        for tip in (8, 12, 16, 20)
    )
    if extended == (True, True, False, False):
        return "two fingers"
    if sum(extended) == 4:
        return "open palm"
    gaps = sorted((dist(p[4], p[tip]) / scale, pose) for tip, pose in
                  ((8, "pinch"), (12, "middle pinch"), (16, "ring pinch")))
    gap, pose = gaps[0]
    if sum(extended) <= 2 and gap < (0.36 if pose == held else 0.25) and gaps[1][0] - gap > 0.055:
        return pose
    if extended == (True, False, False, False):
        return "point"
    if not any(extended):
        dy = p[4][1] - p[2][1]
        if abs(dy) > scale * 0.38 and abs(dy) > abs(p[4][0] - p[2][0]) * 1.25:
            return "thumb up" if dy < 0 else "thumb down"
        return "fist"
    return "unknown"
