import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Button {
    id: kb
    property string kind: "normal"      // normal | pri | red | ghost | hot
    implicitHeight: 38
    leftPadding: 16; rightPadding: 16
    font.pixelSize: 13; font.weight: Font.DemiBold
    background: Rectangle {
        radius: 9
        color: !kb.enabled ? "#15181c"
             : kb.kind === "pri" ? (kb.down ? win.cAcc2 : (kb.hovered ? "#2ba3c9" : win.cAcc))
             : kb.kind === "red" ? (kb.down ? "#b8373b" : win.cRed)
             : kb.kind === "hot" ? (kb.down ? "#d9704a" : win.cHeat)
             : kb.kind === "ghost" ? (kb.hovered ? "#1d2228" : "transparent")
             : (kb.down ? "#232830" : (kb.hovered ? "#22272e" : win.cPanel2))
        border.color: kb.kind === "normal" || kb.kind === "ghost" ? win.cLine : "transparent"
        border.width: 1
        Behavior on color { ColorAnimation { duration: 120 } }
    }
    contentItem: Text {
        text: kb.text; font: kb.font
        color: !kb.enabled ? "#4b5059" : (kb.kind === "normal" || kb.kind === "ghost" ? win.cInk : "white")
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
}
