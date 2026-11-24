import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: nf
    property string label
    property string unit
    property string value
    property bool readOnly: false
    signal committed(string v)
    spacing: 4
    Text { text: nf.label; color: win.cMut; font.pixelSize: 12 }
    KField {
        Layout.fillWidth: true
        text: nf.value
        readOnly: nf.readOnly
        onEditingFinished: if (text !== nf.value) nf.committed(text)
        Text {
            anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
            text: nf.unit; color: win.cMut; font.pixelSize: 12
        }
    }
}
