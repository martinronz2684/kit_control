import QtQuick

// Temperaturverlauf der letzten Minuten: Oberfläche (orange) und Kammer (hell), Sollwerte gestrichelt.
Canvas {
    id: tcv
    property var data: backend.tempHistory || []
    implicitHeight: 70
    onDataChanged: requestPaint()
    onWidthChanged: requestPaint()
    onPaint: {
        var g = getContext("2d"); g.reset()
        var d = data, n = d.length
        g.strokeStyle = "rgba(255,255,255,0.06)"; g.lineWidth = 1
        for (var q = 1; q < 4; q++) { g.beginPath(); g.moveTo(0, height * q / 4); g.lineTo(width, height * q / 4); g.stroke() }
        if (n < 2) {
            g.fillStyle = "rgba(160,168,178,0.6)"; g.font = "11px sans-serif"
            g.fillText(win.t("Temperaturverlauf erscheint nach dem Verbinden"), 6, height / 2 + 4)
            return
        }
        var t0 = d[0][0], t1 = d[n - 1][0], lo = 1e9, hi = -1e9
        for (var i = 0; i < n; i++) for (var c = 1; c <= 4; c++) if (d[i][c] !== null) { lo = Math.min(lo, d[i][c]); hi = Math.max(hi, d[i][c]) }
        if (hi - lo < 10) { var m = (hi + lo) / 2; lo = m - 5; hi = m + 5 }
        function X(t) { return (t - t0) / Math.max(1, t1 - t0) * (width - 2) + 1 }
        function Y(v) { return height - 3 - (v - lo) / (hi - lo) * (height - 6) }
        function line(col, color, dash) {
            g.strokeStyle = color; g.lineWidth = dash ? 1 : 1.8
            g.setLineDash ? g.setLineDash(dash ? [4, 4] : []) : 0
            g.beginPath(); var started = false
            for (var k = 0; k < n; k++) {
                var v = d[k][col]; if (v === null) { started = false; continue }
                if (!started) { g.moveTo(X(d[k][0]), Y(v)); started = true } else g.lineTo(X(d[k][0]), Y(v))
            }
            g.stroke()
        }
        line(3, "rgba(255,143,61,0.55)", true)
        line(4, "rgba(205,210,216,0.45)", true)
        line(2, "rgba(205,210,216,0.9)", false)
        line(1, "#ff8f3d", false)
        g.fillStyle = "rgba(160,168,178,0.8)"; g.font = "10px sans-serif"
        g.fillText(Math.round(hi) + " °C", 4, 11); g.fillText(Math.round(lo) + " °C", 4, height - 4)
        g.fillText(Math.round((t1 - t0) / 60) + win.t(" min"), width - 34, height - 4)
    }
}
