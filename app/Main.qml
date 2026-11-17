// Kit Control – native Oberfläche (Qt Quick, ohne Browser).
// Gezeichnet für 800×450, wird auf dem 5"-Display (720×1280 hochkant) gedreht und skaliert.
import QtQuick
import QtQuick.Window
import "api.js" as Api

Window {
    id: win
    visible: true
    visibility: Window.FullScreen
    width: 800
    height: 450
    color: "#08090c"
    title: "Kit Control"

    // ---------- Farben ----------
    readonly property color cBg: "#0c0e11"
    readonly property color cInk: "#eef1f5"
    readonly property color cMut: "#9aa3b2"
    readonly property color cBlue: "#6b86ff"
    readonly property color cBlue2: "#3a55e6"
    readonly property color cHeat: "#ff8a5c"
    readonly property color cRed: "#e5484d"
    readonly property color cOk: "#2fd38a"
    readonly property color cLine: "#1fffffff"
    readonly property string fontName: "Inter"

    // ---------- Zustand ----------
    property var st: ({ connected: false, message: "Dienst startet …" })
    property var wifi: ({ available: true, current: "", networks: [] })
    property string page: "print"
    property real step: 1
    property real thick: 0.1
    property int jobH: 68
    property int target: 145
    property bool warm: false
    property var moved: ({ print: 0, reservoir: 0 })
    property int lastLayer: -1
    property bool kitdUp: false

    readonly property int rot: {
        var a = Qt.application.arguments
        var i = a.indexOf("--rotation")
        return i >= 0 && i + 1 < a.length ? parseInt(a[i + 1]) : 90
    }
    readonly property bool portrait: win.width < win.height

    function send(body, after) {
        Api.cmd(body, function (j) {
            if (!j) { toast.show("Dienst nicht erreichbar"); return }
            if (!j.ok) toast.show(j.error || "Fehler")
            if (after) after(j.ok)
        })
    }
    function ask(title, text, action) {
        dlg.title = title; dlg.text = text; dlg.action = action; dlg.visible = true
    }
    function loadWifi(rescan) {
        Api.get("/api/wifi" + (rescan ? "?rescan=1" : ""), function (j) { if (j) win.wifi = j })
    }

    Timer {
        interval: 1000; running: true; repeat: true; triggeredOnStart: true
        onTriggered: Api.get("/api/state", function (j) {
            if (!j) { win.kitdUp = false; win.st = { connected: false, message: "Dienst kitd startet …" }; return }
            win.kitdUp = true
            if (j.printing && win.lastLayer >= 0 && j.layer !== win.lastLayer) chamber.sweep()
            win.lastLayer = j.layer === undefined ? -1 : j.layer
            win.st = j
        })
    }
    Timer { interval: 15000; running: true; repeat: true; triggeredOnStart: true; onTriggered: win.loadWifi(false) }

    // ---------- Bausteine ----------
    component Panel: Rectangle {
        radius: 16
        border.color: win.cLine
        border.width: 1
        gradient: Gradient {
            GradientStop { position: 0; color: "#16191e" }
            GradientStop { position: 1; color: "#111317" }
        }
    }
    component Lbl: Text {
        color: win.cMut; font.family: win.fontName; font.pixelSize: 12; font.weight: Font.Medium
        elide: Text.ElideRight
    }
    component Val: Text {
        color: win.cInk; font.family: win.fontName; font.pixelSize: 26; font.weight: Font.Medium
        font.letterSpacing: -0.6
    }
    component KButton: Rectangle {
        id: kb
        property string text: ""
        property string kind: "normal"     // normal | pri | red | hot
        property bool ok: true
        property int size: 14
        signal clicked()
        height: 52; radius: 14
        opacity: ok ? 1 : 0.35
        border.width: kind === "normal" ? 1 : 0
        border.color: "#1affffff"
        gradient: Gradient {
            GradientStop { position: 0; color: ma.pressed ? "#6b86ff" : kb.kind === "pri" ? "#6b86ff" : kb.kind === "red" ? "#f0565b" : kb.kind === "hot" ? "#ff8a5c" : "#262a31" }
            GradientStop { position: 1; color: ma.pressed ? "#3a55e6" : kb.kind === "pri" ? "#3a55e6" : kb.kind === "red" ? "#c9343a" : kb.kind === "hot" ? "#e9531f" : "#1a1d22" }
        }
        Text {
            anchors.centerIn: parent; width: parent.width - 12
            horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
            text: kb.text; color: "white"; font.family: win.fontName; font.pixelSize: kb.size; font.weight: Font.DemiBold
        }
        MouseArea { id: ma; anchors.fill: parent; enabled: kb.ok; onClicked: kb.clicked() }
    }
    component Seg: Rectangle {
        id: sg
        property var items: []        // [[label, value], …]
        property var value
        signal picked(var v)
        height: 46; radius: 12; color: "#59000000"; border.color: win.cLine
        Row {
            anchors.fill: parent; anchors.margins: 4; spacing: 4
            Repeater {
                model: sg.items
                Rectangle {
                    width: (sg.width - 8 - 4 * (sg.items.length - 1)) / sg.items.length; height: parent.height; radius: 9
                    color: sg.value === modelData[1] ? win.cBlue2 : "transparent"
                    Text { anchors.centerIn: parent; text: modelData[0]; color: sg.value === modelData[1] ? "white" : win.cMut; font.family: win.fontName; font.pixelSize: 13; font.weight: Font.DemiBold }
                    MouseArea { anchors.fill: parent; onClicked: sg.picked(modelData[1]) }
                }
            }
        }
    }
    component NavBtn: Rectangle {
        id: nb
        property string key
        property string label
        property string icon
        property bool hot: false
        readonly property bool active: win.page === key
        width: 52; height: 56; radius: 14
        color: active ? (hot ? "#e9531f" : win.cBlue2) : "transparent"
        Column {
            anchors.centerIn: parent; spacing: 3
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: nb.icon; color: nb.active ? "white" : win.cMut; font.pixelSize: 19; font.family: win.fontName }
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: nb.label; color: nb.active ? "white" : win.cMut; font.family: win.fontName; font.pixelSize: 9; font.weight: Font.DemiBold }
        }
        MouseArea { anchors.fill: parent; onClicked: win.page = nb.key }
    }
    component Chip: Rectangle {
        id: ch
        property string text
        property color dot: "transparent"
        property color tint: "#0dffffff"
        signal clicked()
        height: 28; radius: 14; color: tint; border.color: win.cLine
        width: Math.min(260, row.implicitWidth + 22)
        Row {
            id: row; anchors.centerIn: parent; spacing: 6
            Rectangle { visible: ch.dot !== "transparent"; width: 7; height: 7; radius: 4; color: ch.dot; anchors.verticalCenter: parent.verticalCenter }
            Text { text: ch.text; color: win.cInk; font.family: win.fontName; font.pixelSize: 12; font.weight: Font.Medium; elide: Text.ElideRight; width: Math.min(implicitWidth, 220) }
        }
        MouseArea { anchors.fill: parent; onClicked: ch.clicked() }
    }

    // ---------- Oberfläche ----------
    Item {
        id: root
        width: 800; height: 450
        anchors.centerIn: parent
        rotation: win.portrait ? win.rot : 0
        scale: win.portrait ? Math.min(win.width / 450, win.height / 800) : Math.min(win.width / 800, win.height / 450)

        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0; color: "#1a1e25" }
                GradientStop { position: 0.6; color: "#0f1115" }
                GradientStop { position: 1; color: "#08090c" }
            }
        }

        // Navigation
        Panel {
            id: nav
            x: 8; y: 8; width: 64; height: parent.height - 16; radius: 18
            Column {
                anchors.top: parent.top; anchors.topMargin: 8; anchors.horizontalCenter: parent.horizontalCenter; spacing: 6
                Image { source: "../branding/mark.png"; width: 38; height: 38; smooth: true; mipmap: true; anchors.horizontalCenter: parent.horizontalCenter }
                Item { width: 1; height: 2 }
                NavBtn { key: "print"; label: "Druck"; icon: "≡" }
                NavBtn { key: "move"; label: "Bewegung"; icon: "⇅" }
                NavBtn { key: "heat"; label: "Heizung"; icon: "♨"; hot: true }
                NavBtn { key: "jobs"; label: "Jobs"; icon: "▤" }
            }
            NavBtn { key: "sys"; label: "System"; icon: "⚙"; anchors.bottom: parent.bottom; anchors.bottomMargin: 8; anchors.horizontalCenter: parent.horizontalCenter }
        }

        Item {
            id: main
            x: 80; y: 8; width: parent.width - 88; height: parent.height - 16

            // Kopfzeile
            Item {
                id: head
                width: parent.width; height: 34
                Text {
                    anchors.verticalCenter: parent.verticalCenter; x: 4
                    text: ({ print: "Druck", move: "Bewegung", heat: "Heizung", jobs: "Jobs", sys: "System" })[win.page]
                    color: win.cInk; font.family: win.fontName; font.pixelSize: 20; font.weight: Font.DemiBold; font.letterSpacing: -0.4
                }
                Row {
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 6
                    Chip {
                        readonly property var e: win.st.errors || []
                        readonly property var w: win.st.warnings || []
                        visible: e.length + w.length > 0
                        tint: e.length ? "#2ee5484d" : "#24ff6a3d"
                        text: e.length ? "Fehler: " + e[0].title : (w.length ? "Warnung: " + w[0].title : "")
                        onClicked: win.page = "sys"
                    }
                    Chip { text: "WLAN · " + (win.wifi.available === false ? "aus" : (win.wifi.current || "nicht verbunden")); onClicked: wifiOvl.open() }
                    Chip {
                        dot: win.st.connected ? win.cOk : win.cRed
                        text: win.st.connected ? (win.st.model || "Kit") + " · FW " + win.st.firmware + (win.st.demo ? " · Demo" : "") : "getrennt"
                    }
                }
            }

            // ======= Druck =======
            Item {
                visible: win.page === "print"
                y: 42; width: parent.width; height: parent.height - 42

                Panel {
                    id: chamberPanel
                    width: parent.width * 0.575; height: parent.height
                    clip: true
                    Column {
                        x: 14; y: 10; z: 2
                        Lbl { text: "Schicht" }
                        Text { text: win.st.printing ? win.st.layer : "—"; color: win.cInk; font.family: win.fontName; font.pixelSize: 44; font.weight: Font.Light; font.letterSpacing: -1.6 }
                    }
                    Column {
                        anchors.right: parent.right; anchors.rightMargin: 14; y: 12; z: 2
                        Text { anchors.right: parent.right; text: win.st.printing ? win.st.percent + " %" : ""; color: "#8ea2ff"; font.family: win.fontName; font.pixelSize: 26; font.weight: Font.DemiBold }
                        Lbl { anchors.right: parent.right; text: win.st.printing ? "Druck läuft" : (win.st.waiting_for_sd ? "Wartet auf SD-Karte" : "Bereit") }
                    }
                    Chamber {
                        id: chamber
                        printing: !!win.st.printing
                        anchors.bottom: parent.bottom; anchors.bottomMargin: 18
                        anchors.horizontalCenter: parent.horizontalCenter
                    }
                    Rectangle {
                        x: 14; width: parent.width - 28; height: 5; radius: 3; anchors.bottom: parent.bottom; anchors.bottomMargin: 10; color: "#14ffffff"
                        Rectangle { height: parent.height; radius: 3; width: parent.width * (win.st.printing ? win.st.percent / 100 : 0); gradient: Gradient { orientation: Gradient.Horizontal; GradientStop { position: 0; color: "#8ea2ff" } GradientStop { position: 1; color: "#4a67f5" } } }
                    }
                }

                Column {
                    x: chamberPanel.width + 8; width: parent.width - chamberPanel.width - 8; height: parent.height; spacing: 8
                    Row {
                        spacing: 8; width: parent.width
                        Panel {
                            width: (parent.width - 8) / 2; height: 84
                            Column { x: 12; y: 10; spacing: 1
                                Lbl { text: "Pulveroberfläche" }
                                Val { text: Api.de(win.st.surface) + "°"; color: win.cHeat }
                                Lbl { text: "Soll " + Api.de(win.st.printing ? win.st.target_surface_print : win.st.target_surface_warmup) + " °C" } }
                        }
                        Panel {
                            width: (parent.width - 8) / 2; height: 84
                            Column { x: 12; y: 10; spacing: 1
                                Lbl { text: "Kammer" }
                                Val { text: Api.de(win.st.chamber) + "°" }
                                Lbl { text: "Soll " + Api.de(win.st.printing ? win.st.target_chamber_print : win.st.target_chamber_warmup) + " °C" } }
                        }
                    }
                    Row {
                        spacing: 8; width: parent.width
                        Panel {
                            width: (parent.width - 8) / 2; height: 64
                            Column { x: 12; y: 10; Lbl { text: "Verstrichen" } Val { font.pixelSize: 22; text: win.st.printing ? Api.hms(win.st.elapsed_s) : "—" } }
                        }
                        Panel {
                            width: (parent.width - 8) / 2; height: 64
                            Column { x: 12; y: 10; Lbl { text: "Fertig ca." }
                                Val { font.pixelSize: 22
                                    text: {
                                        if (!win.st.printing || !(win.st.percent > 0)) return "—"
                                        var d = new Date(Date.now() + win.st.elapsed_s * (100 - win.st.percent) / win.st.percent * 1000)
                                        return d.getHours() + ":" + ("0" + d.getMinutes()).slice(-2) + " Uhr"
                                    } } }
                        }
                    }
                    Item { width: 1; height: parent.height - 84 - 64 - 52 - 52 - 32 }
                    KButton { width: parent.width; text: "Sintern stoppen & abkühlen"; onClicked: win.ask("Sintern stoppen?", "Der Kit hört auf zu belichten und kühlt ab.", function () { win.send({ cmd: "stop_sintering" }) }) }
                    KButton { width: parent.width; kind: "red"; text: "Druck abbrechen"; onClicked: win.ask("Druck abbrechen?", "Der laufende Druck wird beendet und lässt sich nicht fortsetzen.", function () { win.send({ cmd: "abort_print" }) }) }
                }
            }

            // ======= Bewegung =======
            Item {
                visible: win.page === "move"
                y: 42; width: parent.width; height: parent.height - 42
                Panel {
                    id: movePanel
                    width: parent.width - 298; height: parent.height
                    Column {
                        anchors.fill: parent; anchors.margins: 12; spacing: 8
                        Lbl { text: win.st.printing ? "Während des Drucks gesperrt" : "Schrittweite" }
                        Seg { width: parent.width; items: [["0,1 mm", 0.1], ["1 mm", 1], ["10 mm", 10]]; value: win.step; onPicked: function (v) { win.step = v } }
                        Row {
                            width: parent.width; height: parent.height - 62; spacing: 8
                            Repeater {
                                model: [["Bauplattform", "print"], ["Vorrat", "reservoir"]]
                                Column {
                                    width: (parent.width - 8) / 2; height: parent.height; spacing: 8
                                    Lbl { text: modelData[0] }
                                    KButton { width: parent.width; height: (parent.height - 56) / 2; text: "▲"; size: 22; ok: !win.st.printing
                                        onClicked: win.send({ cmd: "move", platform: modelData[1], mm: -win.step }, function (ok) { if (ok) { var m = win.moved; m[modelData[1]] -= win.step; win.moved = m } }) }
                                    KButton { width: parent.width; height: (parent.height - 56) / 2; text: "▼"; size: 22; ok: !win.st.printing
                                        onClicked: win.send({ cmd: "move", platform: modelData[1], mm: win.step }, function (ok) { if (ok) { var m = win.moved; m[modelData[1]] += win.step; win.moved = m } }) }
                                    Lbl { text: "seit Start " + Api.de(win.moved[modelData[1]]) + " mm" }
                                }
                            }
                        }
                    }
                }
                Column {
                    x: movePanel.width + 8; width: 290; spacing: 8
                    Panel {
                        width: parent.width; height: 128
                        Column { anchors.fill: parent; anchors.margins: 12; spacing: 8
                            Lbl { text: "Beschichter · Schichtdicke" }
                            Seg { width: parent.width; height: 40; items: [["0,10", 0.1], ["0,15", 0.15], ["0,20", 0.2]]; value: win.thick; onPicked: function (v) { win.thick = v } }
                            KButton { width: parent.width; height: 44; kind: "pri"; text: "Schicht auftragen"; ok: !win.st.printing; onClicked: win.send({ cmd: "make_layer", mm: win.thick }) }
                        }
                    }
                    Panel {
                        width: parent.width; height: 140
                        Column { anchors.fill: parent; anchors.margins: 12; spacing: 8
                            Lbl { text: "Pulver laden · Bauhöhe des Jobs" }
                            Row { spacing: 8; width: parent.width
                                KButton { width: 52; height: 44; text: "−"; size: 20; onClicked: win.jobH = Math.max(5, win.jobH - 5) }
                                Val { width: parent.width - 120; height: 44; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; text: win.jobH + " mm" }
                                KButton { width: 52; height: 44; text: "+"; size: 20; onClicked: win.jobH = Math.min(105, win.jobH + 5) } }
                            KButton { width: parent.width; height: 44; text: "Vorrat um " + (win.jobH + 5) + " mm absenken"; ok: !win.st.printing
                                onClicked: win.ask("Pulver laden?", "Vorrat fährt " + (win.jobH + 5) + " mm nach unten (Bauhöhe " + win.jobH + " mm + 5 mm Puffer). Danach Pulver einfüllen und abziehen.", function () { win.send({ cmd: "move", platform: "reservoir", mm: win.jobH + 5 }) }) }
                        }
                    }
                    KButton { width: parent.width; kind: "red"; text: "Motoren stoppen"; onClicked: win.send({ cmd: "freeze_motors" }) }
                }
            }

            // ======= Heizung =======
            Item {
                visible: win.page === "heat"
                y: 42; width: parent.width; height: parent.height - 42
                Panel {
                    id: heatPanel
                    width: parent.width * 0.55; height: parent.height
                    Row {
                        anchors.centerIn: parent; spacing: 14
                        KButton { width: 60; height: 60; radius: 30; text: "−"; size: 26; anchors.verticalCenter: parent.verticalCenter
                            onClicked: { win.target = Math.max(40, win.target - 5); if (win.warm) win.send({ cmd: "target", which: "chamber_warmup", celsius: win.target }) } }
                        Item {
                            width: 240; height: 240
                            Canvas {
                                id: ring
                                anchors.fill: parent
                                property real frac: Math.max(0, Math.min(1, (win.st.chamber || 0) / win.target))
                                onFracChanged: requestPaint()
                                onPaint: {
                                    var c = getContext("2d"); c.reset()
                                    c.lineWidth = 14; c.lineCap = "round"
                                    c.strokeStyle = "#1affffff"; c.beginPath(); c.arc(120, 120, 110, 0, 2 * Math.PI); c.stroke()
                                    var g = c.createLinearGradient(0, 0, 240, 240); g.addColorStop(0, "#ffb08f"); g.addColorStop(1, "#ff6a3d")
                                    c.strokeStyle = g; c.beginPath(); c.arc(120, 120, 110, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * frac); c.stroke()
                                }
                            }
                            Column {
                                anchors.centerIn: parent; spacing: 4
                                Lbl { anchors.horizontalCenter: parent.horizontalCenter; text: "Kammer jetzt" }
                                Text { anchors.horizontalCenter: parent.horizontalCenter; text: Api.de(win.st.chamber) + "°"; color: win.cInk; font.family: win.fontName; font.pixelSize: 54; font.weight: Font.Light; font.letterSpacing: -2 }
                                Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Soll " + win.target + " °C"; color: win.cHeat; font.family: win.fontName; font.pixelSize: 15; font.weight: Font.DemiBold }
                            }
                        }
                        KButton { width: 60; height: 60; radius: 30; text: "+"; size: 26; anchors.verticalCenter: parent.verticalCenter
                            onClicked: { win.target = Math.min(180, win.target + 5); if (win.warm) win.send({ cmd: "target", which: "chamber_warmup", celsius: win.target }) } }
                    }
                }
                Column {
                    x: heatPanel.width + 8; width: parent.width - heatPanel.width - 8; spacing: 8
                    KButton {
                        width: parent.width; kind: win.warm ? "normal" : "hot"; text: win.warm ? "Vorheizen stoppen" : "Vorheizen starten"
                        onClicked: {
                            var on = !win.warm
                            var go = function () { win.send({ cmd: "warmup", on: on }, function (ok) { if (ok) win.warm = on }) }
                            if (on) win.send({ cmd: "target", which: "chamber_warmup", celsius: win.target }, function (ok) { if (ok) go() })
                            else go()
                        }
                    }
                    Panel {
                        width: parent.width; height: 230
                        Column {
                            anchors.fill: parent; anchors.margins: 12; spacing: 14
                            Lbl { text: "Heizstrahler" }
                            Repeater {
                                model: [["Links", "left", 80], ["Rechts", "right", 80], ["Front", "front", 65]]
                                Item {
                                    id: lampRow
                                    width: parent.width; height: 40
                                    property int value: modelData[2]
                                    Text { width: 54; anchors.verticalCenter: parent.verticalCenter; text: modelData[0]; color: win.cInk; font.family: win.fontName; font.pixelSize: 14 }
                                    Item {
                                        id: track
                                        x: 60; width: parent.width - 108; height: 40
                                        Rectangle { anchors.verticalCenter: parent.verticalCenter; width: parent.width; height: 6; radius: 3; color: "#1affffff" }
                                        Rectangle { anchors.verticalCenter: parent.verticalCenter; width: parent.width * lampRow.value / 100; height: 6; radius: 3
                                            gradient: Gradient { orientation: Gradient.Horizontal; GradientStop { position: 0; color: "#ffb08f" } GradientStop { position: 1; color: "#ff6a3d" } } }
                                        Rectangle { width: 30; height: 30; radius: 15; anchors.verticalCenter: parent.verticalCenter; x: track.width * lampRow.value / 100 - 15; color: "#e6e9ee" }
                                        MouseArea {
                                            anchors.fill: parent
                                            function setX(mx) { lampRow.value = Math.round(Math.max(0, Math.min(1, mx / track.width)) * 100) }
                                            onPressed: function (m) { setX(m.x) }
                                            onPositionChanged: function (m) { setX(m.x) }
                                            onReleased: win.send({ cmd: "lamp", which: modelData[1], percent: lampRow.value })
                                        }
                                    }
                                    Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: lampRow.value + " %"; color: win.cInk; font.family: win.fontName; font.pixelSize: 14; font.weight: Font.DemiBold }
                                }
                            }
                        }
                    }
                }
            }

            // ======= Jobs =======
            Panel {
                visible: win.page === "jobs"
                y: 42; width: parent.width; height: parent.height - 42
                Column {
                    anchors.centerIn: parent; width: 440; spacing: 8
                    Lbl { text: "Job auf der SD-Karte im Kit" }
                    Val { text: "Letzten Job erneut drucken" }
                    Lbl { width: parent.width; wrapMode: Text.WordWrap; elide: Text.ElideNone; font.pixelSize: 13
                        text: "Startet den Job, den Central zuletzt auf den Kit übertragen hat. Vorher Pulver laden und die Kammer vorheizen. Die Job-Bibliothek mit Schichtansicht folgt mit dem PC-Durchreichen." }
                    Item { width: 1; height: 6 }
                    KButton { width: 260; kind: "pri"; text: "Druck starten"; ok: !win.st.printing
                        onClicked: win.ask("Druck starten?", "Pulver geladen, Haube geschlossen, Kammer vorgeheizt?", function () { win.send({ cmd: "start_print" }) }) }
                }
            }

            // ======= System =======
            Item {
                visible: win.page === "sys"
                y: 42; width: parent.width; height: parent.height - 42
                Panel {
                    id: msgPanel
                    width: (parent.width - 166) / 2; height: parent.height; clip: true
                    Flickable {
                        anchors.fill: parent; anchors.margins: 12; contentHeight: msgCol.height; clip: true
                        Column {
                            id: msgCol; width: parent.width; spacing: 6
                            Lbl { text: "Meldungen vom Kit" }
                            Text { visible: !(win.st.errors || []).length && !(win.st.warnings || []).length; text: "Keine Fehler oder Warnungen."; color: win.cInk; font.family: win.fontName; font.pixelSize: 13 }
                            Repeater {
                                model: (win.st.errors || []).map(function (m) { m.err = true; return m }).concat(win.st.warnings || [])
                                Rectangle {
                                    width: msgCol.width; height: mc.height + 16; radius: 12
                                    color: modelData.err ? "#1fe5484d" : "#1aff6a3d"; border.color: modelData.err ? "#59e5484d" : "#40ff6a3d"
                                    Column { id: mc; x: 10; y: 8; width: parent.width - 20; spacing: 2
                                        Text { width: parent.width; wrapMode: Text.WordWrap; text: modelData.code + " · " + modelData.title; color: win.cInk; font.family: win.fontName; font.pixelSize: 13; font.weight: Font.DemiBold }
                                        Text { width: parent.width; wrapMode: Text.WordWrap; text: modelData.text; color: "#c9cfd8"; font.family: win.fontName; font.pixelSize: 12 } }
                                }
                            }
                        }
                    }
                }
                Panel {
                    id: infoPanel
                    x: msgPanel.width + 8; width: msgPanel.width; height: parent.height
                    Column {
                        anchors.fill: parent; anchors.margins: 12; spacing: 0
                        Repeater {
                            model: [["Modell", win.st.model], ["Firmware", win.st.firmware], ["Protokoll", win.st.protocol],
                                    ["Geräte-ID", win.st.uid ? win.st.uid.slice(0, 12) + "…" : "—"], ["Zustand", win.st.state],
                                    ["WLAN", win.wifi.current ? win.wifi.current : "—"], ["IP-Adresse", win.wifi.ip || "—"],
                                    ["Hinweis", win.st.message || "—"]]
                            Item {
                                width: parent.width; height: 34
                                Lbl { anchors.verticalCenter: parent.verticalCenter; text: modelData[0] }
                                Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 90; horizontalAlignment: Text.AlignRight; elide: Text.ElideRight
                                    text: modelData[1] === undefined || modelData[1] === null ? "—" : String(modelData[1]); color: win.cInk; font.family: win.fontName; font.pixelSize: 13 }
                                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: win.cLine }
                            }
                        }
                    }
                }
                Column {
                    x: infoPanel.x + infoPanel.width + 8; width: 150; height: parent.height; spacing: 8
                    KButton { width: parent.width; height: 70; kind: "pri"; text: "WLAN"; onClicked: wifiOvl.open() }
                    Item { width: 1; height: parent.height - 70 - 52 - 52 - 24 }
                    KButton { width: parent.width; text: "Neustart"; onClicked: win.ask("Neu starten?", "Der Kit Controller startet neu. Ein laufender Druck läuft auf dem Kit weiter.", function () { win.send({ cmd: "reboot" }) }) }
                    KButton { width: parent.width; kind: "red"; text: "Ausschalten"; onClicked: win.ask("Ausschalten?", "Danach den Strom erst trennen, wenn das Display schwarz ist.", function () { win.send({ cmd: "poweroff" }) }) }
                }
            }
        }

        // ---------- Kein Kit ----------
        Rectangle {
            anchors.fill: parent; visible: !win.st.connected; color: "#d108090c"
            MouseArea { anchors.fill: parent; enabled: parent.visible; onClicked: {} }
            Panel {
                anchors.centerIn: parent; width: 460; height: 150
                Column {
                    anchors.centerIn: parent; width: parent.width - 40; spacing: 8
                    Val { anchors.horizontalCenter: parent.horizontalCenter; font.pixelSize: 20; text: win.kitdUp ? "Kein Kit verbunden" : "Kit Control startet …" }
                    Lbl { width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap; elide: Text.ElideNone; font.pixelSize: 13
                        text: (win.st.message || "USB-Kabel und Strom am Kit prüfen.") + " Central am PC muss getrennt sein." }
                    Row { anchors.horizontalCenter: parent.horizontalCenter; spacing: 8
                        KButton { width: 150; height: 40; text: "WLAN"; onClicked: wifiOvl.open() }
                        KButton { width: 150; height: 40; text: "System"; onClicked: { win.page = "sys"; win.st = Object.assign({}, win.st, { connected: true }) } } }
                }
            }
        }

        // ---------- WLAN ----------
        Rectangle {
            id: wifiOvl
            anchors.fill: parent; visible: false; color: "#0c0e11"
            property string ssid: ""
            property string pw: ""
            property bool showPw: false
            property bool shift: false
            property bool sym: false
            property bool busy: false
            property bool askPw: false
            function open() { askPw = false; pw = ""; visible = true; win.loadWifi(true) }
            function pick(n) {
                if (n.active) { win.ask("WLAN trennen?", "Verbindung zu „" + n.ssid + "“ trennen?", function () { win.send({ cmd: "wifi_disconnect" }, function () { win.loadWifi(false) }) }); return }
                ssid = n.ssid; pw = ""
                if (!n.secure) connect(); else askPw = true
            }
            function connect() {
                busy = true
                win.send({ cmd: "wifi_connect", ssid: ssid, password: pw }, function (ok) { busy = false; if (ok) { visible = false; pw = "" } win.loadWifi(false) })
            }
            MouseArea { anchors.fill: parent }
            Item {
                x: 10; y: 8; width: parent.width - 20; height: 40
                Val { anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 20; text: wifiOvl.askPw ? "Passwort für " + wifiOvl.ssid : "WLAN"; width: parent.width - 240; elide: Text.ElideRight }
                Row { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 8
                    KButton { visible: !wifiOvl.askPw; width: 110; height: 38; text: "Suchen"; onClicked: win.loadWifi(true) }
                    KButton { width: 110; height: 38; text: "Fertig"; onClicked: wifiOvl.visible = false } }
            }
            Panel {
                visible: !wifiOvl.askPw
                x: 10; y: 56; width: parent.width - 20; height: parent.height - 66
                ListView {
                    id: wl
                    anchors.fill: parent; anchors.margins: 6; clip: true; spacing: 2
                    model: win.wifi.networks || []
                    delegate: Rectangle {
                        width: ListView.view.width; height: 50; radius: 12
                        color: modelData.active ? "#1f6b86ff" : (dm.pressed ? "#0fffffff" : "transparent")
                        border.color: modelData.active ? "#996b86ff" : "transparent"
                        Row { x: 14; anchors.verticalCenter: parent.verticalCenter; spacing: 3
                            Repeater { model: 4
                                Rectangle { width: 3; height: 4 + index * 4; radius: 1; anchors.bottom: parent.bottom
                                    color: index < (modelData.signal > 70 ? 4 : modelData.signal > 50 ? 3 : modelData.signal > 30 ? 2 : 1) ? win.cInk : "#2effffff" } } }
                        Text { x: 46; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 170; elide: Text.ElideRight; text: modelData.ssid; color: win.cInk; font.family: win.fontName; font.pixelSize: 15 }
                        Text { anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter
                            text: (modelData.active ? "verbunden  " : "") + (modelData.secure ? "gesichert" : "offen"); color: "#aebcff"; font.family: win.fontName; font.pixelSize: 12; font.weight: Font.DemiBold }
                        MouseArea { id: dm; anchors.fill: parent; onClicked: wifiOvl.pick(modelData) }
                    }
                }
                Lbl { visible: wl.count === 0; anchors.centerIn: parent; text: win.wifi.available === false ? "WLAN nicht verfügbar" : "Suche Netze …" }
            }
            Column {
                visible: wifiOvl.askPw
                x: 10; y: 56; width: parent.width - 20; spacing: 6
                Row {
                    spacing: 8; width: parent.width
                    Rectangle {
                        width: parent.width - 236; height: 46; radius: 12; color: "#66000000"; border.color: "#806b86ff"; clip: true
                        Text { x: 14; anchors.verticalCenter: parent.verticalCenter; text: (wifiOvl.showPw ? wifiOvl.pw : "•".repeat(wifiOvl.pw.length)) + "|"; color: win.cInk; font.family: "monospace"; font.pixelSize: 18 }
                    }
                    KButton { width: 70; height: 46; text: wifiOvl.showPw ? "•••" : "abc"; onClicked: wifiOvl.showPw = !wifiOvl.showPw }
                    KButton { width: 150; height: 46; kind: "pri"; ok: !wifiOvl.busy; text: wifiOvl.busy ? "Verbinde …" : "Verbinden"
                        onClicked: { if (wifiOvl.pw.length < 8) toast.show("Passwort hat mindestens 8 Zeichen"); else wifiOvl.connect() } }
                }
                Repeater {
                    model: wifiOvl.sym ? ["1234567890", "!@#$%&*()=", "-_+.,:;/?'", "\"<>[]{}~^\\|"] : ["1234567890", "qwertzuiop", "asdfghjklü", "yxcvbnmöä"]
                    Row {
                        id: kr
                        property int ri: index
                        anchors.horizontalCenter: parent.horizontalCenter; spacing: 5
                        KButton { visible: kr.ri === 3; width: 96; height: 46; text: wifiOvl.shift ? "⇧ ABC" : "⇧"; onClicked: wifiOvl.shift = !wifiOvl.shift }
                        Repeater {
                            model: modelData.split("")
                            KButton {
                                width: 66; height: 46; size: 18
                                readonly property string ch: wifiOvl.shift ? modelData.toUpperCase() : modelData
                                text: ch
                                onClicked: { if (wifiOvl.pw.length < 63) wifiOvl.pw += ch; if (wifiOvl.shift) wifiOvl.shift = false }
                            }
                        }
                        KButton { visible: kr.ri === 3; width: 96; height: 46; text: "⌫"; onClicked: wifiOvl.pw = wifiOvl.pw.slice(0, -1) }
                    }
                }
                Row {
                    anchors.horizontalCenter: parent.horizontalCenter; spacing: 5
                    KButton { width: 110; height: 46; text: wifiOvl.sym ? "abc" : "#+="; onClicked: wifiOvl.sym = !wifiOvl.sym }
                    KButton { width: 450; height: 46; text: "Leerzeichen"; onClicked: if (wifiOvl.pw.length < 63) wifiOvl.pw += " " }
                    KButton { width: 110; height: 46; text: "Zurück"; onClicked: wifiOvl.askPw = false }
                }
            }
        }

        // ---------- Rückfrage ----------
        Rectangle {
            id: dlg
            anchors.fill: parent; visible: false; color: "#99000000"
            property string title
            property string text
            property var action
            MouseArea { anchors.fill: parent; onClicked: dlg.visible = false }
            Panel {
                anchors.centerIn: parent; width: 400; height: dc.height + 32
                MouseArea { anchors.fill: parent }
                Column {
                    id: dc; x: 16; y: 16; width: parent.width - 32; spacing: 8
                    Val { font.pixelSize: 19; text: dlg.title }
                    Lbl { width: parent.width; wrapMode: Text.WordWrap; elide: Text.ElideNone; font.pixelSize: 13; text: dlg.text }
                    Row { spacing: 8; topPadding: 6
                        KButton { width: (dc.width - 8) / 2; text: "Zurück"; onClicked: dlg.visible = false }
                        KButton { width: (dc.width - 8) / 2; kind: "red"; text: "Ja"; onClicked: { dlg.visible = false; if (dlg.action) dlg.action() } } }
                }
            }
        }

        // ---------- Hinweis ----------
        Rectangle {
            id: toast
            function show(t) { tt.text = t; visible = true; tTimer.restart() }
            visible: false; z: 10
            anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 14
            width: tt.implicitWidth + 32; height: 38; radius: 12; color: "#2a1416"; border.color: "#80e5484d"
            Text { id: tt; anchors.centerIn: parent; color: "#ffb3b5"; font.family: win.fontName; font.pixelSize: 13 }
            Timer { id: tTimer; interval: 4000; onTriggered: toast.visible = false }
        }
    }
}
