import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Kopplung mit dem Kit: Am Kit-Display erscheint ein 6-stelliger Code, der hier eingegeben wird.
// Öffnet sich von selbst, sobald der Pi „nicht gekoppelt“ meldet (backend.pairInfo.state).
Popup {
    id: pd
    objectName: "pairPop"
    anchors.centerIn: parent
    width: 520
    modal: true
    padding: 26
    closePolicy: Popup.NoAutoClose
    background: GlassBg {}
    Overlay.modal: Backdrop {}

    readonly property var info: backend.pairInfo || ({})
    readonly property string st: info.state || "none"
    readonly property bool busy: st === "starting" || st === "confirming"
    property int left: 0
    property string code: ""

    function sync() {
        if (["starting", "code", "confirming", "error"].indexOf(st) >= 0) { if (!opened) open() }
        else if (opened) close()
        if (st === "code" && !busy) Qt.callLater(function () { digits.forceActiveFocus() })
        if (st === "code" && info.error) code = ""
    }
    onStChanged: sync()
    onInfoChanged: sync()
    Component.onCompleted: sync()
    onOpened: code = ""

    Timer {
        interval: 500; repeat: true; running: pd.opened && pd.info.expires !== undefined
        triggeredOnStart: true
        onTriggered: pd.left = Math.max(0, Math.round(pd.info.expires - Date.now() / 1000))
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 14

        RowLayout {
            spacing: 12
            Rectangle {
                width: 40; height: 40; radius: 12; color: win.cSel
                Item {                                   // Schloss
                    anchors.centerIn: parent; width: 20; height: 22
                    Rectangle { x: 4; y: 1; width: 12; height: 14; radius: 6; color: "transparent"; border.color: win.cAcc; border.width: 2.2 }
                    Rectangle { x: 1; y: 9; width: 18; height: 13; radius: 3.5; color: win.cAcc
                        Rectangle { anchors.centerIn: parent; width: 3; height: 5; radius: 1.5; color: win.cSel } }
                }
            }
            ColumnLayout {
                spacing: 2; Layout.fillWidth: true
                Text { text: win.t("Mit dem Kit koppeln"); color: win.cInk; font.pixelSize: 19; font.weight: Font.DemiBold }
                Text { text: pd.info.kit ? win.t("Kit: ") + pd.info.kit + win.t(" · dieser PC: ") + pd.info.pc : ""; color: win.cMut; font.pixelSize: 12
                       Layout.fillWidth: true; elide: Text.ElideRight }
            }
        }

        Body {
            color: win.cMut; font.pixelSize: 13
            text: pd.st === "starting" ? win.t("Frage am Kit eine Kopplung an …")
                : pd.st === "error" ? win.t("Die Kopplung hat nicht geklappt.")
                : win.t("Damit nicht jeder im Netzwerk den Kit bedienen kann, koppelt sich jeder PC einmal mit ihm. Am Kit-Display steht jetzt ein 6-stelliger Code – gib ihn hier ein.")
        }

        // Sechs Ziffernfelder (ein unsichtbares Eingabefeld dahinter)
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 76
            visible: pd.st === "code" || pd.st === "confirming"
            TextInput {
                id: digits
                anchors.fill: parent
                opacity: 0
                text: pd.code
                maximumLength: 6
                inputMethodHints: Qt.ImhDigitsOnly
                validator: RegularExpressionValidator { regularExpression: /[0-9]{0,6}/ }
                enabled: pd.st === "code"
                onTextEdited: {
                    pd.code = text
                    if (text.length === 6) backend.pairConfirm(text)
                }
                Keys.onEscapePressed: backend.pairCancel()
            }
            Row {
                anchors.centerIn: parent
                spacing: 10
                Repeater {
                    model: 6
                    Rectangle {
                        readonly property bool cur: digits.activeFocus && index === Math.min(pd.code.length, 5) && pd.st === "code"
                        width: 58; height: 72; radius: 12
                        color: win.cField
                        border.width: cur ? 2 : 1
                        border.color: pd.info.error && pd.st === "code" && pd.code.length === 0 ? win.cRed : (cur ? win.cAcc : win.cLine)
                        Behavior on border.color { ColorAnimation { duration: 120 } }
                        Text {
                            anchors.centerIn: parent
                            text: pd.code.length > index ? pd.code[index] : ""
                            color: win.cInk; font.pixelSize: 34; font.weight: Font.Light
                        }
                        Rectangle {               // blinkender Cursor im aktuellen Feld
                            visible: parent.cur && pd.code.length === index
                            anchors.centerIn: parent; width: 2; height: 30; color: win.cAcc
                            SequentialAnimation on opacity { loops: Animation.Infinite; running: parent.visible
                                NumberAnimation { to: 0; duration: 500 } NumberAnimation { to: 1; duration: 500 } }
                        }
                    }
                }
            }
            MouseArea { anchors.fill: parent; onClicked: digits.forceActiveFocus() }
        }

        // Zustand: Restzeit, Fehler
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: msgTxt.implicitHeight + 20
            radius: 10
            visible: !!pd.info.error || pd.st === "confirming"
            color: pd.st === "confirming" ? win.cInfoBg : win.cErrBg
            border.color: pd.st === "confirming" ? win.cInfoLine : win.cErrLine
            Text {
                id: msgTxt
                anchors.fill: parent; anchors.margins: 10
                wrapMode: Text.WordWrap; font.pixelSize: 13
                color: pd.st === "confirming" ? win.cInfoInk : win.cErrInk
                text: pd.st === "confirming" ? win.t("Prüfe den Code …") : win.t(pd.info.error || "")
            }
        }
        RowLayout {
            Layout.fillWidth: true
            visible: pd.st === "code"
            Rectangle {
                Layout.fillWidth: true; height: 4; radius: 2; color: win.cTrack
                Rectangle { height: 4; radius: 2; color: win.cAcc; width: parent.width * Math.min(1, pd.left / 120)
                    Behavior on width { NumberAnimation { duration: 450 } } }
            }
            Text {
                text: win.t("noch ") + Math.floor(pd.left / 60) + ":" + ("0" + (pd.left % 60)).slice(-2)
                color: win.cMut; font.pixelSize: 12
            }
        }

        Body {
            visible: pd.st === "error"
            color: win.cMut; font.pixelSize: 12
            text: win.t("Koppeln geht nur, wenn der Kit nicht druckt, nicht vorheizt und kein Pulver vorbereitet. Wurde die Anfrage am Kit abgelehnt, ist dieser PC dort 10 Minuten gesperrt.")
        }

        RowLayout {
            Layout.fillWidth: true; spacing: 10
            Text {
                Layout.fillWidth: true
                visible: pd.st === "code" && pd.left === 0
                text: win.t("Code abgelaufen")
                color: win.cErrInk; font.pixelSize: 12
            }
            Item { Layout.fillWidth: true; visible: !(pd.st === "code" && pd.left === 0) }
            KButton { text: win.t("Später"); kind: "ghost"; enabled: pd.st !== "confirming"; onClicked: backend.pairCancel() }
            KButton {
                visible: pd.st === "error" || (pd.st === "code" && pd.left === 0)
                text: win.t("Neuen Code anfordern")
                onClicked: backend.pairStart()
            }
            KButton {
                visible: pd.st === "code" || pd.st === "confirming" || pd.st === "starting"
                text: win.t("Koppeln"); kind: "pri"
                enabled: pd.st === "code" && pd.code.length === 6 && pd.left > 0
                onClicked: backend.pairConfirm(pd.code)
            }
        }
    }
}
