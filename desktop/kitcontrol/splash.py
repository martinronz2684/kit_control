"""Ladefenster beim Programmstart (wie in Sintratec Central): Kit-Control-Logo, darunter zentriert
„by Rat3d“ und ein Ladebalken, der den Fortschritt beim Laden der Oberfläche zeigt."""
from __future__ import annotations

import os

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

W, H = 560, 340


class Splash(QSplashScreen):
    def __init__(self, assets: str, version: str = ""):
        self.assets = assets
        self.version = version
        self.value = 0.0
        self.text = ""
        super().__init__(self._background())
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

    def _background(self) -> QPixmap:
        pm = QPixmap(W, H)
        pm.fill(QColor("#0c0e11"))
        g = QPainter(pm)
        g.setRenderHint(QPainter.Antialiasing)
        g.setRenderHint(QPainter.SmoothPixmapTransform)
        bg = QLinearGradient(0, 0, 0, H)
        bg.setColorAt(0, QColor("#141a1f"))
        bg.setColorAt(1, QColor("#0c0f12"))
        g.fillRect(0, 0, W, H, bg)
        # dezenter Petrol-Schimmer hinter dem Logo
        glow = QLinearGradient(0, 0, W, 0)
        glow.setColorAt(0.0, QColor(38, 148, 184, 0))
        glow.setColorAt(0.5, QColor(38, 148, 184, 26))
        glow.setColorAt(1.0, QColor(38, 148, 184, 0))
        g.fillRect(0, 70, W, 110, glow)
        g.setPen(QPen(QColor("#262b33"), 1))
        g.drawRect(0, 0, W - 1, H - 1)
        # Kit-Control-Logo
        logo = QPixmap(os.path.join(self.assets, "logo.png"))
        if not logo.isNull():
            lw = 330
            lh = int(logo.height() * lw / max(1, logo.width()))
            g.drawPixmap(int((W - lw) / 2), 92, logo.scaledToWidth(lw, Qt.SmoothTransformation))
            y = 92 + lh + 18
        else:
            y = 150
        # „by [Ratte] Rat3d“ zentriert darunter
        f = QFont("Segoe UI", 10)
        f.setItalic(True)
        g.setFont(f)
        fm = g.fontMetrics()
        by_w = fm.horizontalAdvance("by")
        f2 = QFont("Segoe UI", 10)
        f2.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        rat_w, rat_h = 34, 26
        g.setFont(f2)
        name_w = g.fontMetrics().horizontalAdvance("Rat3d")
        total = by_w + 8 + rat_w + 8 + name_w
        x = (W - total) / 2
        g.setFont(f)
        g.setPen(QColor("#6b737d"))
        g.drawText(QRectF(x, y, by_w + 2, rat_h), Qt.AlignVCenter | Qt.AlignLeft, "by")
        x += by_w + 8
        try:
            from PySide6.QtSvg import QSvgRenderer
            r = QSvgRenderer(os.path.join(self.assets, "rat3d.svg"))
            if r.isValid():
                r.render(g, QRectF(x, y, rat_w, rat_h))
        except Exception:
            pass
        x += rat_w + 8
        g.setFont(f2)
        g.setPen(QColor("#9aa3ad"))
        g.drawText(QRectF(x, y, name_w + 4, rat_h), Qt.AlignVCenter | Qt.AlignLeft, "Rat3d")
        g.end()
        return pm

    def drawContents(self, g: QPainter) -> None:
        g.setRenderHint(QPainter.Antialiasing)
        # Ladebalken
        bx, by_, bw, bh = 60.0, H - 70.0, W - 120.0, 6.0
        track = QPainterPath()
        track.addRoundedRect(QRectF(bx, by_, bw, bh), 3, 3)
        g.fillPath(track, QColor("#232830"))
        v = max(0.0, min(1.0, self.value))
        if v > 0:
            fill = QPainterPath()
            fill.addRoundedRect(QRectF(bx, by_, max(bh, bw * v), bh), 3, 3)
            gr = QLinearGradient(QPointF(bx, 0), QPointF(bx + bw, 0))
            gr.setColorAt(0, QColor("#1f86aa"))
            gr.setColorAt(1, QColor("#3bb4d8"))
            g.fillPath(fill, gr)
        f = QFont("Segoe UI", 9)
        g.setFont(f)
        g.setPen(QColor("#8b9099"))
        g.drawText(QRectF(bx, by_ + 14, bw * 0.75, 20), Qt.AlignLeft | Qt.AlignVCenter, self.text)
        g.setPen(QColor("#59606b"))
        if self.version:
            g.drawText(QRectF(bx, by_ + 14, bw, 20), Qt.AlignRight | Qt.AlignVCenter, "Version " + self.version)

    def step(self, value: float, text: str = "") -> None:
        self.value = value
        if text:
            self.text = text
        self.repaint()
        QApplication.processEvents()
