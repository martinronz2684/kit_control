import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: pr
    property var k: win.kit
    property var job: k.current_job || null
    property bool live: backend.connected && k.connected === true
    property int shownLayer: 0

    // Aktuelle Schicht des laufenden Jobs vom Pi holen, sobald sie sich ändert
    onKChanged: {
        if (job && job.id && k.printing && k.layer && k.layer !== shownLayer) {
            shownLayer = k.layer
            backend.requestPiLayer(job.id, k.layer)
        }
    }
    Connections { target: backend; function onPiLayerReady(d) { liveView.layer = d } }

    RowLayout {
        anchors.fill: parent
        spacing: 18

        // Links: Verbindung, Senden, Bibliothek
        ColumnLayout {
            Layout.preferredWidth: 360
            Layout.maximumWidth: 360
            Layout.fillHeight: true
            spacing: 14

            Card {
                Layout.fillWidth: true
                implicitHeight: con.implicitHeight + 28
                ColumnLayout {
                    id: con
                    anchors.fill: parent; anchors.margins: 14
                    spacing: 10
                    RowLayout {
                        Caption { text: "Kit Control"; Layout.fillWidth: true }
                        KButton { text: backend.searching ? "Sucht …" : "Suchen"; kind: "ghost"; enabled: !backend.searching; onClicked: backend.discover() }
                    }
                    Repeater {
                        model: backend.devices
                        delegate: Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 42; radius: 9
                            color: modelData.host === backend.host ? "#16313c" : (dm.containsMouse ? "#181c21" : "#15181c")
                            border.color: modelData.host === backend.host ? win.cAcc : win.cLine
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                                Text { text: modelData.name; color: win.cInk; font.pixelSize: 13; font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideRight }
                                Text { text: modelData.host; color: win.cMut; font.pixelSize: 12 }
                            }
                            MouseArea { id: dm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: backend.connectHost(modelData.host) }
                        }
                    }
                    RowLayout {
                        spacing: 8
                        KField { id: hostField; Layout.fillWidth: true; placeholderText: "IP-Adresse des Pi"; text: backend.host; onAccepted: backend.connectHost(text) }
                        KButton { text: "Verbinden"; onClicked: backend.connectHost(hostField.text) }
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                implicitHeight: sendCol.implicitHeight + 28
                ColumnLayout {
                    id: sendCol
                    anchors.fill: parent; anchors.margins: 14
                    spacing: 10
                    Caption { text: "Job senden" }
                    Body {
                        color: win.cMut; font.pixelSize: 12
                        text: backend.sliceState === "done"
                              ? (win.meta.layers + " Schichten · " + win.meta.height_mm.toFixed(1) + " mm · " + backend.profile.name)
                              : "Noch kein geslicter Job – unter „Vorschau“ slicen."
                    }
                    KButton { text: "Nur übertragen"; Layout.fillWidth: true; enabled: backend.connected && backend.sliceState === "done"; onClicked: backend.send(false) }
                    KButton {
                        text: "Übertragen und starten"; kind: "pri"; Layout.fillWidth: true
                        enabled: pr.live && backend.sliceState === "done" && k.printing !== true
                        onClicked: confirm.ask("Job zum Kit übertragen und den Druck sofort starten? Der Kit heizt dann auf.", function() { backend.send(true) })
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                Layout.fillHeight: true
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 14
                    spacing: 8
                    RowLayout {
                        Caption { text: "Jobs am Kit"; Layout.fillWidth: true }
                        KButton { text: "Aktualisieren"; kind: "ghost"; enabled: backend.connected; onClicked: backend.refreshJobs() }
                    }
                    ListView {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        clip: true; spacing: 4
                        model: backend.piJobs
                        delegate: Rectangle {
                            width: ListView.view.width
                            height: 50; radius: 8; color: "#15181c"
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 6
                                ColumnLayout {
                                    Layout.fillWidth: true; spacing: 1
                                    Text { text: modelData.name; color: win.cInk; font.pixelSize: 13; elide: Text.ElideRight; Layout.fillWidth: true }
                                    Text { text: (modelData.layers ? modelData.layers + " Schichten · " + modelData.height_mm + " mm" : (modelData.error || "")) ; color: win.cMut; font.pixelSize: 11 }
                                }
                                KButton {
                                    text: "Starten"; kind: "ghost"
                                    enabled: pr.live && k.printing !== true && !modelData.error
                                    onClicked: confirm.ask("„" + modelData.name + "“ jetzt drucken?", function() { backend.cmd({ cmd: "job_start", id: modelData.id }) })
                                }
                            }
                        }
                    }
                }
            }
        }

        // Rechts: Live-Ansicht
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 14

            Card {
                Layout.fillWidth: true
                implicitHeight: 150
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 18
                    spacing: 12
                    RowLayout {
                        spacing: 12
                        Rectangle { width: 10; height: 10; radius: 5; color: !pr.live ? win.cRed : (k.printing ? win.cAcc : win.cOk) }
                        Text {
                            text: !backend.connected ? "Nicht verbunden" : (!k.connected ? (k.message || "Kit nicht am Pi angeschlossen") : (k.state_name || "–"))
                            color: win.cInk; font.pixelSize: 20; font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideRight
                        }
                        Text { visible: k.printing === true; text: (k.percent || 0) + " %"; color: "#5cc3e3"; font.pixelSize: 26; font.weight: Font.DemiBold }
                    }
                    Rectangle {
                        Layout.fillWidth: true; Layout.preferredHeight: 8; radius: 4; color: "#1d2228"
                        Rectangle { width: parent.width * Math.min(1, (k.percent || 0) / 100); height: parent.height; radius: 4; color: win.cAcc; Behavior on width { NumberAnimation { duration: 400 } } }
                    }
                    RowLayout {
                        spacing: 34
                        Stat { label: "Schicht"; value: k.printing ? (k.layer || 0) + (pr.job && pr.job.layers ? " / " + pr.job.layers : "") : "–" }
                        Stat { label: "Druckzeit"; value: k.printing ? win.fmtTime(k.elapsed_s) : "–" }
                        Stat { label: "Job"; value: pr.job ? pr.job.name : "–" }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 14

                Card {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    LayerView {
                        id: liveView
                        anchors.fill: parent; anchors.margins: 14
                        plateMm: backend.plateMm
                        Text {
                            visible: !(k.printing === true)
                            anchors.centerIn: parent
                            text: "Hier erscheint während des Drucks die aktuelle Schicht"
                            color: win.cMut; font.pixelSize: 13
                        }
                    }
                }

                ColumnLayout {
                    Layout.preferredWidth: 300
                    Layout.maximumWidth: 300
                    Layout.fillHeight: true
                    spacing: 14

                    Card {
                        Layout.fillWidth: true
                        implicitHeight: tc.implicitHeight + 28
                        GridLayout {
                            id: tc
                            anchors.fill: parent; anchors.margins: 14
                            columns: 2; rowSpacing: 12; columnSpacing: 10
                            Stat { label: "Oberfläche"; value: win.num(k.surface) + " °C"; tint: win.cHeat }
                            Stat { label: "Kammer"; value: win.num(k.chamber) + " °C" }
                            Text { text: "Soll Druck " + win.num(k.target_surface_print, 0) + " °C"; color: win.cMut; font.pixelSize: 11 }
                            Text { text: "Soll Druck " + win.num(k.target_chamber_print, 0) + " °C"; color: win.cMut; font.pixelSize: 11 }
                            Text { text: "Laser " + win.num(k.laser_speed, 0) + " mm/s"; color: win.cMut; font.pixelSize: 11; Layout.columnSpan: 2 }
                        }
                    }

                    Card {
                        Layout.fillWidth: true
                        implicitHeight: ctl.implicitHeight + 28
                        ColumnLayout {
                            id: ctl
                            anchors.fill: parent; anchors.margins: 14
                            spacing: 8
                            Caption { text: "Steuerung" }
                            RowLayout {
                                spacing: 8
                                KButton { text: "Aufheizen"; kind: "hot"; Layout.fillWidth: true; enabled: pr.live && k.printing !== true; onClicked: backend.cmd({ cmd: "warmup", on: true }) }
                                KButton { text: "Heizen aus"; Layout.fillWidth: true; enabled: pr.live; onClicked: backend.cmd({ cmd: "warmup", on: false }) }
                            }
                            KButton {
                                text: "Zum Abkühlen springen"; Layout.fillWidth: true; enabled: pr.live && k.printing === true
                                onClicked: confirm.ask("Sintern beenden und abkühlen? Der Druck endet nach der aktuellen Schicht.", function() { backend.cmd({ cmd: "stop_sintering" }) })
                            }
                            KButton {
                                text: "Druck abbrechen"; kind: "red"; Layout.fillWidth: true; enabled: pr.live && k.printing === true
                                onClicked: confirm.ask("Druck wirklich abbrechen?", function() { backend.cmd({ cmd: "abort_print" }) })
                            }
                            KButton { text: "Temperaturprotokolle"; kind: "ghost"; Layout.fillWidth: true; onClicked: backend.openFolder("logs") }
                        }
                    }

                    Card {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 14
                            spacing: 6
                            Caption { text: "Meldungen" }
                            ListView {
                                Layout.fillWidth: true; Layout.fillHeight: true
                                clip: true; spacing: 6
                                model: (k.errors || []).concat(k.warnings || [])
                                delegate: Rectangle {
                                    width: ListView.view.width
                                    implicitHeight: mc.implicitHeight + 14
                                    radius: 8
                                    color: modelData.kind === "Fehler" ? "#2a1215" : "#2a2112"
                                    ColumnLayout {
                                        id: mc
                                        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 7
                                        spacing: 1
                                        Text { text: modelData.code + " · " + modelData.title; color: modelData.kind === "Fehler" ? "#ffb4b6" : "#ffd59a"; font.pixelSize: 12; font.weight: Font.DemiBold; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                                        Text { text: modelData.text; color: win.cMut; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                                    }
                                }
                            }
                            Text { visible: !(k.errors && k.errors.length) && !(k.warnings && k.warnings.length); text: pr.live ? "Keine Fehler oder Warnungen" : "–"; color: win.cMut; font.pixelSize: 12 }
                        }
                    }
                }
            }
        }
    }
}
