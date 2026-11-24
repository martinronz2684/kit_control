import QtQuick
import QtQuick.Controls

// Häkchen im Kit-Control-Stil: Kästchen links, Text rechts daneben
CheckBox {
    id: kc
    spacing: 8
    padding: 2
    font.pixelSize: 13
    indicator: Rectangle {
        x: kc.leftPadding
        anchors.verticalCenter: parent.verticalCenter
        width: 18; height: 18; radius: 5
        color: kc.checked ? win.cAcc : "#0f1215"
        border.color: kc.checked ? win.cAcc : (kc.hovered ? "#4a5560" : win.cLine)
        border.width: 1.5
        opacity: kc.enabled ? 1 : 0.4
        Text {
            anchors.centerIn: parent
            visible: kc.checked
            text: "✓"; color: "white"; font.pixelSize: 13; font.weight: Font.Bold
        }
    }
    contentItem: Text {
        text: kc.text
        font: kc.font
        color: win.cInk
        opacity: kc.enabled ? 1 : 0.4
        leftPadding: kc.indicator.width + kc.spacing
        verticalAlignment: Text.AlignVCenter
    }
}
