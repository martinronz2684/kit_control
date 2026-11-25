import QtQuick
import QtQuick3D
import KitControl 1.0

// 3D-Ansicht auf der Grafikkarte: volle Auflösung, Kopien teilen sich ein Netz.
// Koordinaten wie im Slicer (mm, Z nach oben); der Knoten „world“ dreht sie in das Y-oben-System von Qt.
Item {
    id: vg
    property var parts: []
    property int sel: -1
    property real plate: 110
    property real idealXY: 90
    property real idealZ: 110
    property real machineZ: 110
    property real yaw: -32
    property real elev: 26
    property real dist: 330
    property real tx: 0
    property real ty: 0
    property real tz: 40
    objectName: "viewport"
    signal picked(int index)                       // einfacher Klick (Auswahl ersetzen)
    signal pickedMode(int index, string mode)      // "toggle" (Strg) / "add" (Umschalt)
    signal groupMoved(int lead, real dx, real dy, real dz)
    signal contextMenu(int index, real x, real y)
    signal boxSelected(var indices, bool add)
    property bool editable: true                   // false: nur ansehen (Vorschau)
    property real cutZ: 100000                     // Schnitthöhe in mm (darüber ausgeblendet)
    property bool dragGroup: false                 // mehrere ausgewählte Teile werden gemeinsam gezogen
    property rect band: Qt.rect(0, 0, 0, 0)        // Auswahlrahmen (Umschalt + Ziehen)
    signal moved(int index, real x, real y, bool first)
    property int dragIdx: -1          // Teil, das gerade gezogen wird (nur Anzeige, gespeichert beim Loslassen)
    property real dragDx: 0
    property real dragDy: 0
    property real dragDz: 0
    signal moved3(int index, real x, real y, real z)

    function setView(name) {
        if (name === "top") { yaw = 0; elev = 90 }
        else if (name === "front") { yaw = 0; elev = 0 }
        else if (name === "right") { yaw = 90; elev = 0 }
        else { yaw = -32; elev = 26 }
        dist = 330; tx = 0; ty = 0; tz = 40
    }

    function box(hx, hy, h) {
        var c = [[-hx, -hy], [hx, -hy], [hx, hy], [-hx, hy]], s = []
        for (var i = 0; i < 4; i++) {
            var a = c[i], b = c[(i + 1) % 4]
            s.push(a[0], a[1], 0, b[0], b[1], 0)
            s.push(a[0], a[1], h, b[0], b[1], h)
            s.push(a[0], a[1], 0, a[0], a[1], h)
        }
        return s
    }
    function grid() {
        var s = [], h = plate / 2
        for (var v = -h + 10; v < h; v += 10) { s.push(v, -h, 0.02, v, h, 0.02); s.push(-h, v, 0.02, h, v, 0.02) }
        return s
    }
    function cageRings() {
        var s = [], hx = idealXY / 2
        for (var z = 10; z < idealZ; z += 10) {
            s.push(-hx, -hx, z, hx, -hx, z, hx, -hx, z, hx, hx, z, hx, hx, z, -hx, hx, z, -hx, hx, z, -hx, -hx, z)
        }
        return s
    }
    // Bildpunkt -> Strahl in Slicer-Koordinaten [a, b]
    function ray(mx, my) {
        var a = v3.mapTo3DScene(Qt.vector3d(mx, my, 0)), b = v3.mapTo3DScene(Qt.vector3d(mx, my, 1000))
        return [world.mapPositionFromScene(a), world.mapPositionFromScene(b)]
    }
    // Slicer-Koordinaten -> Bildpunkt (für die automatische Prüfung)
    function screenPoint(x, y, z) {
        var p = v3.mapFrom3DScene(world.mapPositionToScene(Qt.vector3d(x, y, z)))
        return Qt.point(p.x, p.y)
    }
    function pickAt(mx, my) {
        var r = ray(mx, my)
        var i = (typeof backend !== "undefined" && backend) ? backend.pickPart(r[0].x, r[0].y, r[0].z, r[1].x, r[1].y, r[1].z) : -1
        if (i < 0) {
            var h = v3.pick(mx, my)
            if (h.objectHit && h.objectHit.partIndex !== undefined) i = h.objectHit.partIndex
        }
        return i
    }
    // Bildpunkt -> Punkt auf einer senkrechten Ebene durch p0, quer zur Blickrichtung (Ansicht von vorne/seitlich)
    function wall(mx, my, p0, n) {
        var r = ray(mx, my), a = r[0], d = r[1].minus(r[0])
        var den = d.x * n.x + d.y * n.y
        if (Math.abs(den) < 1e-9) return null
        var t = ((p0.x - a.x) * n.x + (p0.y - a.y) * n.y) / den
        return Qt.vector3d(a.x + d.x * t, a.y + d.y * t, a.z + d.z * t)
    }
    // Bildpunkt -> Punkt auf der waagrechten Ebene z = z0 (Slicer-Koordinaten)
    function ground(mx, my, z0) {
        var r = ray(mx, my), oa = r[0], ob = r[1]
        if (Math.abs(ob.z - oa.z) < 1e-9) return null
        var t = (z0 - oa.z) / (ob.z - oa.z)
        return Qt.vector3d(oa.x + (ob.x - oa.x) * t, oa.y + (ob.y - oa.y) * t, z0)
    }

    View3D {
        id: v3
        anchors.fill: parent
        camera: cam                     // ohne feste Kamera liefern pick()/mapTo3DScene() nichts -> kein Anklicken/Ziehen
        environment: SceneEnvironment {
            clearColor: win.c3d
            backgroundMode: SceneEnvironment.Color
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.High
        }

        Node {
            id: orbit
            position: Qt.vector3d(vg.tx, vg.tz, -vg.ty)
            eulerRotation: Qt.vector3d(-vg.elev, vg.yaw, 0)
            PerspectiveCamera {
                id: cam
                position: Qt.vector3d(0, 0, vg.dist)
                fieldOfView: 32
                clipNear: 1
                clipFar: 6000
            }
            DirectionalLight {
                eulerRotation: Qt.vector3d(-25, -20, 0)
                brightness: 0.95
                ambientColor: Qt.rgba(0.30, 0.32, 0.36, 1)
            }
        }
        DirectionalLight { eulerRotation: Qt.vector3d(-70, 140, 0); brightness: 0.35 }

        Node {
            id: world
            eulerRotation.x: -90

            // Bauplatte
            Model {
                source: "#Rectangle"
                scale: Qt.vector3d(vg.plate / 100, vg.plate / 100, 1)
                position: Qt.vector3d(0, 0, -0.05)
                materials: DefaultMaterial { diffuseColor: win.light ? "#dde8ee" : "#16252c"; lighting: DefaultMaterial.NoLighting }
            }
            Model {
                geometry: LineGeometry { segments: vg.grid() }
                materials: DefaultMaterial { diffuseColor: win.light ? "#c9d6de" : "#22333f"; lighting: DefaultMaterial.NoLighting }
            }
            // Maschinengrenzen (bläulich) und idealer Bereich (hellgrauer Korb)
            Model {
                geometry: LineGeometry { segments: vg.box(vg.plate / 2, vg.plate / 2, vg.machineZ) }
                materials: DefaultMaterial { diffuseColor: win.light ? "#4c86a6" : "#5a8aa6"; lighting: DefaultMaterial.NoLighting }
            }
            Model {
                geometry: LineGeometry { segments: vg.box(vg.idealXY / 2, vg.idealXY / 2, vg.idealZ) }
                materials: DefaultMaterial { diffuseColor: win.light ? "#6d7884" : "#cfd4da"; lighting: DefaultMaterial.NoLighting }
            }
            Model {
                visible: false                  // waagrechte Höhenlinien im Korb aus (stören beim Ansehen)
                geometry: LineGeometry { segments: vg.cageRings() }
                materials: DefaultMaterial { diffuseColor: "#3a3f46"; lighting: DefaultMaterial.NoLighting }
            }

            Model {
                visible: vg.cutZ < 10000
                source: "#Rectangle"
                position: Qt.vector3d(0, 0, vg.cutZ)
                scale: Qt.vector3d(vg.idealXY / 100, vg.idealXY / 100, 1)
                materials: DefaultMaterial { diffuseColor: "#2694b8"; opacity: 0.18; lighting: DefaultMaterial.NoLighting; cullMode: Material.NoCulling }
            }
            Repeater3D {
                model: vg.parts
                delegate: Model {
                    property int partIndex: index
                    pickable: true
                    geometry: MeshGeometry { key: modelData.gkey }
                    readonly property bool moving: vg.dragIdx >= 0 && (index === vg.dragIdx || (vg.dragGroup && modelData.picked))
                    position: Qt.vector3d(modelData.pos[0] + (moving ? vg.dragDx : 0),
                                          modelData.pos[1] + (moving ? vg.dragDy : 0),
                                          modelData.pos[2] + (moving ? vg.dragDz : 0))
                    rotation: Qt.quaternion(modelData.quat[0], modelData.quat[1], modelData.quat[2], modelData.quat[3])
                    scale: Qt.vector3d(modelData.scale3[0], modelData.scale3[1], modelData.scale3[2])
                    materials: CustomMaterial {
                        // Farben mit Bedeutung: rot = überlappt, orange = außerhalb des idealen Bereichs,
                        // grau-blau = gesperrt; ausgewählt jeweils heller. Schnittebene: cut.frag
                        readonly property bool hi: modelData.picked || index === vg.sel
                        property color baseColor: modelData.status === "overlap" ? (hi ? "#f39a9d" : "#d9464c")
                                 : modelData.status === "outside" ? (hi ? "#f7c987" : "#e3962f")
                                 : (modelData.lock_pos || modelData.lock_orient) ? (hi ? "#b9cbd3" : "#6f8792")
                                 : (hi ? "#8adaf2" : "#2a9cc2")
                        property real cutZ: vg.cutZ
                        shadingMode: CustomMaterial.Shaded
                        cullMode: Material.NoCulling
                        fragmentShader: "cut.frag"
                    }
                }
            }
        }
    }

    Text {
        // rechts oben neben den Ansichts-Tasten (ca. 300 px); wird bei schmalem Fenster umgebrochen statt überlappt
        // eine Zeile unter den Ansichts-Tasten (dort ist immer Platz), notfalls gekürzt
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        anchors.leftMargin: 16; anchors.rightMargin: 16; anchors.topMargin: 56
        elide: Text.ElideRight
        text: win.t("hellgrau: idealer Bereich ") + vg.idealXY + " × " + vg.idealXY + " × " + vg.idealZ + win.t(" mm · bläulich: Bauraum ") + vg.plate + " × " + vg.plate + " × " + vg.machineZ + win.t(" mm")
        color: win.cMut2; font.pixelSize: 11
    }

    function centerOf(i) {
        var p = parts[i]
        return screenPoint(p.x, p.y, p.z + p.size[2] / 2)
    }

    // Auswahlrahmen
    Rectangle {
        visible: vg.band.width > 2 || vg.band.height > 2
        x: vg.band.x; y: vg.band.y; width: vg.band.width; height: vg.band.height
        color: "#262694b8"; border.color: "#2694b8"; border.width: 1; radius: 3
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
        property int idx: -1
        property int mode: 0          // 1 verschieben, 2 drehen, 3 schieben, 4 Rahmen
        property real lx; property real ly
        property real sx; property real sy
        property real px; property real py; property real pz
        property var g0: null
        property bool upright: false
        property var wn: null
        property bool first: true
        property bool addMode: false
        cursorShape: mode === 1 ? Qt.ClosedHandCursor : (mode === 2 ? Qt.SizeAllCursor : Qt.ArrowCursor)
        onPressed: (m) => {
            lx = m.x; ly = m.y; sx = m.x; sy = m.y
            vg.forceActiveFocus()
            if (m.button === Qt.LeftButton) {
                idx = vg.pickAt(m.x, m.y)
                if (m.modifiers & Qt.ControlModifier) {          // Strg: zur Auswahl hinzufügen / entfernen
                    if (idx >= 0) vg.pickedMode(idx, "toggle")
                    mode = 0
                    return
                }
                if ((m.modifiers & Qt.ShiftModifier) && idx < 0) {   // Umschalt + Ziehen auf leerem Grund: Rahmen
                    mode = 4; addMode = true
                    vg.band = Qt.rect(m.x, m.y, 0, 0)
                    return
                }
                if (idx >= 0 && !vg.editable) idx = -1
                if (idx >= 0) {
                    var p = vg.parts[idx]
                    if (!p.picked) vg.picked(idx)
                    vg.dragGroup = p.picked === true
                    px = p.x; py = p.y; pz = p.z
                    // steil von oben: auf der Platte schieben; flach von vorne/seitlich: in der Bildebene
                    // (links/rechts und hoch/runter = Höhe über Platte)
                    upright = vg.elev < 35
                    if (upright) {
                        var r0 = vg.ray(m.x, m.y), dd = r0[1].minus(r0[0])
                        var len = Math.sqrt(dd.x * dd.x + dd.y * dd.y)
                        wn = len > 1e-9 ? Qt.vector3d(dd.x / len, dd.y / len, 0) : Qt.vector3d(0, 1, 0)
                        g0 = vg.wall(m.x, m.y, Qt.vector3d(px, py, pz), wn)
                    } else
                        g0 = vg.ground(m.x, m.y, pz)
                    mode = g0 ? 1 : 2
                    first = true
                } else mode = 2
            } else {
                mode = 3
                g0 = vg.ground(m.x, m.y, vg.tz)
            }
        }
        onPositionChanged: (m) => {
            if (mode === 1) {
                var g = upright ? vg.wall(m.x, m.y, Qt.vector3d(px, py, pz), wn) : vg.ground(m.x, m.y, pz)
                if (!g) return
                var dx = g.x - g0.x, dy = g.y - g0.y, dz = upright ? Math.max(-pz, g.z - g0.z) : 0
                if (first && Math.abs(dx) + Math.abs(dy) + Math.abs(dz) < 0.3) return
                vg.dragIdx = idx; vg.dragDx = dx; vg.dragDy = dy; vg.dragDz = dz   // flüssig nur in der Anzeige
                first = false
            } else if (mode === 2) {
                vg.yaw -= (m.x - lx) * 0.4
                vg.elev = Math.max(-10, Math.min(90, vg.elev + (m.y - ly) * 0.3))
            } else if (mode === 3 && g0) {
                var g2 = vg.ground(m.x, m.y, vg.tz)
                if (g2) { vg.tx -= g2.x - g0.x; vg.ty -= g2.y - g0.y }
            } else if (mode === 4) {
                vg.band = Qt.rect(Math.min(sx, m.x), Math.min(sy, m.y), Math.abs(m.x - sx), Math.abs(m.y - sy))
            }
            lx = m.x; ly = m.y
        }
        onReleased: (m) => {
            if (mode === 1 && vg.dragIdx >= 0) {
                var i = vg.dragIdx
                var dx = Math.round(vg.dragDx * 10) / 10, dy = Math.round(vg.dragDy * 10) / 10, dz = Math.round(vg.dragDz * 10) / 10
                vg.dragIdx = -1; vg.dragDx = 0; vg.dragDy = 0; vg.dragDz = 0
                vg.groupMoved(i, dx, dy, dz)
            } else if (mode === 2 && m.button === Qt.LeftButton && Math.abs(m.x - sx) + Math.abs(m.y - sy) < 4) {
                vg.picked(-1)                                    // Klick ins Leere: Auswahl aufheben
            } else if (mode === 3 && Math.abs(m.x - sx) + Math.abs(m.y - sy) < 5) {
                // Rechtsklick ohne Ziehen: Menü für das Teil unter der Maus
                var hit = vg.pickAt(m.x, m.y)
                if (hit >= 0 && !vg.parts[hit].picked) vg.picked(hit)
                vg.contextMenu(hit, m.x, m.y)
            } else if (mode === 4) {
                var r = vg.band, sel = []
                for (var k = 0; k < vg.parts.length; k++) {
                    var c = vg.centerOf(k)
                    if (c.x >= r.x && c.x <= r.x + r.width && c.y >= r.y && c.y <= r.y + r.height) sel.push(k)
                }
                vg.band = Qt.rect(0, 0, 0, 0)
                vg.boxSelected(sel, addMode)
            }
            mode = 0; idx = -1; vg.dragGroup = false
        }
        onDoubleClicked: (m) => { if (vg.pickAt(m.x, m.y) < 0) vg.setView("iso") }
        onWheel: (w) => { vg.dist = Math.max(60, Math.min(1500, vg.dist * (w.angleDelta.y > 0 ? 1 / 1.12 : 1.12))) }
    }
}
