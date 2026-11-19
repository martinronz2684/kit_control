// Schnitt durch den Kit: links Bauplattform mit Laser und Heizstrahlern, rechts Vorrat.
// Statischer Teil ist ein vorgerendertes Bild (assets/chamber.png, 2×), Bewegtes liegt darüber.
import QtQuick

Item {
    id: c
    property bool printing: false
    function sweep() { if (printing) sweepAnim.restart() }

    width: 660; height: 440
    scale: parent ? Math.min(parent.width / 660, (parent.height - 30) / 440) : 1
    transformOrigin: Item.Bottom

    Image { anchors.fill: parent; source: "assets/chamber.png"; smooth: true; mipmap: true }

    // Heizstrahler glimmen
    Repeater {
        model: [150, 250]
        Image {
            source: "assets/glow-heat.png"
            x: modelData - 50; y: 51; width: 100; height: 100
            opacity: c.printing ? 0.55 : 0.2
            SequentialAnimation on opacity {
                running: c.printing; loops: Animation.Infinite
                NumberAnimation { to: 0.7; duration: 1400; easing.type: Easing.InOutSine }
                NumberAnimation { to: 0.45; duration: 1600; easing.type: Easing.InOutSine }
            }
        }
    }

    // frisch belichtete Schicht leuchtet
    Image {
        source: "assets/glow-blue.png"; x: 84; y: 196; width: 232; height: 56
        opacity: c.printing ? 0.6 : 0
        Behavior on opacity { NumberAnimation { duration: 400 } }
    }

    // Laserstrahl mit Brennpunkt, der über die Schicht wandert
    Item {
        id: laser
        visible: c.printing
        property real tx: 160
        SequentialAnimation on tx {
            running: c.printing; loops: Animation.Infinite
            NumberAnimation { to: 270; duration: 2600; easing.type: Easing.InOutSine }
            NumberAnimation { to: 140; duration: 2200; easing.type: Easing.InOutSine }
            NumberAnimation { to: 230; duration: 1800; easing.type: Easing.InOutSine }
        }
        readonly property real len: Math.sqrt(Math.pow(tx - 200, 2) + Math.pow(224 - 82, 2))
        readonly property real ang: Math.atan2(tx - 200, 224 - 82) * 180 / Math.PI
        Rectangle {
            x: 196; y: 82; width: 8; height: laser.len; radius: 4; transformOrigin: Item.Top; rotation: -laser.ang
            color: "#8ea2ff"; opacity: 0.18
        }
        Rectangle {
            x: 199; y: 82; width: 2; height: laser.len; transformOrigin: Item.Top; rotation: -laser.ang
            gradient: Gradient { GradientStop { position: 0; color: "#408ea2ff" } GradientStop { position: 1; color: "#f0f3ff" } }
        }
        Image {
            source: "assets/glow-blue.png"; width: 64; height: 64; x: laser.tx - 32; y: 224 - 32
            SequentialAnimation on scale {
                running: c.printing; loops: Animation.Infinite
                NumberAnimation { to: 1.25; duration: 300 } NumberAnimation { to: 0.9; duration: 300 }
            }
        }
        Rectangle { x: laser.tx - 3; y: 221; width: 6; height: 6; radius: 3; color: "white" }
    }

    // Beschichter: parkt rechts, fährt bei jeder neuen Schicht über beide Behälter
    Image {
        id: coater
        source: "assets/coater.png"; x: 497; y: 188; width: 60; height: 40; smooth: true
        SequentialAnimation {
            id: sweepAnim
            NumberAnimation { target: coater; property: "x"; to: 94; duration: 1200; easing.type: Easing.InOutCubic }
            PauseAnimation { duration: 150 }
            NumberAnimation { target: coater; property: "x"; to: 497; duration: 1200; easing.type: Easing.InOutCubic }
        }
    }

    Text { x: 100; y: 205; width: 200; horizontalAlignment: Text.AlignHCenter; text: "Bauplattform"; color: "#9aa3b2"; font.family: "Inter"; font.pixelSize: 12; font.weight: Font.DemiBold }
    Text { x: 360; y: 205; width: 200; horizontalAlignment: Text.AlignHCenter; text: "Vorrat"; color: "#9aa3b2"; font.family: "Inter"; font.pixelSize: 12; font.weight: Font.DemiBold }
}
