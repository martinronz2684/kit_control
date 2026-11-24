import QtQuick

// Zeichnet eine Schicht: Konturen hell, Schraffur Petrol. data = {contour: [x0,y0,x1,y1,…], infill: […]}
Canvas {
    id: lv
    property var layer: ({})
    property real plateMm: 110
    onLayerChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        var g = getContext("2d")
        g.reset()
        var k = Math.min(width, height) / (plateMm * 1.08), cx = width / 2, cy = height / 2
        var half = plateMm / 2 * k
        g.fillStyle = "#0f1317"
        g.fillRect(cx - half, cy - half, 2 * half, 2 * half)
        g.strokeStyle = "#1b2026"; g.lineWidth = 1
        for (var v = -50; v <= 50; v += 10) {
            g.beginPath(); g.moveTo(cx + v * k, cy - half); g.lineTo(cx + v * k, cy + half); g.stroke()
            g.beginPath(); g.moveTo(cx - half, cy + v * k); g.lineTo(cx + half, cy + v * k); g.stroke()
        }
        g.strokeStyle = "#2c3640"; g.lineWidth = 1.5
        g.strokeRect(cx - half, cy - half, 2 * half, 2 * half)
        function lines(a, col, w) {
            if (!a || a.length < 4) return
            g.strokeStyle = col; g.lineWidth = w
            g.beginPath()
            for (var i = 0; i + 3 < a.length; i += 4) {
                g.moveTo(cx + a[i] * k, cy - a[i + 1] * k)
                g.lineTo(cx + a[i + 2] * k, cy - a[i + 3] * k)
            }
            g.stroke()
        }
        lines(lv.layer.infill, "rgba(38,148,184,0.85)", Math.max(0.5, 0.12 * k))
        lines(lv.layer.contour, "#d8f3fc", 1.3)
    }
}
