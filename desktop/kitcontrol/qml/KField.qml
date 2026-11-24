import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

TextField {
    id: kf
    implicitHeight: 36
    color: win.cInk
    font.pixelSize: 13
    selectByMouse: true
    placeholderTextColor: "#59606b"
    leftPadding: 10; rightPadding: 10
    background: Rectangle {
        radius: 8
        color: kf.readOnly ? "#111418" : "#0f1215"
        border.color: kf.activeFocus ? win.cAcc : win.cLine
        border.width: 1
    }
}
