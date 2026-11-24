import QtQuick
import QtQuick.Controls

// Schalter im Kit-Control-Stil (Petrol, wenn an)
Switch {
    id: ks
    implicitHeight: 28
    indicator: Rectangle {
        implicitWidth: 40; implicitHeight: 22
        x: ks.leftPadding
        anchors.verticalCenter: parent.verticalCenter
        radius: 11
        color: ks.checked ? win.cAcc : "#262b33"
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
