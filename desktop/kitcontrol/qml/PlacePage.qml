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

            // 3D-Ansicht: auf der Grafikkarte (Qt Quick 3D), sonst die einfache Ansicht als Ersatz
            Loader {
                id: view3d
                anchors.fill: parent
                anchors.margins: 6
                source: backend.gpuView ? "ViewportGPU.qml" : "Viewport3D.qml"
                onStatusChanged: if (status === Loader.Error && source.toString().indexOf("GPU") >= 0) source = "Viewport3D.qml"
                onLoaded: {
                    item.parts = Qt.binding(function() { return pg.parts })
                    item.sel = Qt.binding(function() { return pg.sel })
                    item.plate = backend.plateMm
                    item.idealXY = backend.ideal.xy
                    item.idealZ = backend.ideal.z
                }
                function setView(n) { if (item) item.setView(n) }
            }
            Connections {
                target: view3d.item
                ignoreUnknownSignals: true
                function onPicked(i) { backend.selected = i }
                function onMoved(i, x, y, first) { backend.movePart(i, x, y, first) }
                function onMoved3(i, x, y, z) { backend.movePart3(i, x, y, z) }
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
                width: parent.width - 28; elide: Text.ElideRight
                text: "Bauteil ziehen: verschieben (von oben auf der Platte, von vorne/seitlich auch in der Höhe) · daneben ziehen: drehen · rechte Maustaste: schieben · Mausrad: zoomen"
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
                Layout.preferredHeight: Math.min(320, 150 + Math.max(1, pg.parts.length) * 44)
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 14
                    spacing: 10
                    RowLayout {
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 1
                            Caption { text: "Bauteile (" + pg.parts.length + ")" }
                            Text {
                                visible: pg.parts.length > 0
                                text: "Bauhöhe " + backend.density.height.toFixed(1) + " mm · Packdichte " + backend.density.density.toFixed(1) + " %"
                                color: win.cAcc; font.pixelSize: 11
                            }
                        }
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
                        KButton { text: "Hinzufügen …"; Layout.fillWidth: true; onClicked: openStl.open() }
                        KButton {
                            text: backend.packState === "running" ? "Ordnet an … " + Math.round(backend.packProgress * 100) + " %" : "Auto-Anordnen"
                            kind: "pri"; Layout.fillWidth: true
                            enabled: pg.parts.length > 0
                            onClicked: backend.packState === "running" ? backend.cancelPack() : packPop.open()
                        }
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                Flickable {
                    id: selFlick
                    anchors.fill: parent; anchors.margins: 14
                    contentHeight: selCol.implicitHeight
                    contentWidth: width
                    flickableDirection: Flickable.VerticalFlick
                    boundsBehavior: Flickable.StopAtBounds
                    clip: true
                    ScrollBar.vertical: ScrollBar { policy: selFlick.contentHeight > selFlick.height ? ScrollBar.AlwaysOn : ScrollBar.AsNeeded }
                ColumnLayout {
                    id: selCol
                    width: selFlick.width - (selFlick.contentHeight > selFlick.height ? 10 : 0)
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
                            Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.alignment: Qt.AlignBottom; Layout.bottomMargin: 8
                            elide: Text.ElideRight
                            text: pg.cur ? pg.cur.size[0].toFixed(1) + " × " + pg.cur.size[1].toFixed(1) + " × " + pg.cur.size[2].toFixed(1) + " mm" : ""
                            color: win.cMut; font.pixelSize: 12
                        }
                    }
                    RowLayout {
                        enabled: pg.cur !== null
                        spacing: 8
                        KButton { text: "90° drehen"; Layout.fillWidth: true; Layout.preferredWidth: 1; onClicked: backend.setPart(pg.sel, "rot_z", (pg.cur.rot_z + 90) % 360) }
                        KButton { text: "Auf Fläche legen"; Layout.fillWidth: true; Layout.preferredWidth: 1; onClicked: backend.layFlat(pg.sel) }
                    }
                    RowLayout {
                        enabled: pg.cur !== null
                        spacing: 14
                        KCheck {
                            Layout.preferredWidth: 1
                            id: lockPos
                            checked: pg.cur ? pg.cur.lock_pos : false
                            onToggled: backend.setPart(pg.sel, "lock_pos", checked); text: "Position sperren" }
                        KCheck {
                            Layout.preferredWidth: 1
                            id: lockOri
                            checked: pg.cur ? pg.cur.lock_orient : false
                            onToggled: backend.setPart(pg.sel, "lock_orient", checked); text: "Lage sperren" }
                    }
                    RowLayout {
                        enabled: pg.cur !== null
                        spacing: 8
                        KButton { text: "Duplizieren"; Layout.fillWidth: true; Layout.preferredWidth: 1; onClicked: backend.duplicatePart(pg.sel) }
                        KButton { text: "Entfernen"; kind: "ghost"; Layout.fillWidth: true; Layout.preferredWidth: 1; onClicked: backend.removePart(pg.sel) }
                    }
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
                        KButton { text: "Alles entfernen"; kind: "ghost"; Layout.fillWidth: true; Layout.preferredWidth: 1; enabled: pg.parts.length > 0; onClicked: confirm.ask("Alle Bauteile aus dem Bauraum entfernen?", function() { backend.clearParts() }) }
                        KButton { text: "STL exportieren"; kind: "ghost"; Layout.fillWidth: true; Layout.preferredWidth: 1; enabled: pg.parts.length > 0; onClicked: exportStl.open() }
                    }
                }
                }
            }
        }
    }

    Popup {
        id: packPop
        anchors.centerIn: parent
        width: 440
        modal: true
        padding: 22
        background: Rectangle { radius: 14; color: win.cPanel; border.color: win.cLine }
        property real gap: 3
        property real wall: 2
        property bool rotate: true
        property bool onlySel: false
        property int budget: 8
        property real quality: 0.5
        contentItem: ColumnLayout {
            spacing: 14
            Text { text: "Auto-Anordnen"; color: win.cInk; font.pixelSize: 18; font.weight: Font.DemiBold }
            Body {
                Layout.fillWidth: true; color: win.cMut; font.pixelSize: 12
                text: "Packt alle Teile möglichst niedrig und dicht in den idealen Druckbereich (90 × 90 × 110 mm) – auch übereinander. SLS-Regeln gelten immer: Mindestabstand in alle Richtungen, Abstand zum Rand, nichts verhakt sich. Jedes Teil wird erst so tief wie möglich gepackt und dann in die beste Lage nach SLS-Regeln gedreht, wo das keine Bauhöhe kostet. Gesperrte Teile bleiben, wie sie sind."
            }
            GridLayout {
                columns: 2; columnSpacing: 14; rowSpacing: 10
                Layout.fillWidth: true
                NumField { Layout.fillWidth: true; label: "Abstand zwischen Teilen"; unit: "mm"; value: String(packPop.gap); onCommitted: (v) => packPop.gap = Number(v.replace(",", ".")) }
                NumField { Layout.fillWidth: true; label: "Abstand zum Rand"; unit: "mm"; value: String(packPop.wall); onCommitted: (v) => packPop.wall = Number(v.replace(",", ".")) }
            }
            ColumnLayout {
                spacing: 6
                Text { text: "Gründlichkeit"; color: win.cMut; font.pixelSize: 12 }
                RowLayout {
                    spacing: 8
                    Repeater {
                        model: [[3, "Schnell"], [8, "Gründlich"], [25, "Sehr gründlich"]]
                        delegate: KButton {
                            Layout.fillWidth: true
                            text: modelData[1]
                            kind: packPop.budget === modelData[0] ? "pri" : "normal"
                            onClicked: packPop.budget = modelData[0]
                        }
                    }
                }
            }
            RowLayout {
                spacing: 18
                KCheck {
                    id: rotBox; checked: packPop.rotate; onToggled: packPop.rotate = checked; text: "Teile drehen erlaubt" }
                KCheck {
                    id: selBox; checked: packPop.onlySel; enabled: pg.cur !== null; onToggled: packPop.onlySel = checked; text: "Nur ausgewähltes Teil" }
            }
            RowLayout {
                spacing: 8
                Layout.topMargin: 6
                KButton {
                    text: pg.cur ? "„" + pg.cur.name + "“ auffüllen" : "Mit Kopien auffüllen"; Layout.fillWidth: true; enabled: pg.parts.length > 0
                    onClicked: { packPop.close(); backend.fillChamber(pg.sel, { gap: packPop.gap, wall: packPop.wall, rotate: packPop.rotate, quality: packPop.quality }) }
                    ToolTip.visible: hovered; ToolTip.text: "Das ausgewählte (sonst das erste) Teil so oft kopieren, wie es in den idealen Bereich passt"
                }
                KButton {
                    text: "Flach"
                    ToolTip.visible: hovered
                    ToolTip.text: "Alles nebeneinander auf die Platte legen"
                    onClicked: { packPop.close(); backend.arrange("rows") }
                }
            }
            RowLayout {
                spacing: 8
                Item { Layout.fillWidth: true }
                KButton { text: "Abbrechen"; kind: "ghost"; onClicked: packPop.close() }
                KButton {
                    text: "Anordnen"; kind: "pri"
                    onClicked: { packPop.close(); backend.autoPack({ gap: packPop.gap, wall: packPop.wall, rotate: packPop.rotate, onlySelected: packPop.onlySel, time: packPop.budget, quality: packPop.quality }) }
                }
            }
        }
    }
}
