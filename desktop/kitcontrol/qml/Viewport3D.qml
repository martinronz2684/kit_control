import QtQuick

// Drehbare 3D-Ansicht des Bauraums (gezeichnet im Canvas, läuft ohne Grafiktreiber-Abhängigkeiten).
// Ziehen auf einem Bauteil: verschieben · Ziehen daneben: drehen · rechte Maustaste: schieben · Mausrad: zoomen
Canvas {
    id: vp
    property var parts: []
    property int sel: -1
    property real plate: 110
    property real idealXY: 90
    property real idealZ: 110
    property real yaw: -32
    property real elev: 26
    property real zoom: 1.0
    property real panX: 0
    property real panY: 0
    property var cache: ({})
    property var picks: []
    signal picked(int index)
    signal moved(int index, real x, real y, bool first)

    onPartsChanged: requestPaint()
    onSelChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    function setView(name) {
        if (name === "top") { yaw = 0; elev = 90 }
        else if (name === "front") { yaw = 0; elev = 0 }
        else if (name === "right") { yaw = -90; elev = 0 }
        else { yaw = -32; elev = 26 }
        zoom = 1; panX = 0; panY = 0
        requestPaint()
    }

    function scale() { return Math.min(width, height) / 175 * zoom }

    function mesh(i, p) {
        var m = cache[p.mesh_key]
        if (m === undefined) {
            m = backend.partMesh(i)
            cache[p.mesh_key] = m
        }
        return m
    }

    onPaint: {
        var g = getContext("2d")
        g.reset()
        var k = scale()
        var cx = width / 2 + panX, cy = height * 0.62 + panY
        var yr = yaw * Math.PI / 180, er = elev * Math.PI / 180
        var cyw = Math.cos(yr), syw = Math.sin(yr), ce = Math.cos(er), se = Math.sin(er)
        var tz = 40   // Drehpunkt in der Höhe
        // Welt -> Bild: [x, y, Tiefe]
        function P(x, y, z) {
            var x1 = x * cyw - y * syw, y1 = x * syw + y * cyw, dz = z - tz
            return [cx + x1 * k, cy - (y1 * se + dz * ce) * k, y1 * ce - dz * se]
        }
        function line(a, b) { g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]) }

        // Bauplatte mit Raster
        var h = plate / 2
        var c0 = P(-h, -h, 0), c1 = P(h, -h, 0), c2 = P(h, h, 0), c3 = P(-h, h, 0)
        g.fillStyle = "#11161b"
        g.beginPath(); g.moveTo(c0[0], c0[1]); g.lineTo(c1[0], c1[1]); g.lineTo(c2[0], c2[1]); g.lineTo(c3[0], c3[1]); g.closePath(); g.fill()
        g.strokeStyle = "#1e252c"; g.lineWidth = 1
        g.beginPath()
        for (var v = -h + 10; v < h; v += 10) { line(P(v, -h, 0), P(v, h, 0)); line(P(-h, v, 0), P(h, v, 0)) }
        g.stroke()
        g.strokeStyle = "#34404a"; g.lineWidth = 1.4
        g.beginPath(); g.moveTo(c0[0], c0[1]); g.lineTo(c1[0], c1[1]); g.lineTo(c2[0], c2[1]); g.lineTo(c3[0], c3[1]); g.closePath(); g.stroke()

        // Dreiecke aller Bauteile sammeln
        var tris = []
        for (var i = 0; i < parts.length; i++) {
            var p = parts[i], m = mesh(i, p)
            if (!m) continue
            for (var t = 0; t + 8 < m.length; t += 9) {
                var a = P(m[t] + p.x, m[t + 1] + p.y, m[t + 2] + p.z)
                var b = P(m[t + 3] + p.x, m[t + 4] + p.y, m[t + 5] + p.z)
                var c = P(m[t + 6] + p.x, m[t + 7] + p.y, m[t + 8] + p.z)
                // Normale im Bildraum (x rechts, y oben, z Tiefe) für die Schattierung
                var ux = b[0] - a[0], uy = a[1] - b[1], uz = b[2] - a[2] * 1
                var wx = c[0] - a[0], wy = a[1] - c[1], wz = c[2] - a[2]
                uz *= k; wz *= k
                var nx = uy * wz - uz * wy, ny = uz * wx - ux * wz, nz = ux * wy - uy * wx
                var nl = Math.sqrt(nx * nx + ny * ny + nz * nz) || 1
                var lit = Math.abs((-0.35 * nx + 0.55 * ny - 0.76 * nz) / nl)
                tris.push([(a[2] + b[2] + c[2]) / 3, i, a, b, c, 0.28 + 0.72 * lit])
            }
        }
        tris.sort(function(u, w) { return w[0] - u[0] })
        var pk = []
        for (var j = 0; j < tris.length; j++) {
            var T = tris[j], s = T[5], selp = T[1] === sel
            var r = Math.round((selp ? 120 : 38) * s), gg = Math.round((selp ? 205 : 148) * s), bb = Math.round((selp ? 235 : 184) * s)
            g.fillStyle = "rgb(" + r + "," + gg + "," + bb + ")"
            g.strokeStyle = g.fillStyle
            g.lineWidth = 0.6
            g.beginPath(); g.moveTo(T[2][0], T[2][1]); g.lineTo(T[3][0], T[3][1]); g.lineTo(T[4][0], T[4][1]); g.closePath()
            g.fill(); g.stroke()
            pk.push([T[1], T[2][0], T[2][1], T[3][0], T[3][1], T[4][0], T[4][1]])
        }
        picks = pk

        // Idealer Druckbereich als hellgrauer Korb
        var hx = idealXY / 2, z1 = idealZ
        var q = [P(-hx, -hx, 0), P(hx, -hx, 0), P(hx, hx, 0), P(-hx, hx, 0),
                 P(-hx, -hx, z1), P(hx, -hx, z1), P(hx, hx, z1), P(-hx, hx, z1)]
        g.strokeStyle = "rgba(205,210,216,0.55)"; g.lineWidth = 1.2
        g.beginPath()
        for (var e = 0; e < 4; e++) { line(q[e], q[(e + 1) % 4]); line(q[e + 4], q[(e + 1) % 4 + 4]); line(q[e], q[e + 4]) }
        g.stroke()
        // Korbgitter an den Seiten (dezent)
        g.strokeStyle = "rgba(205,210,216,0.12)"; g.lineWidth = 1
        g.beginPath()
        for (var zz = 10; zz < z1; zz += 10) {
            line(P(-hx, -hx, zz), P(hx, -hx, zz)); line(P(hx, -hx, zz), P(hx, hx, zz))
            line(P(hx, hx, zz), P(-hx, hx, zz)); line(P(-hx, hx, zz), P(-hx, -hx, zz))
        }
        g.stroke()
        g.fillStyle = "rgba(205,210,216,0.7)"; g.font = "11px sans-serif"
        g.fillText(idealXY + " × " + idealXY + " × " + idealZ + " mm", q[7][0] + 6, q[7][1] - 4)
    }

    function hit(mx, my) {
        function side(ax, ay, bx, by, px, py) { return (bx - ax) * (py - ay) - (by - ay) * (px - ax) }
        for (var i = picks.length - 1; i >= 0; i--) {
            var t = picks[i]
            var d1 = side(t[1], t[2], t[3], t[4], mx, my), d2 = side(t[3], t[4], t[5], t[6], mx, my), d3 = side(t[5], t[6], t[1], t[2], mx, my)
            var neg = d1 < 0 || d2 < 0 || d3 < 0, pos = d1 > 0 || d2 > 0 || d3 > 0
            if (!(neg && pos)) return t[0]
        }
        return -1
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
        property int idx: -1
        property real lx; property real ly; property real sx; property real sy
        property real px; property real py
        property bool first: true
        property int mode: 0     // 1 verschieben, 2 drehen, 3 schieben
        cursorShape: mode === 1 ? Qt.ClosedHandCursor : (mode === 2 ? Qt.SizeAllCursor : Qt.ArrowCursor)
        onPressed: (m) => {
            lx = m.x; ly = m.y; sx = m.x; sy = m.y
            if (m.button === Qt.LeftButton) {
                idx = vp.hit(m.x, m.y)
                vp.picked(idx)
                if (idx >= 0) { mode = 1; px = vp.parts[idx].x; py = vp.parts[idx].y; first = true }
                else mode = 2
            } else mode = 3
        }
        onPositionChanged: (m) => {
            if (mode === 1) {
                var k = vp.scale(), yr = vp.yaw * Math.PI / 180
                var se = Math.max(0.25, Math.sin(vp.elev * Math.PI / 180))
                var x1 = (m.x - sx) / k, y1 = (sy - m.y) / (k * se)
                var dx = x1 * Math.cos(yr) + y1 * Math.sin(yr), dy = -x1 * Math.sin(yr) + y1 * Math.cos(yr)
                if (first && Math.abs(dx) + Math.abs(dy) < 0.3) return
                vp.moved(idx, Math.round((px + dx) * 10) / 10, Math.round((py + dy) * 10) / 10, first)
                first = false
            } else if (mode === 2) {
                vp.yaw += (m.x - lx) * 0.4
                vp.elev = Math.max(0, Math.min(90, vp.elev + (m.y - ly) * 0.3))
                vp.requestPaint()
            } else if (mode === 3) {
                vp.panX += m.x - lx; vp.panY += m.y - ly
                vp.requestPaint()
            }
            lx = m.x; ly = m.y
        }
        onReleased: { mode = 0; idx = -1 }
        onDoubleClicked: (m) => { if (vp.hit(m.x, m.y) < 0) vp.setView("iso") }
        onWheel: (w) => {
            vp.zoom = Math.max(0.4, Math.min(8, vp.zoom * (w.angleDelta.y > 0 ? 1.12 : 1 / 1.12)))
            vp.requestPaint()
        }
    }
}
