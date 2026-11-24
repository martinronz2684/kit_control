import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: vp
    property var m: backend.sliceMeta || ({})
    property int count: m.layers ? slider.to : 0
    property bool done: backend.sliceState === "done"

    function show() { if (vp.done) view.layerData = backend.layer(Math.round(slider.value)) }

    Connections {
        target: backend
        function onSliceChanged() {
            if (backend.sliceState === "done") {
                var d = backend.layer(1)
                slider.to = Math.max(1, d.count || 1)
                slider.value = 1
                view.layerData = d
            } else if (backend.sliceState !== "running") {
                view.layerData = ({})
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 18

        Card {
            Layout.fillWidth: true
            Layout.fillHeight: true
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 18
                spacing: 12
                LayerView {
                    id: view
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    plateMm: backend.plateMm
                    Column {
                        visible: !vp.done
                        anchors.centerIn: parent
                        spacing: 12
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: backend.sliceState === "running" ? "Slicen läuft …" : (backend.sliceState === "error" ? "Slicen fehlgeschlagen" : "Noch nicht geslict")
                            color: win.cInk; font.pixelSize: 18; font.weight: Font.DemiBold
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: 420; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                            text: backend.sliceState === "error" ? backend.sliceError : "Mit „Slicen“ entsteht die Druckdatei – danach lassen sich alle Schichten durchblättern."
                            color: backend.sliceState === "error" ? "#ffb4b6" : win.cMut; font.pixelSize: 13
                        }
                    }
                }
                RowLayout {
                    enabled: vp.done
                    opacity: enabled ? 1 : 0.35
                    spacing: 12
                    KButton { text: "◀"; implicitWidth: 40; onClicked: { slider.decrease(); vp.show() } }
                    Slider {
                        id: slider
                        Layout.fillWidth: true
                        from: 1; to: 1; stepSize: 1; value: 1
                        onMoved: vp.show()
                        background: Rectangle {
                            x: slider.leftPadding; y: slider.topPadding + slider.availableHeight / 2 - 2
                            width: slider.availableWidth; height: 4; radius: 2; color: "#232830"
                            Rectangle { width: slider.visualPosition * parent.width; height: 4; radius: 2; color: win.cAcc }
                        }
                        handle: Rectangle {
                            x: slider.leftPadding + slider.visualPosition * (slider.availableWidth - width)
                            y: slider.topPadding + slider.availableHeight / 2 - height / 2
                            width: 18; height: 18; radius: 9; color: win.cInk; border.color: win.cAcc; border.width: 3
                        }
                    }
                    KButton { text: "▶"; implicitWidth: 40; onClicked: { slider.increase(); vp.show() } }
                    Text {
                        text: "Schicht " + Math.round(slider.value) + " / " + Math.round(slider.to) + (view.layerData.z !== undefined ? "  ·  z " + view.layerData.z.toFixed(2) + " mm" : "")
                        color: win.cInk; font.pixelSize: 13
                        Layout.preferredWidth: 220
                    }
                }
            }
        }

        ColumnLayout {
            Layout.preferredWidth: 320
            Layout.maximumWidth: 320
            Layout.fillHeight: true
            spacing: 14

            Card {
                Layout.fillWidth: true
                implicitHeight: sc.implicitHeight + 28
                ColumnLayout {
                    id: sc
                    anchors.fill: parent; anchors.margins: 14
                    spacing: 12
                    Caption { text: "Druckdatei" }
                    Body { text: "Profil: " + backend.profile.name; color: win.cMut }
                    ProgressBar {
                        visible: backend.sliceState === "running"
                        Layout.fillWidth: true
                        value: backend.sliceProgress
                        background: Rectangle { implicitHeight: 6; radius: 3; color: "#232830" }
                        contentItem: Item {
                            Rectangle { width: parent.width * backend.sliceProgress; height: 6; radius: 3; color: win.cAcc }
                        }
                    }
                    KButton {
                        Layout.fillWidth: true
                        text: backend.sliceState === "running" ? "Abbrechen (" + Math.round(backend.sliceProgress * 100) + " %)" : (vp.done ? "Neu slicen" : "Slicen")
                        kind: backend.sliceState === "running" ? "normal" : "pri"
                        enabled: backend.parts.length > 0
                        onClicked: backend.sliceState === "running" ? backend.cancelSlice() : backend.startSlice()
                    }
                }
            }

            Card {
                visible: vp.done
                Layout.fillWidth: true
                implicitHeight: st.implicitHeight + 28
                GridLayout {
                    id: st
                    anchors.fill: parent; anchors.margins: 14
                    columns: 2; rowSpacing: 14; columnSpacing: 10
                    Stat { label: "Schichten"; value: vp.m.layers || "–" }
                    Stat { label: "Bauhöhe"; value: vp.m.height_mm !== undefined ? vp.m.height_mm.toFixed(1) + " mm" : "–" }
                    Stat { label: "Pulver laden"; value: vp.m.powder_mm !== undefined ? vp.m.powder_mm.toFixed(1) + " mm" : "–"; tint: win.cAcc }
                    Stat { label: "Laserweg"; value: vp.m.est_scan_m !== undefined ? Math.round(vp.m.est_scan_m) + " m" : "–" }
                    Stat { label: "Vektoren"; value: vp.m.vectors !== undefined ? Number(vp.m.vectors).toLocaleString(Qt.locale("de_DE"), "f", 0) : "–" }
                    Stat { label: "Rechenzeit"; value: vp.m.slice_s !== undefined ? vp.m.slice_s + " s" : "–" }
                }
            }

            Item { Layout.fillHeight: true }

            KButton { visible: vp.done; Layout.fillWidth: true; text: "Druckdatei speichern …"; kind: "ghost"; onClicked: saveJob.open() }
            KButton { visible: vp.done; Layout.fillWidth: true; text: "Weiter zum Drucken"; kind: "pri"; onClicked: win.page = 4 }
        }
    }
}
