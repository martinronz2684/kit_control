import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Laser-Kalibrierung wie in Sintratec Central („Calibrate“): Muster anzeigen, Skalierung im Kit lesen,
// aus Soll- und Istmaß des Kalibrierteils neu berechnen (berücksichtigt die bereits eingestellte Skalierung)
// und auf den Kit schreiben. Central erlaubt höchstens ±5 %.
Card {
    id: cc
    property bool ready: false
    property var sc: win.kit && win.kit.scaling ? win.kit.scaling : null
    property var factory: win.kit && win.kit.factory ? win.kit.factory.scaling : null
    implicitHeight: col.implicitHeight + 28

    function cur(a) { return sc && sc[a] !== undefined && sc[a] !== null ? Number(sc[a]) : 0 }
    function num(t) { var v = Number(String(t).replace(",", ".")); return isFinite(v) ? v : NaN }
    // wie Central „Calculate“: (aktueller Faktor × Soll / Ist − 1) × 100
    function calc(a, soll, ist) {
        var s = num(soll), i = num(ist)
        if (!(s > 0) || !(i > 0)) return NaN
        return ((1 + cur(a) / 100) * s / i - 1) * 100
    }
    function fmt(v) { return isNaN(v) ? "–" : (v >= 0 ? "+" : "") + v.toFixed(2).replace(".", ",") + " %" }
    property var res: [calc("x", sx.text, ix.text), calc("y", sy.text, iy.text), calc("z", sz.text, iz.text)]
    property bool tooBig: res.some(function (v) { return !isNaN(v) && Math.abs(v) > 5.0005 })
    property bool anyNew: res.some(function (v) { return !isNaN(v) })

    ColumnLayout {
        id: col
        anchors.fill: parent; anchors.margins: 14
        spacing: 8
        Caption { text: "Laser-Kalibrierung" }
        Body {
            Layout.fillWidth: true; font.pixelSize: 12; color: win.cMut
            text: !backend.connected ? "Werte im Kit erscheinen nach dem Verbinden."
                : (sc ? "Im Kit: X " + fmt(cur("x")) + " · Y " + fmt(cur("y")) + " · Z " + fmt(cur("z"))
                        : "Skalierung konnte nicht gelesen werden" + (win.kit && win.kit.scaling_error ? ": " + win.kit.scaling_error : ""))
                  + (factory ? "\nWerkswerte: X " + fmt(Number(factory.x)) + " · Y " + fmt(Number(factory.y)) + " · Z " + fmt(Number(factory.z)) : "")
        }
        RowLayout {
            spacing: 6
            KButton { text: "Muster"; Layout.fillWidth: true; Layout.preferredWidth: 1; enabled: cc.ready; onClicked: backend.cmd({ cmd: "pattern", name: "pattern" }) }
            KButton { text: "Mitte"; Layout.fillWidth: true; Layout.preferredWidth: 1; enabled: cc.ready; onClicked: backend.cmd({ cmd: "pattern", name: "center" }) }
            KButton { text: "Aus"; kind: "ghost"; Layout.fillWidth: true; Layout.preferredWidth: 1; enabled: cc.ready; onClicked: backend.cmd({ cmd: "exit_calibration" }) }
        }
        Text { text: "Kalibrierteil außen messen (mm) – Nut zeigt nach hinten (Y)"; color: win.cMut; font.pixelSize: 12; Layout.topMargin: 4 }
        GridLayout {
            Layout.fillWidth: true
            columns: 4; columnSpacing: 6; rowSpacing: 6
            Text { text: ""; Layout.preferredWidth: 14 }
            Text { text: "Soll"; color: win.cMut; font.pixelSize: 11; Layout.fillWidth: true; Layout.preferredWidth: 1 }
            Text { text: "Ist"; color: win.cMut; font.pixelSize: 11; Layout.fillWidth: true; Layout.preferredWidth: 1 }
            Text { text: "neu"; color: win.cMut; font.pixelSize: 11; Layout.preferredWidth: 70 }
            Text { text: "X"; color: win.cInk; font.pixelSize: 13 }
            KField { id: sx; text: "40"; Layout.fillWidth: true; Layout.preferredWidth: 1 }
            KField { id: ix; Layout.fillWidth: true; Layout.preferredWidth: 1; placeholderText: "gemessen" }
            Text { text: fmt(res[0]); color: win.cInk; font.pixelSize: 12; Layout.preferredWidth: 70 }
            Text { text: "Y"; color: win.cInk; font.pixelSize: 13 }
            KField { id: sy; text: "40"; Layout.fillWidth: true; Layout.preferredWidth: 1 }
            KField { id: iy; Layout.fillWidth: true; Layout.preferredWidth: 1; placeholderText: "gemessen" }
            Text { text: fmt(res[1]); color: win.cInk; font.pixelSize: 12; Layout.preferredWidth: 70 }
            Text { text: "Z"; color: win.cInk; font.pixelSize: 13 }
            KField { id: sz; text: "5"; Layout.fillWidth: true; Layout.preferredWidth: 1 }
            KField { id: iz; Layout.fillWidth: true; Layout.preferredWidth: 1; placeholderText: "gemessen" }
            Text { text: fmt(res[2]); color: win.cInk; font.pixelSize: 12; Layout.preferredWidth: 70 }
        }
        Body {
            visible: cc.tooBig
            Layout.fillWidth: true; font.pixelSize: 12; color: "#ffb4b6"
            text: "Mehr als ±5 % – das erlaubt auch Central nicht. Bitte mechanisch nachjustieren."
        }
        KButton {
            text: "Auf den Kit schreiben"
            kind: "pri"
            Layout.fillWidth: true
            enabled: cc.ready && cc.anyNew && !cc.tooBig
            onClicked: backend.cmd({ cmd: "scaling",
                                     x: isNaN(res[0]) ? cur("x") : Math.round(res[0] * 100) / 100,
                                     y: isNaN(res[1]) ? cur("y") : Math.round(res[1] * 100) / 100,
                                     z: isNaN(res[2]) ? cur("z") : Math.round(res[2] * 100) / 100 })
        }
        KButton { text: "Kalibrierteil zum Drucken hinzufügen"; kind: "ghost"; Layout.fillWidth: true; onClicked: backend.addCalibrationPart() }
    }
}
