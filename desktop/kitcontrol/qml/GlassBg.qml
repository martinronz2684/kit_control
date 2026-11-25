import QtQuick
import QtQuick.Effects

// Halbtransparenter Fensterhintergrund mit Schatten und heller Kante.
Item {
    Rectangle {
        id: glassSrc
        anchors.fill: parent
        radius: 16
        color: "black"
        visible: false
        layer.enabled: true
    }
    MultiEffect {
        source: glassSrc
        anchors.fill: glassSrc
        autoPaddingEnabled: true
        shadowEnabled: true
        shadowColor: win.light ? "#40263a4d" : "#ee000000"
        shadowBlur: 1.0
        shadowVerticalOffset: 14
    }
    Rectangle {
        anchors.fill: parent
        radius: 16
        color: win.light ? Qt.rgba(1, 1, 1, 0.92) : Qt.rgba(0.075, 0.087, 0.102, 0.9)
        border.color: win.light ? "#d3d9e0" : "#33404b"
        border.width: 1
        gradient: Gradient {
            GradientStop { position: 0.0; color: win.light ? Qt.rgba(1, 1, 1, 0.95) : Qt.rgba(0.10, 0.12, 0.14, 0.92) }
            GradientStop { position: 1.0; color: win.light ? Qt.rgba(0.97, 0.98, 0.99, 0.92) : Qt.rgba(0.07, 0.08, 0.095, 0.9) }
        }
    }
}
