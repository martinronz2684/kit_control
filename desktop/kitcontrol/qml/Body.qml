import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Text {
    color: win.cInk
    font.pixelSize: 13
    wrapMode: Text.WordWrap
    // in Layouts: volle Breite nehmen und umbrechen, statt mit langem Text die Schaltflächen hinauszuschieben
    Layout.fillWidth: true
}
