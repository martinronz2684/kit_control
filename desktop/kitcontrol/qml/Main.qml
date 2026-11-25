import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

ApplicationWindow {
    id: win
    width: 1360; height: 860
    minimumWidth: 1120; minimumHeight: 720
    visible: true
    title: "Kit Control"
    color: cBg

    // Farben wie am Display, Akzent Petrol aus dem Logo
    readonly property color cBg: "#0c0e11"
    readonly property color cPanel: "#13161a"
    readonly property color cPanel2: "#1a1e24"
    readonly property color cLine: "#262b33"
    readonly property color cInk: "#eef1f5"
    readonly property color cMut: "#8b9099"
    readonly property color cAcc: "#2694b8"
    readonly property color cAcc2: "#1d7896"
    readonly property color cHeat: "#ff8a5c"
    readonly property color cRed: "#e5484d"
    readonly property color cOk: "#2fd38a"

    property int page: 0
    readonly property var pageNames: [win.t("Platzieren"), win.t("Parameter"), win.t("Vorschau"), win.t("Pulver"), win.t("Drucken")]
    readonly property var pageHints: [
        win.t("Bauteile laden, anordnen und ausrichten"),
        win.t("Pulverprofil wählen oder eigenes anlegen"),
        win.t("Slicen und Schichten prüfen"),
        win.t("Pulver vorbereiten und laden"),
        win.t("Job zum Kit senden und Druck live verfolgen")]
    readonly property var kit: backend.kit || ({})
    // Sprache: Texte sind deutsch geschrieben; bei Englisch über die Übersetzungstabelle (kitcontrol/i18n.py)
    readonly property string lang: backend.lang
    readonly property var en: backend.translations
    function t(s) {
        if (lang !== "en" || s === undefined || s === null) return s
        var v = en[s]
        return v !== undefined ? v : backend.translate(s)
    }
    readonly property var meta: backend.sliceMeta || ({})

    function fmtTime(s) {
        if (s === undefined || s === null) return "–"
        var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60)
        return h + " h " + (m < 10 ? "0" : "") + m + win.t(" min")
    }
    // wie Central: Aufheiz-Restzeit vom Kit, Minuten aufgerundet
    function fmtCountdown(s) {
        if (s === undefined || s === null) return "–"
        var h = Math.floor(s / 3600), m = Math.floor((s - h * 3600) / 60) + 1
        return h > 0 ? h + " h " + m + win.t(" min") : m + win.t(" min")
    }
    function num(v, d) { return (v === undefined || v === null || v === "") ? "–" : Number(v).toFixed(d === undefined ? 1 : d) }

    // ---------- Dialoge ----------
    FileDialog {
        id: openStl
        title: win.t("Bauteile hinzufügen")
        fileMode: FileDialog.OpenFiles
        nameFilters: [win.t("3D-Modelle (*.stl *.STL)")]
        onAccepted: backend.addUrls(selectedFiles)
    }
    FileDialog {
        id: openProject
        title: win.t("Projekt öffnen")
        nameFilters: [win.t("Kit-Control-Projekt (*.kcp)")]
        onAccepted: backend.loadProject(selectedFile)
    }
    FileDialog {
        id: saveProject
        title: win.t("Projekt speichern")
        fileMode: FileDialog.SaveFile
        defaultSuffix: "kcp"
        nameFilters: [win.t("Kit-Control-Projekt (*.kcp)")]
        onAccepted: backend.saveProject(selectedFile)
    }
    FileDialog {
        id: exportStl
        title: win.t("Bauraum als STL exportieren")
        fileMode: FileDialog.SaveFile
        defaultSuffix: "stl"
        nameFilters: [win.t("STL (*.stl)")]
        onAccepted: backend.exportStl(selectedFile)
    }
    FileDialog {
        id: saveJob
        title: win.t("Druckdatei speichern")
        fileMode: FileDialog.SaveFile
        defaultSuffix: "bin"
        nameFilters: [win.t("Druckdatei (*.bin)")]
        onAccepted: backend.saveJob(selectedFile)
    }
    FileDialog {
        id: importProfile
        title: win.t("Profil importieren")
        nameFilters: [win.t("Pulverprofil (*.json)")]
        onAccepted: backend.importProfile(selectedFile)
    }
    FileDialog {
        id: exportProfile
        title: win.t("Profil exportieren")
        fileMode: FileDialog.SaveFile
        defaultSuffix: "json"
        nameFilters: [win.t("Pulverprofil (*.json)")]
        onAccepted: backend.exportProfile(backend.profileId, selectedFile)
    }

    Dialog {
        id: confirm
        property string text
        property var action
        anchors.centerIn: parent
        modal: true
        width: 440
        title: win.t("Bitte bestätigen")
        background: Rectangle { radius: 14; color: win.cPanel; border.color: win.cLine }
        header: Text { text: confirm.title; color: win.cInk; font.pixelSize: 16; font.weight: Font.DemiBold; padding: 20; bottomPadding: 4 }
        contentItem: Body { text: confirm.text; color: win.cMut }
        footer: RowLayout {
            spacing: 10
            Item { Layout.fillWidth: true }
            KButton { text: win.t("Abbrechen"); kind: "ghost"; onClicked: confirm.close() }
            KButton { text: "OK"; kind: "pri"; Layout.rightMargin: 16; Layout.bottomMargin: 16; onClicked: { confirm.close(); if (confirm.action) confirm.action() } }
        }
        function ask(t, a) { text = t; action = a; open() }
    }

    // ---------- Aufbau ----------
    RowLayout {
        anchors.fill: parent
        spacing: 0

        // Seitenleiste
        Rectangle {
            Layout.preferredWidth: 248
            Layout.fillHeight: true
            color: "#0f1215"
            Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: win.cLine }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 18
                spacing: 6

                Image {
                    source: assetDir + "/logo.png"
                    Layout.preferredWidth: 200
                    Layout.preferredHeight: 44
                    fillMode: Image.PreserveAspectFit
                    horizontalAlignment: Image.AlignLeft
                    smooth: true; mipmap: true
                    Layout.bottomMargin: 22; Layout.topMargin: 6
                }

                Repeater {
                    model: win.pageNames
                    delegate: Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 46; radius: 10
                        color: win.page === index ? "#16313c" : (navMa.containsMouse ? "#161a1f" : "transparent")
                        Behavior on color { ColorAnimation { duration: 120 } }
                        Rectangle {
                            visible: win.page === index
                            width: 3; height: 22; radius: 2; color: win.cAcc
                            anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                        }
                        Row {
                            anchors.left: parent.left; anchors.leftMargin: 14; anchors.verticalCenter: parent.verticalCenter
                            spacing: 12
                            Rectangle {
                                width: 24; height: 24; radius: 12
                                color: win.page === index ? win.cAcc : "#1d2228"
                                Text { anchors.centerIn: parent; text: index + 1; color: "white"; font.pixelSize: 12; font.weight: Font.DemiBold }
                            }
                            Text {
                                text: win.t(modelData)
                                color: win.page === index ? win.cInk : "#b9bec6"
                                font.pixelSize: 14; font.weight: win.page === index ? Font.DemiBold : Font.Normal
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }
                        MouseArea { id: navMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: win.page = index }
                    }
                }

                Item { Layout.fillHeight: true }

                // Kit-Zustand
                Card {
                    Layout.fillWidth: true
                    implicitHeight: kitCol.implicitHeight + 28
                    color: "#111418"
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: win.page = 4 }
                    ColumnLayout {
                        id: kitCol
                        anchors.fill: parent; anchors.margins: 14
                        spacing: 8
                        RowLayout {
                            spacing: 8
                            Rectangle {
                                width: 9; height: 9; radius: 5
                                color: !backend.connected ? win.cRed : (win.kit.connected ? win.cOk : win.cHeat)
                            }
                            Text {
                                Layout.fillWidth: true
                                text: !backend.host ? win.t("Kein Kit gewählt")
                                    : !backend.connected ? win.t("Verbinde …")
                                    : (win.kit.connected ? (win.kit.state_name || win.t("Kit verbunden")) : win.t("Pi ohne Kit"))
                                color: win.cInk; font.pixelSize: 13; font.weight: Font.DemiBold
                                elide: Text.ElideRight
                            }
                        }
                        Text { text: backend.host || win.t("Unter „Drucken“ verbinden"); color: win.cMut; font.pixelSize: 11 }
                        RowLayout {
                            visible: backend.connected && win.kit.connected === true
                            spacing: 14
                            Column { Caption { text: win.t("Oberfläche") } Text { text: win.num(win.kit.surface) + " °C"; color: win.cHeat; font.pixelSize: 15; font.weight: Font.DemiBold } }
                            Column { Caption { text: win.t("Kammer") } Text { text: win.num(win.kit.chamber) + " °C"; color: win.cInk; font.pixelSize: 15; font.weight: Font.DemiBold } }
                        }
                        Text {
                            visible: win.kit.countdown_on === true
                            text: win.t("Aufheizen: noch ") + win.fmtCountdown(win.kit.countdown_s)
                            color: win.cHeat; font.pixelSize: 12
                        }
                        Rectangle {
                            visible: win.kit.printing === true
                            Layout.fillWidth: true; Layout.preferredHeight: 5; radius: 3; color: "#1d2228"
                            Rectangle { width: parent.width * Math.min(1, (win.kit.percent || 0) / 100); height: parent.height; radius: 3; color: win.cAcc }
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 6
                    Text {
                        text: win.t("Version ") + backend.version
                        color: "#4e545d"; font.pixelSize: 11
                        Layout.fillWidth: true
                    }
                    // Einstellungen
                    Rectangle {
                        width: 30; height: 30; radius: 8
                        color: gearMa.containsMouse ? "#1b2026" : "transparent"
                        border.color: gearMa.containsMouse ? win.cLine : "transparent"
                        Text { anchors.centerIn: parent; text: "⚙"; color: gearMa.containsMouse ? win.cInk : "#8a919b"; font.pixelSize: 18 }
                        MouseArea { id: gearMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: settingsPop.open() }
                        ToolTip.visible: gearMa.containsMouse; ToolTip.text: win.t("Einstellungen")
                    }
                }
            }
        }

        // Inhalt
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // Update-Hinweis
            Rectangle {
                visible: backend.updateVersion !== ""
                Layout.fillWidth: true
                Layout.preferredHeight: 46
                color: "#123441"
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 24; anchors.rightMargin: 16
                    Body { text: win.t("Neue Version ") + backend.updateVersion + win.t(" verfügbar."); Layout.fillWidth: true }
                    ProgressBar {
                        visible: backend.updateProgress >= 0
                        value: backend.updateProgress
                        Layout.preferredWidth: 160
                    }
                    KButton { text: backend.updateProgress >= 0 ? win.t("Lädt …") : win.t("Jetzt aktualisieren"); kind: "pri"; enabled: backend.updateProgress < 0; onClicked: backend.installUpdate() }
                }
            }

            // Kopf
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 28; Layout.rightMargin: 24; Layout.topMargin: 20; Layout.bottomMargin: 14
                spacing: 10
                ColumnLayout {
                    spacing: 2
                    Text { text: (win.page + 1) + ". " + win.pageNames[win.page]; color: win.cInk; font.pixelSize: 24; font.weight: Font.DemiBold }
                    Text { text: win.pageHints[win.page]; color: win.cMut; font.pixelSize: 13 }
                }
                Item { Layout.fillWidth: true }
                KButton { text: win.t("Projekt öffnen"); kind: "ghost"; onClicked: openProject.open() }
                KButton { text: win.t("Projekt speichern"); kind: "ghost"; enabled: backend.parts.length > 0; onClicked: saveProject.open() }
                KButton {
                    visible: win.page < 4
                    text: win.t("Weiter"); kind: "pri"
                    onClicked: win.page = win.page + 1
                }
            }

            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.leftMargin: 24; Layout.rightMargin: 24; Layout.bottomMargin: 24
                currentIndex: win.page

                PlacePage {}
                ParamPage {}
                PreviewPage {}
                PowderPage {}
                PrintPage {}
            }
        }
    }

    // Meldungen unten rechts
    Rectangle {
        id: toast
        property string kind: "info"
        anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 22
        width: Math.min(520, toastText.implicitWidth + 40)
        height: toastText.implicitHeight + 24
        radius: 12
        color: kind === "error" ? "#3a1416" : (kind === "ok" ? "#0f2f22" : "#16252c")
        border.color: kind === "error" ? win.cRed : (kind === "ok" ? win.cOk : win.cAcc)
        opacity: 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 180 } }
        Body { id: toastText; anchors.centerIn: parent; width: Math.min(480, implicitWidth); text: "" }
        Timer { id: toastTimer; interval: 5000; onTriggered: toast.opacity = 0 }
        Connections {
            target: backend
            function onMessage(text, kind) {
                toastText.text = win.t(text); toast.kind = kind; toast.opacity = 1
                toastTimer.interval = kind === "error" ? 8000 : 4000
                toastTimer.restart()
            }
        }
    }

    SettingsPopup { id: settingsPop }
}
