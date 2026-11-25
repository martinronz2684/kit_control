import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: pr
    property var k: win.kit
    property var job: k.current_job || null
    property bool live: backend.connected && k.connected === true
    property int tab: 0                       // 0 = Jobs am Kit, 1 = Verlauf
    property int shownLayer: 0

    // Aktuelle Schicht des laufenden Jobs vom Pi holen, sobald sie sich ändert
    onKChanged: {
        if (job && job.id && k.printing && k.layer && k.layer !== shownLayer) {
            shownLayer = k.layer
            backend.requestPiLayer(job.id, k.layer)
        }
    }
    Connections { target: backend; function onPiLayerReady(d) { liveView.layerData = d } }

    RowLayout {
        anchors.fill: parent
        spacing: 18

        // Links: Verbindung, Senden, Bibliothek
        ColumnLayout {
            Layout.preferredWidth: 360
            Layout.maximumWidth: 360
            Layout.minimumWidth: 270
            Layout.fillWidth: true
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
                        KButton { text: backend.searching ? win.t("Sucht …") : win.t("Suchen"); kind: "ghost"; enabled: !backend.searching; onClicked: backend.discover() }
                    }
                    Repeater {
                        model: backend.devices
                        delegate: Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 42; radius: 9
                            color: modelData.host === backend.host ? win.cSel : (dm.containsMouse ? win.cHover : win.cRow)
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
                        KField { id: hostField; Layout.fillWidth: true; placeholderText: win.t("IP-Adresse des Pi"); text: backend.host; onAccepted: backend.connectHost(text) }
                        KButton { text: win.t("Verbinden"); onClicked: backend.connectHost(hostField.text) }
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
                    Caption { text: win.t("Job senden") }
                    Body {
                        color: win.cMut; font.pixelSize: 12
                        text: backend.sliceState === "done"
                              ? (win.meta.layers + win.t(" Schichten · ") + win.meta.height_mm.toFixed(1) + win.t(" mm · ca. ") + win.fmtTime(backend.estimate.seconds) + " · " + backend.profile.name)
                              : win.t("Noch kein geslicter Job – unter „Vorschau“ slicen.")
                    }
                    KButton { text: win.t("Nur übertragen"); Layout.fillWidth: true; enabled: backend.connected && backend.sliceState === "done"; onClicked: backend.send(false) }
                    KButton {
                        text: win.t("Übertragen und starten"); kind: "pri"; Layout.fillWidth: true
                        enabled: pr.live && backend.sliceState === "done" && k.printing !== true
                        onClicked: confirm.ask(win.t("Job zum Kit übertragen und den Druck sofort starten? Der Kit heizt dann auf."), function() { backend.send(true) })
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
                        spacing: 6
                        KButton { text: win.t("Jobs am Kit"); kind: pr.tab === 0 ? "pri" : "ghost"; implicitHeight: 30; onClicked: pr.tab = 0 }
                        KButton { text: win.t("Verlauf"); kind: pr.tab === 1 ? "pri" : "ghost"; implicitHeight: 30; onClicked: pr.tab = 1 }
                        Item { Layout.fillWidth: true }
                        KButton { visible: pr.tab === 0; text: win.t("Aktualisieren"); kind: "ghost"; implicitHeight: 30; enabled: backend.connected; onClicked: backend.refreshJobs() }
                    }
                    // Druckverlauf
                    ListView {
                        visible: pr.tab === 1
                        Layout.fillWidth: true; Layout.fillHeight: true
                        clip: true; spacing: 4
                        model: backend.printHistory
                        Text {
                            visible: parent.count === 0; anchors.centerIn: parent; width: parent.width - 20
                            horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                            text: win.t("Noch keine Drucke aufgezeichnet – beendete Drucke erscheinen hier.")
                            color: win.cMut; font.pixelSize: 12
                        }
                        delegate: Rectangle {
                            width: ListView.view.width
                            height: 50; radius: 8; color: win.cRow
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10
                                Rectangle { width: 8; height: 8; radius: 4; color: modelData.result === "fertig" ? win.cOk : win.cHeat }
                                ColumnLayout {
                                    Layout.fillWidth: true; spacing: 1
                                    Text { text: modelData.name; color: win.cInk; font.pixelSize: 13; elide: Text.ElideRight; Layout.fillWidth: true }
                                    Text {
                                        text: Qt.formatDateTime(new Date(modelData.end * 1000), "dd.MM.yy hh:mm") + " · " + win.fmtTime(modelData.duration_s)
                                              + " · " + modelData.layers + win.t(" Schichten") + (modelData.result === "fertig" ? "" : " · " + win.t("abgebrochen bei ") + modelData.percent + " %")
                                        color: win.cMut; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true
                                    }
                                }
                            }
                        }
                    }
                    ListView {
                        visible: pr.tab === 0
                        Layout.fillWidth: true; Layout.fillHeight: true
                        clip: true; spacing: 4
                        model: backend.piJobs
                        delegate: Rectangle {
                            width: ListView.view.width
                            height: 50; radius: 8; color: win.cRow
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 6
                                ColumnLayout {
                                    Layout.fillWidth: true; spacing: 1
                                    Text { text: modelData.name; color: win.cInk; font.pixelSize: 13; elide: Text.ElideRight; Layout.fillWidth: true }
                                    Text { text: (modelData.layers ? modelData.layers + win.t(" Schichten · ") + modelData.height_mm + win.t(" mm") : (modelData.error || "")) ; color: win.cMut; font.pixelSize: 11 }
                                }
                                KButton {
                                    text: win.t("Starten"); kind: "ghost"
                                    enabled: pr.live && k.printing !== true && !modelData.error
                                    onClicked: confirm.ask("„" + modelData.name + win.t("“ jetzt drucken?"), function() { backend.cmd({ cmd: "job_start", id: modelData.id }) })
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
                            text: !backend.connected ? win.t("Nicht verbunden") : (!k.connected ? (k.message || win.t("Kit nicht am Pi angeschlossen")) : (k.state_name || "–"))
                            color: win.cInk; font.pixelSize: 20; font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideRight
                        }
                        Text { visible: k.printing === true; text: (k.percent || 0) + " %"; color: "#5cc3e3"; font.pixelSize: 26; font.weight: Font.DemiBold }
                    }
                    Rectangle {
                        Layout.fillWidth: true; Layout.preferredHeight: 8; radius: 4; color: win.cTrack
                        Rectangle { width: parent.width * Math.min(1, (k.percent || 0) / 100); height: parent.height; radius: 4; color: win.cAcc; Behavior on width { NumberAnimation { duration: 400 } } }
                    }
                    RowLayout {
                        spacing: 34
                        Stat { label: win.t("Schicht"); value: k.printing ? (k.layer || 0) + (pr.job && pr.job.layers ? " / " + pr.job.layers : "") : "–" }
                        Stat { label: win.t("Druckzeit"); value: k.printing ? win.fmtTime(k.elapsed_s) : "–" }
                        Stat {
                            visible: k.countdown_on === true
                            label: win.t("Aufheizen noch")
                            value: win.fmtCountdown(k.countdown_s)
                            tint: win.cHeat
                        }
                        Stat {
                            visible: k.countdown_on !== true
                            label: win.t("Restzeit (geschätzt)")
                            value: !k.printing ? "–"
                                 : (k.layer > 3 && pr.job && pr.job.layers) ? win.fmtTime(k.elapsed_s / k.layer * Math.max(0, pr.job.layers - k.layer))
                                 : (k.percent > 2 ? win.fmtTime(k.elapsed_s / k.percent * (100 - k.percent)) : "–")
                            tint: win.cAcc
                        }
                        Stat { label: win.t("Job"); value: pr.job ? pr.job.name : "–" }
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
                    Layout.minimumWidth: 200
                    LayerView {
                        id: liveView
                        anchors.fill: parent; anchors.margins: 14
                        plateMm: backend.plateMm
                        Text {
                            visible: !(k.printing === true)
                            anchors.centerIn: parent
                            width: parent.width - 24
                            wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter
                            text: win.t("Hier erscheint während des Drucks die aktuelle Schicht")
                            color: win.cMut; font.pixelSize: 13
                        }
                    }
                }

                Flickable {
                    id: rightFl
                    Layout.preferredWidth: 300
                    Layout.maximumWidth: 300
                    Layout.minimumWidth: 260
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    contentWidth: width
                    contentHeight: Math.max(height, rightCol.implicitHeight)
                    flickableDirection: Flickable.VerticalFlick
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { policy: rightCol.implicitHeight > rightFl.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff }
                ColumnLayout {
                    id: rightCol
                    width: rightFl.width - (rightCol.implicitHeight > rightFl.height ? 10 : 0)
                    height: Math.max(rightFl.height, implicitHeight)
                    spacing: 14

                    Card {
                        Layout.fillWidth: true
                        implicitHeight: tc.implicitHeight + 28
                        GridLayout {
                            id: tc
                            anchors.fill: parent; anchors.margins: 14
                            columns: 2; rowSpacing: 12; columnSpacing: 10
                            Stat { label: win.t("Oberfläche"); value: win.num(k.surface) + " °C"; tint: win.cHeat }
                            Stat { label: win.t("Kammer"); value: win.num(k.chamber) + " °C" }
                            Text { text: win.t("Soll Druck ") + win.num(k.target_surface_print, 0) + " °C"; color: win.cMut; font.pixelSize: 11 }
                            Text { text: win.t("Soll Druck ") + win.num(k.target_chamber_print, 0) + " °C"; color: win.cMut; font.pixelSize: 11 }
                            Text { text: win.t("Laser ") + win.num(k.laser_speed, 0) + win.t(" mm/s"); color: win.cMut; font.pixelSize: 11; Layout.columnSpan: 2 }
                            TempChart { Layout.columnSpan: 2; Layout.fillWidth: true; Layout.preferredHeight: 70 }
                        }
                    }

                    Card {
                        Layout.fillWidth: true
                        implicitHeight: ctl.implicitHeight + 28
                        ColumnLayout {
                            id: ctl
                            anchors.fill: parent; anchors.margins: 14
                            spacing: 8
                            Caption { text: win.t("Steuerung") }
                            RowLayout {
                                spacing: 8
                                KButton { text: win.t("Aufheizen"); kind: "hot"; Layout.fillWidth: true; enabled: pr.live && k.printing !== true; onClicked: backend.cmd({ cmd: "warmup", on: true }) }
                                KButton { text: win.t("Heizen aus"); Layout.fillWidth: true; enabled: pr.live; onClicked: backend.cmd({ cmd: "warmup", on: false }) }
                            }
                            KButton {
                                text: win.t("Zum Abkühlen springen"); Layout.fillWidth: true; enabled: pr.live && k.printing === true
                                onClicked: confirm.ask(win.t("Sintern beenden und abkühlen? Der Druck endet nach der aktuellen Schicht."), function() { backend.cmd({ cmd: "stop_sintering" }) })
                            }
                            KButton {
                                text: win.t("Druck abbrechen"); kind: "red"; Layout.fillWidth: true; enabled: pr.live && k.printing === true
                                onClicked: confirm.ask(win.t("Druck wirklich abbrechen?"), function() { backend.cmd({ cmd: "abort_print" }) })
                            }
                            KButton { text: win.t("Temperaturprotokolle"); kind: "ghost"; Layout.fillWidth: true; onClicked: backend.openFolder("logs") }
                        }
                    }

                    Card {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: 110
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 14
                            spacing: 6
                            Caption { text: win.t("Meldungen") }
                            ListView {
                                Layout.fillWidth: true; Layout.fillHeight: true
                                clip: true; spacing: 6
                                model: (k.errors || []).concat(k.warnings || [])
                                delegate: Rectangle {
                                    width: ListView.view.width
                                    implicitHeight: mc.implicitHeight + 14
                                    radius: 8
                                    color: modelData.kind === "Fehler" ? win.cErrBg : "#2a2112"
                                    ColumnLayout {
                                        id: mc
                                        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 7
                                        spacing: 1
                                        Text { text: modelData.code + " · " + modelData.title; color: modelData.kind === "Fehler" ? win.cErrInk : win.cWarnInk; font.pixelSize: 12; font.weight: Font.DemiBold; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                                        Text { text: modelData.text; color: win.cMut; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                                    }
                                }
                            }
                            Text { visible: !(k.errors && k.errors.length) && !(k.warnings && k.warnings.length); text: pr.live ? win.t("Keine Fehler oder Warnungen") : "–"; color: win.cMut; font.pixelSize: 12 }
                        }
                    }
                }
                }
            }
        }
    }
}
