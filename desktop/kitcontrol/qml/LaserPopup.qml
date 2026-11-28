import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

// Laserkorrektur: Scans des Kalibriermusters auswerten und die Werte zum Pi schicken. Der Pi rechnet jeden Job beim
// Übertragen um (Maßstab, Winkligkeit, Schräglauf, Verzerrung). Auswertung: kitslice/lasercal.py.
Popup {
    id: lp
    objectName: "laserPop"
    anchors.centerIn: parent
    width: Math.min(1120, parent.width - 60)
    height: Math.min(800, parent.height - 40)
    modal: true
    padding: 22
    background: GlassBg {}
    Overlay.modal: Backdrop {}

    readonly property var c: backend.laserComp || ({})
    readonly property var res: backend.lcResult || ({})
    readonly property bool hasRes: res.ok === true
    readonly property var scans: backend.lcScans || []
    readonly property bool kitOk: backend.connected && win.kit.printing !== true && !win.kit.transfer
    property bool useScale: false
    property real gainMul: 1
    property string leanXText: ""
    property string leanYText: ""
    function numOf(t, fallback) { var v = Number(String(t).replace(",", ".")); return t === "" ? fallback : v }

    onOpened: backend.refreshComp()

    function sgn(v, d) {
        if (v === undefined || v === null || isNaN(v)) return "–"
        return (v > 0 ? "+" : v < 0 ? "−" : "±") + win.fnum(Math.abs(v), d)
    }
    function deg(v) { return sgn(v, 3) + "°" }
    function pct(v) { return sgn(v, 3) + " %" }

    FileDialog {
        id: scanDlg
        title: win.t("Scan des Kalibriermusters öffnen")
        fileMode: FileDialog.OpenFiles
        nameFilters: [win.t("Bilder (*.png *.tif *.tiff *.jpg *.jpeg *.bmp)")]
        onAccepted: backend.lcAddScans(selectedFiles)
    }

    // Kleine Wertzeile: Name links, Wert rechts
    component ValRow: RowLayout {
        property string name
        property string value
        property color tint: win.cInk
        Layout.fillWidth: true
        spacing: 8
        Text { text: parent.name; color: win.cMut; font.pixelSize: 13; Layout.fillWidth: true; elide: Text.ElideRight }
        Text { text: parent.value; color: parent.tint; font.pixelSize: 13; font.weight: Font.DemiBold }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 14

        RowLayout {
            Layout.fillWidth: true
            ColumnLayout {
                spacing: 2; Layout.fillWidth: true
                Text { text: win.t("Laserkorrektur"); color: win.cInk; font.pixelSize: 21; font.weight: Font.DemiBold }
                Text { text: win.t("Maßstab, Winkligkeit, Schräglauf und Verzerrung – der Kit Control am Pi rechnet jeden Job beim Übertragen danach um.")
                       color: win.cMut; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideRight }
            }
            KButton { text: win.t("Schließen"); kind: "ghost"; onClicked: lp.close() }
        }

        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            spacing: 14

            // ================= links: am Kit gespeichert, Schräglauf, Anleitung =================
            Flickable {
                id: leftFlick
                Layout.preferredWidth: 380; Layout.fillHeight: true
                contentHeight: leftCol.implicitHeight; clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: leftFlick.contentHeight > leftFlick.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff }
                ColumnLayout {
                    id: leftCol
                    width: leftFlick.width - (leftFlick.contentHeight > leftFlick.height ? 12 : 0)
                    spacing: 12

                    Card {
                        Layout.fillWidth: true
                        implicitHeight: kitCol.implicitHeight + 28
                        ColumnLayout {
                            id: kitCol
                            anchors.fill: parent; anchors.margins: 14
                            spacing: 8
                            RowLayout {
                                Layout.fillWidth: true
                                Caption { text: win.t("Am Kit gespeichert"); Layout.fillWidth: true }
                                Rectangle {
                                    implicitWidth: pill.implicitWidth + 18; implicitHeight: 22; radius: 11
                                    color: lp.c.active ? win.cSel : win.cTrack
                                    Text { id: pill; anchors.centerIn: parent; font.pixelSize: 11; font.weight: Font.DemiBold
                                        color: lp.c.active ? win.cAcc : win.cMut
                                        text: !backend.connected ? win.t("nicht verbunden")
                                            : lp.c.enabled === undefined ? win.t("Pi-Update nötig")
                                            : lp.c.active ? win.t("aktiv") : (lp.c.enabled === false ? win.t("aus") : win.t("alles 0")) }
                                }
                            }
                            ValRow { name: win.t("Maßstab X"); value: lp.pct(lp.c.scale_x_pct || 0) }
                            ValRow { name: win.t("Maßstab Y"); value: lp.pct(lp.c.scale_y_pct || 0) }
                            ValRow { name: win.t("Winkligkeit X/Y"); value: lp.deg(lp.c.skew_deg || 0) }
                            ValRow { name: win.t("Schräglauf X / Y je 100 mm"); value: lp.sgn(lp.c.lean_x_mm_per_100 || 0, 3) + " / " + lp.sgn(lp.c.lean_y_mm_per_100 || 0, 3) + " mm" }
                            ValRow { name: win.t("Verzerrung (Tabelle)"); value: lp.c.grid_max_um ? win.t("bis ") + win.fnum(lp.c.grid_max_um, 0) + " µm" : win.t("keine") }
                            ValRow { name: win.t("Gemessen"); value: lp.c.info && lp.c.info.measured ? Qt.formatDateTime(new Date(lp.c.info.measured * 1000), "dd.MM.yyyy HH:mm") : win.t("noch nie") }
                            RowLayout {
                                Layout.fillWidth: true; Layout.topMargin: 4; spacing: 8
                                KSwitch {
                                    checked: lp.c.enabled !== false
                                    enabled: lp.kitOk && lp.c.enabled !== undefined
                                    onToggled: backend.setCompEnabled(checked)
                                }
                                Text { text: win.t("Korrektur anwenden"); color: win.cInk; font.pixelSize: 13; Layout.fillWidth: true }
                                KButton { text: win.t("Auf 0"); kind: "ghost"; enabled: lp.kitOk && (lp.c.active || lp.c.grid_max_um > 0 || lp.c.info !== undefined)
                                          onClicked: backend.resetComp() }
                            }
                        }
                    }

                    Card {
                        Layout.fillWidth: true
                        implicitHeight: leanCol.implicitHeight + 28
                        ColumnLayout {
                            id: leanCol
                            anchors.fill: parent; anchors.margins: 14
                            spacing: 8
                            Caption { text: win.t("Schräglauf der Bauplattform") }
                            Body { color: win.cMut; font.pixelSize: 12
                                text: win.t("Von Hand gemessen: hohen Quader drucken und mit der Messuhr den Versatz oben gegenüber unten bestimmen (in Richtung +X / +Y positiv). Der Pi verschiebt jede Schicht entsprechend zurück.") }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 10
                                NumField { Layout.fillWidth: true; Layout.preferredWidth: 1; label: win.t("X je 100 mm"); unit: "mm"
                                    value: win.fnum(lp.c.lean_x_mm_per_100 || 0, 3); onCommitted: (v) => lp.leanXText = v }
                                NumField { Layout.fillWidth: true; Layout.preferredWidth: 1; label: win.t("Y je 100 mm"); unit: "mm"
                                    value: win.fnum(lp.c.lean_y_mm_per_100 || 0, 3); onCommitted: (v) => lp.leanYText = v }
                                KButton {
                                    Layout.alignment: Qt.AlignBottom
                                    text: win.t("Senden"); enabled: lp.kitOk && lp.c.enabled !== undefined && (lp.leanXText !== "" || lp.leanYText !== "")
                                    onClicked: {
                                        var x = lp.numOf(lp.leanXText, lp.c.lean_x_mm_per_100 || 0), y = lp.numOf(lp.leanYText, lp.c.lean_y_mm_per_100 || 0)
                                        if (isFinite(x) && isFinite(y) && Math.abs(x) <= 5 && Math.abs(y) <= 5) {
                                            backend.setLean(x, y); lp.leanXText = ""; lp.leanYText = ""
                                        } else backend.message(win.t("Schräglauf: Werte zwischen −5 und +5 mm"), "error")
                                    }
                                }
                            }
                        }
                    }

                    Card {
                        Layout.fillWidth: true
                        implicitHeight: howCol.implicitHeight + 28
                        color: win.cField
                        ColumnLayout {
                            id: howCol
                            anchors.fill: parent; anchors.margins: 14
                            spacing: 6
                            Caption { text: win.t("So wird gemessen") }
                            Repeater {
                                model: [
                                    win.t("Thermopapier plan auf ein Blech kleben und genau auf Beschichterhöhe fahren. Laser-X-Richtung am Rand markieren."),
                                    win.t("Am Kit: Kalibrieren → Muster anzeigen, laufen lassen, bis die Linien deutlich dunkel sind. Heizung aus."),
                                    win.t("Gleich danach scannen, 1200 dpi (oder 2400), Graustufen, als PNG oder TIFF. Am besten zweimal: normal und um 90° gedreht."),
                                    win.t("Scans hier laden, Lage so drehen, dass Laser-X nach rechts zeigt, auswerten."),
                                    win.t("Ergebnis prüfen und auf den Kit übernehmen. Zur Kontrolle das Muster neu brennen.")]
                                RowLayout {
                                    Layout.fillWidth: true; spacing: 10
                                    Rectangle { Layout.alignment: Qt.AlignTop; width: 20; height: 20; radius: 10; color: win.cSel
                                        Text { anchors.centerIn: parent; text: index + 1; color: win.cAcc; font.pixelSize: 11; font.weight: Font.Bold } }
                                    Body { text: modelData; font.pixelSize: 12; color: win.cInk }
                                }
                            }
                        }
                    }
                }
            }

            // ================= rechts: Scans und Ergebnis =================
            Flickable {
                id: rightFlick
                Layout.fillWidth: true; Layout.fillHeight: true
                contentHeight: rightCol.implicitHeight; clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: rightFlick.contentHeight > rightFlick.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff }
            ColumnLayout {
                id: rightCol
                width: rightFlick.width - (rightFlick.contentHeight > rightFlick.height ? 12 : 0)
                spacing: 12

                Card {
                    id: scanCard
                    Layout.fillWidth: true
                    implicitHeight: scanCol.implicitHeight + 28
                    ColumnLayout {
                        id: scanCol
                        anchors.fill: parent; anchors.margins: 14
                        spacing: 10
                        RowLayout {
                            Layout.fillWidth: true
                            Caption { text: win.t("Scans des Kalibriermusters"); Layout.fillWidth: true }
                            KButton { text: win.t("Scan hinzufügen …"); enabled: !backend.lcBusy && lp.scans.length < 4; onClicked: scanDlg.open() }
                            KButton { text: backend.lcBusy ? win.t("Werte aus …") : win.t("Auswerten"); kind: "pri"
                                      enabled: !backend.lcBusy && lp.scans.length > 0; onClicked: backend.lcAnalyze() }
                        }
                        Body {
                            visible: lp.scans.length === 0
                            color: win.cMut; font.pixelSize: 12
                            text: win.t("Noch kein Scan geladen. Das Muster muss vollständig mit etwas Rand auf dem Bild sein (mindestens 85 × 85 mm).")
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            visible: lp.scans.length > 0
                            spacing: 10
                            Repeater {
                                model: lp.scans
                                Rectangle {
                                    Layout.preferredWidth: 168; Layout.preferredHeight: 214
                                    radius: 12; color: win.cField; border.color: modelData.error ? win.cErrLine : win.cLine
                                    ColumnLayout {
                                        anchors.fill: parent; anchors.margins: 8
                                        spacing: 6
                                        Rectangle {
                                            Layout.fillWidth: true; Layout.preferredHeight: 116
                                            radius: 8; color: "#ffffff"; clip: true
                                            Image {
                                                anchors.centerIn: parent
                                                width: modelData.rot % 180 === 0 ? parent.width : parent.height
                                                height: modelData.rot % 180 === 0 ? parent.height : parent.width
                                                fillMode: Image.PreserveAspectFit
                                                source: modelData.url; sourceSize.width: 360; asynchronous: true
                                                rotation: modelData.rot
                                                Behavior on rotation { NumberAnimation { duration: 160 } }
                                            }
                                            // Achsen des Lasers: so muss die Markierung auf dem Papier liegen
                                            Item {
                                                x: 8; y: parent.height - 30; width: 40; height: 24
                                                Rectangle { x: 0; y: 20; width: 30; height: 2.5; color: win.cRed }
                                                Text { x: 31; y: 13; text: "X"; color: win.cRed; font.pixelSize: 11; font.weight: Font.Bold }
                                                Rectangle { x: 0; y: -8; width: 2.5; height: 30; color: "#2fa64a" }
                                                Text { x: 5; y: -12; text: "Y"; color: "#2fa64a"; font.pixelSize: 11; font.weight: Font.Bold }
                                            }
                                        }
                                        Text { text: modelData.name; color: win.cInk; font.pixelSize: 12; font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideMiddle }
                                        RowLayout {
                                            Layout.fillWidth: true; spacing: 4
                                            KButton { text: "⟲"; implicitHeight: 28; leftPadding: 8; rightPadding: 8; onClicked: backend.lcSet(index, { rot: modelData.rot + 270 }) }
                                            KButton { text: "⟳"; implicitHeight: 28; leftPadding: 8; rightPadding: 8; onClicked: backend.lcSet(index, { rot: modelData.rot + 90 }) }
                                            KField {
                                                Layout.fillWidth: true; implicitHeight: 28; font.pixelSize: 12
                                                text: String(Math.round(modelData.dpi))
                                                onUserChanged: backend.lcSet(index, { dpi: text })
                                                Text { anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter
                                                    text: "dpi"; color: modelData.dpi_known ? win.cMut : win.cHeat; font.pixelSize: 11 }
                                            }
                                            KButton { text: "✕"; kind: "ghost"; implicitHeight: 28; leftPadding: 8; rightPadding: 8; onClicked: backend.lcRemove(index) }
                                        }
                                        Text {
                                            Layout.fillWidth: true; wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight
                                            font.pixelSize: 11
                                            color: modelData.error ? win.cErrInk : (modelData.result ? win.cOk : (modelData.dpi_known ? win.cMut : win.cHeat))
                                            text: modelData.error ? modelData.error
                                                : modelData.result ? win.t("✓ ") + modelData.result.samples + win.t(" Messstellen · Rest ") + win.fnum(modelData.result.rms_um, 1) + " µm"
                                                : modelData.dpi_known ? win.t("Lage prüfen: Laser-X nach rechts")
                                                : win.t("Auflösung nicht in der Datei – dpi prüfen")
                                        }
                                    }
                                }
                            }
                            Item { Layout.fillWidth: true }
                        }
                    }
                }

                Card {
                    Layout.fillWidth: true
                    implicitHeight: Math.max(rightFlick.height - scanCard.height - 12, resCol.implicitHeight + 28, 380)
                    RowLayout {
                        anchors.fill: parent; anchors.margins: 14
                        spacing: 16

                        // Muster: Soll grau, gemessen (übertrieben) in Petrol
                        Item {
                            Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumWidth: 260
                            Canvas {
                                id: devCanvas
                                anchors.fill: parent
                                property real gain: 1
                                property var lines: lp.res.lines || []
                                onLinesChanged: requestPaint()
                                Connections { target: lp; function onGainMulChanged() { devCanvas.requestPaint() } }
                                Connections { target: win; function onLightChanged() { devCanvas.requestPaint() } }
                                onWidthChanged: requestPaint()
                                onHeightChanged: requestPaint()
                                onPaint: {
                                    var ctx = getContext("2d"); ctx.reset()
                                    var S = Math.min(width, height) - 30, ox = (width - S) / 2, oy = (height - S) / 2 + 8, k = S / 92
                                    function P(x, y) { return [ox + S / 2 + x * k, oy + S / 2 - y * k] }
                                    var L = lines
                                    if (!L.length) {
                                        ctx.strokeStyle = win.light ? "#d3d9e0" : "#262b33"; ctx.lineWidth = 1.2
                                        var h = [40, 80 / 3, 40 / 3]
                                        for (var i = 0; i < 3; i++) { var a = P(-h[i], h[i]); ctx.strokeRect(a[0], a[1], 2 * h[i] * k, 2 * h[i] * k) }
                                        var e = P(-40, 0), f = P(40, 0), g = P(0, -40), q = P(0, 40), d1 = P(-40, -40), d2 = P(40, 40), d3 = P(-40, 40), d4 = P(40, -40)
                                        ctx.beginPath(); ctx.moveTo(e[0], e[1]); ctx.lineTo(f[0], f[1]); ctx.moveTo(g[0], g[1]); ctx.lineTo(q[0], q[1])
                                        ctx.moveTo(d1[0], d1[1]); ctx.lineTo(d2[0], d2[1]); ctx.moveTo(d3[0], d3[1]); ctx.lineTo(d4[0], d4[1]); ctx.stroke()
                                        return
                                    }
                                    var mx = 0
                                    L.forEach(function (ln) { ln.forEach(function (p) { mx = Math.max(mx, Math.hypot(p[2], p[3])) }) })
                                    gain = mx > 1e-6 ? Math.max(1, Math.round(0.055 * S / (mx * k) * lp.gainMul)) : 1
                                    ctx.lineWidth = 1.2; ctx.strokeStyle = win.light ? "#c2cad3" : "#39414c"
                                    L.forEach(function (ln) { ctx.beginPath(); ln.forEach(function (p, i) { var a = P(p[0], p[1]); if (i) ctx.lineTo(a[0], a[1]); else ctx.moveTo(a[0], a[1]) }); ctx.stroke() })
                                    ctx.lineWidth = 2; ctx.strokeStyle = win.cAcc
                                    L.forEach(function (ln) { ctx.beginPath(); ln.forEach(function (p, i) { var a = P(p[0] + p[2] * gain, p[1] + p[3] * gain); if (i) ctx.lineTo(a[0], a[1]); else ctx.moveTo(a[0], a[1]) }); ctx.stroke() })
                                }
                            }
                            Text {
                                anchors.top: parent.top; anchors.left: parent.left; anchors.right: gainRow.left; anchors.rightMargin: 8
                                text: lp.hasRes ? win.t("Gebrannt ohne Korrektur, Abweichung ×") + devCanvas.gain : win.t("Hier erscheint das gemessene Muster")
                                color: win.cMut; font.pixelSize: 12; wrapMode: Text.WordWrap
                            }
                            Row {
                                id: gainRow
                                anchors.top: parent.top; anchors.right: parent.right; spacing: 4
                                visible: lp.hasRes
                                KButton { text: "−"; implicitHeight: 26; leftPadding: 10; rightPadding: 10; onClicked: lp.gainMul = Math.max(0.25, lp.gainMul / 2) }
                                KButton { text: "+"; implicitHeight: 26; leftPadding: 10; rightPadding: 10; onClicked: lp.gainMul = Math.min(8, lp.gainMul * 2) }
                            }
                        }

                        ColumnLayout {
                            id: resCol
                            Layout.preferredWidth: 290; Layout.maximumWidth: 290; Layout.fillHeight: true
                            spacing: 8
                            Caption { text: win.t("Ergebnis") }
                            Body {
                                visible: !lp.hasRes
                                color: win.cMut; font.pixelSize: 12
                                text: backend.lcBusy ? win.t("Werte die Scans aus …") : win.t("Scans laden und auswerten. Die Auswertung sucht das Muster selbst und misst jede Linie alle 0,5 mm quer ab.")
                            }
                            ColumnLayout {
                                visible: lp.hasRes
                                Layout.fillWidth: true; spacing: 6
                                ValRow { name: win.t("Maßstab X"); value: lp.pct(lp.res.scale_x_pct) }
                                ValRow { name: win.t("Maßstab Y"); value: lp.pct(lp.res.scale_y_pct) }
                                ValRow { name: win.t("Winkligkeit X/Y"); value: lp.deg(lp.res.skew_deg) }
                                ValRow { name: win.t("Verzerrung bis"); value: win.fnum(lp.res.nonlinear_max_um, 0) + " µm" }
                                ValRow { name: win.t("Verdrehung (nur Info)"); value: lp.deg(lp.res.rotation_deg); tint: win.cMut }
                                ValRow { name: win.t("Restabweichung"); value: win.fnum(lp.res.rms_um, 1) + " µm"
                                         tint: lp.res.rms_um > 25 ? win.cHeat : win.cOk }
                                ValRow { visible: !!lp.res.spread; name: win.t("Unterschied der Scans (Winkel)"); value: lp.res.spread ? win.fnum(lp.res.spread.skew_deg, 3) + "°" : ""; tint: win.cMut }
                                Body {
                                    visible: lp.res.scans === 1
                                    color: win.cWarnInk; font.pixelSize: 11
                                    text: win.t("Nur ein Scan: Schiefe und Verzug des Scanners stecken mit im Ergebnis. Ein zweiter, um 90° gedrehter Scan hebt sie auf.")
                                }
                                Rectangle { Layout.fillWidth: true; height: 1; color: win.cLine; Layout.topMargin: 2; Layout.bottomMargin: 2 }
                                KCheck { text: win.t("Maßstab aus dem Scan übernehmen"); checked: lp.useScale; onToggled: lp.useScale = checked }
                                Body {
                                    color: win.cMut; font.pixelSize: 11
                                    text: lp.useScale ? win.t("Der Maßstab hängt an der Genauigkeit des Scanners (oft 0,1–0,3 %). Digitale Skalierung im Kit dann auf 0 lassen.")
                                                      : win.t("Empfohlen: Winkligkeit und Verzerrung aus dem Scan, den Maßstab wie bisher über das Kalibrierteil und die digitale Skalierung im Kit.")
                                }
                            }
                            Item { Layout.fillHeight: true }
                            KButton {
                                Layout.fillWidth: true
                                text: win.t("Auf den Kit übernehmen"); kind: "pri"
                                enabled: lp.hasRes && lp.kitOk && lp.c.enabled !== undefined
                                onClicked: backend.lcApply(lp.useScale)
                            }
                            Text {
                                Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 11; color: win.cMut
                                visible: lp.hasRes && !lp.kitOk
                                text: !backend.connected ? win.t("Zum Übernehmen mit dem Kit verbinden.") : win.t("Nicht während eines Drucks.")
                            }
                        }
                    }
                }
            }
            }
        }
    }
}
