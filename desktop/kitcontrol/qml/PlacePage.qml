import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: pg
    property var parts: backend.parts
    property var problems: backend.problems
    property int sel: backend.selected
    property var cur: sel >= 0 && sel < parts.length ? parts[sel] : null
    property var selection: backend.selection || []
    readonly property int nSel: selection.length
    readonly property bool active: win.page === 0 && !packPop.opened

    // Tastenkürzel (wirken nicht, solange ein Eingabefeld die Taste braucht)
    Shortcut { sequences: [StandardKey.Delete, "Backspace"]; enabled: pg.active && pg.nSel > 0; onActivated: backend.removeSelected() }
    Shortcut { sequence: "Ctrl+D"; enabled: pg.active && pg.nSel > 0; onActivated: backend.duplicateSelected() }
    Shortcut { sequence: "R"; enabled: pg.active && pg.nSel > 0; onActivated: backend.rotateSelected() }
    Shortcut { sequence: "F"; enabled: pg.active && pg.nSel > 0; onActivated: backend.layFlatSelected() }
    Shortcut { sequence: StandardKey.Undo; enabled: pg.active; onActivated: backend.undo() }
    Shortcut { sequences: [StandardKey.Redo, "Ctrl+Y"]; enabled: pg.active; onActivated: backend.redo() }
    Shortcut { sequence: "A"; enabled: pg.active && pg.parts.length > 0 && backend.packState !== "running"; onActivated: packPop.open() }
    Shortcut { sequence: StandardKey.SelectAll; enabled: pg.active; onActivated: backend.selectAll() }
    Shortcut { sequence: "Esc"; enabled: pg.active && pg.nSel > 0; onActivated: backend.selectNone() }
    Shortcut { sequence: "1"; enabled: pg.active; onActivated: view3d.setView("iso") }
    Shortcut { sequence: "2"; enabled: pg.active; onActivated: view3d.setView("top") }
    Shortcut { sequence: "3"; enabled: pg.active; onActivated: view3d.setView("front") }
    Shortcut { sequence: "4"; enabled: pg.active; onActivated: view3d.setView("right") }

    // Rechtsklick-Menü in der 3D-Ansicht
    Menu {
        id: partMenu
        property int target: -1
        readonly property bool any: pg.nSel > 0
        background: Rectangle { implicitWidth: 240; radius: 10; color: win.cPanel; border.color: win.cLine }
        delegate: MenuItem {
            id: mi
            implicitHeight: 34
            contentItem: RowLayout {
                spacing: 10
                Text { text: mi.text; color: mi.enabled ? win.cInk : "#59606b"; font.pixelSize: 13; Layout.fillWidth: true; elide: Text.ElideRight }
                Text { text: mi.action && mi.action.shortcut ? String(mi.action.shortcut) : ""; color: win.cMut; font.pixelSize: 11 }
            }
            background: Rectangle { radius: 6; color: mi.highlighted ? "#16313c" : "transparent"; anchors.fill: parent; anchors.margins: 3 }
        }
        Action { text: partMenu.any && pg.nSel > 1 ? pg.nSel + win.t(" Teile ausgewählt") : (pg.cur ? pg.cur.name : win.t("Kein Bauteil ausgewählt")); enabled: false }
        MenuSeparator { contentItem: Rectangle { implicitHeight: 1; color: win.cLine } }
        Action { text: win.t("Duplizieren"); shortcut: "Ctrl+D"; enabled: partMenu.any; onTriggered: backend.duplicateSelected() }
        Action { text: win.t("90° drehen"); shortcut: "R"; enabled: partMenu.any; onTriggered: backend.rotateSelected() }
        Action { text: win.t("Auf Fläche legen"); shortcut: "F"; enabled: partMenu.any; onTriggered: backend.layFlatSelected() }
        Action { text: win.t("Mit Kopien auffüllen"); enabled: pg.nSel === 1; onTriggered: backend.fillChamber(pg.sel, { gap: backend.settings.pack_gap, wall: backend.settings.pack_wall, rotate: true }) }
        MenuSeparator { contentItem: Rectangle { implicitHeight: 1; color: win.cLine } }
        Action { text: pg.cur && pg.cur.lock_pos ? win.t("Position entsperren") : win.t("Position sperren"); enabled: partMenu.any; onTriggered: backend.lockSelected("lock_pos", !(pg.cur && pg.cur.lock_pos)) }
        Action { text: pg.cur && pg.cur.lock_orient ? win.t("Lage entsperren") : win.t("Lage sperren"); enabled: partMenu.any; onTriggered: backend.lockSelected("lock_orient", !(pg.cur && pg.cur.lock_orient)) }
        MenuSeparator { contentItem: Rectangle { implicitHeight: 1; color: win.cLine } }
        Action { text: win.t("Alles auswählen"); shortcut: "Ctrl+A"; enabled: pg.parts.length > 0; onTriggered: backend.selectAll() }
        Action { text: win.t("Entfernen"); shortcut: "Entf"; enabled: partMenu.any; onTriggered: backend.removeSelected() }
    }

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
                    item.idealXY = Qt.binding(function () { return backend.ideal.xy })
                    item.idealZ = Qt.binding(function () { return backend.ideal.z })
                }
                function setView(n) { if (item) item.setView(n) }
            }
            Connections {
                target: view3d.item
                ignoreUnknownSignals: true
                function onPicked(i) { backend.selectPart(i, "set") }
                function onPickedMode(i, mode) { backend.selectPart(i, mode) }
                function onGroupMoved(i, dx, dy, dz) { backend.moveSelected(i, dx, dy, dz) }
                function onContextMenu(i, x, y) { partMenu.target = i; partMenu.popup(view3d, x, y) }
                function onBoxSelected(idx, add) {
                    if (add) { var cur = backend.selection.slice(); for (var k = 0; k < idx.length; k++) if (cur.indexOf(idx[k]) < 0) cur.push(idx[k]); backend.selectIndices(cur) }
                    else backend.selectIndices(idx)
                }
                function onMoved(i, x, y, first) { backend.movePart(i, x, y, first) }
                function onMoved3(i, x, y, z) { backend.movePart3(i, x, y, z) }
            }

            // Ansichten
            Row {
                anchors.top: parent.top; anchors.left: parent.left; anchors.margins: 14
                spacing: 6
                Repeater {
                    model: [["iso", "3D"], ["top", win.t("Oben")], ["front", win.t("Vorne")], ["right", win.t("Rechts")]]
                    delegate: KButton { text: win.t(modelData[1]); kind: "ghost"; implicitHeight: 32; onClicked: view3d.setView(modelData[0]) }
                }
            }
            Text {
                anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.margins: 14
                width: parent.width - 28; elide: Text.ElideRight
                text: win.t("Bauteil ziehen: verschieben (von oben auf der Platte, von vorne/seitlich auch in der Höhe) · daneben ziehen: drehen · rechte Maustaste: schieben · Mausrad: zoomen")
                color: "#59606b"; font.pixelSize: 11
            }

            // Leerer Bauraum
            Column {
                visible: pg.parts.length === 0
                anchors.centerIn: parent
                spacing: 14
                Image { source: assetDir + "/mark.png"; width: 64; height: 64; fillMode: Image.PreserveAspectFit; anchors.horizontalCenter: parent.horizontalCenter; opacity: 0.8; mipmap: true }
                Text { text: win.t("STL-Dateien hierher ziehen"); color: win.cInk; font.pixelSize: 18; font.weight: Font.DemiBold; anchors.horizontalCenter: parent.horizontalCenter }
                Text { text: win.t("oder über „Hinzufügen“ auswählen"); color: win.cMut; font.pixelSize: 13; anchors.horizontalCenter: parent.horizontalCenter }
                KButton { text: win.t("Hinzufügen …"); kind: "pri"; anchors.horizontalCenter: parent.horizontalCenter; onClicked: openStl.open() }
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
                            Caption { text: win.t("Bauteile (") + pg.parts.length + ")" }
                            Text {
                                visible: pg.parts.length > 0
                                text: win.t("Bauhöhe ") + backend.density.height.toFixed(1) + win.t(" mm · Packdichte ") + backend.density.density.toFixed(1) + " %"
                                color: win.cAcc; font.pixelSize: 11
                            }
                        }
                        KButton { text: "↶"; kind: "ghost"; implicitWidth: 38; enabled: backend.canUndo; onClicked: backend.undo(); ToolTip.visible: hovered; ToolTip.text: win.t("Rückgängig") }
                        KButton { text: "↷"; kind: "ghost"; implicitWidth: 38; enabled: backend.canRedo; onClicked: backend.redo(); ToolTip.visible: hovered; ToolTip.text: win.t("Wiederholen") }
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
                                Text {
                                    visible: modelData.lock_pos || modelData.lock_orient
                                    text: "🔒"
                                    color: "#ffd59a"; font.pixelSize: 12
                                    ToolTip.visible: lockMa.containsMouse; ToolTip.text: modelData.lock_pos ? win.t("Position gesperrt – Auto-Anordnen bewegt dieses Teil nicht") : win.t("Lage gesperrt – wird nicht gedreht")
                                    MouseArea { id: lockMa; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
                                }
                                Text { text: modelData.name; color: win.cInk; font.pixelSize: 13; elide: Text.ElideRight; Layout.fillWidth: true }
                                Text { text: modelData.size[0].toFixed(1) + " × " + modelData.size[1].toFixed(1) + " × " + modelData.size[2].toFixed(1); color: win.cMut; font.pixelSize: 11 }
                            }
                            MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true; onClicked: backend.selected = index }
                        }
                    }
                    RowLayout {
                        spacing: 8
                        KButton { text: win.t("Hinzufügen …"); Layout.fillWidth: true; onClicked: openStl.open() }
                        KButton {
                            text: backend.packState === "running" ? win.t("Abbrechen (") + Math.round(backend.packProgress * 100) + " %)" : win.t("Auto-Anordnen")
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
                    Caption { text: pg.nSel > 1 ? pg.nSel + win.t(" Teile ausgewählt – Tasten wirken auf alle") : (pg.cur ? win.t("Ausgewählt: ") + pg.cur.name : win.t("Kein Bauteil ausgewählt")) }
                    GridLayout {
                        enabled: pg.cur !== null
                        opacity: enabled ? 1 : 0.4
                        columns: 2; columnSpacing: 10; rowSpacing: 8
                        Layout.fillWidth: true
                        NumField { Layout.fillWidth: true; label: win.t("Position X"); unit: "mm"; value: pg.cur ? pg.cur.x.toFixed(1) : ""; onCommitted: (v) => backend.setPart(pg.sel, "x", v) }
                        NumField { Layout.fillWidth: true; label: win.t("Position Y"); unit: "mm"; value: pg.cur ? pg.cur.y.toFixed(1) : ""; onCommitted: (v) => backend.setPart(pg.sel, "y", v) }
                        NumField { Layout.fillWidth: true; label: win.t("Drehen (Gieren)"); unit: "°"; value: pg.cur ? String(pg.cur.rot_z) : ""; onCommitted: (v) => backend.setPart(pg.sel, "rot_z", v) }
                        NumField { Layout.fillWidth: true; label: win.t("Skalierung"); unit: "%"; value: pg.cur ? String(pg.cur.scale_pct) : ""; onCommitted: (v) => backend.setPart(pg.sel, "scale_pct", v) }
                        NumField { Layout.fillWidth: true; label: win.t("Kippen (Rollen)"); unit: "°"; value: pg.cur ? String(pg.cur.rot_x) : ""; onCommitted: (v) => backend.setPart(pg.sel, "rot_x", v) }
                        NumField { Layout.fillWidth: true; label: win.t("Kippen (Nicken)"); unit: "°"; value: pg.cur ? String(pg.cur.rot_y) : ""; onCommitted: (v) => backend.setPart(pg.sel, "rot_y", v) }
                        NumField { Layout.fillWidth: true; label: win.t("Höhe über Platte"); unit: "mm"; value: pg.cur ? pg.cur.z.toFixed(1) : ""; onCommitted: (v) => backend.setPart(pg.sel, "z_lift", v) }
                        Text {
                            Layout.fillWidth: true; Layout.preferredWidth: 1; Layout.alignment: Qt.AlignBottom; Layout.bottomMargin: 8
                            elide: Text.ElideRight
                            text: pg.cur ? pg.cur.size[0].toFixed(1) + " × " + pg.cur.size[1].toFixed(1) + " × " + pg.cur.size[2].toFixed(1) + win.t(" mm") : ""
                            color: win.cMut; font.pixelSize: 12
                        }
                    }
                    RowLayout {
                        enabled: pg.cur !== null
                        spacing: 8
                        KButton { text: win.t("90° drehen"); Layout.fillWidth: true; Layout.preferredWidth: 1; onClicked: backend.rotateSelected() }
                        KButton { text: win.t("Auf Fläche legen"); Layout.fillWidth: true; Layout.preferredWidth: 1; onClicked: backend.layFlatSelected() }
                    }
                    RowLayout {
                        enabled: pg.cur !== null
                        spacing: 14
                        KCheck {
                            Layout.preferredWidth: 1
                            id: lockPos
                            checked: pg.cur ? pg.cur.lock_pos : false
                            onToggled: backend.lockSelected("lock_pos", checked); text: win.t("Position sperren") }
                        KCheck {
                            Layout.preferredWidth: 1
                            id: lockOri
                            checked: pg.cur ? pg.cur.lock_orient : false
                            onToggled: backend.lockSelected("lock_orient", checked); text: win.t("Lage sperren") }
                    }
                    RowLayout {
                        enabled: pg.cur !== null
                        spacing: 8
                        KButton { text: win.t("Duplizieren"); Layout.fillWidth: true; Layout.preferredWidth: 1; onClicked: backend.duplicateSelected() }
                        KButton { text: win.t("Entfernen"); kind: "ghost"; Layout.fillWidth: true; Layout.preferredWidth: 1; onClicked: backend.removeSelected() }
                    }
                    Repeater {
                        model: backend.notes
                        delegate: Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: nt.implicitHeight + 16
                            radius: 8; color: "#2a2312"; border.color: "#5c4a22"
                            Body { id: nt; anchors.fill: parent; anchors.margins: 8; text: "ⓘ " + win.t(modelData); color: "#ffd59a"; font.pixelSize: 12 }
                        }
                    }
                    Repeater {
                        model: pg.problems
                        delegate: Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: pt.implicitHeight + 16
                            radius: 8; color: "#2a1215"; border.color: "#5c2226"
                            Body { id: pt; anchors.fill: parent; anchors.margins: 8; text: "⚠ " + win.t(modelData); color: "#ffb4b6"; font.pixelSize: 12 }
                        }
                    }
                    RowLayout {
                        spacing: 8
                        KButton { text: win.t("Alles entfernen"); kind: "ghost"; Layout.fillWidth: true; Layout.preferredWidth: 1; enabled: pg.parts.length > 0; onClicked: confirm.ask(win.t("Alle Bauteile aus dem Bauraum entfernen?"), function() { backend.clearParts() }) }
                        KButton { text: win.t("STL exportieren"); kind: "ghost"; Layout.fillWidth: true; Layout.preferredWidth: 1; enabled: pg.parts.length > 0; onClicked: exportStl.open() }
                    }
                }
                }
            }
        }
    }

    Popup {
        id: packPop
        objectName: "packPop"
        anchors.centerIn: parent
        width: 440
        modal: true
        padding: 22
        background: Rectangle { radius: 14; color: win.cPanel; border.color: win.cLine }
        property real gap: backend.settings.pack_gap
        property real wall: backend.settings.pack_wall
        property bool rotate: true
        property bool onlySel: false
        property int budget: 8
        property real quality: 0.5
        contentItem: ColumnLayout {
            spacing: 14
            Text { text: win.t("Auto-Anordnen"); color: win.cInk; font.pixelSize: 18; font.weight: Font.DemiBold }
            Body {
                Layout.fillWidth: true; color: win.cMut; font.pixelSize: 12
                text: win.t("Packt alle Teile möglichst niedrig und dicht in den idealen Druckbereich (") + backend.ideal.xy + " × " + backend.ideal.xy + " × " + backend.ideal.z + win.t(" mm) – auch übereinander. SLS-Regeln gelten immer: Mindestabstand in alle Richtungen, Abstand zum Rand, nichts verhakt sich. Jedes Teil wird erst so tief wie möglich gepackt und dann in die beste Lage nach SLS-Regeln gedreht, wo das keine Bauhöhe kostet. Gesperrte Teile bleiben, wie sie sind.")
            }
            Rectangle {
                visible: backend.lockedCount > 0
                Layout.fillWidth: true
                implicitHeight: lockRow.implicitHeight + 16
                radius: 8; color: "#2a2312"; border.color: "#5c4a22"
                RowLayout {
                    id: lockRow
                    anchors.fill: parent; anchors.margins: 8
                    spacing: 10
                    Body {
                        Layout.fillWidth: true; color: "#ffd59a"; font.pixelSize: 12
                        text: backend.lockedCount + win.t(" Teile sind gesperrt (🔒) und werden nicht bewegt bzw. gedreht – das kann viel Bauhöhe kosten.")
                    }
                    KButton { text: win.t("Sperren aufheben"); onClicked: backend.unlockAll() }
                }
            }
            GridLayout {
                columns: 2; columnSpacing: 14; rowSpacing: 10
                Layout.fillWidth: true
                NumField { Layout.fillWidth: true; label: win.t("Abstand zwischen Teilen"); unit: "mm"; value: String(packPop.gap); onCommitted: (v) => packPop.gap = Number(v.replace(",", ".")) }
                NumField { Layout.fillWidth: true; label: win.t("Abstand zum Rand"); unit: "mm"; value: String(packPop.wall); onCommitted: (v) => packPop.wall = Number(v.replace(",", ".")) }
            }
            ColumnLayout {
                spacing: 6
                Text { text: win.t("Gründlichkeit"); color: win.cMut; font.pixelSize: 12 }
                RowLayout {
                    spacing: 8
                    Repeater {
                        model: [[3, win.t("Schnell")], [8, win.t("Gründlich")], [25, win.t("Sehr gründlich")]]
                        delegate: KButton {
                            Layout.fillWidth: true
                            text: win.t(modelData[1])
                            kind: packPop.budget === modelData[0] ? "pri" : "normal"
                            onClicked: packPop.budget = modelData[0]
                        }
                    }
                }
            }
            RowLayout {
                spacing: 18
                KCheck {
                    id: rotBox; checked: packPop.rotate; onToggled: packPop.rotate = checked; text: win.t("Teile drehen erlaubt") }
                KCheck {
                    id: selBox; checked: packPop.onlySel; enabled: pg.cur !== null; onToggled: packPop.onlySel = checked; text: win.t("Nur ausgewähltes Teil") }
            }
            RowLayout {
                spacing: 8
                Layout.topMargin: 6
                KButton {
                    text: pg.cur ? "„" + pg.cur.name + win.t("“ auffüllen") : win.t("Mit Kopien auffüllen"); Layout.fillWidth: true; enabled: pg.parts.length > 0
                    onClicked: { packPop.close(); backend.fillChamber(pg.sel, { gap: packPop.gap, wall: packPop.wall, rotate: packPop.rotate, quality: packPop.quality }) }
                    ToolTip.visible: hovered; ToolTip.text: win.t("Das ausgewählte (sonst das erste) Teil so oft kopieren, wie es in den idealen Bereich passt")
                }
                KButton {
                    text: win.t("Flach")
                    ToolTip.visible: hovered
                    ToolTip.text: win.t("Alles nebeneinander auf die Platte legen")
                    onClicked: { packPop.close(); backend.arrange("rows") }
                }
            }
            RowLayout {
                spacing: 8
                Item { Layout.fillWidth: true }
                KButton { text: win.t("Abbrechen"); kind: "ghost"; onClicked: packPop.close() }
                KButton {
                    text: win.t("Anordnen"); kind: "pri"
                    onClicked: { packPop.close(); backend.autoPack({ gap: packPop.gap, wall: packPop.wall, rotate: packPop.rotate, onlySelected: packPop.onlySel, time: packPop.budget, quality: packPop.quality }) }
                }
            }
        }
    }
}
