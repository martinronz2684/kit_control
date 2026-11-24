import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: pw
    property var m: backend.sliceMeta || ({})
    property real step: 0.1
    property bool ready: backend.connected && win.kit.connected === true && win.kit.printing !== true
    property bool prep: win.kit.state_name !== undefined && String(win.kit.state_name).indexOf("Pulver") >= 0

    function mv(platform, dir) { backend.cmd({ cmd: "move", platform: platform, mm: dir * pw.step }) }

    RowLayout {
        anchors.fill: parent
        spacing: 18

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 18

            Card {
                Layout.fillWidth: true
                implicitHeight: 130
                RowLayout {
                    anchors.fill: parent; anchors.margins: 22
                    spacing: 30
                    Stat { label: "Pulver laden"; value: pw.m.powder_mm !== undefined ? pw.m.powder_mm.toFixed(1) + " mm" : "–"; tint: win.cAcc }
                    Stat { label: "Bauhöhe"; value: pw.m.height_mm !== undefined ? pw.m.height_mm.toFixed(1) + " mm" : "–" }
                    Body {
                        Layout.fillWidth: true
                        color: win.cMut
                        text: pw.m.powder_mm !== undefined
                              ? "Vorrat nur so weit füllen, wie der Job braucht: Bauhöhe + 5 mm Puffer."
                              : "Nach dem Slicen steht hier, wie viel Pulver der Job braucht (Bauhöhe + 5 mm)."
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 18

                // Bauplattform
                Card {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 20
                        spacing: 12
                        Caption { text: "Bauplattform" }
                        Item { Layout.fillHeight: true }
                        KButton { text: "▲  hoch"; Layout.fillWidth: true; implicitHeight: 54; enabled: pw.ready; onClicked: pw.mv("print", -1) }
                        KButton { text: "▼  runter"; Layout.fillWidth: true; implicitHeight: 54; enabled: pw.ready; onClicked: pw.mv("print", 1) }
                        Item { Layout.fillHeight: true }
                    }
                }
                // Vorrat
                Card {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 20
                        spacing: 12
                        Caption { text: "Vorrat" }
                        Item { Layout.fillHeight: true }
                        KButton { text: "▲  hoch"; Layout.fillWidth: true; implicitHeight: 54; enabled: pw.ready; onClicked: pw.mv("reservoir", -1) }
                        KButton { text: "▼  runter"; Layout.fillWidth: true; implicitHeight: 54; enabled: pw.ready; onClicked: pw.mv("reservoir", 1) }
                        Item { Layout.fillHeight: true }
                    }
                }
            }
        }

        Flickable {
            id: rightFlick
            Layout.preferredWidth: 320
            Layout.maximumWidth: 320
            Layout.fillHeight: true
            clip: true
            contentWidth: width
            contentHeight: rightCol.implicitHeight
            flickableDirection: Flickable.VerticalFlick
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: rightFlick.contentHeight > rightFlick.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff }
        ColumnLayout {
            id: rightCol
            width: rightFlick.width - (rightFlick.contentHeight > rightFlick.height ? 10 : 0)
            spacing: 14

            Card {
                Layout.fillWidth: true
                implicitHeight: sc.implicitHeight + 28
                ColumnLayout {
                    id: sc
                    anchors.fill: parent; anchors.margins: 14
                    spacing: 10
                    Caption { text: "Schrittweite" }
                    RowLayout {
                        spacing: 8
                        Repeater {
                            model: [0.1, 1, 5, 10]
                            delegate: KButton {
                                Layout.fillWidth: true
                                text: String(modelData).replace(".", ",") + " mm"
                                leftPadding: 4; rightPadding: 4
                                kind: pw.step === modelData ? "pri" : "normal"
                                onClicked: pw.step = modelData
                            }
                        }
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                implicitHeight: pc.implicitHeight + 28
                ColumnLayout {
                    id: pc
                    anchors.fill: parent; anchors.margins: 14
                    spacing: 10
                    Caption { text: "Pulvervorbereitung" }
                    KButton { text: "Starten"; Layout.fillWidth: true; enabled: pw.ready; onClicked: backend.cmd({ cmd: "powder_prep_on" }) }
                    KButton { text: "Beenden"; kind: "ghost"; Layout.fillWidth: true; enabled: pw.ready; onClicked: backend.cmd({ cmd: "powder_prep_off" }) }
                    KButton { text: "Pulver auftragen (0,15 mm)"; kind: "pri"; Layout.fillWidth: true; enabled: pw.ready; onClicked: backend.cmd({ cmd: "make_layer", mm: 0.15 }) }
                }
            }

            CalibCard { Layout.fillWidth: true; ready: pw.ready }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: hint.implicitHeight + 24
                radius: 12; color: "#15181c"; border.color: win.cLine
                Body {
                    id: hint
                    anchors.fill: parent; anchors.margins: 12
                    font.pixelSize: 12; color: win.cMut
                    text: !backend.connected ? "Nicht mit dem Kit Control verbunden – unter „Drucken“ verbinden."
                        : win.kit.printing === true ? "Während des Drucks gesperrt."
                        : "Fahren wie am Display. Die Freigabe für die Bedienung vom PC erfolgt am Pi (KIT_REMOTE=1)."
                }
            }
        }
        }
    }
}
