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

            Viewport3D {
                id: view3d
                anchors.fill: parent
                anchors.margins: 6
                parts: pg.parts
                sel: pg.sel
                plate: backend.plateMm
                idealXY: backend.ideal.xy
                idealZ: backend.ideal.z
                onPicked: (i) => backend.selected = i
                onMoved: (i, x, y, first) => backend.movePart(i, x, y, first)
            }

            // Ansichten
            Row {
                anchors.top: parent.top; anchors.left: parent.left; anchors.margins: 14
                spacing: 6
                Repeater {
                    model: [["iso", "3D"], ["top", "Oben"], ["front", "Vorne"], ["right", "Rechts"]]
                    delegate: KButton { text: modelData[1]; kind: "ghost"; implicitHeight: 32; onClicked: view3d.setView(modelData[0]) }
                }
            }
            Text {
                anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.margins: 14
                text: "Bauteil ziehen: verschieben · daneben ziehen: drehen · rechte Maustaste: schieben · Mausrad: zoomen"
                color: "#59606b"; font.pixelSize: 11
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
                        KButton { text: "3D-Nesting"; Layout.fillWidth: true; enabled: pg.parts.length > 0; onClicked: backend.arrange("nest"); ToolTip.visible: hovered; ToolTip.text: "Alle Teile dicht im idealen Bereich packen, auch übereinander" }
                        KButton { text: "Flach"; implicitWidth: 64; enabled: pg.parts.length > 0; onClicked: backend.arrange("rows"); ToolTip.visible: hovered; ToolTip.text: "Alle Teile nebeneinander auf die Platte legen" }
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
                        NumField { Layout.fillWidth: true; label: "Höhe über Platte"; unit: "mm"; value: pg.cur ? pg.cur.z.toFixed(1) : ""; onCommitted: (v) => backend.setPart(pg.sel, "z_lift", v) }
                        Text {
                            Layout.fillWidth: true; Layout.alignment: Qt.AlignBottom; Layout.bottomMargin: 8
                            text: pg.cur ? pg.cur.size[0].toFixed(1) + " × " + pg.cur.size[1].toFixed(1) + " × " + pg.cur.size[2].toFixed(1) + " mm" : ""
                            color: win.cMut; font.pixelSize: 12
                        }
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
                        model: backend.notes
                        delegate: Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: nt.implicitHeight + 16
                            radius: 8; color: "#2a2312"; border.color: "#5c4a22"
                            Body { id: nt; anchors.fill: parent; anchors.margins: 8; text: "ⓘ " + modelData; color: "#ffd59a"; font.pixelSize: 12 }
                        }
                    }
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
