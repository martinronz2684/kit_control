import QtQuick
import QtQuick.Controls

// Schalter im Kit-Control-Stil (Petrol, wenn an)
Switch {
    id: ks
    implicitHeight: 28
    padding: 0
    implicitWidth: 40                   // Breite = Schalter selbst (sonst überdeckt er den Text daneben)
    indicator: Rectangle {
        implicitWidth: 40; implicitHeight: 22
        x: 0
        anchors.verticalCenter: parent.verticalCenter
        radius: 11
        color: ks.checked ? win.cAcc : win.cLine
        border.color: ks.checked ? win.cAcc : "#3a414b"
        Behavior on color { ColorAnimation { duration: 120 } }
        Rectangle {
            x: ks.checked ? parent.width - width - 3 : 3
            anchors.verticalCenter: parent.verticalCenter
            width: 16; height: 16; radius: 8
            color: "white"
            Behavior on x { NumberAnimation { duration: 120 } }
        }
    }
    contentItem: Item {}
}
