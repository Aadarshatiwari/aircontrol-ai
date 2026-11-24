"""Custom-painted preview and mode surfaces."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

CYAN = QColor("#48ddee")
MUTED = QColor("#8395ac")
GRID = QColor("#213046")
WHITE = QColor("#e5f2ff")


class Preview(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(400, 290)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image = None
        self.message = "Camera off"
        self.cursor = None

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(GRID)
        p.setBrush(QColor("#090f1a"))
        p.drawRoundedRect(rect, 14, 14)
        if self.image:
            image = self.image
            ratio = min((rect.width() - 16) / image.width(), (rect.height() - 16) / image.height())
            w, h = image.width() * ratio, image.height() * ratio
            p.drawImage(QRectF(rect.center().x() - w / 2, rect.center().y() - h / 2, w, h), image)
        else:
            p.setPen(QPen(GRID, 1, Qt.PenStyle.DotLine))
            for x in range(24, self.width() - 10, 24):
                p.drawLine(x, 10, x, self.height() - 10)
            for y in range(24, self.height() - 10, 24):
                p.drawLine(10, y, self.width() - 10, y)
            p.setFont(QFont("Helvetica Neue", 14))
            p.setPen(MUTED)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.message)
        if self.cursor:
            x, y = self.cursor
            point = QPointF(12 + x * (self.width() - 24), 12 + y * (self.height() - 24))
            p.setPen(QPen(CYAN, 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(point, 9, 9)
            p.drawEllipse(point, 2, 2)


class ModeSurface(QWidget):
    ROWS = (tuple("1234567890"), tuple("QWERTYUIOP"), tuple("ASDFGHJKL"),
            tuple("ZXCVBNM"), ("Space", "Backspace", "Enter"))

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(225)
        self.mode = "Drawing"
        self.strokes = []
        self.active = None
        self.cursor = None

    def rects(self):
        for row, keys in enumerate(self.ROWS):
            for column, key in enumerate(keys):
                yield key, QRectF(column / len(keys), row / len(self.ROWS),
                                  1 / len(keys), 1 / len(self.ROWS))

    def select(self, position):
        if position:
            point = QPointF(*position)
            return next((key for key, rect in self.rects() if rect.contains(point)), None)
        return None

    def stroke(self, point):
        if self.active is None:
            path = QPainterPath(QPointF(*point))
            self.active = (point, path)
            self.strokes.append(self.active)
            if len(self.strokes) > 180:
                self.strokes.pop(0)
        else:
            _, path = self.active
            path.lineTo(QPointF(*point))
            if path.elementCount() >= 4000:
                self.active = None
                self.stroke(point)

    def scale(self, point):
        return QPointF(point[0] * self.width(), point[1] * self.height())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#0a111e"))
        if self.mode == "Keyboard":
            hovered = self.select(self.cursor)
            for key, rect in self.rects():
                cell = QRectF(rect.x() * self.width(), rect.y() * self.height(),
                              rect.width() * self.width(), rect.height() * self.height()).adjusted(3, 3, -3, -3)
                p.setPen(CYAN if key == hovered else GRID)
                p.setBrush(QColor("#153347" if key == hovered else "#131e30"))
                p.drawRoundedRect(cell, 7, 7)
                p.setPen(WHITE)
                p.drawText(cell, Qt.AlignmentFlag.AlignCenter, key)
        else:
            p.setPen(QPen(GRID, 1, Qt.PenStyle.DotLine))
            for x in range(20, self.width(), 20):
                p.drawLine(x, 0, x, self.height())
            for y in range(20, self.height(), 20):
                p.drawLine(0, y, self.width(), y)
            pen = QPen(CYAN, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            pen.setCosmetic(True)
            p.save()
            p.scale(self.width(), self.height())
            p.setPen(pen)
            for origin, path in self.strokes:
                p.drawPoint(QPointF(*origin))
                p.drawPath(path)
            p.restore()
        if self.cursor:
            p.setPen(QPen(CYAN, 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(self.scale(self.cursor), 6, 6)
