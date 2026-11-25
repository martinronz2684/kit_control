import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects

// Karte mit weichem Schatten (liegt unter der Karte, z = −1) und feiner Lichtkante oben.
Rectangle {
    id: card
    radius: 14
    color: win.cPanel
    border.color: win.cLine
    border.width: 1
    property bool shadow: true

    Rectangle {
        id: shadowSrc
        anchors.fill: parent
        radius: card.radius
        color: "black"
        visible: false
        layer.enabled: card.shadow && card.color.a > 0.5
    }
    MultiEffect {
        z: -1
        visible: card.shadow && card.color.a > 0.5
        source: shadowSrc
        anchors.fill: shadowSrc
        autoPaddingEnabled: true
        shadowEnabled: true
        shadowColor: win.light ? "#2a3a4a5a" : "#cc000000"
        shadowBlur: 0.9
        shadowVerticalOffset: win.light ? 3 : 6
        shadowHorizontalOffset: 0
        opacity: win.light ? 0.6 : 0.85
    }
    // Lichtkante oben (wirkt wie leicht erhabenes Glas)
    Rectangle {
        visible: card.color.a > 0.5
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        anchors.leftMargin: card.radius; anchors.rightMargin: card.radius; anchors.topMargin: 1
        height: 1
        color: win.light ? "#ffffff" : "#14ffffff"
    }
}
