"""Fehler- und Warncodes des Sintratec Kit (aus der Sintratec-Fehlerliste, übersetzt).

FW = vom Kit gemeldet, Central = nur von Central erzeugt (hier nur zur Vollständigkeit).
"""
CODES = {
    1: ("FW", "Fehler", "Thermistoren uneinig", "Zwei redundante Thermistoren weichen stark voneinander ab. Einer ist evtl. defekt."),
    2: ("FW", "Fehler", "Pyrometer gestört", "Mit dem Pyrometer (IR-Sensor) stimmt etwas nicht."),
    3: ("FW", "Fehler", "SD-Karte gestört", "Problem mit der SD-Karte im Kit. Herausziehen und wieder einstecken."),
    4: ("FW", "Fehler", "SD-Karte fehlt", "Keine SD-Karte im Kit eingesteckt."),
    64: ("Central", "Fehler", "USB-Fehler", "Lesefehler nach dem Senden eines Befehls."),
    79: ("Central", "Fehler", "USB-Fehler", "Dateiübertragung vom Kit abgebrochen."),
    80: ("FW", "Warnung", "Vorrat: Referenzfahrt", "Die Vorratsachse hat ein Problem bei der Referenzfahrt."),
    81: ("FW", "Warnung", "Beschichter: Referenzfahrt", "Die Beschichterachse hat ein Problem bei der Referenzfahrt."),
    82: ("FW", "Warnung", "Bauplattform: Referenzfahrt", "Die Achse der Bauplattform hat ein Problem bei der Referenzfahrt."),
    83: ("FW", "Fehler", "Kammerheizung zu heiß", "Kammerheizung über der zulässigen Temperatur. Druck abgebrochen, um die Maschine zu schützen."),
    84: ("FW", "Fehler", "Heizstrahler zu heiß", "Oberflächenheizung (Lampen) über der zulässigen Temperatur."),
    87: ("FW", "Warnung", "Vorrat leer", "Endschalter des Vorrats im Druck erreicht: zu wenig Pulver für den Rest des Drucks."),
    88: ("FW", "Warnung", "Bauraum voll", "Endschalter des Bauraums im Druck erreicht: nicht genug Bauhöhe für den Rest des Drucks."),
    89: ("FW", "Warnung", "Unbekannter Befehl im Job", "Der Kit fand einen unbekannten Befehl in der Druckdatei und hat den Druck abgebrochen."),
    90: ("FW", "Warnung", "SD-Lesefehler im Druck", "Der Kit konnte die SD-Karte während des Drucks nicht lesen."),
    91: ("FW", "Fehler", "Thermistoren uneinig (Abschaltung)", "Ein redundanter Thermistor meldete eine Abweichung, der Kit hat abgeschaltet."),
    92: ("FW", "Fehler", "Überhitzung Kammer", "Kammerheizung im Betrieb überhitzt, Abschaltung zum Schutz."),
    93: ("FW", "Fehler", "Überhitzung Oberfläche", "Oberflächenheizung im Betrieb überhitzt, Abschaltung zum Schutz."),
    94: ("FW", "Warnung", "Pyrometer-Fehler", "Das Pyrometer hatte im Betrieb einen Fehler."),
    95: ("FW", "Warnung", "Laserschlüssel aus", "Der Laserschlüssel steht auf Aus."),
    96: ("FW", "Fehler", "Beschichter klemmt", "Der Pulverbeschichter steckt fest."),
    99: ("FW", "Fehler", "Laser nicht kalibriert", "Der Laser ist nicht kalibriert oder die Kalibrierdaten fehlen."),
    100: ("FW", "Fehler", "Laser nicht kalibriert (Druckstart)", "Laser nicht kalibriert oder Kalibrierdaten verloren, Druck abgebrochen."),
    109: ("FW", "Warnung", "Temperaturregelung zurückgesetzt", "Die Temperaturregelung war lange nicht aktiv und wurde zurückgesetzt."),
    112: ("Central", "Warnung", "Chip-ID nicht erkannt", "Central kann die Lizenzdatei nicht lesen."),
}


def describe(code: int) -> dict:
    src, kind, title, text = CODES.get(code, ("?", "Unbekannt", f"Code {code}", "Nicht in der Sintratec-Liste."))
    return {"code": code, "source": src, "kind": kind, "title": title, "text": text}
