"""
Graph visuals: AgentNode, DirectorNode, Connection.

Fix vs. V1: connections now register themselves with both endpoint
nodes, and each node's itemChange() calls prepareGeometryChange() +
update() on every attached connection when the node moves. Previously
the connection's boundingRect() read the *other* item's live pos()
without ever telling Qt its own cached geometry was stale, which is
exactly the kind of thing that causes stale/ghosted line segments
while dragging.
"""

from enum import Enum

from PyQt6.QtCore import Qt, QPointF, QRectF, QVariantAnimation, QEasingCurve
from PyQt6.QtGui import QColor, QPen, QBrush, QFont, QPainter, QRadialGradient
from PyQt6.QtWidgets import QGraphicsObject, QGraphicsItem

from config import AGENT_CONFIGS


class AgentStatus(str, Enum):
    OFFLINE = "OFFLINE"
    IDLE = "IDLE"
    THINKING = "THINKING"
    EXECUTING = "EXECUTING"
    DONE = "DONE"
    ERROR = "ERROR"


STATUS_COLORS = {
    AgentStatus.OFFLINE: QColor("#3a3f4b"),
    AgentStatus.IDLE: QColor("#6b7280"),
    AgentStatus.THINKING: QColor("#4fa3ff"),
    AgentStatus.EXECUTING: QColor("#f2a93b"),
    AgentStatus.DONE: QColor("#2fd18f"),
    AgentStatus.ERROR: QColor("#ff5c5c"),
}


class _MovableNode(QGraphicsObject):
    """Shared base: tracks attached connections and notifies them on move."""

    def __init__(self):
        super().__init__()
        self._connections: list["Connection"] = []
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    def register_connection(self, conn: "Connection"):
        self._connections.append(conn)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for conn in self._connections:
                conn.prepareGeometryChange()
                conn.update()
        return super().itemChange(change, value)


class AgentNode(_MovableNode):
    clicked_signal_owner = None  # set by MainWindow via a plain callback, see set_click_handler

    RADIUS = 42

    def __init__(self, key: str, cfg: dict, available: bool, x: float, y: float):
        super().__init__()
        self.key = key
        self.cfg = cfg
        self.status = AgentStatus.IDLE if available else AgentStatus.OFFLINE
        self.tokens_per_sec = 0.0
        self.setPos(x, y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self._click_handler = None

    def set_click_handler(self, fn):
        self._click_handler = fn

    def boundingRect(self) -> QRectF:
        r = self.RADIUS + 10
        return QRectF(-r, -r - 26, 2 * r, 2 * r + 66)

    def set_status(self, status: AgentStatus):
        if self.status == AgentStatus.OFFLINE:
            return
        self.status = status
        self.update()

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.RADIUS
        color = STATUS_COLORS[self.status]

        if self.status in (AgentStatus.THINKING, AgentStatus.EXECUTING):
            glow = QRadialGradient(QPointF(0, 0), r * 1.9)
            c1 = QColor(color); c1.setAlpha(120)
            c2 = QColor(color); c2.setAlpha(0)
            glow.setColorAt(0.0, c1)
            glow.setColorAt(1.0, c2)
            painter.setBrush(QBrush(glow))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(0, 0), r * 1.9, r * 1.9)

        body_grad = QRadialGradient(QPointF(-r * 0.3, -r * 0.3), r * 1.4)
        body_grad.setColorAt(0.0, QColor("#20242f"))
        body_grad.setColorAt(1.0, QColor("#12141c"))
        painter.setBrush(QBrush(body_grad))
        pen = QPen(color, 3)
        if self.status == AgentStatus.OFFLINE:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawEllipse(QPointF(0, 0), r, r)

        painter.setPen(QPen(color, 0))
        painter.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        painter.drawText(QRectF(-r, -12, 2 * r, 24), Qt.AlignmentFlag.AlignCenter, self.status.value)

        painter.setPen(QPen(QColor("#e6e8ee")))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.drawText(QRectF(-70, r + 6, 140, 18), Qt.AlignmentFlag.AlignCenter, self.cfg["name"])
        painter.setPen(QPen(QColor("#9aa0ad")))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(QRectF(-70, r + 22, 140, 16), Qt.AlignmentFlag.AlignCenter, self.cfg["role"])

        if self.tokens_per_sec > 0.1:
            painter.setPen(QPen(QColor("#6b7280")))
            painter.setFont(QFont("Consolas", 7))
            painter.drawText(QRectF(-70, r + 38, 140, 14), Qt.AlignmentFlag.AlignCenter,
                              f"{self.tokens_per_sec:0.1f} tok/s")

    def mousePressEvent(self, event):
        if self._click_handler:
            self._click_handler(self.key)
        super().mousePressEvent(event)


class DirectorNode(_MovableNode):
    RADIUS = 30

    def __init__(self, x: float, y: float):
        super().__init__()
        self.setPos(x, y)
        self.active = False
        self.cycle_text = ""

    def boundingRect(self) -> QRectF:
        r = self.RADIUS + 10
        return QRectF(-r, -r, 2 * r, 2 * r + 40)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.RADIUS
        color = QColor("#e6c15c") if self.active else QColor("#8b7a45")
        grad = QRadialGradient(QPointF(0, 0), r * 1.3)
        grad.setColorAt(0.0, QColor("#2a2620"))
        grad.setColorAt(1.0, QColor("#14120e"))
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(color, 3))
        painter.drawEllipse(QPointF(0, 0), r, r)
        painter.setPen(QPen(color))
        painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        painter.drawText(QRectF(-r, -8, 2 * r, 16), Qt.AlignmentFlag.AlignCenter, "DIRECTOR")
        painter.setPen(QPen(QColor("#e6e8ee")))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.drawText(QRectF(-60, r + 4, 120, 16), Qt.AlignmentFlag.AlignCenter, "SWARM DIRECTOR")
        if self.cycle_text:
            painter.setPen(QPen(QColor("#9aa0ad")))
            painter.setFont(QFont("Consolas", 8))
            painter.drawText(QRectF(-60, r + 20, 120, 16), Qt.AlignmentFlag.AlignCenter, self.cycle_text)


PULSE_COLORS = {
    "THINK": "#4fa3ff",
    "TOOL": "#f2a93b",
    "VERIFY": "#ff5c5c",
    "SUCCESS": "#2fd18f",
}


class Connection(QGraphicsObject):
    """Line between two nodes with a traveling particle fired on demand.
    Registers itself with both endpoints so moving either one keeps
    this item's geometry correctly invalidated (see _MovableNode)."""

    def __init__(self, node_a: _MovableNode, node_b: _MovableNode, base_color="#232733"):
        super().__init__()
        self.node_a = node_a
        self.node_b = node_b
        node_a.register_connection(self)
        node_b.register_connection(self)
        self.base_color = QColor(base_color)
        self.setZValue(-1)
        self._particle_t = None
        self._particle_color = QColor(PULSE_COLORS["THINK"])
        self._anim = QVariantAnimation()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(600)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.valueChanged.connect(self._on_anim_value)
        self._anim.finished.connect(self._on_anim_finished)

    def boundingRect(self) -> QRectF:
        p1, p2 = self.node_a.pos(), self.node_b.pos()
        return QRectF(p1, p2).normalized().adjusted(-20, -20, 20, 20)

    def fire_pulse(self, kind: str):
        self._particle_color = QColor(PULSE_COLORS.get(kind, PULSE_COLORS["THINK"]))
        self.prepareGeometryChange()
        self._anim.stop()
        self._anim.start()

    def _on_anim_value(self, v):
        self._particle_t = v
        self.update()

    def _on_anim_finished(self):
        self._particle_t = None
        self.update()

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        p1, p2 = self.node_a.pos(), self.node_b.pos()
        painter.setPen(QPen(self.base_color, 1.4))
        painter.drawLine(p1, p2)
        if self._particle_t is not None:
            x = p1.x() + (p2.x() - p1.x()) * self._particle_t
            y = p1.y() + (p2.y() - p1.y()) * self._particle_t
            glow = QRadialGradient(QPointF(x, y), 12)
            c1 = QColor(self._particle_color); c1.setAlpha(220)
            c2 = QColor(self._particle_color); c2.setAlpha(0)
            glow.setColorAt(0.0, c1)
            glow.setColorAt(1.0, c2)
            painter.setBrush(QBrush(glow))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(x, y), 12, 12)
            painter.setBrush(QBrush(self._particle_color))
            painter.drawEllipse(QPointF(x, y), 3.5, 3.5)
