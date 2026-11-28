import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import QtQuick.Dialogs

ApplicationWindow {
    id: win
    width: 1360; height: 860
    minimumWidth: 1120; minimumHeight: 720
    visible: true
    // Fortschritt auch im Fenstertitel / in der Taskleiste sichtbar
    title: !backend.connected || !kit.connected ? "Kit Control"
           : kit.printing === true ? (kit.countdown_on === true ? "Kit Control – " + t(win.t("Aufheizen: noch ")) + fmtCountdown(kit.countdown_s)
                                                               : "Kit Control – " + Math.round(kit.percent || 0) + " %" + (kit.percent > 2 ? " · " + fmtTime(kit.elapsed_s / kit.percent * (100 - kit.percent)) : ""))
           : "Kit Control"
    color: cBg

    // Farben wie am Display, Akzent Petrol aus dem Logo; helles Design über die Einstellungen
    readonly property bool light: (backend.settings || {}).theme === "light"
    function th(d, l) { return light ? l : d }
    readonly property color cBg: th("#0c0e11", "#e9edf1")
    readonly property color cSide: th("#0f1215", "#f6f8fa")
    readonly property color cPanel: th("#13161a", "#ffffff")
    readonly property color cPanel2: th("#1a1e24", "#f2f5f7")
    readonly property color cLine: th("#262b33", "#d3d9e0")
    readonly property color cInk: th("#eef1f5", "#1a1f26")
    readonly property color cMut: th("#8b9099", "#5d6672")
    readonly property color cMut2: th("#9aa3ad", "#6c7581")
    readonly property color cDim: th("#59606b", "#9aa2ad")
    readonly property color cAcc: th("#2694b8", "#1f87ab")
    readonly property color cAcc2: th("#1d7896", "#196f8d")
    readonly property color cHeat: th("#ff8a5c", "#d9622e")
    readonly property color cRed: th("#e5484d", "#c9353a")
    readonly property color cOk: th("#2fd38a", "#1d9e64")
    readonly property color cField: th("#0f1215", "#f8fafb")
    readonly property color cHover: th("#181c21", "#eef2f5")
    readonly property color cSel: th("#16313c", "#d7eef6")
    readonly property color cTrack: th("#232830", "#dde3e8")
    readonly property color cRow: th("#15181c", "#f3f5f7")
    readonly property color cWarnBg: th("#2a2312", "#fff4dc")
    readonly property color cWarnLine: th("#5c4a22", "#e8c98a")
    readonly property color cWarnInk: th("#ffd59a", "#8a5a00")
    readonly property color cErrBg: th("#2a1215", "#fde8e9")
    readonly property color cErrLine: th("#5c2226", "#efb1b4")
    readonly property color cErrInk: th("#ffb4b6", "#a3262c")
    readonly property color cInfoBg: th("#16252c", "#e6f4f9")
    readonly property color cInfoLine: th("#1f4757", "#b4dae7")
    readonly property color cInfoInk: th("#a9d7e7", "#1d6a86")
    readonly property color c3d: th("#13161a", "#eef1f4")

    property int page: 0
    property bool showStart: true          // Startseite, bis etwas geladen oder sie geschlossen wird
    readonly property var pageNames: [win.t("Platzieren"), win.t("Parameter"), win.t("Vorschau"), win.t("Pulver"), win.t("Drucken")]
    readonly property var pageHints: [
        win.t("Bauteile laden, anordnen und ausrichten"),
        win.t("Pulverprofil wählen oder eigenes anlegen"),
        win.t("Slicen und Schichten prüfen"),
        win.t("Pulver vorbereiten und laden"),
        win.t("Job zum Kit senden und Druck live verfolgen")]
    readonly property var kit: backend.kit || ({})
    // Schalter „Bedienung vom PC“ am Kit-Display (der Pi meldet ihn im Zustand)
    readonly property bool remoteOn: kit.remote_control === true
    readonly property string remoteHint: t("Bedienung vom PC ist am Kit ausgeschaltet – am Display unter System → „Bedienung vom PC“ einschalten.")
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
    // Zahl mit Tausenderpunkt und Komma (Deutsch) bzw. Punkt (Englisch)
    function fnum(v, d) {
        if (v === undefined || v === null || v === "" || isNaN(v)) return "–"
        return Number(v).toLocaleString(Qt.locale(backend.lang === "en" ? "en_US" : "de_DE"), "f", d === undefined ? 1 : d)
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
        background: GlassBg {}
        Overlay.modal: Backdrop {}
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
            color: win.cSide
            gradient: Gradient {
                GradientStop { position: 0.0; color: win.th("#11161a", "#fbfcfd") }
                GradientStop { position: 1.0; color: win.th("#0c0f12", "#f1f4f7") }
            }
            Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: win.cLine }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 18
                spacing: 6

                Image {
                    id: logoImg
                    source: assetDir + (win.light ? "/logo_dark.png" : "/logo.png")
                    Layout.preferredWidth: 200
                    Layout.preferredHeight: 44
                    fillMode: Image.PreserveAspectFit
                    horizontalAlignment: Image.AlignLeft
                    smooth: true; mipmap: true
                    Layout.topMargin: 6
                }
                // „Kit Control by Rat3d“
                RowLayout {
                    spacing: 5
                    Layout.leftMargin: 50
                    Layout.topMargin: -4
                    Layout.bottomMargin: 20
                    Text { text: "by"; color: win.cDim; font.pixelSize: 10; font.italic: true; Layout.alignment: Qt.AlignVCenter }
                    Image {
                        source: assetDir + (win.light ? "/rat3d_dark.svg" : "/rat3d.svg")
                        sourceSize: Qt.size(56, 44)
                        Layout.preferredWidth: 26; Layout.preferredHeight: 20
                        fillMode: Image.PreserveAspectFit
                        smooth: true; mipmap: true
                    }
                    Text { text: "Rat3d"; color: win.cDim; font.pixelSize: 10; font.letterSpacing: 1; Layout.alignment: Qt.AlignVCenter }
                }

                Repeater {
                    model: win.pageNames
                    delegate: Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 46; radius: 10
                        color: win.page === index ? win.cSel : (navMa.containsMouse ? win.cHover : "transparent")
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
                                color: win.page === index ? win.cAcc : win.cTrack
                                Text { anchors.centerIn: parent; text: index + 1; color: "white"; font.pixelSize: 12; font.weight: Font.DemiBold }
                            }
                            Text {
                                text: win.t(modelData)
                                color: win.page === index ? win.cInk : win.cMut2
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
                    color: win.cField
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: win.page = 4 }
                    ColumnLayout {
                        id: kitCol
                        anchors.fill: parent; anchors.margins: 14
                        spacing: 8
                        RowLayout {
                            spacing: 8
                            Rectangle {
                                width: 9; height: 9; radius: 5
                                color: win.needsPairing ? win.cHeat : !backend.connected ? win.cRed : (win.kit.connected ? win.cOk : win.cHeat)
                            }
                            Text {
                                Layout.fillWidth: true
                                text: !backend.host ? win.t("Kein Kit gewählt")
                                    : win.needsPairing ? win.t("Nicht gekoppelt")
                                    : !backend.connected ? win.t("Verbinde …")
                                    : (win.kit.connected ? (win.kit.state_name || win.t("Kit verbunden")) : win.t("Pi ohne Kit"))
                                color: win.cInk; font.pixelSize: 13; font.weight: Font.DemiBold
                                elide: Text.ElideRight
                            }
                        }
                        Text { text: backend.host || win.t("Unter „Drucken“ verbinden"); color: win.cMut; font.pixelSize: 11 }
                        KButton {
                            visible: win.needsPairing && !pairPop.opened
                            Layout.fillWidth: true; implicitHeight: 32
                            text: win.t("Mit dem Kit koppeln"); kind: "pri"
                            onClicked: backend.pairStart()
                        }
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
                            Layout.fillWidth: true; Layout.preferredHeight: 5; radius: 3; color: win.cTrack
                            Rectangle { width: parent.width * Math.min(1, (win.kit.percent || 0) / 100); height: parent.height; radius: 3; color: win.cAcc }
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 6
                    Text {
                        text: win.t("Version ") + backend.version
                        color: win.cDim; font.pixelSize: 11
                        Layout.fillWidth: true
                    }
                    // Meldungsverlauf
                    Rectangle {
                        width: 30; height: 30; radius: 8
                        color: bellMa.containsMouse ? win.cHover : "transparent"
                        border.color: bellMa.containsMouse ? win.cLine : "transparent"
                        // Glocke einfarbig gezeichnet (kein buntes Emoji)
                        Canvas {
                            id: bellIcon
                            anchors.centerIn: parent; width: 16; height: 16
                            property color c: bellMa.containsMouse ? win.cInk : win.cMut2
                            onCChanged: requestPaint()
                            onPaint: {
                                var g = getContext("2d"); g.reset()
                                g.strokeStyle = c; g.fillStyle = c; g.lineWidth = 1.4; g.lineJoin = "round"
                                g.beginPath()
                                g.moveTo(3, 12); g.lineTo(13, 12)
                                g.moveTo(4, 12); g.lineTo(4, 7.5)
                                g.bezierCurveTo(4, 4.2, 6, 2.6, 8, 2.6)
                                g.bezierCurveTo(10, 2.6, 12, 4.2, 12, 7.5)
                                g.lineTo(12, 12)
                                g.stroke()
                                g.beginPath(); g.arc(8, 13.6, 1.5, 0, Math.PI); g.fill()
                                g.beginPath(); g.moveTo(8, 1.2); g.lineTo(8, 2.6); g.stroke()
                            }
                        }
                        Rectangle {
                            visible: win.unread > 0
                            anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 1
                            width: Math.max(14, badge.implicitWidth + 6); height: 14; radius: 7; color: win.cMut2
                            Text { id: badge; anchors.centerIn: parent; text: win.unread > 9 ? "9+" : win.unread; color: win.cSide; font.pixelSize: 9; font.weight: Font.Bold }
                        }
                        MouseArea { id: bellMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: msgPop.opened ? msgPop.close() : msgPop.open() }
                        ToolTip.visible: bellMa.containsMouse; ToolTip.text: win.t("Meldungen")
                    }
                    // Einstellungen
                    Rectangle {
                        width: 30; height: 30; radius: 8
                        color: gearMa.containsMouse ? win.cHover : "transparent"
                        border.color: gearMa.containsMouse ? win.cLine : "transparent"
                        Text { anchors.centerIn: parent; text: "\u2699\uFE0E"; color: gearMa.containsMouse ? win.cInk : win.cMut2; font.pixelSize: 18 }
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
                color: win.th("#123441", "#dff1f7")
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
                // weicher Seitenwechsel
                onCurrentIndexChanged: { pageFade.restart() }
                opacity: 1
                NumberAnimation on opacity { id: pageFade; from: 0.0; to: 1.0; duration: 220; easing.type: Easing.OutCubic; running: false }

                PlacePage {}
                ParamPage {}
                PreviewPage {}
                PowderPage {}
                PrintPage {}
            }
        }
    }

    // Startseite: zuletzt geöffnete Projekte
    Item {
        id: startPage
        objectName: "startPage"
        visible: win.showStart && win.page === 0 && backend.parts.length === 0
        x: 248; y: 0; width: parent.width - 248; height: parent.height
        Rectangle { anchors.fill: parent; color: win.cBg; opacity: 0.97 }
        MouseArea { anchors.fill: parent }        // nichts darunter anklicken
        ColumnLayout {
            anchors.centerIn: parent
            width: Math.min(640, parent.width - 80)
            spacing: 18
            Text { text: win.t("Willkommen bei Kit Control"); color: win.cInk; font.pixelSize: 28; font.weight: Font.DemiBold }
            Text { text: win.t("Neues Projekt beginnen oder ein zuletzt geöffnetes fortsetzen."); color: win.cMut; font.pixelSize: 14 }
            RowLayout {
                Layout.fillWidth: true; spacing: 10
                KButton { text: win.t("Bauteile hinzufügen …"); kind: "pri"; Layout.fillWidth: true; Layout.preferredWidth: 1; implicitHeight: 46; onClicked: { win.showStart = false; openStl.open() } }
                KButton { text: win.t("Projekt öffnen …"); Layout.fillWidth: true; Layout.preferredWidth: 1; implicitHeight: 46; onClicked: openProject.open() }
                KButton { text: win.t("Leeres Projekt"); kind: "ghost"; Layout.fillWidth: true; Layout.preferredWidth: 1; implicitHeight: 46; onClicked: win.showStart = false }
            }
            Caption { text: win.t("Zuletzt geöffnet"); visible: backend.recentProjects.length > 0; Layout.topMargin: 8 }
            Repeater {
                model: backend.recentProjects
                delegate: Card {
                    Layout.fillWidth: true
                    implicitHeight: 58
                    color: rma.containsMouse ? win.cHover : win.cPanel
                    Behavior on color { ColorAnimation { duration: 100 } }
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 16
                        spacing: 12
                        Text { text: "▣"; color: win.cAcc; font.pixelSize: 20 }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 2
                            Text { text: modelData.name; color: win.cInk; font.pixelSize: 14; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
                            Text { text: modelData.path; color: win.cDim; font.pixelSize: 11; elide: Text.ElideMiddle; Layout.fillWidth: true }
                        }
                        Text { text: Qt.formatDateTime(new Date(modelData.time * 1000), "dd.MM.yy hh:mm") + " · " + modelData.parts + win.t(" Teile"); color: win.cMut; font.pixelSize: 11 }
                    }
                    MouseArea { id: rma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { win.showStart = false; backend.loadProject(modelData.path) } }
                }
            }
            Text {
                text: win.t("Tipp: STL-Dateien oder Projekte (.kcp) einfach ins Fenster ziehen.")
                color: win.cDim; font.pixelSize: 12; Layout.topMargin: 6
            }
        }
        DropArea {
            anchors.fill: parent
            keys: ["text/uri-list"]
            onDropped: (d) => { win.showStart = false; backend.addUrls(d.urls) }
        }
    }

    // Meldungen unten rechts: Fehler bleiben stehen, bis man sie wegklickt; Verlauf über die Glocke
    property var msgLog: []
    property int unread: 0
    Rectangle {
        id: toast
        property string kind: "info"
        anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 22
        width: Math.min(560, toastRow.implicitWidth + 32)
        height: toastText.implicitHeight + 26
        radius: 12
        color: kind === "error" ? win.cErrBg : (kind === "ok" ? win.th("#0f2f22", "#e3f6ec") : win.cInfoBg)
        border.color: kind === "error" ? win.cRed : (kind === "ok" ? win.cOk : win.cAcc)
        opacity: 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 180 } }
        transform: Translate { y: toast.opacity < 1 ? 12 * (1 - toast.opacity) : 0 }
        RowLayout {
            id: toastRow
            anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 10
            spacing: 10
            Body { id: toastText; Layout.maximumWidth: 480; text: "" }
            Text {
                text: "✕"; color: win.cMut; font.pixelSize: 13
                MouseArea { anchors.fill: parent; anchors.margins: -6; cursorShape: Qt.PointingHandCursor; onClicked: toast.opacity = 0 }
            }
        }
        Timer { id: toastTimer; interval: 5000; onTriggered: toast.opacity = 0 }
        Connections {
            target: backend
            function onMessage(text, kind) {
                var t = win.t(text)
                toastText.text = t; toast.kind = kind; toast.opacity = 1
                if (kind === "error") toastTimer.stop()          // Fehler bleiben stehen
                else { toastTimer.interval = 4500; toastTimer.restart() }
                var l = win.msgLog.slice(); l.unshift({ text: t, kind: kind, time: Qt.formatTime(new Date(), "hh:mm") })
                win.msgLog = l.slice(0, 60)
                if (!msgPop.opened) win.unread = win.unread + 1
            }
        }
    }

    Popup {
        id: msgPop
        objectName: "msgPop"
        x: 18; y: parent.height - height - 70
        width: 420; height: Math.min(460, msgList.contentHeight + 70)
        padding: 16
        background: GlassBg {}
        onOpened: win.unread = 0
        ColumnLayout {
            anchors.fill: parent
            spacing: 8
            RowLayout {
                Caption { text: win.t("Meldungen"); Layout.fillWidth: true }
                KButton { text: win.t("Leeren"); kind: "ghost"; implicitHeight: 28; onClicked: win.msgLog = [] }
            }
            ListView {
                id: msgList
                Layout.fillWidth: true; Layout.fillHeight: true
                clip: true; spacing: 4
                model: win.msgLog
                Text { visible: parent.count === 0; text: win.t("Keine Meldungen"); color: win.cMut; font.pixelSize: 12 }
                delegate: RowLayout {
                    width: ListView.view.width
                    spacing: 8
                    Rectangle { width: 7; height: 7; radius: 4; Layout.alignment: Qt.AlignTop; Layout.topMargin: 5; color: modelData.kind === "error" ? win.cRed : (modelData.kind === "ok" ? win.cOk : win.cAcc) }
                    Text { text: modelData.time; color: win.cDim; font.pixelSize: 11; Layout.alignment: Qt.AlignTop }
                    Text { text: modelData.text; color: win.cInk; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                }
            }
        }
    }

    SettingsPopup { id: settingsPop }
    PairDialog { id: pairPop }
    LaserPopup { id: laserPop }
    function openLaser() { settingsPop.close(); laserPop.open() }
    readonly property string pairState: (backend.pairInfo || {}).state || "none"
    readonly property bool needsPairing: !backend.connected && ["needed", "starting", "code", "confirming", "error", "dismissed"].indexOf(pairState) >= 0

    // Update beim Start anbieten (gefunden schon im Ladefenster)
    Popup {
        id: updatePop
        objectName: "updatePop"
        anchors.centerIn: parent
        width: 440
        modal: true
        padding: 22
        background: GlassBg {}
        Overlay.modal: Backdrop {}
        property bool shown: false
        function offer() { if (!shown && backend.updateVersion !== "") { shown = true; open() } }
        Component.onCompleted: Qt.callLater(offer)
        Connections { target: backend; function onUpdateChanged() { updatePop.offer() } }
        ColumnLayout {
            anchors.fill: parent
            spacing: 14
            Text { text: win.t("Update verfügbar"); color: win.cInk; font.pixelSize: 18; font.weight: Font.DemiBold }
            Body {
                Layout.fillWidth: true; color: win.cMut
                text: win.t("Version ") + backend.updateVersion + win.t(" ist da (installiert: ") + backend.version + win.t("). Jetzt herunterladen und installieren? Kit Control startet danach neu.")
            }
            ProgressBar {
                visible: backend.updateProgress >= 0
                Layout.fillWidth: true
                value: backend.updateProgress
                background: Rectangle { implicitHeight: 6; radius: 3; color: win.cTrack }
                contentItem: Item { Rectangle { width: parent.width * backend.updateProgress; height: 6; radius: 3; color: win.cAcc } }
            }
            RowLayout {
                Layout.fillWidth: true; spacing: 10
                Item { Layout.fillWidth: true }
                KButton { text: win.t("Später"); kind: "ghost"; enabled: backend.updateProgress < 0; onClicked: updatePop.close() }
                KButton { text: backend.updateProgress >= 0 ? win.t("Lädt …") : win.t("Jetzt aktualisieren"); kind: "pri"; enabled: backend.updateProgress < 0; onClicked: backend.installUpdate() }
            }
        }
    }
}
