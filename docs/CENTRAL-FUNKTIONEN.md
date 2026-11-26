# Funktionsumfang Sintratec Central 1.2.0 → Kit Control

Ermittelt aus den JARs von Central 1.2.0 (Bedienoberfläche, Kit-Modul, Build-Processor, 3D-Toolkit, Framework).
Der Slicer liegt in `desktop/kitslice/`.
Status: ✅ fertig · 🟡 Grundlage da, Oberfläche fehlt · ⬜ offen · ⛔ bewusst nicht übernommen.
Spalte „Pi“ = Touch-Oberfläche am Kit, „PC“ = Kit Control Desktop.

## 1. Platzieren („1. Place“)
| Funktion in Central | Pi | PC | Anmerkung |
|---|---|---|---|
| STL importieren, auch per Drag & Drop | – | 🟡 | `desktop/kitslice/stl.py` (binär + ASCII) |
| Mehrere Bauteile, Kopieren, Löschen, Alles auswählen | – | ⬜ | |
| Verschieben, Drehen (Gieren/Nicken/Rollen), Skalieren, Höhe über Platte | – | ✅ | 3D-Ansicht, drehbar |
| Position zurücksetzen | – | ⬜ | |
| Rückgängig / Wiederholen | – | ⬜ | |
| Automatisch platzieren (Central: 3D-Packung mit Physik-Engine, auch übereinander) | – | ✅ | 3D-Nesting über Höhenkarten im idealen Bereich 90 × 90 × 110 mm, 4 Drehungen; „Flach“ legt alles nebeneinander |
| „Smart rotate“ (günstige Lage berechnen) | – | 🟡 | `Part.lay_flat` (größte Fläche nach unten) |
| Warnungen: außerhalb Bauraum, Überlappung, außerhalb idealem Bereich | – | ✅ | idealer Bereich als hellgrauer Korb |
| Bauraum 110 mm (max. 130 mm), Ursprung Mitte | – | ✅ | aus `PrinterSpecKit` |
| Druckjob speichern/öffnen (.stec), STL exportieren | – | ⬜ | eigenes Projektformat (Bauteile + Lage + Profil) |

## 2. Parameter („2. Parameters“)
| Funktion | Pi | PC | Anmerkung |
|---|---|---|---|
| Vorlagen Sintratec PA12 / Sintratec TPE | ✅ | ✅ | Werte 1:1 aus `KitPA12CB_Z100`, `KitTPE_Z100` |
| Neues Material direkt in der Liste anlegen | – | ✅ | |
| Custom: Schichthöhe, Anzahl Perimeter, Perimeter-Versatz, Schraffur-Versatz, Schraffur-Abstand | – | ✅ | `desktop/kitslice/profiles.py`, **speicherbar**, Import/Export (JSON) |
| Zusätzlich: Temperaturen, Lasergeschwindigkeit, Heizstrahler im Profil | ✅ | ✅ | neu – der Pi stellt sie vor dem Druckstart ein |
| Warnung beim Wechsel PA12 → TPE (Dichtungen) | ⬜ | ⬜ | |
| Vorschau anzeigen | – | 🟡 | |

## Erweiterungen (nicht in Central)
| Funktion | Pi | PC | Anmerkung |
|---|---|---|---|
| Intelligentes Auto-Anordnen (24 Lagen je Teil, mehrere Durchläufe, Packdichte, Teile sperren, nur ausgewählte) | – | ✅ | angelehnt an PreForm 3D-Packing |
| Bauraum mit Kopien auffüllen | – | ✅ | |
| Dünne Wände erhalten | – | ✅ | wie EOS „Edge“ |
| Geschätzte Restzeit beim Druck | – | ✅ | aus Druckzeit je Schicht |
| Haut/Kern (Kern lockerer schraffiert) | – | ✅ | Profiloption |
| Schachbrett-/Inselschraffur | – | ✅ | Profiloption |
| Winkelschritt je Schicht (z. B. 67°) | – | ✅ | Profiloption |
| Kontur vor/nach Füllung, mehrere Perimeter | – | ✅ | Profiloption |
| Schwundausgleich X/Y/Z je Material | – | ✅ | Profiloption |
| Laserwege optimieren (Inseln/Konturen nach kürzestem Weg) | – | ✅ | Profiloption |

## 3. Vorschau
| Funktion | Pi | PC | Anmerkung |
|---|---|---|---|
| Schichten mit Schieberegler durchblättern („Layer n/m“) | ✅ | 🟡 | `/api/jobs/<id>/layer/<n>` bzw. lokal aus dem Slicer |
| Slicer wie Central (Kontur, Schraffur 4×90°, Zickzack, Versätze, leere Schichten) | – | ✅ | `desktop/kitslice/`, nach dem Bytecode des Build-Processors |
| Querschnitte wie Central: je Teil an den Schichtgrenzen z = k·Schicht ab Unterkante, 32-Bit-Kantenregel, Umrissverfolgung, flache Flächen auf der Ebene, Mindestvektor | – | ✅ | `desktop/kitslice/central.py` – Schicht für Schicht gegen Central 1.2.0 geprüft (Kalibrierteil, Testkörper, INDX-Halter/Thimble/Dichtungshalter: identisch). Abweichung mit Absicht: Central verliert durch einen Fehler beim Zusammenbau immer die oberste Schicht eines Teils; hier entfällt nur eine Schicht genau auf der Oberkante |

## 4. Pulver („3. Powder“)
| Funktion | Pi | PC | Anmerkung |
|---|---|---|---|
| Pulvervorbereitung ein/aus | ✅ | ⬜ | |
| Bauplattform / Vorrat fahren, kleiner Schritt 0,1 mm, großer 5 mm | ✅ | ⬜ | |
| Pulver auftragen (Schicht 0,15 mm), Beschichter fahren | ✅ | ⬜ | |
| Pulver laden nach Programmhöhe + 5 mm | ✅ | ⬜ | Erweiterung von Kit Control |

## 5. Drucken („4. Print“)
| Funktion | Pi | PC | Anmerkung |
|---|---|---|---|
| Job übertragen und starten | ✅ | 🟡 | `POST /api/jobs`, wahlweise nur übertragen oder sofort starten |
| Aufheizen, Aufheizen stoppen, Aufheizen überspringen (mit Warnung) | ✅ | ⬜ | |
| Druck abbrechen, „Skip to cooldown“, Sintern erzwingen | ✅ | ⬜ | |
| Live: Oberflächen-/Kammertemperatur, Schicht, Fortschritt, Zeit, Zustand | ✅ | 🟡 | `/api/events` jede Sekunde, aus dem Netz lesbar |
| Aktuelle Schicht als Bild | ✅ | ⬜ | |
| Temperatur-Log als CSV (Datum;Schicht;Oberfläche;Kammer) | ⬜ | ⬜ | |
| Fehler- und Warnungsdetails | ✅ | ⬜ | Warnung 81 ausgeblendet |
| Tür offen / SD-Karten-Fehler anzeigen | ✅ | ⬜ | |

## 6. Live-Parameter
| Funktion | Pi | PC | Anmerkung |
|---|---|---|---|
| Sollwerte Aufheizen (Oberfläche/Kammer) | ✅ | ⬜ | |
| Sollwerte Druck (Oberfläche/Kammer) | ✅ | ⬜ | |
| Lasergeschwindigkeit | ✅ | ⬜ | |
| Warnung bei Oberfläche > Grenzwert beim Aufheizen | ⬜ | ⬜ | |
| Heizstrahler links/rechts/vorne | ✅ | ⬜ | in Central nur intern |

## 7. Kalibrierung
| Funktion | Pi | PC | Anmerkung |
|---|---|---|---|
| Kalibriermuster / Mittelpunkt anzeigen, beenden | ✅ | ✅ | PC: Seite „Pulver“ |
| Achsen referenzieren | ✅ (nur nach Bestätigung) | ⬜ | Grundsatz: Pi stößt das nie selbst an |
| Digitale Skalierung berechnen (Soll/Ist, ±5 %) und senden | ✅ | ✅ | PC zeigt die Werte im Kit und die gesicherten Werkswerte |
| Kalibrierteil / Musterkarte (PDF) speichern | ⬜ | ✅ | PC: Kalibrierteil 40 × 40 × 5 mm (innen 30 × 30, Nut hinten als Y-Marke) |

## 8. Verbindung, System
| Funktion | Pi | PC | Anmerkung |
|---|---|---|---|
| Kit per USB verbinden, Fehlerhilfe | ✅ | – | |
| PC ↔ Kit | – | 🟡 | eigene API über WLAN/LAN oder USB-Netz, automatische Suche (UDP 8767) |
| Firmware flashen | ⛔ | ⛔ | gesperrt – zu riskant, Hersteller insolvent |
| Automatische Updates beim Start | ✅ | ⬜ | PC: bei jedem Start GitHub-Releases prüfen und Update anbieten |
| Über, Protokolle öffnen, Einstellungen | ✅ | ⬜ | |
| Setup für Windows | – | ⬜ | `KitControl-Setup.exe` über GitHub Actions |
| Sintratec-Cloud (AWS-Konto, Fehlerbeschreibungen online) | ⛔ | ⛔ | Dienste existieren nicht mehr; Fehlertexte liegen lokal |
| Sintratec S1 | ⛔ | ⛔ | nur Kit |
