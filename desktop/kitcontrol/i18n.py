"""Übersetzung Deutsch → Englisch.

Die Oberfläche ist deutsch geschrieben; jeder sichtbare Text läuft in QML durch win.t("…"). Bei Englisch wird er
hier nachgeschlagen: erst genau (EN), dann Meldungen mit Zahlen/Namen über Muster (PATTERNS) und Anfänge
(PREFIXES). Was nicht gefunden wird, bleibt deutsch – nie leer.
"""
from __future__ import annotations

import re

EN: dict[str, str] = {
    # Navigation, Fenster
    "Platzieren": "Place", "Parameter": "Parameters", "Vorschau": "Preview", "Pulver": "Powder", "Drucken": "Print",
    "Bauteile laden, anordnen und ausrichten": "Load, arrange and orient parts",
    "Pulverprofil wählen oder eigenes anlegen": "Choose a powder profile or create your own",
    "Slicen und Schichten prüfen": "Slice and check the layers",
    "Pulver vorbereiten und laden": "Prepare and load powder",
    "Job zum Kit senden und Druck live verfolgen": "Send the job to the Kit and follow the print live",
    " min": " min", "Weiter": "Next", "Version ": "Version ", "Einstellungen": "Settings",
    "Neue Version ": "New version ", " verfügbar.": " available.", "Lädt …": "Downloading …",
    "Jetzt aktualisieren": "Update now", "Bitte bestätigen": "Please confirm", "Abbrechen": "Cancel",
    "Kein Kit gewählt": "No Kit selected", "Verbinde …": "Connecting …", "Kit verbunden": "Kit connected",
    "Pi ohne Kit": "Pi without Kit", "Unter „Drucken“ verbinden": "Connect under “Print”",
    "Oberfläche": "Surface", "Kammer": "Chamber", "Aufheizen: noch ": "Heating up: ",
    # Dateidialoge
    "Bauteile hinzufügen": "Add parts", "3D-Modelle (*.stl *.STL)": "3D models (*.stl *.STL)",
    "Projekt öffnen": "Open project", "Kit-Control-Projekt (*.kcp)": "Kit Control project (*.kcp)",
    "Projekt speichern": "Save project", "Bauraum als STL exportieren": "Export build volume as STL",
    "STL (*.stl)": "STL (*.stl)", "Druckdatei speichern": "Save print file", "Druckdatei (*.bin)": "Print file (*.bin)",
    "Profil importieren": "Import profile", "Pulverprofil (*.json)": "Powder profile (*.json)",
    "Profil exportieren": "Export profile",
    # Parameter
    " (eigen)": " (custom)", "Materialien": "Materials", "+ Neues Material": "+ New material",
    "Neues Material": "New material", "Vorlage": "Template", "auf Basis ": "based on ",
    " µm · Schraffur ": " µm · hatch ", " µm · Kontur ": " µm · contour ", "Importieren": "Import",
    "Exportieren": "Export", "Profilordner öffnen": "Open profile folder", "Name": "Name",
    "Vorlage aus Sintratec Central – Werte unverändert übernommen. Zum Anpassen als eigenes Profil speichern; die Felder lassen sich dafür bearbeiten.":
        "Template from Sintratec Central – values taken over unchanged. To adjust, save it as a custom profile; the fields can be edited for that.",
    "Slicer (wie Central „Print Parameters“)": "Slicer (like Central “Print Parameters”)",
    "Schichthöhe": "Layer height", "Anzahl Perimeter": "Perimeters", "Perimeter-Versatz": "Perimeter offset",
    "Schraffur-Versatz": "Hatch offset", "Schraffur-Abstand": "Hatch spacing", "Mindestvektorlänge": "Minimum vector length",
    "Schraffurwinkel je Schicht (reihum)": "Hatch angle per layer (in turn)",
    "Originalkontur zusätzlich lasern": "Also laser the original contour",
    "Strategien (leer/0 = wie Central)": "Strategies (empty/0 = like Central)",
    "Winkelschritt je Schicht": "Angle step per layer", "Liste oben (z. B. 67)": "list above (e.g. 67)",
    "Schachbrett-Felder (mm)": "Checkerboard islands (mm)", "aus (z. B. 5)": "off (e.g. 5)",
    "Hautschichten oben/unten": "Skin layers top/bottom", "aus (z. B. 3)": "off (e.g. 3)",
    "Schraffur-Abstand im Kern (µm)": "Core hatch spacing (µm)", "wie oben (z. B. 240)": "as above (e.g. 240)",
    "Schwundausgleich X (%)": "Shrink compensation X (%)", "Schwundausgleich Y (%)": "Shrink compensation Y (%)",
    "Schwundausgleich Z (%)": "Shrink compensation Z (%)", "Kontur vor Füllung": "Contour before infill",
    "Laserwege optimieren": "Optimize laser paths", "Dünne Wände erhalten": "Keep thin walls",
    "Temperaturen (am Kit vor dem Druck eingestellt)": "Temperatures (set on the Kit before printing)",
    "Oberfläche Aufheizen": "Surface heat-up", "Kammer Aufheizen": "Chamber heat-up",
    "Oberfläche Druck": "Surface print", "Kammer Druck": "Chamber print",
    "Laser (leer = Wert am Kit lassen)": "Laser (empty = keep the Kit's value)",
    "Geschwindigkeit Füllung": "Infill speed", "unverändert": "unchanged", "Geschwindigkeit Kontur": "Contour speed",
    "Änderungen legen automatisch ein eigenes Profil an.": "Changes automatically create a custom profile.",
    "Änderungen werden sofort gespeichert.": "Changes are saved immediately.",
    "Als neues Profil speichern": "Save as new profile", "Löschen": "Delete", "Profil „": "Delete profile “",
    "“ löschen?": "”?",
    # Platzieren
    "Oben": "Top", "Vorne": "Front", "Rechts": "Right", "Links": "Left",
    "Bauteil ziehen: verschieben (von oben auf der Platte, von vorne/seitlich auch in der Höhe) · daneben ziehen: drehen · rechte Maustaste: schieben · Mausrad: zoomen":
        "Drag a part: move it (from above on the plate, from the front/side also in height) · drag beside: rotate · right mouse button: pan · wheel: zoom",
    "STL-Dateien hierher ziehen": "Drop STL files here", "oder über „Hinzufügen“ auswählen": "or choose them with “Add”",
    "Hinzufügen …": "Add …", "Bauteile (": "Parts (", "Bauhöhe ": "Build height ", " mm · Packdichte ": " mm · packing density ",
    "Rückgängig": "Undo", "Wiederholen": "Redo",
    "Position gesperrt – Auto-Anordnen bewegt dieses Teil nicht": "Position locked – auto-arrange does not move this part",
    "Lage gesperrt – wird nicht gedreht": "Orientation locked – will not be rotated",
    "Abbrechen (": "Cancel (", "Auto-Anordnen": "Auto-arrange", "Ausgewählt: ": "Selected: ",
    "Position X": "Position X", "Position Y": "Position Y", "Drehen (Gieren)": "Rotate (yaw)", "Skalierung": "Scale",
    "Kippen (Rollen)": "Tilt (roll)", "Kippen (Nicken)": "Tilt (pitch)", "Höhe über Platte": "Height above plate",
    " mm": " mm", "90° drehen": "Rotate 90°", "Auf Fläche legen": "Lay flat", "Position sperren": "Lock position",
    "Lage sperren": "Lock orientation", "Duplizieren": "Duplicate", "Entfernen": "Remove", "Alles entfernen": "Remove all",
    "Alle Bauteile aus dem Bauraum entfernen?": "Remove all parts from the build volume?", "STL exportieren": "Export STL",
    "Packt alle Teile möglichst niedrig und dicht in den idealen Druckbereich (":
        "Packs all parts as low and dense as possible into the ideal print area (",
    " mm) – auch übereinander. SLS-Regeln gelten immer: Mindestabstand in alle Richtungen, Abstand zum Rand, nichts verhakt sich. Jedes Teil wird erst so tief wie möglich gepackt und dann in die beste Lage nach SLS-Regeln gedreht, wo das keine Bauhöhe kostet. Gesperrte Teile bleiben, wie sie sind.":
        " mm) – also on top of each other. SLS rules always apply: minimum spacing in every direction, distance to the edge, nothing interlocks. Every part is first packed as low as possible and then turned into its best orientation by SLS rules wherever that costs no build height. Locked parts stay as they are.",
    " Teile sind gesperrt (🔒) und werden nicht bewegt bzw. gedreht – das kann viel Bauhöhe kosten.":
        " parts are locked (🔒) and will not be moved or rotated – this can cost a lot of build height.",
    "Sperren aufheben": "Unlock all", "Abstand zwischen Teilen": "Spacing between parts", "Abstand zum Rand": "Distance to edge",
    "Gründlichkeit": "Thoroughness", "Schnell": "Fast", "Gründlich": "Thorough", "Sehr gründlich": "Very thorough",
    "Teile drehen erlaubt": "Rotating parts allowed", "Nur ausgewähltes Teil": "Selected part only",
    "“ auffüllen": "”", "Mit Kopien auffüllen": "Fill with copies",
    "Das ausgewählte (sonst das erste) Teil so oft kopieren, wie es in den idealen Bereich passt":
        "Copy the selected (otherwise the first) part as often as it fits into the ideal area",
    "Flach": "Flat", "Alles nebeneinander auf die Platte legen": "Put everything side by side on the plate",
    "Anordnen": "Arrange",
    # Pulver
    "Pulver laden": "Load powder", "Bauhöhe": "Build height",
    "Vorrat nur so weit füllen, wie der Job braucht: Bauhöhe + 5 mm Puffer.": "Only fill the feed as far as the job needs: build height + 5 mm buffer.",
    "Nach dem Slicen steht hier, wie viel Pulver der Job braucht (Bauhöhe + 5 mm).": "After slicing, this shows how much powder the job needs (build height + 5 mm).",
    "Bauplattform": "Build platform", "▲  hoch": "▲  up", "▼  runter": "▼  down", "Vorrat": "Feed",
    "Schrittweite": "Step", "Pulvervorbereitung": "Powder preparation", "Starten": "Start", "Beenden": "Stop",
    "Pulver auftragen (0,15 mm)": "Apply powder (0.15 mm)",
    "Nicht mit dem Kit Control verbunden – unter „Drucken“ verbinden.": "Not connected to Kit Control – connect under “Print”.",
    "Während des Drucks gesperrt.": "Locked while printing.",
    "Fahren wie am Display. Die Freigabe für die Bedienung vom PC erfolgt am Pi (KIT_REMOTE=1).":
        "Moves like on the display. Control from the PC is enabled on the Pi (KIT_REMOTE=1).",
    # Kalibrierung
    "Laser-Kalibrierung": "Laser calibration", "Werte im Kit erscheinen nach dem Verbinden.": "The Kit's values appear after connecting.",
    "Im Kit: X ": "In the Kit: X ", "Skalierung konnte nicht gelesen werden": "Scaling could not be read",
    "\\nWerkswerte: X ": "\\nFactory values: X ", "\nWerkswerte: X ": "\nFactory values: X ",
    "Muster": "Pattern", "Mitte": "Center", "Aus": "Off",
    "Kalibrierteil außen messen (mm) – Nut zeigt nach hinten (Y)": "Measure the calibration part outside (mm) – the groove points to the back (Y)",
    "Soll": "Target", "Ist": "Actual",
    "Mehr als ±5 % – das erlaubt auch Central nicht. Bitte mechanisch nachjustieren.": "More than ±5 % – Central does not allow this either. Please readjust mechanically.",
    "Auf den Kit schreiben": "Write to the Kit", "Kalibrierteil zum Drucken hinzufügen": "Add calibration part for printing",
    # Vorschau
    "Slicen läuft …": "Slicing …", "Slicen fehlgeschlagen": "Slicing failed", "Noch nicht geslict": "Not sliced yet",
    "Mit „Slicen“ entsteht die Druckdatei – danach lassen sich alle Schichten durchblättern.": "“Slice” creates the print file – afterwards you can browse all layers.",
    "Schicht ": "Layer ", "Druckdatei": "Print file", "Profil: ": "Profile: ", "Neu slicen": "Slice again", "Slicen": "Slice",
    "Schichten": "Layers", "Druckzeit (geschätzt)": "Print time (estimated)", "Laserweg": "Laser path", "Vektoren": "Vectors",
    "Rechenzeit": "Computing time", "Ohne Aufheizen. Berechnet mit ": "Without heat-up. Calculated with ", " mm/s": " mm/s",
    ", an ": ", adjusted to ", " echten Drucken angepasst.": " real prints.", " – wird mit jedem Druck genauer.": " – gets more accurate with every print.",
    "Druckdatei speichern …": "Save print file …", "Weiter zum Drucken": "Continue to printing",
    # Drucken
    "Sucht …": "Searching …", "Suchen": "Search", "IP-Adresse des Pi": "IP address of the Pi", "Verbinden": "Connect",
    "Job senden": "Send job", " Schichten · ": " layers · ", " mm · ca. ": " mm · approx. ",
    "Noch kein geslicter Job – unter „Vorschau“ slicen.": "No sliced job yet – slice under “Preview”.",
    "Nur übertragen": "Transfer only", "Übertragen und starten": "Transfer and start",
    "Job zum Kit übertragen und den Druck sofort starten? Der Kit heizt dann auf.": "Transfer the job to the Kit and start printing right away? The Kit will heat up.",
    "Jobs am Kit": "Jobs on the Kit", "Aktualisieren": "Refresh", "“ jetzt drucken?": "” now?",
    "Nicht verbunden": "Not connected", "Kit nicht am Pi angeschlossen": "Kit not connected to the Pi",
    "Schicht": "Layer", "Druckzeit": "Print time", "Aufheizen noch": "Heating up", "Restzeit (geschätzt)": "Remaining (estimated)",
    "Job": "Job", "Hier erscheint während des Drucks die aktuelle Schicht": "The current layer appears here while printing",
    "Soll Druck ": "Print target ", "Laser ": "Laser ", "Steuerung": "Control", "Aufheizen": "Heat up", "Heizen aus": "Heating off",
    "Zum Abkühlen springen": "Skip to cool-down",
    "Sintern beenden und abkühlen? Der Druck endet nach der aktuellen Schicht.": "Stop sintering and cool down? The print ends after the current layer.",
    "Druck abbrechen": "Cancel print", "Druck wirklich abbrechen?": "Really cancel the print?",
    "Temperaturprotokolle": "Temperature logs", "Meldungen": "Messages", "Keine Fehler oder Warnungen": "No errors or warnings",
    # 3D-Ansicht
    "Bauraum ": "Build volume ", "hellgrau: idealer Bereich ": "light grey: ideal area ", " mm · bläulich: Bauraum ": " mm · bluish: build volume ",
    # Einstellungen
    "Schließen": "Close", "Sprache": "Language", "Idealer Druckbereich": "Ideal print area",
    "Bereich mit der gleichmäßigsten Temperatur. Auto-Anordnen packt hier hinein, Teile außerhalb werden markiert. Bauraum: 110 × 110 mm, bis 130 mm hoch.":
        "Area with the most even temperature. Auto-arrange packs into it, parts outside are marked. Build volume: 110 × 110 mm, up to 130 mm high.",
    "Breite und Tiefe": "Width and depth", "Höhe": "Height", "Standard": "Default", "Auto-Anordnen – Vorgaben": "Auto-arrange – defaults",
    "Heizstrahler-Leistung (Experte)": "Heater lamp power (expert)",
    "Wirkt sofort und bleibt im Kit gespeichert. Der Kit kann den Wert nicht zurückmelden – angezeigt wird, was der Pi zuletzt gesendet hat. Tipp: eine Lampe so einstellen, dass sie gleich hell leuchtet wie eine noch originale.":
        "Takes effect immediately and stays stored in the Kit. The Kit cannot report the value back – shown is what the Pi sent last. Tip: set a lamp so it glows as bright as one that is still original.",
    "original": "original", "Senden": "Send",
    "Senden geht nur mit verbundenem Kit und nicht während des Drucks (Freigabe am Pi: KIT_REMOTE=1).": "Sending only works with a connected Kit and not while printing (enabled on the Pi: KIT_REMOTE=1).",
    "Druckzeit-Schätzung": "Print time estimate", "Lasergeschwindigkeit, wenn das Profil keine vorgibt": "Laser speed if the profile sets none",
    "mm/s": "mm/s", "Lernwerte zurücksetzen": "Reset learned values", "Gelernt aus ": "Learned from ", " Drucken, Faktor ": " prints, factor ",
    ". Die Geschwindigkeit übernimmt Kit Control auch vom Kit, sobald einer verbunden ist.": ". Kit Control also takes the speed from the Kit as soon as one is connected.",
    "Beim Start": "On start", "Nach Updates suchen": "Check for updates", "Mit dem zuletzt verwendeten Kit verbinden": "Connect to the last used Kit",
    "Ordner und Info": "Folders and info", "Profile": "Profiles", "Kit Control ": "Kit Control ",
    " · github.com/martinronz2684/kit_control": " · github.com/martinronz2684/kit_control",
    # Meldungen aus Python (genau)
    "Bitte STL-Dateien wählen": "Please choose STL files", "Projekt gespeichert": "Project saved", "STL exportiert": "STL exported",
    "Profil gespeichert": "Profile saved", "Profil exportiert": "Profile exported", "Bitte zuerst ein Bauteil hinzufügen": "Please add a part first",
    "Druckdatei gespeichert": "Print file saved", "Kein Kit Control gewählt": "No Kit Control selected", "Bitte zuerst slicen": "Please slice first",
    "Übertrage Job …": "Transferring job …", "Job übertragen – Druck startet": "Job transferred – print starting",
    "Job liegt in der Bibliothek am Kit": "Job is in the library on the Kit", "Ausgeführt": "Done", "Fehler": "Error",
    "Keine Teile gesperrt": "No parts locked", "Druckzeit-Lernwerte zurückgesetzt": "Learned print time values reset",
    "Nicht alle Bauteile passen in den idealen Druckbereich": "Not all parts fit into the ideal print area",
    "Kalibrierteil hinzugefügt (40 × 40 × 5 mm, Nut hinten = Y) – drucken, außen messen, unter „Pulver“ eintragen":
        "Calibration part added (40 × 40 × 5 mm, groove at the back = Y) – print it, measure outside, enter under Settings",
    "Keine Bauteile im Bauraum": "No parts in the build volume", "Profil braucht einen Namen": "A profile needs a name",
    "Heizstrahler 0–100 %": "Heater lamps 0–100 %", "Winkelschritt 1–179°": "Angle step 1–179°",
    "Schachbrettfelder 2–50 mm (0 = aus)": "Checkerboard islands 2–50 mm (0 = off)", "Hautschichten 0–20": "Skin layers 0–20",
    "Kern-Schraffurabstand muss ≥ Schraffur-Abstand und ≤ 1000 µm sein": "Core hatch spacing must be ≥ hatch spacing and ≤ 1000 µm",
    "Schwundausgleich höchstens ±5 %": "Shrink compensation at most ±5 %",
    "Vorlagen sind schreibgeschützt – bitte als eigenes Profil speichern": "Templates are read-only – please save as a custom profile",
    "Vorlagen lassen sich nicht löschen": "Templates cannot be deleted", "Keine Kit-Control-Projektdatei": "Not a Kit Control project file",
    "Anordnen abgebrochen – Anordnung unverändert": "Arranging cancelled – arrangement unchanged",
    "Teile passen nicht in den idealen Bereich – Abstand verringern oder Teile verkleinern": "Parts do not fit into the ideal area – reduce the spacing or scale the parts down",
    "Während des Drucks gesperrt": "Locked while printing",
    # Startseite, Meldungen, Auswahl, Schnitt, Verlauf, Design
    "Willkommen bei Kit Control": "Welcome to Kit Control",
    "Neues Projekt beginnen oder ein zuletzt geöffnetes fortsetzen.": "Start a new project or continue a recent one.",
    "Bauteile hinzufügen …": "Add parts …", "Projekt öffnen …": "Open project …", "Leeres Projekt": "Empty project",
    "Zuletzt geöffnet": "Recently opened", " Teile": " parts",
    "Tipp: STL-Dateien oder Projekte (.kcp) einfach ins Fenster ziehen.": "Tip: simply drop STL files or projects (.kcp) into the window.",
    "Leeren": "Clear", "Keine Meldungen": "No messages", " Teile ausgewählt": " parts selected",
    "Kein Bauteil ausgewählt": "No part selected", "Position entsperren": "Unlock position", "Lage entsperren": "Unlock orientation",
    "Alles auswählen": "Select all", "Entf": "Del", "Schnitt": "Section",
    "Füllung je Höhe – orange: leere Schicht": "Fill per height – orange: empty layer",
    "Schnittebene: alles darüber ausblenden": "Section plane: hide everything above",
    " Teile ausgewählt – Tasten wirken auf alle": " parts selected – buttons act on all",
    "Fertig ca. (jetzt gestartet)": "Done approx. (if started now)", " Uhr": "",
    "Druckzeit ohne Aufheizen, Fertig-Uhrzeit mit ca. 1,5 h Aufheizen. Berechnet mit ": "Print time without heat-up, finish time includes approx. 1.5 h heat-up. Calculated with ",
    "Verlauf": "History", "Noch keine Drucke aufgezeichnet – beendete Drucke erscheinen hier.": "No prints recorded yet – finished prints appear here.",
    " Schichten": " layers", "abgebrochen bei ": "cancelled at ", "Design": "Theme", "Dunkel": "Dark", "Hell (Werkstatt)": "Light (workshop)",
    "Windows-Benachrichtigungen (Druck fertig, Aufheizen fertig, Fehler)": "Windows notifications (print done, heat-up done, errors)",
    "Temperaturverlauf erscheint nach dem Verbinden": "Temperature history appears after connecting",
    "Aufheizen fertig": "Heat-up done", "Druck fertig": "Print finished", "Druck beendet": "Print ended", "Fehler am Kit": "Error on the Kit",
}

# Meldungen mit Zahlen/Namen: (regulärer Ausdruck, englische Vorlage)
PATTERNS: list[tuple[re.Pattern, str]] = [(re.compile(a), b) for a, b in [
    (r"^Angeordnet( – (\d+) gesperrte Teile wurden nicht bewegt)?: Bauhöhe ([\d.]+) mm, Packdichte ([\d.]+) %, leere Schichten ([\d.]+) mm \((\d+) Durchläufe\)(.*)$",
     None),
    (r"^(.+): außerhalb des idealen Druckbereichs \((.+)\)$", r"\1: outside the ideal print area (\2)"),
    (r"^(.+) und (.+) überlappen$", r"\1 and \2 overlap"),
    (r"^Sperre bei (\d+) Teilen aufgehoben$", r"Lock removed from \1 parts"),
    (r"^Profil „(.+)“ importiert$", r"Profile “\1” imported"),
    (r"^Angeordnet, aber höher als der ideale Bereich \((.+) mm\)$", r"Arranged, but higher than the ideal area (\1 mm)"),
    (r"^(.+) fehlt$", r"\1 missing"),
    (r"^Temperatur (.+): 0–(.+) °C$", r"Temperature \1: 0–\2 °C"),
    (r"^Lasergeschwindigkeit (.+) mm/s$", r"Laser speed \1 mm/s"),
    (r"^(\d+) Kopien hinzugefügt$", r"\1 copies added"),
    (r"^(.+): der Druck startet$", r"\1: the print is starting"),
    (r"^Kein Platz für weitere Kopien$", "No room for more copies"),
]]

PREFIXES: list[tuple[str, str]] = [
    ("Anordnen fehlgeschlagen: ", "Arranging failed: "), ("Speichern fehlgeschlagen: ", "Saving failed: "),
    ("Projekt lässt sich nicht öffnen: ", "Cannot open project: "), ("Export fehlgeschlagen: ", "Export failed: "),
    ("Import fehlgeschlagen: ", "Import failed: "), ("Senden fehlgeschlagen: ", "Sending failed: "),
    ("Job übertragen, aber nicht gestartet: ", "Job transferred but not started: "),
    ("Update fehlgeschlagen: ", "Update failed: "), ("Am Kit Control ist die Bedienung vom PC aus gesperrt", "Control from the PC is locked on Kit Control"),
    ("Verbindung fehlgeschlagen: ", "Connection failed: "),
]


def _arranged(m: re.Match) -> str:
    lk = f" – {m.group(2)} locked parts were not moved" if m.group(1) else ""
    tail = m.group(7) or ""
    tail = tail.replace(" – Ausrichtungsregeln gelockert, weil die Teile sonst nicht passen",
                        " – orientation rules relaxed because the parts would not fit otherwise")
    return (f"Arranged{lk}: build height {m.group(3)} mm, packing density {m.group(4)} %, "
            f"empty layers {m.group(5)} mm ({m.group(6)} passes){tail}")


def translate(text: str, lang: str = "en") -> str:
    """Text in die gewählte Sprache; unbekannte Texte bleiben unverändert."""
    if lang != "en" or not text:
        return text
    if text in EN:
        return EN[text]
    for rx, rep in PATTERNS:
        m = rx.match(text)
        if m:
            return _arranged(m) if rep is None else rx.sub(rep, text)
    for de, en in PREFIXES:
        if text.startswith(de):
            rest = text[len(de):]
            return en + translate(rest, lang)
    return text
