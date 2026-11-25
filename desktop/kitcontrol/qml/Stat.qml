import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: stat
    property string label
    property string value
    property color tint: win.cInk
    spacing: 2
    Layout.fillWidth: true
    Layout.preferredWidth: 1
    Caption { text: stat.label; elide: Text.ElideRight; Layout.fillWidth: true }
    Text { text: stat.value; color: stat.tint; font.pixelSize: 22; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
}
