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
    color: "#0a0a0c"
    title: "Kit Control"

    // ---------- Farben ----------
    readonly property color cBg: "#0c0e11"
    readonly property color cInk: "#eef1f5"
    readonly property color cMut: "#8b9099"
    readonly property color cBlue: "#2fa6cc"
    readonly property color cBlue2: "#1b809f"
    readonly property color cHeat: "#ff8a5c"
    readonly property color cRed: "#e5484d"
    readonly property color cOk: "#2fd38a"
    readonly property color cLine: "#14ffffff"
    readonly property string fontName: "Inter"

    // ---------- Zustand ----------
    property var st: ({ connected: false, message: "Dienst startet …" })
    property var wifi: ({ available: true, current: "", networks: [] })
    property string page: "print"
    property real step: 1
    property real thick: 0.1
    property int jobH: 68
    property int target: 145          // Soll Kammer beim Vorheizen
    property int targetSurf: 150      // Soll Pulverbett (Oberfläche) beim Vorheizen
    property bool targetsLoaded: false
    property bool warm: false
    property var moved: ({ print: 0, reservoir: 0 })
    // Angenommene Ausgangstiefe der Platten (mm unter der Pulverebene), bis der Kit echte Werte liefert
    readonly property var baseDepth: ({ print: 70, reservoir: 30 })
    // Job, den der Kit druckt (vom Pi gestartet oder von Central über den Pi übertragen)
    readonly property var job: st.current_job && st.current_job.layers ? st.current_job : null
    // Job-Bibliothek auf dem Pi
    property var jobs: []
    property bool autostart: true
    function loadJobs() { Api.get("/api/jobs", function (j) { if (j) { win.jobs = j.jobs; win.autostart = j.autostart } }) }
    property real seenCentral: -1
    property real seenResult: -1
    property string seenCurrent: ""
    // Kalibrierung: bearbeitete Skalierung in % (wird erst mit „An Kit senden“ übertragen)
    property var scEdit: ({ x: 0, y: 0, z: 0 })
    property bool scDirty: false
    function scKit(k) { return win.st.scaling ? win.st.scaling[k] : 0 }
    function pct(v) { return (v > 0 ? "+" : v < 0 ? "−" : "±") + Api.de(Math.abs(v).toFixed(2)) + " %" }
    // Material & Parameter: Sollwerte (°C) und Lasergeschwindigkeit (mm/s), erst mit „An Kit senden“ übertragen
    readonly property var materials: ({ PA12: { sw: 150, cw: 140, sp: 170, cp: 140 }, TPE: { sw: 90, cw: 40, sp: 96, cp: 40 } })
    property var pEdit: ({ sw: 150, cw: 140, sp: 170, cp: 140, laser: 650 })
    property bool pDirty: false
    function pKit() { return { sw: st.target_surface_warmup, cw: st.target_chamber_warmup, sp: st.target_surface_print, cp: st.target_chamber_print, laser: st.laser_speed } }
    function materialOf(p) {
        for (var m in materials) { var t = materials[m]; if (p.sw === t.sw && p.cw === t.cw && p.sp === t.sp && p.cp === t.cp) return m }
        return "custom"
    }
    // Wie Central: Liegt der Druck-Sollwert der Oberfläche unter 130 °C, ist der Kit auf TPE eingestellt
    readonly property string kitMaterial: st.target_surface_print === undefined ? "" : (st.target_surface_print < 130 ? "TPE" : "PA12")
    onStChanged: {
        if (!targetsLoaded && st.target_surface_warmup !== undefined) {
            targetsLoaded = true
            targetSurf = Math.round(st.target_surface_warmup); target = Math.round(st.target_chamber_warmup)
        }
        if (!scDirty && st.scaling) scEdit = { x: st.scaling.x, y: st.scaling.y, z: st.scaling.z }
        if (!pDirty && st.target_surface_print !== undefined) pEdit = pKit()
        // Meldungen zur Job-Bibliothek (beim ersten Zustand nur merken, nicht anzeigen)
        var cj = st.central_job, jr = st.job_result
        if (cj && cj.ts !== seenCentral) {
            if (seenCentral >= 0)
                toast.show(cj.error ? cj.error
                           : cj.started === true ? "Job von Central gespeichert und gestartet"
                           : cj.started === false ? "Job von Central gespeichert – nicht gestartet (Autostart aus)"
                           : "Job von Central wird gespeichert …", !!cj.error)
            seenCentral = cj.ts; loadJobs()
        }
        if (jr && jr.ts !== seenResult) {
            if (seenResult >= 0) toast.show(jr.ok ? "„" + jr.name + "“ gestartet" : "Start fehlgeschlagen – " + jr.error, !jr.ok)
            seenResult = jr.ts; loadJobs()
        }
        if (seenCentral < 0) seenCentral = 0
        if (seenResult < 0) seenResult = 0
        // Bauhöhe des laufenden Jobs für Laden & Entladen übernehmen
        if (job && job.id !== seenCurrent) { seenCurrent = job.id; if (job.height_mm > 0) jobH = Math.round(job.height_mm) }
    }
    // Wie Central (Pulver-Fenster): Beim Öffnen von „Bewegung“ geht der Kit in die Pulvervorbereitung,
    // beim Verlassen wieder heraus. Nur darin lassen sich Platten fahren und Schichten auftragen.
    property string lastPage: "print"
    onPageChanged: {
        if (page === "move" && st.connected && st.state === 1)
            send({ cmd: "powder_prep_on" })
        else if (lastPage === "move" && page !== "move" && st.connected && st.state === 4)
            send({ cmd: "powder_prep_off" })
        lastPage = page
    }
    function depth(k) { return Math.max(0, Math.min(110, win.baseDepth[k] + win.moved[k])) }
    property int lastLayer: -1
    property bool kitdUp: false
    property var upd: ({ current: "", latest: null, available: false, running: false, log: [] })
    property bool updWasRunning: false

    readonly property int rot: {
        var a = Qt.application.arguments
        var i = a.indexOf("--rotation")
        return i >= 0 && i + 1 < a.length ? parseInt(a[i + 1]) : 90
    }
    readonly property bool portrait: win.width < win.height

    function send(body, after) {
        Api.cmd(body, function (j) {
            if (!j) { toast.show("Dienst nicht erreichbar", true); return }
            if (!j.ok) toast.show(j.error || "Fehler", true)
            if (after) after(j.ok)
        })
    }
    function jog(platform, mm) {
        win.send({ cmd: "move", platform: platform, mm: mm }, function (ok) {
            if (!ok) return
            var m = { print: win.moved.print, reservoir: win.moved.reservoir }
            m[platform] += mm; win.moved = m
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
            win.addTemp(j)
        })
    }
    // Temperaturverlauf für die Heizungsseite: alle 5 s ein Wert, 30 Minuten
    property var tHist: []
    property real tLast: 0
    function addTemp(j) {
        var now = Date.now()
        if (!j.connected || j.surface === undefined || now - tLast < 5000) return
        tLast = now
        var h = tHist.slice(-359)
        h.push({ s: j.surface, c: j.chamber, ts: j.printing ? j.target_surface_print : j.target_surface_warmup,
                 tc: j.printing ? j.target_chamber_print : j.target_chamber_warmup })
        tHist = h
    }
    Timer { interval: 15000; running: true; repeat: true; triggeredOnStart: true; onTriggered: win.loadWifi(false) }

    // Software-Update: Stand abfragen (schnell, solange ein Update läuft), alle 6 h im Repo nachsehen
    function loadUpd() {
        Api.get("/api/update", function (j) {
            if (!j) return
            if (win.updWasRunning && !j.running) toast.show(j.log && j.log.length ? j.log[j.log.length - 1] : "Update beendet")
            win.updWasRunning = j.running
            win.upd = j
        })
    }
    function checkUpd() { Api.cmd({ cmd: "update_check" }, function (j) { if (j && j.update) win.upd = j.update }) }
    // Beim Start einmal nach neuer Software suchen und sie gleich anbieten (WLAN braucht nach dem Booten etwas)
    property bool updOffered: false
    property int updTries: 0
    Timer {
        id: startUpd
        interval: win.updTries === 0 ? 8000 : 20000; running: !win.updOffered && win.updTries < 6; repeat: true
        onTriggered: {
            win.updTries++
            Api.cmd({ cmd: "update_check" }, function (j) {
                if (!j || !j.update) return
                win.upd = j.update
                if (!j.update.latest) return                 // noch kein Netz – später nochmal
                win.updOffered = true
                if (j.update.available && !j.update.running && !win.st.printing && !win.st.transfer) updOvl.open()
            })
        }
    }
    Timer { interval: (win.upd.running || updOvl.visible) ? 2000 : 60000; running: true; repeat: true; triggeredOnStart: true; onTriggered: win.loadUpd() }
    Timer { interval: 20000; running: true; onTriggered: win.checkUpd() }
    Timer { interval: 6 * 3600 * 1000; running: true; repeat: true; onTriggered: win.checkUpd() }

    // ---------- Bausteine ----------
    component Panel: Rectangle {
        radius: 20
        color: "#151518"
    }
    component Lbl: Text {
        color: win.cMut; font.family: win.fontName; font.pixelSize: 12; font.weight: Font.Medium
        elide: Text.ElideRight
    }
    component Val: Text {
        color: win.cInk; font.family: win.fontName; font.pixelSize: 28; font.weight: Font.Light
        font.letterSpacing: -0.8
    }
    component KButton: Rectangle {
        id: kb
        property string text: ""
        property string kind: "normal"     // normal | pri | acc (Petrol) | red | hot (Heizen)
        property bool ok: true
        property int size: 14
        signal clicked()
        height: 52; radius: Math.min(height / 2, 22)
        opacity: ok ? 1 : 0.35
        scale: ma.pressed ? 0.97 : 1
        Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
        // Hauptaktion weiß mit dunkler Schrift, Warnaktionen nur farbig getönt
        color: kind === "pri" ? (ma.pressed ? "#d4d6db" : "#f2f3f5")
             : kind === "red" ? (ma.pressed ? "#4de5484d" : "#29e5484d")
             : kind === "hot" ? (ma.pressed ? "#4dff7a45" : "#29ff7a45")
             : kind === "acc" ? (ma.pressed ? "#166d88" : win.cBlue2)
             : (ma.pressed ? "#2c2c31" : "#1d1d21")
        Behavior on color { ColorAnimation { duration: 120 } }
        Text {
            anchors.centerIn: parent; width: parent.width - 16
            horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
            text: kb.text
            color: kb.kind === "pri" ? "#0a0a0c" : kb.kind === "red" ? "#ff6b70" : kb.kind === "hot" ? "#ff9b70" : kb.kind === "acc" ? "#ffffff" : "#eef1f5"
            font.family: win.fontName; font.pixelSize: kb.size; font.weight: Font.Medium; font.letterSpacing: -0.2
        }
        MouseArea { id: ma; anchors.fill: parent; enabled: kb.ok; onClicked: kb.clicked() }
    }
    component Seg: Rectangle {
        id: sg
        property var items: []        // [[label, value], …]
        property var value
        signal picked(var v)
        height: 44; radius: 22; color: "#1e1e22"
        Row {
            anchors.fill: parent; anchors.margins: 4; spacing: 4
            Repeater {
                model: sg.items
                Rectangle {
                    width: (sg.width - 8 - 4 * (sg.items.length - 1)) / sg.items.length; height: parent.height; radius: 18
                    color: sg.value === modelData[1] ? "#3a3a42" : "transparent"
                    Behavior on color { ColorAnimation { duration: 150 } }
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
        readonly property bool active: key === "sys" ? ["sys", "cal", "params"].indexOf(win.page) >= 0 : win.page === key
        width: 56; height: 54; radius: 16
        color: nb.active ? "#24242a" : "transparent"
        Behavior on color { ColorAnimation { duration: 150 } }
        Rectangle { visible: nb.active; width: 3; height: 18; radius: 2; x: -6; anchors.verticalCenter: parent.verticalCenter; color: nb.hot ? win.cHeat : win.cBlue }
        Column {
            anchors.centerIn: parent; spacing: 4
            Image { anchors.horizontalCenter: parent.horizontalCenter; source: "assets/i-" + nb.icon + ".png"; width: 22; height: 22; smooth: true; mipmap: true; opacity: nb.active ? 1 : 0.45 }
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: nb.label; color: nb.active ? "white" : win.cMut; font.family: win.fontName; font.pixelSize: 9; font.weight: Font.Medium }
        }
        MouseArea { anchors.fill: parent; onClicked: win.page = nb.key }
    }
    // Draufsicht einer Schicht aus der Jobdatei: Kontur hell, Füllung gedämpft (Linien vom Pi in mm)
    component LayerView: Rectangle {
        id: lv
        property var job: null          // { id, layers, bbox }
        property int layerNo: 0
        property var ld: null
        property string hint: "Kein Job"
        radius: 14; color: "#0e0f11"; border.color: "#2a2d33"; border.width: 1
        function load() {
            if (!job || !job.layers || layerNo < 1) { ld = null; cv.requestPaint(); return }
            var want = job.id + "/" + layerNo
            Api.get("/api/jobs/" + job.id + "/layer/" + layerNo, function (j) {
                if (lv.job && lv.job.id + "/" + lv.layerNo === want) { lv.ld = j; cv.requestPaint() }
            })
        }
        Timer { id: lvT; interval: 90; onTriggered: lv.load() }
        onJobChanged: lvT.restart()
        onLayerNoChanged: lvT.restart()
        Canvas {
            id: cv
            anchors.fill: parent; anchors.margins: 8
            onPaint: {
                var g = getContext("2d"); g.reset()
                var d = lv.ld, b = lv.job ? lv.job.bbox : null
                if (!d || !b) return
                // Ausschnitt: Bauraum 130 mm um die Mitte des Jobs, größer falls nötig
                var span = Math.max(130, b[2] - b[0] + 10, b[3] - b[1] + 10)
                var cx = (b[0] + b[2]) / 2, cy = (b[1] + b[3]) / 2
                var k = Math.min(width, height) / span, ox = width / 2, oy = height / 2
                function line(a, col, w) {
                    g.strokeStyle = col; g.lineWidth = w; g.beginPath()
                    for (var i = 0; i + 3 < a.length; i += 4) {
                        g.moveTo(ox + (a[i] - cx) * k, oy - (a[i + 1] - cy) * k)
                        g.lineTo(ox + (a[i + 2] - cx) * k, oy - (a[i + 3] - cy) * k)
                    }
                    g.stroke()
                }
                // Bauplatte 110 mm (bevorzugter Bereich des Kits) als Orientierung
                g.strokeStyle = "#22ffffff"; g.lineWidth = 1
                var p = 110 * k; g.strokeRect(ox - p / 2, oy - p / 2, p, p)
                line(d.infill, "#7a2fa6cc", Math.max(0.6, 0.35 * k))
                line(d.contour, "#8fdcf2", 1.4)
            }
        }
        Text { visible: !lv.ld; anchors.centerIn: parent; width: parent.width - 24; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
            text: lv.hint; color: win.cMut; font.family: win.fontName; font.pixelSize: 12 }
    }
    // Temperaturring: Ist-Wert im Verhältnis zum Sollwert
    component HeatRing: Canvas {
        id: hr
        property real value: 0
        property real goal: 1
        property real frac: Math.max(0, Math.min(1, value / Math.max(1, goal)))
        onFracChanged: requestPaint()
        onWidthChanged: requestPaint()
        onPaint: {
            var c = getContext("2d"); c.reset()
            var r = width / 2 - 9, m = width / 2
            c.lineWidth = 10; c.lineCap = "round"
            c.strokeStyle = "#1affffff"; c.beginPath(); c.arc(m, m, r, 0, 2 * Math.PI); c.stroke()
            var end = -Math.PI / 2 + 2 * Math.PI * frac
            c.strokeStyle = "#ff7a45"; c.beginPath(); c.arc(m, m, r, -Math.PI / 2, end); c.stroke()
            if (frac > 0.01) { c.fillStyle = "#ffffff"; c.beginPath(); c.arc(m + r * Math.cos(end), m + r * Math.sin(end), 3.5, 0, 2 * Math.PI); c.fill() }
        }
    }
    component Chip: Rectangle {
        id: ch
        property string text
        property color dot: "transparent"
        property color tint: "#18181c"
        signal clicked()
        height: 28; radius: 14; color: tint
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

        Rectangle { anchors.fill: parent; color: "#0a0a0c" }

        // Navigation
        Item {
            id: nav
            x: 8; y: 8; width: 64; height: parent.height - 16
            Column {
                anchors.top: parent.top; anchors.topMargin: 8; anchors.horizontalCenter: parent.horizontalCenter; spacing: 6
                Image { source: "../branding/mark.png"; width: 40; height: 40; fillMode: Image.PreserveAspectFit; smooth: true; mipmap: true; anchors.horizontalCenter: parent.horizontalCenter }
                Item { width: 1; height: 2 }
                NavBtn { key: "print"; label: "Druck"; icon: "print" }
                NavBtn { key: "move"; label: "Bewegung"; icon: "move" }
                NavBtn { key: "heat"; label: "Heizung"; icon: "heat"; hot: true }
                NavBtn { key: "jobs"; label: "Jobs"; icon: "jobs" }
            }
            NavBtn { key: "sys"; label: "System"; icon: "system"; anchors.bottom: parent.bottom; anchors.bottomMargin: 8; anchors.horizontalCenter: parent.horizontalCenter }
        }

        Item {
            id: main
            x: 80; y: 8; width: parent.width - 88; height: parent.height - 16

            // Kopfzeile
            Item {
                id: head
                width: parent.width; height: 34
                // Unterseiten von System: Zurück-Pfeil
                Rectangle {
                    id: backBtn
                    visible: win.page === "cal" || win.page === "params"
                    width: visible ? 34 : 0; height: 34; radius: 17; color: backMa.pressed ? "#2c2c31" : "#1d1d21"
                    Text { anchors.centerIn: parent; text: "‹"; color: win.cInk; font.family: win.fontName; font.pixelSize: 24; anchors.verticalCenterOffset: -2 }
                    MouseArea { id: backMa; anchors.fill: parent; onClicked: win.page = "sys" }
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter; x: backBtn.width + (backBtn.visible ? 10 : 4)
                    width: Math.max(0, chips.x - x - 12); elide: Text.ElideRight
                    text: ({ print: "Druck", move: "Bewegung", heat: "Heizung", jobs: "Jobs", cal: "Kalibrieren", params: "Parameter", sys: "System" })[win.page]
                    color: win.cInk; font.family: win.fontName; font.pixelSize: 22; font.weight: Font.Medium; font.letterSpacing: -0.6
                }
                Row {
                    id: chips
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
                        text: win.st.connected ? (win.st.model || "Kit") + " · FW " + win.st.firmware + (win.st.demo ? " · Demo" : "") + (win.st.central ? " · Central" : "") : "getrennt"
                    }
                }
            }

            // ======= Druck =======
            Item {
                opacity: win.page === "print" ? 1 : 0; visible: opacity > 0
                Behavior on opacity { NumberAnimation { duration: 180 } }
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
                        Text { anchors.right: parent.right; text: win.st.printing ? win.st.percent + " %" : ""; color: "#5cc3e3"; font.family: win.fontName; font.pixelSize: 26; font.weight: Font.DemiBold }
                        Lbl { anchors.right: parent.right; text: win.st.printing ? "Druck läuft" : (win.st.waiting_for_sd ? "Wartet auf SD-Karte" : "Bereit") }
                    }
                    Chamber {
                        id: chamber
                        printing: !!win.st.printing
                        buildDepth: win.depth("print"); resDepth: win.depth("reservoir")
                        anchors.bottom: parent.bottom; anchors.bottomMargin: 18
                        anchors.horizontalCenter: parent.horizontalCenter
                    }
                    Rectangle {
                        x: 14; width: parent.width - 28; height: 5; radius: 3; anchors.bottom: parent.bottom; anchors.bottomMargin: 10; color: "#14ffffff"
                        Rectangle {
                            id: bar
                            height: parent.height; radius: 3; clip: true
                            width: parent.width * (win.st.printing ? win.st.percent / 100 : 0)
                            Behavior on width { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
                            color: win.cBlue
                            Image {
                                source: "assets/glow-white.png"; width: 80; height: 30; y: -12; opacity: 0.5
                                NumberAnimation on x { from: -80; to: bar.width; duration: 2200; loops: Animation.Infinite; running: win.st.printing === true }
                            }
                        }
                    }
                }

                Column {
                    x: chamberPanel.width + 8; width: parent.width - chamberPanel.width - 8; height: parent.height; spacing: 8
                    Row {
                        spacing: 8; width: parent.width
                        Panel {
                            width: (parent.width - 8) / 2; height: 84
                            Column { x: 12; y: 10; spacing: 1
                                Lbl { text: "Pulverbett" }
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
                    Panel {
                        width: parent.width; height: parent.height - 84 - 52 - 52 - 24
                        LayerView {
                            id: curLayer
                            x: 10; y: 15; width: parent.height - 30; height: width
                            job: win.job
                            layerNo: win.job ? (win.st.printing ? Math.max(1, Math.min(win.job.layers, win.st.layer)) : win.job.layers) : 0
                            hint: "Schichtvorschau erscheint, sobald ein Job über den Pi läuft"
                        }
                        Column {
                            x: curLayer.width + 22; y: 10; width: parent.width - curLayer.width - 32; spacing: 2
                            Lbl { text: "Aktuelle Schicht" }
                            Text { text: win.st.printing ? win.st.layer : "—"; color: win.cInk; font.family: win.fontName; font.pixelSize: 26; font.weight: Font.Light }
                            Lbl { text: win.job && win.st.printing ? "von " + win.job.layers + " · Z " + Api.de(win.st.layer * win.job.layer_mm) + " mm" : " " ; font.pixelSize: 11 }
                            Item { width: 1; height: 6 }
                            Lbl { text: "Verstrichen" }
                            Text { text: win.st.printing ? Api.hms(win.st.elapsed_s) : "—"; color: win.cInk; font.family: win.fontName; font.pixelSize: 16 }
                            Item { width: 1; height: 4 }
                            Lbl { text: "Fertig ca." }
                            Text { color: win.cInk; font.family: win.fontName; font.pixelSize: 16
                                text: {
                                    if (!win.st.printing || !(win.st.percent > 0)) return "—"
                                    var d = new Date(Date.now() + win.st.elapsed_s * (100 - win.st.percent) / win.st.percent * 1000)
                                    return d.getHours() + ":" + ("0" + d.getMinutes()).slice(-2) + " Uhr"
                                } }
                        }
                    }
                    KButton { width: parent.width; text: "Sintern stoppen & abkühlen"; onClicked: win.ask("Sintern stoppen?", "Der Kit hört auf zu belichten und kühlt ab.", function () { win.send({ cmd: "stop_sintering" }) }) }
                    KButton { width: parent.width; kind: "red"; text: "Druck abbrechen"; onClicked: win.ask("Druck abbrechen?", "Der laufende Druck wird beendet und lässt sich nicht fortsetzen.", function () { win.send({ cmd: "abort_print" }) }) }
                }
            }

            // ======= Bewegung =======
            // Je Achse eine Karte: große Position, Schacht mit Pulver und massiver Platte, Fahrtasten daneben.
            Item {
                id: movePage
                opacity: win.page === "move" ? 1 : 0; visible: opacity > 0
                Behavior on opacity { NumberAnimation { duration: 180 } }
                y: 42; width: parent.width; height: parent.height - 42
                readonly property real leftW: width - 268
                property bool coating: false

                Seg {
                    width: movePage.leftW - 150; height: 44
                    items: [["0,1 mm", 0.1], ["1 mm", 1], ["10 mm", 10]]; value: win.step; onPicked: function (v) { win.step = v }
                }
                KButton { x: movePage.leftW - 142; width: 142; height: 44; kind: "red"; text: "Motoren stoppen"; size: 13; onClicked: win.send({ cmd: "freeze_motors" }) }
                Repeater {
                    // [Name, Achse, angenommene Starttiefe in mm für die Zeichnung]
                    model: [["Bauplattform", "print"], ["Vorrat", "reservoir"]]
                    Panel {
                        id: ax
                        readonly property string key: modelData[1]
                        readonly property real depth: win.depth(key)
                        x: index * (movePage.leftW / 2 + 4); y: 52
                        width: movePage.leftW / 2 - 4; height: movePage.height - 52

                        Lbl { x: 14; y: 12; text: modelData[0] }
                        Row {
                            x: 14; y: 28; spacing: 4
                            Text { text: (win.moved[ax.key] > 0 ? "−" : win.moved[ax.key] < 0 ? "+" : "") + Api.de(Math.abs(win.moved[ax.key]))
                                color: win.cInk; font.family: win.fontName; font.pixelSize: 40; font.weight: Font.Light; font.letterSpacing: -1.4 }
                            Text { y: 21; text: "mm"; color: win.cMut; font.family: win.fontName; font.pixelSize: 16 }
                        }
                        Lbl { x: 14; y: 78; text: win.st.printing ? "Während des Drucks gesperrt" : "seit Start"; font.pixelSize: 11 }

                        // Schacht: dünnes Blech, Pulver mit Korn, massive Platte
                        Item {
                            id: well
                            x: 22; y: 108; width: parent.width - 22 - 14 - 76 - 18; height: parent.height - 108 - 16
                            readonly property real plateY: 4 + ax.depth / 110 * (height - 14)
                            Rectangle { x: -8; y: 0; width: 8; height: 1.5; color: "#c9ced6" }                 // Deck links
                            Rectangle { x: well.width; y: 0; width: 8; height: 1.5; color: "#c9ced6" }         // Deck rechts
                            Item {
                                x: 1.5; y: 1.5; width: parent.width - 3; height: parent.height - 3; clip: true
                                Image { width: parent.width; height: well.plateY; source: "assets/powder.png"; fillMode: Image.Tile; smooth: false
                                    Behavior on height { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } } }
                                Rectangle {
                                    visible: ax.key === "print"
                                    x: parent.width * 0.18; width: parent.width * 0.3; height: Math.min(40, well.plateY * 0.5); radius: 4
                                    y: well.plateY - height - 6
                                    color: "#292fa6cc"; border.color: "#5cc3e3"; border.width: 1.2
                                    Behavior on y { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }
                                }
                                Rectangle {
                                    visible: ax.key === "print"
                                    x: parent.width * 0.56; width: parent.width * 0.3; height: Math.min(24, well.plateY * 0.35); radius: 4
                                    y: well.plateY - height - 6
                                    color: "#292fa6cc"; border.color: "#5cc3e3"; border.width: 1.2
                                    Behavior on y { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }
                                }
                                Rectangle {
                                    y: well.plateY; width: parent.width; height: 10; radius: 1.5
                                    color: "#b4bac2"; border.color: "#c9ced6"; border.width: 1
                                    Behavior on y { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }
                                }
                            }
                            Rectangle { x: 0; y: 0; width: 1.5; height: parent.height; color: "#c9ced6" }
                            Rectangle { x: parent.width - 1.5; y: 0; width: 1.5; height: parent.height; color: "#c9ced6" }
                            Rectangle { x: 0; y: parent.height - 1.5; width: parent.width; height: 1.5; color: "#c9ced6" }
                        }
                        // Fahrtasten
                        Column {
                            x: parent.width - 14 - 76; y: 108; width: 76; spacing: 8
                            readonly property real h: (ax.height - 108 - 16 - 16 - 44) / 2
                            KButton { width: 76; height: parent.h; text: "▲"; size: 22; ok: !win.st.printing; onClicked: win.jog(ax.key, -win.step) }
                            KButton { width: 76; height: parent.h; text: "▼"; size: 22; ok: !win.st.printing; onClicked: win.jog(ax.key, win.step) }
                            KButton { width: 76; height: 44; text: "Start"; size: 13; ok: !win.st.printing && win.moved[ax.key] !== 0
                                onClicked: win.jog(ax.key, -win.moved[ax.key]) }
                        }
                    }
                }

                // Rechte Spalte: Beschichter, Pulver laden, Stopp
                Column {
                    x: movePage.leftW + 8; width: 260; spacing: 8
                    Panel {
                        width: parent.width; height: 176
                        Column { anchors.fill: parent; anchors.margins: 12; spacing: 8
                            Item { width: parent.width; height: 16
                                Lbl { text: "Beschichter" }
                                Lbl { anchors.right: parent.right; text: movePage.coating ? "fährt …" : "in Parkposition" } }
                            // Mini-Ansicht: Bauplatte, Blech, Vorrat, Parkplatz
                            Item {
                                id: rc; width: parent.width; height: 30
                                Rectangle { y: 22; width: parent.width * 0.42; height: 1.5; color: "#c9ced6" }
                                Rectangle { x: parent.width * 0.42; y: 22; width: 1.5; height: 8; color: "#c9ced6" }
                                Rectangle { x: parent.width * 0.425; y: 22; width: parent.width * 0.42; height: 1.5; color: "#8b9099" }
                                Rectangle { x: parent.width * 0.845; y: 22; width: parent.width * 0.155; height: 1.5; color: "#c9ced6" }
                                Rectangle {
                                    id: rcCar; y: 6; width: 30; height: 15; radius: 3; color: "#151518"; border.color: "#c9ced6"; border.width: 1.2
                                    x: rc.width - width
                                    Rectangle { x: 5; y: parent.height; width: 20; height: 2; color: "#c9ced6" }
                                }
                                SequentialAnimation {
                                    id: rcAnim
                                    NumberAnimation { target: rcCar; property: "x"; to: 0; duration: 1200; easing.type: Easing.InOutCubic }
                                    NumberAnimation { target: rcCar; property: "x"; to: rc.width - 30; duration: 1200; easing.type: Easing.InOutCubic }
                                    onStopped: movePage.coating = false
                                }
                            }
                            Seg { width: parent.width; height: 38; items: [["0,10", 0.1], ["0,15", 0.15], ["0,20", 0.2]]; value: win.thick; onPicked: function (v) { win.thick = v } }
                            KButton { width: parent.width; height: 44; kind: "pri"; text: "Schicht auftragen"; ok: !win.st.printing && !movePage.coating
                                onClicked: win.send({ cmd: "make_layer", mm: win.thick }, function (ok) {
                                    if (!ok) return
                                    movePage.coating = true; rcAnim.restart()
                                    var m = { print: win.moved.print + win.thick, reservoir: win.moved.reservoir - win.thick }; win.moved = m
                                }) }
                        }
                    }
                    Panel {
                        width: parent.width; height: 196
                        Column { anchors.fill: parent; anchors.margins: 12; spacing: 8
                            Lbl { text: "Laden & Entladen · Bauhöhe des Jobs" }
                            Row { spacing: 8; width: parent.width
                                KButton { width: 48; height: 44; text: "−"; size: 20; onClicked: win.jobH = Math.max(5, win.jobH - 5) }
                                Val { width: parent.width - 112; height: 44; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; text: win.jobH + " mm" }
                                KButton { width: 48; height: 44; text: "+"; size: 20; onClicked: win.jobH = Math.min(105, win.jobH + 5) } }
                            KButton { width: parent.width; height: 44; text: "Pulver laden · Vorrat −" + (win.jobH + 5) + " mm"; size: 13; ok: !win.st.printing
                                onClicked: win.ask("Pulver laden?", "Vorrat fährt " + (win.jobH + 5) + " mm nach unten (Bauhöhe " + win.jobH + " mm + 5 mm Puffer). Danach Pulver einfüllen und abziehen.", function () { win.jog("reservoir", win.jobH + 5) }) }
                            KButton { width: parent.width; height: 44; text: "Entladen · Bauplatte +" + win.jobH + " mm"; size: 13; ok: !win.st.printing
                                onClicked: win.ask("Kuchen entnehmen?", "Die Bauplattform fährt " + win.jobH + " mm nach oben und hebt den Pulverkuchen aus der Kammer. Nur bei abgekühlter Kammer öffnen.", function () { win.jog("print", -win.jobH) }) }
                        }
                    }
                }
            }

            // ======= Heizung =======
            Item {
                id: heatPage
                opacity: win.page === "heat" ? 1 : 0; visible: opacity > 0
                Behavior on opacity { NumberAnimation { duration: 180 } }
                y: 42; width: parent.width; height: parent.height - 42
                // Zwei Heizkreise wie im Kit: Pulverbett (Oberfläche, IR-Heizer + Pyrometer) und Kammer (Kammerheizung)
                Column {
                    id: heatPanel
                    width: parent.width * 0.58; height: parent.height; spacing: 8
                    Repeater {
                        model: [["Pulverbett (Oberfläche)", "surface", "surface_warmup", 180, "IR-Heizer · gemessen mit Pyrometer"],
                                ["Kammer", "chamber", "chamber_warmup", 150, "Kammerheizung · Thermistoren"]]
                        Panel {
                            id: hc
                            readonly property bool surf: modelData[1] === "surface"
                            readonly property int goal: surf ? win.targetSurf : win.target
                            function setGoal(v) {
                                v = Math.max(20, Math.min(modelData[3], v))
                                if (surf) win.targetSurf = v; else win.target = v
                                if (win.warm) win.send({ cmd: "target", which: modelData[2], celsius: v })
                            }
                            width: parent.width; height: (parent.height - 8) / 2
                            HeatRing {
                                x: 14; width: parent.height - 28; height: width; anchors.verticalCenter: parent.verticalCenter
                                value: win.st[modelData[1]] || 0; goal: hc.goal
                                Column {
                                    anchors.centerIn: parent
                                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: (win.st[modelData[1]] !== undefined ? Math.round(win.st[modelData[1]]) : "—") + "°"
                                        color: win.cInk; font.family: win.fontName; font.pixelSize: 40; font.weight: Font.Light; font.letterSpacing: -1.5 }
                                    Lbl { anchors.horizontalCenter: parent.horizontalCenter; text: "jetzt"; font.pixelSize: 11 }
                                }
                            }
                            Column {
                                x: parent.height + 2; y: 14; width: parent.width - parent.height - 16; spacing: 4
                                Text { text: modelData[0]; color: win.cInk; font.family: win.fontName; font.pixelSize: 16; font.weight: Font.Medium; width: parent.width; elide: Text.ElideRight }
                                Lbl { text: modelData[4]; font.pixelSize: 11; width: parent.width }
                                Item { width: 1; height: 6 }
                                Row {
                                    spacing: 8
                                    KButton { width: 48; height: 48; text: "−"; size: 20; onClicked: hc.setGoal(hc.goal - 5) }
                                    Column { width: parent.parent.width - 112; anchors.verticalCenter: parent.verticalCenter
                                        Lbl { anchors.horizontalCenter: parent.horizontalCenter; text: "Soll Vorheizen"; font.pixelSize: 11 }
                                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: hc.goal + " °C"; color: win.cHeat; font.family: win.fontName; font.pixelSize: 24; font.weight: Font.Light } }
                                    KButton { width: 48; height: 48; text: "+"; size: 20; onClicked: hc.setGoal(hc.goal + 5) }
                                }
                                Lbl { font.pixelSize: 11; width: parent.width; elide: Text.ElideRight
                                    text: "Im Druck: " + (win.st[hc.surf ? "target_surface_print" : "target_chamber_print"] !== undefined ? Math.round(win.st[hc.surf ? "target_surface_print" : "target_chamber_print"]) + " °C" : "—") + " · max. " + modelData[3] + " °C" }
                            }
                        }
                    }
                }
                Column {
                    x: heatPanel.width + 8; width: parent.width - heatPanel.width - 8; spacing: 8
                    KButton {
                        width: parent.width; kind: win.warm ? "normal" : "hot"; text: win.warm ? "Vorheizen stoppen" : "Vorheizen starten"
                        onClicked: {
                            var on = !win.warm
                            var go = function () { win.send({ cmd: "warmup", on: on }, function (ok) { if (ok) win.warm = on }) }
                            if (on) win.send({ cmd: "target", which: "surface_warmup", celsius: win.targetSurf }, function (ok) {
                                if (ok) win.send({ cmd: "target", which: "chamber_warmup", celsius: win.target }, function (ok2) { if (ok2) go() }) })
                            else go()
                        }
                    }
                    Panel {
                        id: trendPanel
                        width: parent.width; height: heatPage.height - 52 - 8 - 96 - 8
                        Lbl { x: 12; y: 10; text: "Verlauf · 30 min" }
                        Row {
                            anchors.right: parent.right; anchors.rightMargin: 12; y: 10; spacing: 10
                            Row { spacing: 4; Rectangle { width: 10; height: 3; radius: 1.5; color: win.cHeat; anchors.verticalCenter: parent.verticalCenter } Lbl { text: "Pulverbett" } }
                            Row { spacing: 4; Rectangle { width: 10; height: 3; radius: 1.5; color: "#d6dbe1"; anchors.verticalCenter: parent.verticalCenter } Lbl { text: "Kammer" } }
                        }
                        Canvas {
                            id: trend
                            x: 12; y: 32; width: parent.width - 24; height: parent.height - 44
                            property var data: win.tHist
                            onDataChanged: requestPaint()
                            onPaint: {
                                var g = getContext("2d"); g.reset()
                                var d = data, n = d.length
                                g.font = "11px " + win.fontName
                                if (n < 2) {
                                    g.fillStyle = "#6b7079"; g.fillText("Verlauf erscheint nach den ersten Messwerten", 0, height / 2)
                                    return
                                }
                                var lo = 1e9, hi = -1e9
                                for (var i = 0; i < n; i++) {
                                    lo = Math.min(lo, d[i].s, d[i].c, d[i].tc || 1e9); hi = Math.max(hi, d[i].s, d[i].c, d[i].ts || -1e9)
                                }
                                lo = Math.floor((lo - 5) / 10) * 10; hi = Math.ceil((hi + 5) / 10) * 10
                                var L = 30, W = width - L, H = height - 16
                                function X(k) { return L + W * k / 359 }
                                function Y(v) { return 8 + H * (1 - (v - lo) / (hi - lo)) }
                                g.strokeStyle = "rgba(255,255,255,0.06)"; g.lineWidth = 1; g.fillStyle = "#6b7079"
                                var step = (hi - lo) > 80 ? 40 : 20
                                for (var v = lo; v <= hi; v += step) {
                                    g.beginPath(); g.moveTo(L, Y(v)); g.lineTo(width, Y(v)); g.stroke()
                                    g.fillText(v + "°", 0, Y(v) + 4)
                                }
                                var off = 360 - n
                                function line(key, col, w, dash) {
                                    g.strokeStyle = col; g.lineWidth = w; g.setLineDash(dash || [])
                                    g.beginPath(); var started = false
                                    for (var i = 0; i < n; i++) {
                                        var v = d[i][key]; if (v === undefined || v === null || isNaN(v)) { started = false; continue }
                                        if (!started) { g.moveTo(X(off + i), Y(v)); started = true } else g.lineTo(X(off + i), Y(v))
                                    }
                                    g.stroke(); g.setLineDash([])
                                }
                                line("ts", "rgba(255,138,92,0.45)", 1, [4, 4])
                                line("tc", "rgba(214,219,225,0.35)", 1, [4, 4])
                                line("c", "#d6dbe1", 2)
                                line("s", "#ff8a5c", 2)
                            }
                        }
                    }
                    Panel {
                        width: parent.width; height: 96
                        Column {
                            anchors.fill: parent; anchors.margins: 12; spacing: 4
                            Lbl { text: "So heizt der Kit" }
                            Lbl { width: parent.width; wrapMode: Text.WordWrap; elide: Text.ElideNone; font.pixelSize: 11; maximumLineCount: 4
                                text: "Die IR-Heizer regelt der Kit selbst auf den Sollwert des Pulverbetts, die Kammerheizung auf den Kammer-Sollwert. Gestrichelt: Sollwerte." }
                        }
                    }
                }
            }

            // ======= Jobs =======
            // Bibliothek auf dem Pi: Jobs von Central werden beim Übertragen mitgespeichert und lassen sich hier erneut starten
            Item {
                id: jobsPage
                opacity: win.page === "jobs" ? 1 : 0; visible: opacity > 0
                Behavior on opacity { NumberAnimation { duration: 180 } }
                y: 42; width: parent.width; height: parent.height - 42
                property string selId: ""
                readonly property var sel: {
                    for (var i = 0; i < win.jobs.length; i++) if (win.jobs[i].id === selId) return win.jobs[i]
                    return win.jobs.length ? win.jobs[0] : null
                }
                readonly property int layers: sel && sel.layers ? sel.layers : 0
                readonly property var tr: win.st.transfer || null
                property int pick: 1
                onSelChanged: {
                    pick = Math.max(1, Math.round(layers * 0.5))
                    if (sel && sel.height_mm > 0 && !win.st.printing) win.jobH = Math.round(sel.height_mm)   // für Pulver laden / Entladen
                }
                onVisibleChanged: if (visible) win.loadJobs()
                function fmtDate(t) { var d = new Date(t * 1000); return ("0" + d.getDate()).slice(-2) + "." + ("0" + (d.getMonth() + 1)).slice(-2) + ". " + d.getHours() + ":" + ("0" + d.getMinutes()).slice(-2) }

                Panel {
                    id: prevPanel
                    width: parent.height; height: parent.height
                    LayerView {
                        id: prevView
                        x: 12; y: 12; width: parent.width - 24; height: parent.height - 24 - 48
                        job: jobsPage.sel
                        layerNo: jobsPage.pick
                        hint: !jobsPage.sel ? "Noch keine Jobs. Druckjobs, die Central über den Pi schickt, landen automatisch hier."
                              : jobsPage.sel.error ? "Keine Vorschau: " + jobsPage.sel.error
                              : !jobsPage.sel.layers ? "Job wird ausgewertet …" : "Lade Schicht …"
                    }
                    Text { x: 22; y: 20; visible: jobsPage.layers > 0; color: win.cMut; font.family: win.fontName; font.pixelSize: 12
                        text: "Schicht " + jobsPage.pick + " / " + jobsPage.layers + " · Z " + Api.de(jobsPage.pick * (jobsPage.sel ? jobsPage.sel.layer_mm : 0), 2) + " mm" }
                    // Schichtregler
                    Item {
                        id: slider
                        x: 14; y: parent.height - 12 - 40; width: parent.width - 28; height: 40
                        opacity: jobsPage.layers > 0 ? 1 : 0.3
                        Rectangle { y: 18; width: parent.width; height: 4; radius: 2; color: "#2a2a30" }
                        Rectangle { y: 18; width: knob.x + 14; height: 4; radius: 2; color: win.cBlue }
                        Rectangle {
                            id: knob; y: 6; width: 28; height: 28; radius: 14; color: "#f2f3f5"
                            x: jobsPage.layers > 1 ? (jobsPage.pick - 1) / (jobsPage.layers - 1) * (slider.width - 28) : 0
                        }
                        MouseArea {
                            anchors.fill: parent; enabled: jobsPage.layers > 0
                            function setFrom(mx) { jobsPage.pick = Math.round(1 + Math.max(0, Math.min(1, (mx - 14) / (slider.width - 28))) * (jobsPage.layers - 1)) }
                            onPressed: function (m) { setFrom(m.x) }
                            onPositionChanged: function (m) { setFrom(m.x) }
                        }
                    }
                }
                Panel {
                    id: listPanel
                    x: prevPanel.width + 8; width: parent.width - prevPanel.width - 8; height: parent.height
                    Lbl { x: 16; y: 14; text: "Jobs auf dem Pi" }
                    ListView {
                        id: jobList
                        x: 8; y: 34; width: parent.width - 16; height: parent.height - 34 - detail.height - 12
                        clip: true; spacing: 4; model: win.jobs
                        delegate: Rectangle {
                            readonly property bool act: !!jobsPage.sel && jobsPage.sel.id === modelData.id
                            width: jobList.width; height: 50; radius: 12
                            color: act ? "#1d3a44" : "#1c1c20"
                            border.color: act ? win.cBlue2 : "transparent"; border.width: 1
                            Column { x: 12; y: 7; width: parent.width - 24; spacing: 2
                                Text { width: parent.width; elide: Text.ElideRight; text: modelData.name; color: win.cInk; font.family: win.fontName; font.pixelSize: 14 }
                                Text { width: parent.width; elide: Text.ElideRight; color: win.cMut; font.family: win.fontName; font.pixelSize: 11
                                    text: (modelData.layers ? modelData.layers + " Schichten · " + Api.de(modelData.height_mm) + " mm" : (modelData.error ? "ohne Vorschau" : "wird ausgewertet …"))
                                          + (modelData.starts ? " · " + modelData.starts + "× gedruckt" : "") }
                            }
                            MouseArea { anchors.fill: parent; onClicked: jobsPage.selId = modelData.id }
                        }
                        Text { visible: win.jobs.length === 0; anchors.centerIn: parent; width: parent.width - 20; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                            text: "Leer"; color: win.cMut; font.family: win.fontName; font.pixelSize: 12 }
                    }
                    Column {
                        id: detail
                        x: 16; y: parent.height - height - 14; width: parent.width - 32; spacing: 8
                        Item { width: parent.width; height: 32
                            Text { anchors.verticalCenter: parent.verticalCenter; width: parent.width - 116; wrapMode: Text.WordWrap; maximumLineCount: 2
                                text: "Jobs von Central sofort drucken"; color: win.cInk; font.family: win.fontName; font.pixelSize: 12 }
                            Seg { anchors.right: parent.right; width: 108; height: 32; items: [["Aus", false], ["An", true]]; value: win.autostart
                                onPicked: function (v) {
                                    if (v === win.autostart) return
                                    win.autostart = v
                                    win.send({ cmd: "job_autostart", on: v }, function (ok) {
                                        win.loadJobs()
                                        if (ok) toast.show(v ? "Jobs von Central starten sofort (wie bisher)" : "Jobs von Central werden nur gespeichert – Start hier am Display")
                                    })
                                } }
                        }
                        // Übertragung zum Kit läuft
                        Column { width: parent.width; spacing: 6; visible: !!jobsPage.tr
                            Lbl { width: parent.width; text: jobsPage.tr ? jobsPage.tr.phase + (jobsPage.tr.total ? " · " + Math.floor(100 * jobsPage.tr.sent / jobsPage.tr.total) + " %" : "") : "" }
                            Rectangle { width: parent.width; height: 6; radius: 3; color: "#2a2a30"
                                Rectangle { height: parent.height; radius: 3; color: win.cBlue; width: jobsPage.tr && jobsPage.tr.total ? parent.width * jobsPage.tr.sent / jobsPage.tr.total : 0 } }
                        }
                        Row { width: parent.width; spacing: 8; visible: !jobsPage.tr
                            KButton { width: 52; height: 52; text: "✕"; ok: !!jobsPage.sel
                                onClicked: win.ask("Job löschen?", "„" + jobsPage.sel.name + "“ wird vom Pi gelöscht.", function () {
                                    win.send({ cmd: "job_delete", id: jobsPage.sel.id }, function () { jobsPage.selId = ""; win.loadJobs() }) }) }
                            KButton { width: parent.width - 60; height: 52; kind: "pri"; text: "Drucken"
                                ok: !!jobsPage.sel && win.st.connected && !win.st.printing
                                onClicked: win.ask("„" + jobsPage.sel.name + "“ drucken?",
                                    "Pulver geladen" + (jobsPage.sel.height_mm ? " (Vorrat mind. " + Math.round(jobsPage.sel.height_mm + 5) + " mm)" : "") + ", Haube geschlossen? Der Pi schaltet das Vorheizen ein, überträgt den Job zum Kit und startet ihn.",
                                    function () { win.send({ cmd: "job_start", id: jobsPage.sel.id }) }) }
                        }
                    }
                }
            }

            // ======= Kalibrieren =======
            // Wie das Central-Fenster „Calibrate“: Muster/Mittelpunkt zeigen, Referenzfahrt, digitale Skalierung (max. ±5 %)
            Item {
                id: calPage
                opacity: win.page === "cal" ? 1 : 0; visible: opacity > 0
                Behavior on opacity { NumberAnimation { duration: 180 } }
                y: 42; width: parent.width; height: parent.height - 42
                readonly property bool locked: !win.st.connected || !!win.st.printing
                function step(k, d) {
                    var v = Math.round((win.scEdit[k] + d) * 100) / 100
                    v = Math.max(-5, Math.min(5, v))
                    var e = { x: win.scEdit.x, y: win.scEdit.y, z: win.scEdit.z }; e[k] = v
                    win.scEdit = e; win.scDirty = true
                }
                Panel {
                    id: scPanel
                    width: parent.width - 276; height: parent.height
                    Column {
                        anchors.fill: parent; anchors.margins: 14; spacing: 8
                        Item { width: parent.width; height: 16
                            Lbl { text: "Digitale Skalierung · max. ±5 %" }
                            Lbl { anchors.right: parent.right; text: win.scDirty ? "nicht gesendet" : (win.st.scaling ? "wie im Kit" : "—"); color: win.scDirty ? win.cHeat : win.cMut } }
                        Repeater {
                            model: [["X", "x"], ["Y", "y"], ["Z", "z"]]
                            Item {
                                width: parent.width; height: 58
                                Text { y: 8; text: modelData[0]; color: win.cInk; font.family: win.fontName; font.pixelSize: 22; font.weight: Font.Medium }
                                KButton { x: 36; y: 4; width: 52; height: 48; text: "−"; size: 20; ok: !calPage.locked; onClicked: calPage.step(modelData[1], -0.05) }
                                Column {
                                    x: 96; width: parent.width - 96 - 60; y: 2
                                    Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: win.pct(win.scEdit[modelData[1]])
                                        color: win.cInk; font.family: win.fontName; font.pixelSize: 26; font.weight: Font.Light }
                                    Lbl { width: parent.width; horizontalAlignment: Text.AlignHCenter; font.pixelSize: 11; text: "Kit: " + win.pct(win.scKit(modelData[1])) }
                                }
                                KButton { x: parent.width - 52; y: 4; width: 52; height: 48; text: "+"; size: 20; ok: !calPage.locked; onClicked: calPage.step(modelData[1], 0.05) }
                            }
                        }
                        Lbl { text: "Z-Skalierung möglichst gering halten."; font.pixelSize: 11 }
                        Row {
                            spacing: 8; width: parent.width
                            KButton { width: (parent.width - 16) / 3; height: 46; size: 13; text: "Berechnen"; ok: !calPage.locked; onClicked: calcOvl.open() }
                            KButton { width: (parent.width - 16) / 3; height: 46; size: 13; text: "Kit-Werte"; ok: win.scDirty
                                onClicked: { win.scDirty = false; win.scEdit = { x: win.scKit("x"), y: win.scKit("y"), z: win.scKit("z") } } }
                            KButton { width: (parent.width - 16) / 3; height: 46; size: 13; text: "Werkswerte"; ok: !calPage.locked && !!win.st.factory
                                onClicked: { var f = win.st.factory.scaling; win.scEdit = { x: f.x, y: f.y, z: f.z }; win.scDirty = true
                                    toast.show("Werkswerte vom " + win.st.factory.saved + " geladen – noch nicht gesendet") } }
                        }
                        KButton {
                            width: parent.width; kind: "pri"; text: "An Kit senden"; ok: !calPage.locked && win.scDirty
                            onClicked: win.ask("Skalierung senden?",
                                "X " + win.pct(win.scEdit.x) + " · Y " + win.pct(win.scEdit.y) + " · Z " + win.pct(win.scEdit.z) + "\nWirkt auf alle folgenden Drucke.",
                                function () { win.send({ cmd: "scaling", x: win.scEdit.x, y: win.scEdit.y, z: win.scEdit.z }, function (ok) { if (ok) { win.scDirty = false; toast.show("Skalierung im Kit gespeichert") } }) })
                        }
                    }
                }
                Column {
                    x: scPanel.width + 8; width: 268; spacing: 8
                    Panel {
                        width: parent.width; height: 214
                        Column { anchors.fill: parent; anchors.margins: 12; spacing: 8
                            Lbl { text: "Kalibriermuster" }
                            KButton { width: parent.width; height: 46; text: "Muster anzeigen"; ok: !calPage.locked; onClicked: win.send({ cmd: "pattern", name: "pattern" }) }
                            KButton { width: parent.width; height: 46; text: "Mittelpunkt anzeigen"; ok: !calPage.locked; onClicked: win.send({ cmd: "pattern", name: "center" }) }
                            KButton { width: parent.width; height: 46; text: "Anzeige aus"; ok: !!win.st.connected; onClicked: win.send({ cmd: "pattern", name: "off" }) }
                        }
                    }
                    Panel {
                        width: parent.width; height: 170
                        Column { anchors.fill: parent; anchors.margins: 12; spacing: 8
                            Lbl { text: "Referenzfahrt" }
                            Lbl { width: parent.width; wrapMode: Text.WordWrap; elide: Text.ElideNone; font.pixelSize: 12
                                text: "Fährt Bauplattform, Vorrat und Beschichter auf ihre Ausgangsposition – wie „Home all axes“ in Central." }
                            KButton { width: parent.width; height: 46; text: "Referenzfahrt starten"; ok: !calPage.locked
                                onClicked: win.ask("Referenzfahrt?", "Alle Achsen fahren auf ihre Ausgangsposition. Bauraum frei?", function () {
                                    win.send({ cmd: "pattern", name: "home", confirmed: true }, function (ok) { if (ok) win.moved = { print: 0, reservoir: 0 } }) }) }
                        }
                    }
                }

                // Berechnen aus dem vermessenen Kalibrierdruck (Formel wie Central)
                Rectangle {
                    id: calcOvl
                    parent: root; anchors.fill: parent; color: "#cc000000"; visible: false; z: 20
                    property var soll: ({ x: 50, y: 50, z: 50 })
                    property var ist: ({ x: 50, y: 50, z: 50 })
                    function open() { visible = true }
                    function bump(which, k, d) {
                        var o = which === "soll" ? soll : ist
                        var n = { x: o.x, y: o.y, z: o.z }; n[k] = Math.max(1, Math.round((o[k] + d) * 100) / 100)
                        if (which === "soll") soll = n; else ist = n
                    }
                    MouseArea { anchors.fill: parent }
                    Panel {
                        anchors.centerIn: parent; width: 640; height: 330; color: "#1b1b1f"
                        Column {
                            anchors.fill: parent; anchors.margins: 16; spacing: 10
                            Text { text: "Aus Messung berechnen"; color: win.cInk; font.family: win.fontName; font.pixelSize: 20; font.weight: Font.Medium }
                            Lbl { text: "Kalibrierdruck vermessen. Berücksichtigt die im Kit eingestellte Skalierung." }
                            Repeater {
                                model: [["X", "x"], ["Y", "y"], ["Z", "z"]]
                                Row {
                                    spacing: 6; height: 44
                                    Text { width: 24; anchors.verticalCenter: parent.verticalCenter; text: modelData[0]; color: win.cInk; font.family: win.fontName; font.pixelSize: 18; font.weight: Font.Medium }
                                    Lbl { width: 30; anchors.verticalCenter: parent.verticalCenter; text: "Soll" }
                                    KButton { width: 40; height: 44; text: "−"; onClicked: calcOvl.bump("soll", modelData[1], -1) }
                                    Text { width: 84; anchors.verticalCenter: parent.verticalCenter; horizontalAlignment: Text.AlignHCenter; text: Api.de(calcOvl.soll[modelData[1]].toFixed(2)) + " mm"; color: win.cInk; font.family: win.fontName; font.pixelSize: 15 }
                                    KButton { width: 40; height: 44; text: "+"; onClicked: calcOvl.bump("soll", modelData[1], 1) }
                                    Item { width: 10; height: 1 }
                                    Lbl { width: 22; anchors.verticalCenter: parent.verticalCenter; text: "Ist" }
                                    KButton { width: 50; height: 44; size: 12; text: "−0,1"; onClicked: calcOvl.bump("ist", modelData[1], -0.1) }
                                    KButton { width: 54; height: 44; size: 12; text: "−0,01"; onClicked: calcOvl.bump("ist", modelData[1], -0.01) }
                                    Text { width: 84; anchors.verticalCenter: parent.verticalCenter; horizontalAlignment: Text.AlignHCenter; text: Api.de(calcOvl.ist[modelData[1]].toFixed(2)) + " mm"; color: win.cInk; font.family: win.fontName; font.pixelSize: 15 }
                                    KButton { width: 54; height: 44; size: 12; text: "+0,01"; onClicked: calcOvl.bump("ist", modelData[1], 0.01) }
                                    KButton { width: 50; height: 44; size: 12; text: "+0,1"; onClicked: calcOvl.bump("ist", modelData[1], 0.1) }
                                }
                            }
                            Row {
                                spacing: 8; width: parent.width
                                KButton { width: (parent.width - 8) / 2; height: 48; text: "Abbrechen"; onClicked: calcOvl.visible = false }
                                KButton { width: (parent.width - 8) / 2; height: 48; kind: "pri"; text: "Übernehmen"
                                    onClicked: {
                                        var e = {}, keys = ["x", "y", "z"]
                                        for (var i = 0; i < 3; i++) {
                                            var k = keys[i], f = 1 + win.scKit(k) / 100
                                            var p = (f * calcOvl.soll[k] / calcOvl.ist[k] - 1) * 100
                                            if (Math.abs(p) > 5.0005) { toast.show(k.toUpperCase() + ": mehr als ±5 % – bitte mechanisch nachjustieren", true); return }
                                            e[k] = Math.round(p * 100) / 100
                                        }
                                        win.scEdit = e; win.scDirty = true; calcOvl.visible = false
                                        toast.show("Neue Werte übernommen – mit „An Kit senden“ übertragen")
                                    } }
                            }
                        }
                    }
                }
            }

            // ======= Material & Parameter =======
            Item {
                id: parPage
                opacity: win.page === "params" ? 1 : 0; visible: opacity > 0
                Behavior on opacity { NumberAnimation { duration: 180 } }
                y: 42; width: parent.width; height: parent.height - 42
                readonly property bool locked: !win.st.connected || !!win.st.printing
                function set(k, v, lo, hi) {
                    var e = { sw: win.pEdit.sw, cw: win.pEdit.cw, sp: win.pEdit.sp, cp: win.pEdit.cp, laser: win.pEdit.laser }
                    e[k] = Math.max(lo, Math.min(hi, Math.round(v))); win.pEdit = e; win.pDirty = true
                }
                Panel {
                    id: tPanel
                    width: parent.width - 276; height: parent.height
                    Column {
                        anchors.fill: parent; anchors.margins: 14; spacing: 8
                        Item { width: parent.width; height: 16
                            Lbl { text: "Material" }
                            Lbl { anchors.right: parent.right; text: win.kitMaterial ? "im Kit eingestellt: " + win.kitMaterial : "" } }
                        Seg {
                            width: parent.width; height: 42
                            items: [["PA12", "PA12"], ["TPE", "TPE"], ["Eigene", "custom"]]
                            value: win.materialOf(win.pEdit)
                            onPicked: function (v) {
                                if (v === "custom" || parPage.locked) return
                                var t = win.materials[v]
                                win.pEdit = { sw: t.sw, cw: t.cw, sp: t.sp, cp: t.cp, laser: win.pEdit.laser }; win.pDirty = true
                            }
                        }
                        Item { width: 1; height: 2 }
                        Repeater {
                            model: [["Aufwärmen · Pulverbett", "sw", 180], ["Aufwärmen · Kammer", "cw", 150],
                                    ["Druck · Pulverbett", "sp", 180], ["Druck · Kammer", "cp", 150]]
                            Item {
                                width: parent.width; height: 52
                                Column { y: 6
                                    Lbl { text: modelData[0] }
                                    Lbl { font.pixelSize: 11; text: "Kit: " + (win.pKit()[modelData[1]] !== undefined ? Math.round(win.pKit()[modelData[1]]) + " °C" : "—") + " · max. " + modelData[2] + " °C" } }
                                KButton { x: parent.width - 196; y: 2; width: 48; height: 48; text: "−"; size: 20; ok: !parPage.locked; onClicked: parPage.set(modelData[1], win.pEdit[modelData[1]] - 1, 0, modelData[2]) }
                                Text { x: parent.width - 144; width: 92; height: 52; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                    text: win.pEdit[modelData[1]] + " °C"; color: win.cHeat; font.family: win.fontName; font.pixelSize: 24; font.weight: Font.Light }
                                KButton { x: parent.width - 48; y: 2; width: 48; height: 48; text: "+"; size: 20; ok: !parPage.locked; onClicked: parPage.set(modelData[1], win.pEdit[modelData[1]] + 1, 0, modelData[2]) }
                            }
                        }
                    }
                }
                Column {
                    x: tPanel.width + 8; width: 268; spacing: 8
                    Panel {
                        width: parent.width; height: 168
                        Column { anchors.fill: parent; anchors.margins: 12; spacing: 6
                            Lbl { text: "Lasergeschwindigkeit" }
                            Row { spacing: 4
                                Text { text: win.pEdit.laser; color: win.cInk; font.family: win.fontName; font.pixelSize: 38; font.weight: Font.Light; font.letterSpacing: -1.2 }
                                Text { y: 20; text: "mm/s"; color: win.cMut; font.family: win.fontName; font.pixelSize: 14 } }
                            Lbl { font.pixelSize: 11; text: "Kit: " + (win.st.laser_speed !== undefined ? Math.round(win.st.laser_speed) + " mm/s" : "—") + " · Central-Vorgabe 650" }
                            Row { spacing: 6
                                KButton { width: 59; height: 44; size: 12; text: "−50"; ok: !parPage.locked; onClicked: parPage.set("laser", win.pEdit.laser - 50, 1, 1000) }
                                KButton { width: 59; height: 44; size: 12; text: "−10"; ok: !parPage.locked; onClicked: parPage.set("laser", win.pEdit.laser - 10, 1, 1000) }
                                KButton { width: 59; height: 44; size: 12; text: "+10"; ok: !parPage.locked; onClicked: parPage.set("laser", win.pEdit.laser + 10, 1, 1000) }
                                KButton { width: 59; height: 44; size: 12; text: "+50"; ok: !parPage.locked; onClicked: parPage.set("laser", win.pEdit.laser + 50, 1, 1000) } }
                        }
                    }
                    Panel {
                        width: parent.width; height: parent.parent.height - 168 - 8
                        Column { anchors.fill: parent; anchors.margins: 12; spacing: 8
                            Lbl { text: win.pDirty ? "Änderungen noch nicht gesendet" : "Werte wie im Kit"; color: win.pDirty ? win.cHeat : win.cMut }
                            Row { spacing: 8
                                KButton { width: 118; height: 46; size: 13; text: "Kit-Werte"; ok: win.pDirty; onClicked: { win.pDirty = false; win.pEdit = win.pKit() } }
                                KButton { width: 118; height: 46; size: 13; text: "Werkswerte"; ok: !parPage.locked && !!(win.st.factory && win.st.factory.live)
                                    onClicked: { var f = win.st.factory.live
                                        win.pEdit = { sw: Math.round(f.surface_warmup), cw: Math.round(f.chamber_warmup), sp: Math.round(f.surface_print), cp: Math.round(f.chamber_print), laser: Math.round(f.laser_speed) }
                                        win.pDirty = true; toast.show("Werkswerte vom " + win.st.factory.saved + " geladen – noch nicht gesendet") } } }
                            KButton { width: parent.width; height: 44; size: 13; text: "Heizstrahler (Experte) …"; ok: !parPage.locked; onClicked: lampOvl.visible = true }
                            Item { width: 1; height: Math.max(0, parent.height - 16 - 46 - 44 - 52 - 32) }
                            KButton {
                                width: parent.width; kind: "pri"; text: "An Kit senden"; ok: !parPage.locked && win.pDirty
                                onClicked: {
                                    var e = win.pEdit, newMat = win.materialOf(e), old = win.kitMaterial
                                    var txt = "Aufwärmen " + e.sw + " / " + e.cw + " °C · Druck " + e.sp + " / " + e.cp + " °C · Laser " + e.laser + " mm/s"
                                    if (old === "PA12" && newMat === "TPE")
                                        txt = "Umstellung auf TPE: Im Kit darf kein PA12 mehr sein. Laut Sintratec ist der Weg zurück zu PA12 danach nicht ohne Weiteres möglich.\n" + txt
                                    else if (old === "TPE" && newMat === "PA12")
                                        txt = "Umstellung auf PA12: Kein TPE mehr im Kit. Laut Sintratec müssen danach alle Pulverdichtungen gegen neue getauscht werden.\n" + txt
                                    win.ask("Parameter senden?", txt, function () {
                                        win.send({ cmd: "targets", surface_warmup: e.sw, chamber_warmup: e.cw, surface_print: e.sp, chamber_print: e.cp }, function (ok) {
                                            if (!ok) return
                                            win.send({ cmd: "laser_speed", mm_s: e.laser }, function (ok2) { if (ok2) { win.pDirty = false; toast.show("Parameter im Kit gespeichert") } })
                                        })
                                    })
                                }
                            }
                        }
                    }
                }

                // Experten-Dialog: Heizstrahler-Leistung. Central stellt sie beim Kit nie ein, die Firmware speichert sie
                // dauerhaft und meldet sie nicht zurück – angezeigt wird, was der Pi zuletzt gesendet hat.
                Rectangle {
                    id: lampOvl
                    parent: root; anchors.fill: parent; color: "#cc000000"; visible: false; z: 20
                    MouseArea { anchors.fill: parent }
                    Panel {
                        anchors.centerIn: parent; width: 560; height: 340; color: "#1b1b1f"
                        Column {
                            anchors.fill: parent; anchors.margins: 16; spacing: 10
                            Text { text: "Heizstrahler (Experte)"; color: win.cInk; font.family: win.fontName; font.pixelSize: 20; font.weight: Font.Medium }
                            Lbl { width: parent.width; wrapMode: Text.WordWrap; elide: Text.ElideNone; font.pixelSize: 12
                                text: "Wirkt sofort und bleibt im Kit gespeichert. Der Kit kann den Wert nicht zurückmelden – „original“ heißt: vom Pi nie verändert. Tipp: eine Lampe so einstellen, dass sie gleich hell leuchtet wie eine noch originale." }
                            Repeater {
                                model: [["Links", "left"], ["Rechts", "right"], ["Vorne", "front"]]
                                Item {
                                    width: parent.width; height: 52
                                    readonly property var cur: win.st.lamps ? win.st.lamps[modelData[1]] : undefined
                                    function sendPct(v) {
                                        v = Math.max(10, Math.min(100, v))
                                        win.send({ cmd: "lamp", which: modelData[1], percent: v, expert: true })
                                    }
                                    Text { y: 14; width: 80; text: modelData[0]; color: win.cInk; font.family: win.fontName; font.pixelSize: 16 }
                                    KButton { x: 90; y: 2; width: 56; height: 48; size: 13; text: "−5"; onClicked: parent.sendPct((parent.cur === undefined ? 100 : parent.cur) - 5) }
                                    KButton { x: 152; y: 2; width: 56; height: 48; size: 13; text: "−1"; onClicked: parent.sendPct((parent.cur === undefined ? 100 : parent.cur) - 1) }
                                    Text { x: 214; width: 100; height: 52; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                        text: parent.cur === undefined ? "original" : parent.cur + " %"; color: win.cHeat; font.family: win.fontName; font.pixelSize: 20; font.weight: Font.Light }
                                    KButton { x: 320; y: 2; width: 56; height: 48; size: 13; text: "+1"; onClicked: parent.sendPct((parent.cur === undefined ? 100 : parent.cur) + 1) }
                                    KButton { x: 382; y: 2; width: 56; height: 48; size: 13; text: "+5"; onClicked: parent.sendPct((parent.cur === undefined ? 100 : parent.cur) + 5) }
                                }
                            }
                            KButton { width: parent.width; height: 48; text: "Schließen"; onClicked: lampOvl.visible = false }
                        }
                    }
                }
            }

            // ======= System =======
            Item {
                opacity: win.page === "sys" ? 1 : 0; visible: opacity > 0
                Behavior on opacity { NumberAnimation { duration: 180 } }
                y: 42; width: parent.width; height: parent.height - 42
                Panel {
                    id: msgPanel
                    width: (parent.width - 166) / 2; height: parent.height - 60; clip: true
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
                            // Auf Wunsch ausgeblendete Warnungen (z. B. 81) – nur zur Info, nicht oben im Kopf
                            Lbl { visible: (win.st.hidden_warnings || []).length > 0; width: msgCol.width; wrapMode: Text.WordWrap; elide: Text.ElideNone; font.pixelSize: 11
                                text: "Ausgeblendet: " + (win.st.hidden_warnings || []).map(function (m) { return m.code + " " + m.title }).join(", ") }
                        }
                    }
                }
                Row {
                    y: msgPanel.height + 8; spacing: 8
                    KButton { width: (msgPanel.width - 8) / 2; height: 52; size: 13; text: "Kalibrieren"; onClicked: win.page = "cal" }
                    KButton { width: (msgPanel.width - 8) / 2; height: 52; size: 13; text: "Parameter"; onClicked: win.page = "params" }
                }
                Panel {
                    id: infoPanel
                    x: msgPanel.width + 8; width: msgPanel.width; height: parent.height
                    Column {
                        anchors.fill: parent; anchors.margins: 12; spacing: 0
                        Repeater {
                            model: [["Modell", win.st.model], ["Firmware", win.st.firmware], ["Protokoll", win.st.protocol],
                                    ["Geräte-ID", win.st.uid ? win.st.uid.slice(0, 12) + "…" : "—"], ["Zustand", win.st.state_name || win.st.state],
                                    ["WLAN", win.wifi.current ? win.wifi.current : "—"], ["Central", win.st.central ? "verbunden (" + win.st.central_peer + ")" : "—"], ["IP-Adresse", win.wifi.ip || "—"],
                                    
                                    ["Hinweis", win.st.message || "—"]]
                            Item {
                                width: parent.width; height: 34
                                Lbl { anchors.verticalCenter: parent.verticalCenter; text: modelData[0] }
                                Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 90; horizontalAlignment: Text.AlignRight; elide: Text.ElideRight
                                    text: modelData[1] === undefined || modelData[1] === null ? "—" : String(modelData[1]); color: win.cInk; font.family: win.fontName; font.pixelSize: 13 }
                                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: win.cLine }
                                // Antippen zeigt den vollen Text (z. B. lange USB-Fehlermeldungen)
                                MouseArea { anchors.fill: parent; onClicked: if (modelData[1]) toast.show(modelData[0] + ": " + String(modelData[1])) }
                            }
                        }
                    }
                }
                Column {
                    x: infoPanel.x + infoPanel.width + 8; width: 150; height: parent.height; spacing: 6
                    KButton { width: parent.width; height: 44; kind: "pri"; text: "WLAN"; onClicked: wifiOvl.open() }
                    KButton { width: parent.width; height: 44; kind: win.upd.available ? "acc" : "normal"; text: win.upd.running ? "Update läuft …" : (win.upd.available ? "Update verfügbar" : "Software"); onClicked: updOvl.open() }
                    Lbl { text: "Bedienung vom PC" }
                    Seg {
                        width: parent.width; height: 32
                        items: [["Aus", false], ["An", true]]
                        value: win.st.remote_control === true
                        onPicked: function (v) {
                            if (v === (win.st.remote_control === true)) return
                            win.send({ cmd: "remote_control", on: v }, function (ok) {
                                if (ok) toast.show(v ? "Kit Control am PC darf heizen, fahren und beschichten – nicht während eines Drucks"
                                                     : "Bedienung vom PC aus – nur noch hier am Display")
                            })
                        }
                    }
                    Lbl { text: "PC-Verbindung für Central" }
                    Seg {
                        width: parent.width; height: 32
                        items: [["WLAN", "wlan"], ["USB", "usb"]]
                        value: win.st.pc_link || "wlan"
                        onPicked: function (v) {
                            if (v === (win.st.pc_link || "wlan")) return
                            win.ask(v === "usb" ? "PC über USB verbinden?" : "PC über WLAN verbinden?",
                                    v === "usb" ? "Der USB-C-Anschluss des Pi wird zum Netzwerkanschluss für den PC. Den Pi dann über die GPIO-Pins oder ein Netzteil mit Datendurchleitung versorgen – ein PC-Anschluss liefert nicht genug Strom."
                                                : "Central verbindet sich wieder über das WLAN mit dem Pi.",
                                    function () { win.send({ cmd: "pc_link", mode: v }) })
                        }
                    }
                    Lbl { text: "Demo ohne Kit" }
                    Seg {
                        width: parent.width; height: 32
                        items: [["Aus", false], ["An", true]]
                        value: win.st.demo === true
                        onPicked: function (v) {
                            if (v === (win.st.demo === true)) return
                            win.send({ cmd: "demo", on: v })
                            toast.show(v ? "Demo-Modus an: simulierter Kit, nichts wird an echte Hardware gesendet" : "Demo-Modus aus: suche Kit über USB")
                        }
                    }
                    Item { width: 1; height: Math.max(0, parent.height - 4 * 44 - 3 * (16 + 32) - 10 * 6) }
                    KButton { width: parent.width; height: 44; text: "Neustart"; onClicked: win.ask("Neu starten?", "Der Kit Controller startet neu. Ein laufender Druck läuft auf dem Kit weiter.", function () { win.send({ cmd: "reboot" }) }) }
                    KButton { width: parent.width; height: 44; kind: "red"; text: "Ausschalten"; ok: !win.st.printing && !win.st.transfer; onClicked: win.ask("Ausschalten?", "Danach den Strom erst trennen, wenn das Display schwarz ist.", function () { win.send({ cmd: "poweroff" }) }) }
                }
            }
        }

        // ---------- Kein Kit ----------
        // Deckt nur die Seiten ab, die den Kit brauchen. Navigation, System und WLAN bleiben bedienbar.
        Rectangle {
            x: main.x; y: main.y + 42; width: main.width; height: main.height - 42
            radius: 16; color: "#e60c0e11"
            visible: !win.st.connected && win.page !== "sys"
            MouseArea { anchors.fill: parent }
            Column {
                anchors.centerIn: parent; width: 440; spacing: 10
                Val { anchors.horizontalCenter: parent.horizontalCenter; font.pixelSize: 20; text: win.kitdUp ? "Kein Kit verbunden" : "Kit Control startet …" }
                Lbl { width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap; elide: Text.ElideNone; font.pixelSize: 13
                    text: "Kit per USB an den Pi anschließen und einschalten. Central am PC muss dabei getrennt sein." }
                Lbl { width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap; elide: Text.ElideNone; font.pixelSize: 11; color: "#6f7888"
                    visible: !!win.st.message; text: win.st.message || "" }
                Row { anchors.horizontalCenter: parent.horizontalCenter; spacing: 8; topPadding: 4
                    KButton { width: 150; height: 44; text: "WLAN"; onClicked: wifiOvl.open() }
                    KButton { width: 150; height: 44; text: "System"; onClicked: win.page = "sys" }
                    KButton { width: 150; height: 44; kind: "pri"; text: "Demo starten"; visible: win.kitdUp; onClicked: { win.send({ cmd: "demo", on: true }); toast.show("Demo-Modus an: simulierter Kit") } } }
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
                        color: modelData.active ? "#1f2fa6cc" : (dm.pressed ? "#0fffffff" : "transparent")
                        border.color: modelData.active ? "#992fa6cc" : "transparent"
                        Row { x: 14; anchors.verticalCenter: parent.verticalCenter; spacing: 3
                            Repeater { model: 4
                                Rectangle { width: 3; height: 4 + index * 4; radius: 1; anchors.bottom: parent.bottom
                                    color: index < (modelData.signal > 70 ? 4 : modelData.signal > 50 ? 3 : modelData.signal > 30 ? 2 : 1) ? win.cInk : "#2effffff" } } }
                        Text { x: 46; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 170; elide: Text.ElideRight; text: modelData.ssid; color: win.cInk; font.family: win.fontName; font.pixelSize: 15 }
                        Text { anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter
                            text: (modelData.active ? "verbunden  " : "") + (modelData.secure ? "gesichert" : "offen"); color: "#8fd3ea"; font.family: win.fontName; font.pixelSize: 12; font.weight: Font.DemiBold }
                        MouseArea { id: dm; anchors.fill: parent; onClicked: wifiOvl.pick(modelData) }
                    }
                }
                Lbl { visible: wl.count === 0; anchors.centerIn: parent; text: win.wifi.available === false ? "WLAN nicht verfügbar" : "Suche Netze …" }
            }
            Column {
                visible: wifiOvl.askPw
                x: 10; width: parent.width - 20; spacing: 6
                anchors.bottom: parent.bottom; anchors.bottomMargin: 10
                Row {
                    spacing: 8; width: parent.width
                    Rectangle {
                        width: parent.width - 236; height: 46; radius: 12; color: "#66000000"; border.color: "#802fa6cc"; clip: true
                        Text { x: 14; anchors.verticalCenter: parent.verticalCenter; text: (wifiOvl.showPw ? wifiOvl.pw : "•".repeat(wifiOvl.pw.length)) + "|"; color: win.cInk; font.family: "monospace"; font.pixelSize: 18 }
                    }
                    KButton { width: 70; height: 46; text: wifiOvl.showPw ? "•••" : "abc"; onClicked: wifiOvl.showPw = !wifiOvl.showPw }
                    KButton { width: 150; height: 46; kind: "pri"; ok: !wifiOvl.busy; text: wifiOvl.busy ? "Verbinde …" : "Verbinden"
                        onClicked: { if (wifiOvl.pw.length < 8) toast.show("Passwort hat mindestens 8 Zeichen", true); else wifiOvl.connect() } }
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

        // ---------- Software-Update ----------
        Rectangle {
            id: updOvl
            anchors.fill: parent; visible: false; color: "#d108090c"
            function open() { visible = true; win.checkUpd() }
            MouseArea { anchors.fill: parent }
            Panel {
                anchors.centerIn: parent; width: 520; height: 330
                Column {
                    x: 18; y: 16; width: parent.width - 36; spacing: 10
                    Val { font.pixelSize: 20; text: win.upd.available && !win.upd.running ? "Neue Software verfügbar" : "Software" }
                    Row {
                        spacing: 10; width: parent.width
                        Rectangle { width: (parent.width - 10) / 2; height: 62; radius: 12; color: "#0bffffff"
                            Column { x: 12; y: 10; Lbl { text: "Installiert" } Val { font.pixelSize: 20; text: win.upd.current || "—" } } }
                        Rectangle { width: (parent.width - 10) / 2; height: 62; radius: 12; color: win.upd.available ? "#262fa6cc" : "#0bffffff"
                            Column { x: 12; y: 10; Lbl { text: "Im Repository" } Val { font.pixelSize: 20; color: win.upd.available ? "#5cc3e3" : win.cInk; text: win.upd.latest || "—" } } }
                    }
                    Rectangle {
                        width: parent.width; height: 96; radius: 12; color: "#59000000"; clip: true
                        Column {
                            x: 12; y: 8; width: parent.width - 24; spacing: 2
                            Repeater {
                                model: win.upd.running || (win.upd.log && win.upd.log.length) ? win.upd.log : [win.upd.error ? win.upd.error : (win.upd.available ? "Eine neue Version liegt bereit." : (win.upd.latest ? "Kit Control ist aktuell." : "Prüfe auf Updates …"))]
                                Text { width: parent.width; elide: Text.ElideRight; text: modelData; color: "#c9cfd8"; font.family: "monospace"; font.pixelSize: 12 }
                            }
                        }
                    }
                    Lbl { width: parent.width; wrapMode: Text.WordWrap; elide: Text.ElideNone; font.pixelSize: 12
                        text: win.upd.running ? "Das Update dauert einige Minuten. Die Oberfläche startet dabei kurz neu." : "Hinweis: Solange der Kit druckt, ist ein Update gesperrt." }
                    Row {
                        spacing: 8
                        KButton { width: 150; height: 46; text: win.upd.available && !win.upd.running ? "Später" : "Schließen"; onClicked: updOvl.visible = false }
                        KButton { width: 150; height: 46; text: "Neu prüfen"; ok: !win.upd.running; onClicked: win.checkUpd() }
                        KButton { width: 184; height: 46; kind: "acc"; ok: !win.upd.running && !win.st.printing
                            text: win.upd.running ? "Läuft …" : "Jetzt aktualisieren"
                            onClicked: win.send({ cmd: "update_start" }, function (ok) { if (ok) { win.updWasRunning = true; win.loadUpd() } }) }
                    }
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
            property bool err: false
            function show(t, isErr) { tt.text = t; err = isErr === true; visible = true; tTimer.restart() }
            visible: false; z: 10
            anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 14
            width: Math.min(tt.implicitWidth, 620) + 32; height: tt.height + 20; radius: 12
            color: err ? "#2a1416" : "#1c2228"; border.color: err ? "#80e5484d" : "#552fa6cc"
            Text { id: tt; anchors.centerIn: parent; width: Math.min(implicitWidth, 620); wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter; color: toast.err ? "#ffb3b5" : win.cInk; font.family: win.fontName; font.pixelSize: 13 }
            Timer { id: tTimer; interval: Math.max(6000, tt.text.length * 70); onTriggered: toast.visible = false }
            MouseArea { anchors.fill: parent; onClicked: toast.visible = false }
        }

        // ---------- Start: gleiches Bild wie der Bootbildschirm, dann weich ausblenden ----------
        Rectangle {
            id: intro
            anchors.fill: parent; z: 100; color: "#000000"
            readonly property real sc: 400 / 913          // wie Plymouth: Logo = halbe Breite
            Image {
                id: introLogo
                source: "../branding/logo.png"; width: 400; height: 200 * intro.sc
                x: (parent.width - width) / 2; y: parent.height / 2 - height / 2 - 40
                smooth: true; mipmap: true
            }
            Image {
                id: introBy
                source: "../branding/by-rat3d.png"; width: 295 * intro.sc * 0.62; height: 80 * intro.sc * 0.62
                x: (parent.width - width) / 2; y: introLogo.y + introLogo.height + 18
                smooth: true; mipmap: true
            }
            Rectangle {
                width: parent.width * 0.28; height: 3; x: (parent.width - width) / 2; y: introBy.y + introBy.height + 40
                color: "#26ffffff"; radius: 1.5
                Rectangle { width: parent.width; height: parent.height; radius: 1.5; color: win.cBlue }
            }
            MouseArea { anchors.fill: parent }          // Tipps während des Einblendens nicht durchreichen
            SequentialAnimation on opacity {
                running: true
                PauseAnimation { duration: 700 }
                NumberAnimation { to: 0; duration: 450; easing.type: Easing.InOutQuad }
                ScriptAction { script: intro.visible = false }
            }
        }

    }
}
