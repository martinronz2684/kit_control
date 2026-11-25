import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Einstellungen (Zahnrad unten links): Sprache, idealer Bereich, Anordnen-Vorgaben, Heizstrahler,
// Laser-Kalibrierung, Druckzeit-Schätzung, Start-Verhalten, Ordner.
Popup {
    id: sp
    objectName: "settingsPop"
    anchors.centerIn: parent
    width: Math.min(600, parent.width - 80)
    height: Math.min(spCol.implicitHeight + 2 * padding, parent.height - 60)
    modal: true
    padding: 22
    background: Rectangle { radius: 14; color: win.cPanel; border.color: win.cLine }
    readonly property var st: backend.settings || ({})
    readonly property bool ready: backend.connected && win.kit.connected === true && win.kit.printing !== true
    function num(t) { var v = Number(String(t).replace(",", ".")); return isFinite(v) ? v : NaN }

    Flickable {
        id: spFlick
        anchors.fill: parent
        contentWidth: width
        contentHeight: spCol.implicitHeight
        flickableDirection: Flickable.VerticalFlick
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        ScrollBar.vertical: ScrollBar { policy: spFlick.contentHeight > spFlick.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff }

        ColumnLayout {
            id: spCol
            width: spFlick.width - (spFlick.contentHeight > spFlick.height ? 14 : 0)
            spacing: 16

            RowLayout {
                Layout.fillWidth: true
                Text { text: win.t("Einstellungen"); color: win.cInk; font.pixelSize: 20; font.weight: Font.DemiBold; Layout.fillWidth: true }
                KButton { text: win.t("Schließen"); kind: "ghost"; onClicked: sp.close() }
            }

            // Sprache
            ColumnLayout {
                Layout.fillWidth: true; spacing: 6
                Caption { text: win.t("Sprache") }
                RowLayout {
                    Layout.fillWidth: true; spacing: 8
                    KButton { text: "Deutsch"; Layout.fillWidth: true; Layout.preferredWidth: 1; kind: sp.st.lang === "de" ? "pri" : "normal"; onClicked: backend.setSetting("lang", "de") }
                    KButton { text: "English"; Layout.fillWidth: true; Layout.preferredWidth: 1; kind: sp.st.lang === "en" ? "pri" : "normal"; onClicked: backend.setSetting("lang", "en") }
                }
            }

            // Idealer Baubereich
            ColumnLayout {
                Layout.fillWidth: true; spacing: 6
                Caption { text: win.t("Idealer Druckbereich") }
                Body {
                    Layout.fillWidth: true; font.pixelSize: 12; color: win.cMut
                    text: win.t("Bereich mit der gleichmäßigsten Temperatur. Auto-Anordnen packt hier hinein, Teile außerhalb werden markiert. Bauraum: 110 × 110 mm, bis 130 mm hoch.")
                }
                RowLayout {
                    Layout.fillWidth: true; spacing: 12
                    NumField {
                        Layout.fillWidth: true; Layout.preferredWidth: 1
                        label: win.t("Breite und Tiefe"); unit: "mm"; value: String(sp.st.ideal_xy)
                        onCommitted: (v) => { var n = sp.num(v); if (!isNaN(n)) backend.setSetting("ideal_xy", n) }
                    }
                    NumField {
                        Layout.fillWidth: true; Layout.preferredWidth: 1
                        label: win.t("Höhe"); unit: "mm"; value: String(sp.st.ideal_z)
                        onCommitted: (v) => { var n = sp.num(v); if (!isNaN(n)) backend.setSetting("ideal_z", n) }
                    }
                    KButton { text: win.t("Standard"); kind: "ghost"; Layout.alignment: Qt.AlignBottom; onClicked: backend.resetIdeal() }
                }
            }

            // Anordnen-Vorgaben
            ColumnLayout {
                Layout.fillWidth: true; spacing: 6
                Caption { text: win.t("Auto-Anordnen – Vorgaben") }
                RowLayout {
                    Layout.fillWidth: true; spacing: 12
                    NumField {
                        Layout.fillWidth: true; Layout.preferredWidth: 1
                        label: win.t("Abstand zwischen Teilen"); unit: "mm"; value: String(sp.st.pack_gap)
                        onCommitted: (v) => { var n = sp.num(v); if (n >= 0) backend.setSetting("pack_gap", n) }
                    }
                    NumField {
                        Layout.fillWidth: true; Layout.preferredWidth: 1
                        label: win.t("Abstand zum Rand"); unit: "mm"; value: String(sp.st.pack_wall)
                        onCommitted: (v) => { var n = sp.num(v); if (n >= 0) backend.setSetting("pack_wall", n) }
                    }
                }
            }

            // Heizstrahler (Lampenleistung)
            ColumnLayout {
                Layout.fillWidth: true; spacing: 6
                Caption { text: win.t("Heizstrahler-Leistung (Experte)") }
                Body {
                    Layout.fillWidth: true; font.pixelSize: 12; color: win.cMut
                    text: win.t("Wirkt sofort und bleibt im Kit gespeichert. Der Kit kann den Wert nicht zurückmelden – angezeigt wird, was der Pi zuletzt gesendet hat. Tipp: eine Lampe so einstellen, dass sie gleich hell leuchtet wie eine noch originale.")
                }
                RowLayout {
                    Layout.fillWidth: true; spacing: 12
                    Repeater {
                        model: [[win.t("Links"), "left"], [win.t("Rechts"), "right"], [win.t("Vorne"), "front"]]
                        delegate: ColumnLayout {
                            Layout.fillWidth: true; Layout.preferredWidth: 1
                            spacing: 4
                            readonly property var cur: win.kit.lamps ? win.kit.lamps[modelData[1]] : undefined
                            Text {
                                text: win.t(modelData[0]) + "  ·  " + (cur !== undefined ? cur + " %" : win.t("original"))
                                color: win.cMut; font.pixelSize: 12; elide: Text.ElideRight; Layout.fillWidth: true
                            }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 6
                                KField { id: lampF; Layout.fillWidth: true; placeholderText: "0–100"; text: cur !== undefined ? String(cur) : "" }
                                KButton {
                                    text: win.t("Senden")
                                    enabled: sp.ready && sp.num(lampF.text) >= 0 && sp.num(lampF.text) <= 100
                                    onClicked: backend.cmd({ cmd: "lamp", which: modelData[1], percent: sp.num(lampF.text), expert: true })
                                }
                            }
                        }
                    }
                }
                Body {
                    visible: !sp.ready
                    Layout.fillWidth: true; font.pixelSize: 12; color: win.cMut
                    text: win.t("Senden geht nur mit verbundenem Kit und nicht während des Drucks (Freigabe am Pi: KIT_REMOTE=1).")
                }
            }

            // Kalibrierung
            CalibCard { Layout.fillWidth: true; ready: sp.ready; color: "transparent"; border.width: 0 }

            // Druckzeit-Schätzung
            ColumnLayout {
                Layout.fillWidth: true; spacing: 6
                Caption { text: win.t("Druckzeit-Schätzung") }
                RowLayout {
                    Layout.fillWidth: true; spacing: 12
                    NumField {
                        Layout.fillWidth: true; Layout.preferredWidth: 1
                        label: win.t("Lasergeschwindigkeit, wenn das Profil keine vorgibt"); unit: win.t("mm/s"); value: String(sp.st.kit_laser_speed)
                        onCommitted: (v) => { var n = sp.num(v); if (n > 0) backend.setSetting("kit_laser_speed", n) }
                    }
                    KButton { text: win.t("Lernwerte zurücksetzen"); kind: "ghost"; Layout.alignment: Qt.AlignBottom; onClicked: backend.resetEstimate() }
                }
                Body {
                    Layout.fillWidth: true; font.pixelSize: 12; color: win.cMut
                    text: win.t("Gelernt aus ") + sp.st.est_learned + win.t(" Drucken, Faktor ") + Number(sp.st.est_factor || 1).toFixed(2).replace(".", win.lang === "en" ? "." : ",")
                          + win.t(". Die Geschwindigkeit übernimmt Kit Control auch vom Kit, sobald einer verbunden ist.")
                }
            }

            // Start
            ColumnLayout {
                Layout.fillWidth: true; spacing: 4
                Caption { text: win.t("Beim Start") }
                KCheck { text: win.t("Nach Updates suchen"); checked: sp.st.check_updates === true; onToggled: backend.setSetting("check_updates", checked) }
                KCheck { text: win.t("Mit dem zuletzt verwendeten Kit verbinden"); checked: sp.st.auto_connect === true; onToggled: backend.setSetting("auto_connect", checked) }
                KCheck { text: win.t("Windows-Benachrichtigungen (Druck fertig, Aufheizen fertig, Fehler)"); checked: sp.st.notify === true; onToggled: backend.setSetting("notify", checked) }
            }

            // Ordner / Info
            ColumnLayout {
                Layout.fillWidth: true; spacing: 6
                Caption { text: win.t("Ordner und Info") }
                RowLayout {
                    Layout.fillWidth: true; spacing: 8
                    KButton { text: win.t("Profile"); Layout.fillWidth: true; Layout.preferredWidth: 1; onClicked: backend.openFolder("profiles") }
                    KButton { text: win.t("Temperaturprotokolle"); Layout.fillWidth: true; Layout.preferredWidth: 1; onClicked: backend.openFolder("logs") }
                    KButton { text: win.t("Einstellungen"); Layout.fillWidth: true; Layout.preferredWidth: 1; onClicked: backend.openFolder("data") }
                }
                Body {
                    Layout.fillWidth: true; font.pixelSize: 12; color: win.cMut
                    text: win.t("Kit Control ") + backend.version + win.t(" · github.com/martinronz2684/kit_control")
                }
            }
        }
    }
}
