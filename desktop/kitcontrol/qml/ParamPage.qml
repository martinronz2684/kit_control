import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: pp
    property var prof: backend.profile
    property var ed: JSON.parse(JSON.stringify(prof))
    property bool ro: prof.builtin === true
    property string err: ""
    onProfChanged: { ed = JSON.parse(JSON.stringify(prof)); err = ""; nameField.text = prof.builtin ? prof.name + win.t(" (eigen)") : prof.name }

    function setv(key, v) {
        v = Number(String(v).replace(",", "."))
        // µm-Felder: Eingaben unter 5 als mm verstehen (0.05 -> 50 µm)
        if (/_um$/.test(key) && v > 0 && v < 5) v = Math.round(v * 1000)
        ed[key] = v
        apply()
    }
    // Jede Änderung gilt sofort: eigene Profile werden gespeichert, aus einer Vorlage entsteht automatisch ein eigenes Profil
    function apply() { save(false, true) }
    function setTemp(key, v) { if (!ed.temps) ed.temps = {}; ed.temps[key] = Number(String(v).replace(",", ".")); apply() }
    function save(asNew, quiet) {
        var q = JSON.parse(JSON.stringify(ed))
        q.name = nameField.text
        q.hatch_angles_deg = angleField.text.split(/[;,]/).map(function(s) { return Number(s.trim()) }).filter(function(n) { return !isNaN(n) })
        q.laser_speed_mm_s = laserField.text.trim() === "" ? null : Number(laserField.text.replace(",", "."))
        q.contour_speed_mm_s = contourField.text.trim() === "" ? null : Number(contourField.text.replace(",", "."))
        function n(t) { var v = String(t).trim().replace(",", "."); return v === "" ? null : Number(v) }
        q.hatch_angle_step_deg = n(stepField.text)
        q.island_mm = n(islandField.text) || 0
        q.skin_layers = n(skinField.text) || 0
        q.core_spacing_um = n(coreField.text)
        q.shrink_pct = { x: n(shrinkX.text) || 0, y: n(shrinkY.text) || 0, z: n(shrinkZ.text) || 0 }
        q.contour_first = contourFirst.checked
        q.optimize_path = optPath.checked
        q.keep_thin = keepThin.checked
        // Heizstrahler-Leistung: jetzt unter Einstellungen (direkt am Kit); Profilwert bleibt, wie er ist
        if (asNew || q.builtin) {
            q.base = q.id; delete q.id; q.builtin = false
            if (q.name === pp.prof.name) q.name = pp.prof.name + win.t(" (eigen)")
        }
        err = quiet ? backend.applyProfile(q) : backend.saveProfile(q)
    }

    RowLayout {
        anchors.fill: parent
        spacing: 18

        // Profilliste
        Card {
            Layout.preferredWidth: 300
            Layout.fillHeight: true
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 14
                spacing: 8
                RowLayout {
                    Caption { text: win.t("Materialien"); Layout.fillWidth: true }
                    KButton { text: win.t("+ Neues Material"); kind: "pri"; implicitHeight: 32; onClicked: backend.newProfile(win.t("Neues Material")) }
                }
                ListView {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true; spacing: 6
                    model: backend.profiles
                    delegate: Rectangle {
                        width: ListView.view.width
                        height: 62; radius: 10
                        color: modelData.id === backend.profileId ? "#16313c" : (pm.containsMouse ? "#181c21" : "#15181c")
                        border.color: modelData.id === backend.profileId ? win.cAcc : win.cLine
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 10
                            spacing: 2
                            RowLayout {
                                Text { text: modelData.name; color: win.cInk; font.pixelSize: 14; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
                                Rectangle {
                                    visible: modelData.builtin === true
                                    radius: 6; color: "#1d2228"; implicitWidth: vt.implicitWidth + 12; implicitHeight: 18
                                    Text { id: vt; anchors.centerIn: parent; text: win.t("Vorlage"); color: win.cMut; font.pixelSize: 10 }
                                }
                            }
                            Text {
                                text: (modelData.base ? win.t("auf Basis ") + modelData.base.toUpperCase() + " · " : "") + modelData.layer_um + win.t(" µm · Schraffur ") + modelData.hatch_spacing_um + win.t(" µm · Kontur ") + modelData.perimeter_offset_um + " µm"
                                color: win.cMut; font.pixelSize: 11
                            }
                        }
                        MouseArea { id: pm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: backend.selectProfile(modelData.id) }
                    }
                }
                RowLayout {
                    spacing: 8
                    KButton { text: win.t("Importieren"); kind: "ghost"; Layout.fillWidth: true; onClicked: importProfile.open() }
                    KButton { text: win.t("Exportieren"); kind: "ghost"; Layout.fillWidth: true; onClicked: exportProfile.open() }
                }
                KButton { text: win.t("Profilordner öffnen"); kind: "ghost"; Layout.fillWidth: true; onClicked: backend.openFolder("profiles") }
            }
        }

        // Editor
        Card {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Flickable {
                id: edFlick
                anchors.fill: parent; anchors.margins: 20
                contentHeight: edCol.implicitHeight
                contentWidth: width                     // nur senkrecht scrollen, Inhalt nie breiter als die Karte
                flickableDirection: Flickable.VerticalFlick
                boundsBehavior: Flickable.StopAtBounds
                clip: true
                ScrollBar.vertical: ScrollBar {}
                ColumnLayout {
                    id: edCol
                    width: edFlick.width - 12
                    spacing: 16

                    RowLayout {
                        Layout.maximumWidth: edCol.width
                        Layout.fillWidth: true
                        spacing: 12
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4
                            Text { text: win.t("Name"); color: win.cMut; font.pixelSize: 12 }
                            KField { id: nameField; onUserChanged: pp.apply(); Layout.fillWidth: true; Component.onCompleted: text = pp.prof.builtin ? pp.prof.name + win.t(" (eigen)") : pp.prof.name }
                        }
                    }
                    Rectangle {
                        visible: pp.ro
                        Layout.fillWidth: true
                        implicitHeight: roText.implicitHeight + 20
                        radius: 10; color: "#16252c"; border.color: "#1f4757"
                        Body {
                            id: roText; anchors.fill: parent; anchors.margins: 10
                            text: win.t("Vorlage aus Sintratec Central – Werte unverändert übernommen. Zum Anpassen als eigenes Profil speichern; die Felder lassen sich dafür bearbeiten.")
                            color: "#a9d7e7"; font.pixelSize: 12
                        }
                    }

                    Caption { text: win.t("Slicer (wie Central „Print Parameters“)") }
                    GridLayout {
                        Layout.maximumWidth: edCol.width
                        Layout.fillWidth: true
                        columns: 3; columnSpacing: 14; rowSpacing: 12
                        NumField { Layout.fillWidth: true; label: win.t("Schichthöhe"); unit: "µm"; value: String(pp.prof.layer_um); onCommitted: (v) => pp.setv("layer_um", Number(v)) }
                        NumField { Layout.fillWidth: true; label: win.t("Anzahl Perimeter"); unit: ""; value: String(pp.prof.perimeters); onCommitted: (v) => pp.setv("perimeters", Number(v)) }
                        NumField { Layout.fillWidth: true; label: win.t("Perimeter-Versatz"); unit: "µm"; value: String(pp.prof.perimeter_offset_um); onCommitted: (v) => pp.setv("perimeter_offset_um", Number(v)) }
                        NumField { Layout.fillWidth: true; label: win.t("Schraffur-Versatz"); unit: "µm"; value: String(pp.prof.hatch_offset_um); onCommitted: (v) => pp.setv("hatch_offset_um", Number(v)) }
                        NumField { Layout.fillWidth: true; label: win.t("Schraffur-Abstand"); unit: "µm"; value: String(pp.prof.hatch_spacing_um); onCommitted: (v) => pp.setv("hatch_spacing_um", Number(v)) }
                        NumField { Layout.fillWidth: true; label: win.t("Mindestvektorlänge"); unit: "µm"; value: String(pp.prof.min_vector_um); onCommitted: (v) => pp.setv("min_vector_um", Number(v)) }
                    }
                    ColumnLayout {
                        Layout.maximumWidth: edCol.width
                        Layout.fillWidth: true
                        spacing: 4
                        Text { text: win.t("Schraffurwinkel je Schicht (reihum)"); color: win.cMut; font.pixelSize: 12 }
                        KField { id: angleField; onUserChanged: pp.apply(); Layout.fillWidth: true; text: (pp.prof.hatch_angles_deg || []).join(", ") }
                    }
                    KCheck {
                        id: origBox
                        text: win.t("Originalkontur zusätzlich lasern")
                        checked: pp.prof.draw_original_boundary === true
                        onToggled: { pp.ed.draw_original_boundary = checked; pp.apply() }
                    }

                    Caption { text: win.t("Strategien (leer/0 = wie Central)"); Layout.topMargin: 6 }
                    GridLayout {
                        Layout.maximumWidth: edCol.width
                        Layout.fillWidth: true
                        columns: 3; columnSpacing: 14; rowSpacing: 12
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 4
                            Text { text: win.t("Winkelschritt je Schicht"); color: win.cMut; font.pixelSize: 12 }
                            KField { id: stepField; onUserChanged: pp.apply(); Layout.fillWidth: true; placeholderText: win.t("Liste oben (z. B. 67)"); text: pp.prof.hatch_angle_step_deg ? String(pp.prof.hatch_angle_step_deg) : "" }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 4
                            Text { text: win.t("Schachbrett-Felder (mm)"); color: win.cMut; font.pixelSize: 12 }
                            KField { id: islandField; onUserChanged: pp.apply(); Layout.fillWidth: true; placeholderText: win.t("aus (z. B. 5)"); text: pp.prof.island_mm ? String(pp.prof.island_mm) : "" }
                        }
                        Item { Layout.fillWidth: true }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 4
                            Text { text: win.t("Hautschichten oben/unten"); color: win.cMut; font.pixelSize: 12 }
                            KField { id: skinField; onUserChanged: pp.apply(); Layout.fillWidth: true; placeholderText: win.t("aus (z. B. 3)"); text: pp.prof.skin_layers ? String(pp.prof.skin_layers) : "" }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 4
                            Text { text: win.t("Schraffur-Abstand im Kern (µm)"); color: win.cMut; font.pixelSize: 12 }
                            KField { id: coreField; onUserChanged: pp.apply(); Layout.fillWidth: true; placeholderText: win.t("wie oben (z. B. 240)"); text: pp.prof.core_spacing_um ? String(pp.prof.core_spacing_um) : "" }
                        }
                        Item { Layout.fillWidth: true }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 4
                            Text { text: win.t("Schwundausgleich X (%)"); color: win.cMut; font.pixelSize: 12 }
                            KField { id: shrinkX; onUserChanged: pp.apply(); Layout.fillWidth: true; text: pp.prof.shrink_pct ? String(pp.prof.shrink_pct.x) : "0" }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 4
                            Text { text: win.t("Schwundausgleich Y (%)"); color: win.cMut; font.pixelSize: 12 }
                            KField { id: shrinkY; onUserChanged: pp.apply(); Layout.fillWidth: true; text: pp.prof.shrink_pct ? String(pp.prof.shrink_pct.y) : "0" }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 4
                            Text { text: win.t("Schwundausgleich Z (%)"); color: win.cMut; font.pixelSize: 12 }
                            KField { id: shrinkZ; onUserChanged: pp.apply(); Layout.fillWidth: true; text: pp.prof.shrink_pct ? String(pp.prof.shrink_pct.z) : "0" }
                        }
                    }
                    Flow {
                        Layout.maximumWidth: edCol.width
                        Layout.fillWidth: true
                        spacing: 24
                        Row {
                            spacing: 8
                            KSwitch { id: contourFirst; onToggled: pp.apply(); checked: pp.prof.contour_first !== false }
                            Text { text: win.t("Kontur vor Füllung"); color: win.cInk; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                        }
                        Row {
                            spacing: 8
                            KSwitch { id: optPath; onToggled: pp.apply(); checked: pp.prof.optimize_path === true }
                            Text { text: win.t("Laserwege optimieren"); color: win.cInk; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                        }
                        Row {
                            spacing: 8
                            KSwitch { id: keepThin; onToggled: pp.apply(); checked: pp.prof.keep_thin !== false }
                            Text { text: win.t("Dünne Wände erhalten"); color: win.cInk; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                        }
                    }

                    Caption { text: win.t("Temperaturen (am Kit vor dem Druck eingestellt)"); Layout.topMargin: 6 }
                    GridLayout {
                        Layout.maximumWidth: edCol.width
                        Layout.fillWidth: true
                        columns: 4; columnSpacing: 14; rowSpacing: 12
                        NumField { Layout.fillWidth: true; label: win.t("Oberfläche Aufheizen"); unit: "°C"; value: pp.prof.temps ? String(pp.prof.temps.surface_warmup) : ""; onCommitted: (v) => pp.setTemp("surface_warmup", v) }
                        NumField { Layout.fillWidth: true; label: win.t("Kammer Aufheizen"); unit: "°C"; value: pp.prof.temps ? String(pp.prof.temps.chamber_warmup) : ""; onCommitted: (v) => pp.setTemp("chamber_warmup", v) }
                        NumField { Layout.fillWidth: true; label: win.t("Oberfläche Druck"); unit: "°C"; value: pp.prof.temps ? String(pp.prof.temps.surface_print) : ""; onCommitted: (v) => pp.setTemp("surface_print", v) }
                        NumField { Layout.fillWidth: true; label: win.t("Kammer Druck"); unit: "°C"; value: pp.prof.temps ? String(pp.prof.temps.chamber_print) : ""; onCommitted: (v) => pp.setTemp("chamber_print", v) }
                    }

                    Caption { text: win.t("Laser (leer = Wert am Kit lassen)"); Layout.topMargin: 6 }
                    GridLayout {
                        Layout.maximumWidth: edCol.width
                        Layout.fillWidth: true
                        columns: 2; columnSpacing: 14; rowSpacing: 12
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 4
                            Text { text: win.t("Geschwindigkeit Füllung"); color: win.cMut; font.pixelSize: 12 }
                            KField { id: laserField; onUserChanged: pp.apply(); Layout.fillWidth: true; placeholderText: win.t("unverändert"); text: pp.prof.laser_speed_mm_s === null || pp.prof.laser_speed_mm_s === undefined ? "" : String(pp.prof.laser_speed_mm_s) }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 4
                            Text { text: win.t("Geschwindigkeit Kontur"); color: win.cMut; font.pixelSize: 12 }
                            KField { id: contourField; onUserChanged: pp.apply(); Layout.fillWidth: true; placeholderText: win.t("unverändert"); text: pp.prof.contour_speed_mm_s === null || pp.prof.contour_speed_mm_s === undefined ? "" : String(pp.prof.contour_speed_mm_s) }
                        }
                    }

                    Text { visible: pp.err !== ""; text: "⚠ " + pp.err; color: "#ffb4b6"; font.pixelSize: 13; Layout.topMargin: 4; Layout.fillWidth: true; wrapMode: Text.WordWrap }

                    RowLayout {
                        Layout.maximumWidth: edCol.width
                        Layout.topMargin: 8
                        spacing: 10
                        Text {
                            text: pp.ro ? win.t("Änderungen legen automatisch ein eigenes Profil an.") : win.t("Änderungen werden sofort gespeichert.")
                            color: win.cMut; font.pixelSize: 12
                            Layout.fillWidth: true; elide: Text.ElideRight
                        }
                        KButton { text: win.t("Als neues Profil speichern"); onClicked: pp.save(true, false) }
                        KButton {
                            visible: !pp.ro
                            text: win.t("Löschen"); kind: "ghost"
                            onClicked: confirm.ask(win.t("Profil „") + pp.prof.name + win.t("“ löschen?"), function() { backend.deleteProfile(pp.prof.id) })
                        }
                    }
                }
            }
        }
    }
}
