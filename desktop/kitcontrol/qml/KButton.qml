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
        color: !kb.enabled ? win.cRow
             : kb.kind === "pri" ? (kb.down ? win.cAcc2 : (kb.hovered ? "#2ba3c9" : win.cAcc))
             : kb.kind === "red" ? (kb.down ? "#b8373b" : win.cRed)
             : kb.kind === "hot" ? (kb.down ? "#d9704a" : win.cHeat)
             : kb.kind === "ghost" ? (kb.hovered ? win.cTrack : "transparent")
             : (kb.down ? win.cTrack : (kb.hovered ? win.cHover : win.cPanel2))
        border.color: kb.kind === "normal" || kb.kind === "ghost" ? win.cLine : "transparent"
        border.width: 1
        // Hauptknopf mit leichtem Verlauf und heller Oberkante
        gradient: kb.kind === "pri" && kb.enabled && !kb.down ? priGrad : null
        Gradient {
            id: priGrad
            GradientStop { position: 0.0; color: kb.hovered ? "#3bb4d8" : "#2fa6cc" }
            GradientStop { position: 1.0; color: kb.hovered ? "#2394b9" : "#1f86aa" }
        }
        Rectangle {
            visible: kb.kind === "pri" && kb.enabled
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
            anchors.margins: 1; anchors.leftMargin: 8; anchors.rightMargin: 8
            height: 1; color: "#40ffffff"
        }
        Behavior on color { ColorAnimation { duration: 120 } }
    }
    contentItem: Text {
        text: kb.text; font: kb.font
        color: !kb.enabled ? win.cDim : (kb.kind === "normal" || kb.kind === "ghost" ? win.cInk : "white")
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
}
