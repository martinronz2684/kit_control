import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

TextField {
    id: kf
    // nur echte Eingaben melden (nicht schon beim Verlassen des Feldes)
    property bool edited: false
    signal userChanged()
    onTextEdited: edited = true
    onEditingFinished: if (edited) { edited = false; userChanged() }
    implicitHeight: 36
    color: win.cInk
    font.pixelSize: 13
    selectByMouse: true
    placeholderTextColor: win.cDim
    leftPadding: 10; rightPadding: 10
    background: Rectangle {
        radius: 8
        color: kf.readOnly ? win.cField : win.cSide
        border.color: kf.activeFocus ? win.cAcc : win.cLine
        border.width: 1
    }
}
