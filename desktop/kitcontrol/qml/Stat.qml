import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    property string label
    property string value
    property color tint: win.cInk
    spacing: 2
    Caption { text: parent.label }
    Text { text: parent.value; color: parent.tint; font.pixelSize: 22; font.weight: Font.DemiBold }
}
