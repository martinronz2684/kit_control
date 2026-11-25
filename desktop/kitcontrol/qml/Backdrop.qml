import QtQuick
import QtQuick.Effects

// Hintergrund hinter Fenstern (Popups): Oberfläche weichgezeichnet und abgedunkelt.
Item {
    ShaderEffectSource {
        id: snap
        anchors.fill: parent
        sourceItem: win.contentItem
        live: true
        visible: false
    }
    MultiEffect {
        anchors.fill: parent
        source: snap
        blurEnabled: true
        blur: 0.75
        blurMax: 40
        saturation: -0.2
        brightness: win.light ? 0.05 : -0.1
    }
    Rectangle { anchors.fill: parent; color: win.light ? "#55e9edf1" : "#88070a0d" }
}
