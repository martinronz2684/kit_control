// Schnitt durch den Kit: links Bauplattform mit Laser und Heizstrahlern, rechts Vorrat.
// Gezeichnet in 660×440 und auf die verfügbare Fläche skaliert.
import QtQuick

Item {
    id: c
    property bool printing: false
    function sweep() { if (printing) sweepAnim.restart() }

    width: 660; height: 440
    scale: parent ? Math.min(parent.width / 660, (parent.height - 30) / 440) : 1
    transformOrigin: Item.Bottom

    component Grad3: Gradient {
        property color a; property color b; property color m: a
        GradientStop { position: 0; color: a }
        GradientStop { position: 0.15; color: m }
        GradientStop { position: 1; color: b }
    }

    // Gehäuse
    Rectangle { x: 50; y: 214; width: 560; height: 212; radius: 18; gradient: Grad3 { a: "#23272f"; b: "#121418" } }
    Rectangle { x: 40; y: 200; width: 580; height: 24; radius: 10; gradient: Grad3 { a: "#4a505b"; m: "#2c3139"; b: "#1b1f25" } }

    // Bauraum (links)
    Rectangle { x: 100; y: 224; width: 200; height: 192; radius: 6; color: "#0b0c0f" }
    Rectangle { x: 104; y: 224; width: 192; height: 122; gradient: Grad3 { a: "#f4f5f7"; m: "#e2e5ea"; b: "#a9afb9" } }
    Rectangle { x: 124; y: 262; width: 56; height: 74; radius: 9; color: "#b9a48c" }
    Rectangle { x: 196; y: 290; width: 80; height: 46; radius: 9; color: "#b9a48c" }
    Rectangle { x: 124; y: 236; width: 40; height: 20; radius: 6; color: "#c8b49c" }
    Rectangle { x: 104; y: 222; width: 192; height: 4; color: "#6b86ff"; opacity: c.printing ? 1 : 0.25 }
    Rectangle { x: 102; y: 346; width: 196; height: 12; radius: 3; gradient: Grad3 { a: "#e9edf2"; m: "#8d95a2"; b: "#4a515c" } }
    Rectangle { x: 190; y: 358; width: 20; height: 58; color: "#8d95a2" }

    // Vorrat (rechts)
    Rectangle { x: 360; y: 224; width: 200; height: 192; radius: 6; color: "#0b0c0f" }
    Rectangle { x: 364; y: 224; width: 192; height: 58; gradient: Grad3 { a: "#f4f5f7"; m: "#e2e5ea"; b: "#a9afb9" } }
    Rectangle { x: 362; y: 282; width: 196; height: 12; radius: 3; gradient: Grad3 { a: "#e9edf2"; m: "#8d95a2"; b: "#4a515c" } }
    Rectangle { x: 450; y: 294; width: 20; height: 122; color: "#8d95a2" }

    // Heizstrahler mit Wärmekegel
    Repeater {
        model: [96, 228]
        Item {
            Rectangle { x: modelData - 8; y: 108; width: 92; height: 92; opacity: c.printing ? 1 : 0.4
                gradient: Gradient { GradientStop { position: 0; color: "#55ff6a3d" } GradientStop { position: 1; color: "#00ff6a3d" } } }
            Rectangle { x: modelData - 10; y: 84; width: 96; height: 32; radius: 16; color: "#ff6a3d"; opacity: c.printing ? 0.28 : 0.1 }
            Rectangle { x: modelData - 8; y: 84; width: 92; height: 9; radius: 4.5; color: "#2c3139" }
            Rectangle { x: modelData; y: 92; width: 76; height: 16; radius: 8
                gradient: Gradient { GradientStop { position: 0; color: "#ffe2d6" } GradientStop { position: 1; color: "#ff6a3d" } } }
        }
    }

    // Laser
    Rectangle { x: 176; y: 24; width: 48; height: 56; radius: 11; color: "#2a2f38"; border.color: "#3a404b" }
    Rectangle { x: 197; y: 36; width: 6; height: 6; radius: 3; color: "#b9c6ff" }
    Item {
        visible: c.printing
        Rectangle { x: 199; y: 82; width: 2; height: 147; transformOrigin: Item.Top; rotation: -15
            gradient: Gradient { GradientStop { position: 0; color: "#408ea2ff" } GradientStop { position: 1; color: "#e6ecff" } } }
        Rectangle { x: 216; y: 203; width: 44; height: 44; radius: 22; color: "#8ea2ff"; opacity: 0.25 }
        Rectangle { x: 226; y: 213; width: 24; height: 24; radius: 12; color: "#8ea2ff"; opacity: 0.45 }
        Rectangle { x: 234; y: 221; width: 8; height: 8; radius: 4; color: "white" }
    }

    // Beschichter (parkt rechts, fährt bei jeder neuen Schicht über beide Behälter)
    Item {
        id: coater
        x: 566; y: 172
        Rectangle { width: 46; height: 24; radius: 5; color: "#2c3139"; border.color: "#4a505b" }
        Rectangle { x: 5; y: 24; width: 36; height: 6; radius: 2; color: "#b8bec8" }
        SequentialAnimation {
            id: sweepAnim
            NumberAnimation { target: coater; property: "x"; to: 96; duration: 1100; easing.type: Easing.InOutQuad }
            PauseAnimation { duration: 200 }
            NumberAnimation { target: coater; property: "x"; to: 566; duration: 1100; easing.type: Easing.InOutQuad }
        }
    }

    Text { x: 100; y: 204; width: 200; horizontalAlignment: Text.AlignHCenter; text: "Bauplattform"; color: "#9aa3b2"; font.pixelSize: 12; font.weight: Font.DemiBold }
    Text { x: 360; y: 204; width: 200; horizontalAlignment: Text.AlignHCenter; text: "Vorrat"; color: "#9aa3b2"; font.pixelSize: 12; font.weight: Font.DemiBold }
}
