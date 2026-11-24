import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: pg
    property var parts: backend.parts
    property var problems: backend.problems
    property int sel: backend.selected
    property var cur: sel >= 0 && sel < parts.length ? parts[sel] : null

    RowLayout {
        anchors.fill: parent
        spacing: 18

        // Bauplatte (Draufsicht)
        Card {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            Canvas {
                id: plate
                anchors.fill: parent
                anchors.margins: 18
                property real k: Math.min(width, height) / (backend.plateMm * 1.1)
                property real cx: width / 2
                property real cy: height / 2

                function hit(mx, my) {
                    var x = (mx - cx) / k, y = (cy - my) / k
                    for (var i = pg.parts.length - 1; i >= 0; i--) {
                        var p = pg.parts[i], o = p.outline, inside = false
                        for (var a = 0, b = o.length - 1; a < o.length; b = a++) {
                            var ya = o[a][1] + p.y, yb = o[b][1] + p.y
                            var xa = o[a][0] + p.x, xb = o[b][0] + p.x
                            if ((ya > y) !== (yb > y) && x < (xb - xa) * (y - ya) / (yb - ya) + xa) inside = !inside
                        }
                        if (inside) return i
                    }
                    return -1
                }

                onPaint: {
                    var g = getContext("2d")
                    g.reset()
                    var half = backend.plateMm / 2 * k
                    // Platte
                    g.fillStyle = "#0f1317"
                    g.fillRect(cx - half, cy - half, 2 * half, 2 * half)
                    g.strokeStyle = "#1b2026"; g.lineWidth = 1
                    for (var v = -50; v <= 50; v += 10) {
                        g.beginPath(); g.moveTo(cx + v * k, cy - half); g.lineTo(cx + v * k, cy + half); g.stroke()
                        g.beginPath(); g.moveTo(cx - half, cy + v * k); g.lineTo(cx + half, cy + v * k); g.stroke()
                    }
                    g.strokeStyle = "#2c3640"; g.lineWidth = 1.5
                    g.strokeRect(cx - half, cy - half, 2 * half, 2 * half)
                    // Mittelkreuz
                    g.strokeStyle = "#2a3b44"; g.lineWidth = 1
                    g.beginPath(); g.moveTo(cx - 8, cy); g.lineTo(cx + 8, cy); g.moveTo(cx, cy - 8); g.lineTo(cx, cy + 8); g.stroke()
                    // Bauteile
                    for (var i = 0; i < pg.parts.length; i++) {
                        var p = pg.parts[i], o = p.outline
                        if (o.length < 3) continue
                        g.beginPath()
                        for (var j = 0; j < o.length; j++) {
                            var X = cx + (o[j][0] + p.x) * k, Y = cy - (o[j][1] + p.y) * k
                            if (j === 0) g.moveTo(X, Y); else g.lineTo(X, Y)
                        }
                        g.closePath()
                        g.fillStyle = i === pg.sel ? "rgba(38,148,184,0.55)" : "rgba(38,148,184,0.25)"
                        g.fill()
                        g.strokeStyle = i === pg.sel ? "#7fd3ee" : "#2694b8"
                        g.lineWidth = i === pg.sel ? 2 : 1.2
                        g.stroke()
                    }
                    // Maßstab
                    g.fillStyle = "#59606b"; g.font = "11px sans-serif"
                    g.fillText(backend.plateMm + " × " + backend.plateMm + " mm", cx - half, cy + half + 14)
                }
                onWidthChanged: requestPaint()
                onHeightChanged: requestPaint()
                Connections { target: backend; function onPartsChanged() { plate.requestPaint() } }

                MouseArea {
                    anchors.fill: parent
                    property int idx: -1
                    property real sx; property real sy; property real px; property real py
                    property bool first: true
                    cursorShape: idx >= 0 && pressed ? Qt.ClosedHandCursor : Qt.ArrowCursor
                    onPressed: (m) => {
                        idx = plate.hit(m.x, m.y)
                        backend.selected = idx
                        if (idx >= 0) { sx = m.x; sy = m.y; px = pg.parts[idx].x; py = pg.parts[idx].y; first = true }
                    }
                    onPositionChanged: (m) => {
                        if (idx < 0 || !pressed) return
                        var dx = (m.x - sx) / plate.k, dy = (sy - m.y) / plate.k
                        if (first && Math.abs(dx) + Math.abs(dy) < 0.3) return
                        backend.movePart(idx, Math.round((px + dx) * 10) / 10, Math.round((py + dy) * 10) / 10, first)
                        first = false
                    }
                    onReleased: idx = -1
                }
            }

            // Leerer Bauraum
            Column {
                visible: pg.parts.length === 0
                anchors.centerIn: parent
                spacing: 14
                Image { source: assetDir + "/mark.png"; width: 64; height: 64; fillMode: Image.PreserveAspectFit; anchors.horizontalCenter: parent.horizontalCenter; opacity: 0.8; mipmap: true }
                Text { text: "STL-Dateien hierher ziehen"; color: win.cInk; font.pixelSize: 18; font.weight: Font.DemiBold; anchors.horizontalCenter: parent.horizontalCenter }
                Text { text: "oder über „Hinzufügen“ auswählen"; color: win.cMut; font.pixelSize: 13; anchors.horizontalCenter: parent.horizontalCenter }
                KButton { text: "Hinzufügen …"; kind: "pri"; anchors.horizontalCenter: parent.horizontalCenter; onClicked: openStl.open() }
            }

            DropArea {
                id: drop
                anchors.fill: parent
                keys: ["text/uri-list"]
                onDropped: (d) => { backend.addUrls(d.urls) }
                Rectangle {
                    anchors.fill: parent; radius: 14
                    visible: drop.containsDrag
                    color: "#202694b8"; border.color: win.cAcc; border.width: 2
                }
            }
        }

        // Rechte Spalte
        ColumnLayout {
            Layout.preferredWidth: 340
            Layout.maximumWidth: 340
            Layout.fillHeight: true
            spacing: 14

            Card {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(300, 96 + pg.parts.length * 44)
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 14
                    spacing: 10
                    RowLayout {
                        Caption { text: "Bauteile (" + pg.parts.length + ")"; Layout.fillWidth: true }
                        KButton { text: "↶"; kind: "ghost"; implicitWidth: 38; enabled: backend.canUndo; onClicked: backend.undo(); ToolTip.visible: hovered; ToolTip.text: "Rückgängig" }
                        KButton { text: "↷"; kind: "ghost"; implicitWidth: 38; enabled: backend.canRedo; onClicked: backend.redo(); ToolTip.visible: hovered; ToolTip.text: "Wiederholen" }
                    }
                    ListView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 4
                        model: pg.parts
                        delegate: Rectangle {
                            width: ListView.view.width
                            height: 40; radius: 8
                            color: index === pg.sel ? "#16313c" : (ma.containsMouse ? "#181c21" : "transparent")
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10
                                Text { text: modelData.name; color: win.cInk; font.pixelSize: 13; elide: Text.ElideRight; Layout.fillWidth: true }
                                Text { text: modelData.size[0].toFixed(1) + " × " + modelData.size[1].toFixed(1) + " × " + modelData.size[2].toFixed(1); color: win.cMut; font.pixelSize: 11 }
                            }
                            MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true; onClicked: backend.selected = index }
                        }
                    }
                    RowLayout {
                        spacing: 8
                        KButton { text: "Hinzufügen …"; kind: "pri"; Layout.fillWidth: true; onClicked: openStl.open() }
                        KButton { text: "Anordnen"; Layout.fillWidth: true; enabled: pg.parts.length > 0; onClicked: backend.arrange() }
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                Layout.fillHeight: true
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 14
                    spacing: 10
                    Caption { text: pg.cur ? "Ausgewählt: " + pg.cur.name : "Kein Bauteil ausgewählt" }
                    GridLayout {
                        enabled: pg.cur !== null
                        opacity: enabled ? 1 : 0.4
                        columns: 2; columnSpacing: 10; rowSpacing: 8
                        Layout.fillWidth: true
                        NumField { Layout.fillWidth: true; label: "Position X"; unit: "mm"; value: pg.cur ? pg.cur.x.toFixed(1) : ""; onCommitted: (v) => backend.setPart(pg.sel, "x", v) }
                        NumField { Layout.fillWidth: true; label: "Position Y"; unit: "mm"; value: pg.cur ? pg.cur.y.toFixed(1) : ""; onCommitted: (v) => backend.setPart(pg.sel, "y", v) }
                        NumField { Layout.fillWidth: true; label: "Drehen (Gieren)"; unit: "°"; value: pg.cur ? String(pg.cur.rot_z) : ""; onCommitted: (v) => backend.setPart(pg.sel, "rot_z", v) }
                        NumField { Layout.fillWidth: true; label: "Skalierung"; unit: "%"; value: pg.cur ? String(pg.cur.scale_pct) : ""; onCommitted: (v) => backend.setPart(pg.sel, "scale_pct", v) }
                        NumField { Layout.fillWidth: true; label: "Kippen (Rollen)"; unit: "°"; value: pg.cur ? String(pg.cur.rot_x) : ""; onCommitted: (v) => backend.setPart(pg.sel, "rot_x", v) }
                        NumField { Layout.fillWidth: true; label: "Kippen (Nicken)"; unit: "°"; value: pg.cur ? String(pg.cur.rot_y) : ""; onCommitted: (v) => backend.setPart(pg.sel, "rot_y", v) }
                    }
                    RowLayout {
                        enabled: pg.cur !== null
                        spacing: 8
                        KButton { text: "90° drehen"; Layout.fillWidth: true; onClicked: backend.setPart(pg.sel, "rot_z", (pg.cur.rot_z + 90) % 360) }
                        KButton { text: "Auf Fläche legen"; Layout.fillWidth: true; onClicked: backend.layFlat(pg.sel) }
                    }
                    RowLayout {
                        enabled: pg.cur !== null
                        spacing: 8
                        KButton { text: "Duplizieren"; Layout.fillWidth: true; onClicked: backend.duplicatePart(pg.sel) }
                        KButton { text: "Entfernen"; kind: "ghost"; Layout.fillWidth: true; onClicked: backend.removePart(pg.sel) }
                    }
                    Item { Layout.fillHeight: true }
                    Repeater {
                        model: pg.problems
                        delegate: Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: pt.implicitHeight + 16
                            radius: 8; color: "#2a1215"; border.color: "#5c2226"
                            Body { id: pt; anchors.fill: parent; anchors.margins: 8; text: "⚠ " + modelData; color: "#ffb4b6"; font.pixelSize: 12 }
                        }
                    }
                    RowLayout {
                        spacing: 8
                        KButton { text: "Alles entfernen"; kind: "ghost"; Layout.fillWidth: true; enabled: pg.parts.length > 0; onClicked: confirm.ask("Alle Bauteile aus dem Bauraum entfernen?", function() { backend.clearParts() }) }
                        KButton { text: "STL exportieren"; kind: "ghost"; Layout.fillWidth: true; enabled: pg.parts.length > 0; onClicked: exportStl.open() }
                    }
                }
            }
        }
    }
}
