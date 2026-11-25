import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: vp
    property var m: backend.sliceMeta || ({})
    property int count: m.layers ? slider.to : 0
    property bool done: backend.sliceState === "done"
    readonly property int heatS: 5400      // Aufheizen typisch ~1,5 h (für die Fertig-Uhrzeit)

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
                            text: backend.sliceState === "running" ? win.t("Slicen läuft …") : (backend.sliceState === "error" ? win.t("Slicen fehlgeschlagen") : win.t("Noch nicht geslict"))
                            color: win.cInk; font.pixelSize: 18; font.weight: Font.DemiBold
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: 420; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                            text: backend.sliceState === "error" ? backend.sliceError : win.t("Mit „Slicen“ entsteht die Druckdatei – danach lassen sich alle Schichten durchblättern.")
                            color: backend.sliceState === "error" ? win.cErrInk : win.cMut; font.pixelSize: 13
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
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
                            width: slider.availableWidth; height: 4; radius: 2; color: win.cTrack
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
                        text: win.t("Schicht ") + Math.round(slider.value) + " / " + Math.round(slider.to) + (view.layerData.z !== undefined ? "  ·  z " + view.layerData.z.toFixed(2) + win.t(" mm") : "")
                        color: win.cInk; font.pixelSize: 13
                        Layout.preferredWidth: 230; elide: Text.ElideRight
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
                    Caption { text: win.t("Druckdatei") }
                    Body { text: win.t("Profil: ") + backend.profile.name; color: win.cMut }
                    ProgressBar {
                        visible: backend.sliceState === "running"
                        Layout.fillWidth: true
                        value: backend.sliceProgress
                        background: Rectangle { implicitHeight: 6; radius: 3; color: win.cTrack }
                        contentItem: Item {
                            Rectangle { width: parent.width * backend.sliceProgress; height: 6; radius: 3; color: win.cAcc }
                        }
                    }
                    KButton {
                        Layout.fillWidth: true
                        text: backend.sliceState === "running" ? win.t("Abbrechen (") + Math.round(backend.sliceProgress * 100) + " %)" : (vp.done ? win.t("Neu slicen") : win.t("Slicen"))
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
                    Stat { label: win.t("Schichten"); value: vp.m.layers || "–" }
                    Stat { label: win.t("Bauhöhe"); value: vp.m.height_mm !== undefined ? vp.m.height_mm.toFixed(1) + win.t(" mm") : "–" }
                    Stat { label: win.t("Pulver laden"); value: vp.m.powder_mm !== undefined ? vp.m.powder_mm.toFixed(1) + win.t(" mm") : "–"; tint: win.cAcc }
                    Stat {
                        label: win.t("Druckzeit")
                        value: backend.estimate.seconds !== undefined ? win.fmtTime(backend.estimate.seconds) : "–"
                        tint: win.cAcc
                    }
                    Stat {
                        label: win.t("Fertig ca.")
                        value: backend.estimate.seconds !== undefined ? Qt.formatTime(new Date(Date.now() + (backend.estimate.seconds + vp.heatS) * 1000), "hh:mm") + win.t(" Uhr") : "–"
                        tint: win.cAcc
                    }
                    Stat { label: win.t("Laserweg"); value: vp.m.est_scan_m !== undefined ? Math.round(vp.m.est_scan_m) + " m" : "–" }
                    Stat { label: win.t("Vektoren"); value: vp.m.vectors !== undefined ? Number(vp.m.vectors).toLocaleString(Qt.locale("de_DE"), "f", 0) : "–" }
                    Stat { label: win.t("Rechenzeit"); value: vp.m.slice_s !== undefined ? vp.m.slice_s + " s" : "–" }
                }
            }

            Text {
                visible: vp.done && backend.estimate.seconds !== undefined
                Layout.fillWidth: true; wrapMode: Text.WordWrap
                text: win.t("Druckzeit ohne Aufheizen, Fertig-Uhrzeit mit ca. 1,5 h Aufheizen. Berechnet mit ") + Math.round(backend.estimate.laser_mm_s || 0) + win.t(" mm/s")
                      + (backend.estimate.learned > 0 ? win.t(", an ") + backend.estimate.learned + win.t(" echten Drucken angepasst.") : win.t(" – wird mit jedem Druck genauer."))
                color: win.cMut; font.pixelSize: 11
            }

            Item { Layout.fillHeight: true }

            KButton { visible: vp.done; Layout.fillWidth: true; text: win.t("Druckdatei speichern …"); kind: "ghost"; onClicked: saveJob.open() }
            KButton { visible: vp.done; Layout.fillWidth: true; text: win.t("Weiter zum Drucken"); kind: "pri"; onClicked: win.page = 4 }
        }
    }
}
