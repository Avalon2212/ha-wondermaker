<p align="center"><img src="custom_components/wondermaker/brand/logo@2x.png" alt="WonderMaker" width="420"></p>

# WonderMaker für Home Assistant

Lokale Integration für **WonderMaker ZR-Drucker** (getestet mit dem *ZR Ultra S*, 4-fach-Toolchanger mit Klipper). Sie nutzt die **Moonraker-API** (Port 7125). Keine Cloud, kein Konto.

> **Inoffizielles Community-Projekt.** Nicht mit WonderMaker verbunden und nicht von WonderMaker unterstützt. „WonderMaker" ist eine Marke des jeweiligen Inhabers und wird hier nur zur Beschreibung der Kompatibilität genannt. Das Icon in diesem Repository ist ein eigenes, neutrales Design.

## Funktionen
- **Sensoren:** Druckstatus, Fortschritt, Datei, Restzeit, Fertigstellung, **Schicht aktuell/gesamt**, aktives Werkzeug, Temperatur je Werkzeug, Bauraum, Bett, Lüfter, Host-Diagnose
- **Binärsensoren:** Druckt, Pausiert, Fehler, Filament und Dock je Werkzeug, Filamentpfade, Wechsler-Sensoren, Türschalter
- **Buttons:** Pause, Fortsetzen, Abbrechen, Homen, Not-Stopp, Neustarts
- **Number:** Solltemperaturen (Werkzeuge, Bett, Bauraum), Faktoren, Lüfter
- **Kamera** und **Vorschaubild**, Dienste `send_gcode` und `start_print`
- **Licht** nur, wenn Klipper eine Bauraumbeleuchtung als `output_pin`/`led` kennt

## Installation
1. **HACS:** Benutzerdefiniertes Repository hinzufügen (Kategorie *Integration*), „WonderMaker" installieren, Home Assistant neu starten.
   **Manuell:** Ordner `custom_components/wondermaker` nach `/config/custom_components/` kopieren und neu starten.
2. *Einstellungen → Geräte & Dienste → Integration hinzufügen → WonderMaker*.
3. Drucker-IP und Port `7125` eintragen. Einen API-Schlüssel brauchst du nur, wenn Moonraker die HA-IP ablehnt (`trusted_clients` in der `moonraker.conf`).

## Benachrichtigungen
*Einstellungen → Geräte & Dienste → WonderMaker → Konfigurieren → Benachrichtigungen*

Wähle die `notify`-Dienste (z. B. die Mobile-App deines Handys) und schalte ein, worüber du informiert werden willst:

| Schalter | Wann | Foto |
|---|---|---|
| Druck fertig | ein Druck endet erfolgreich | optionaler Schalter (nach kurzer Verzögerung) |
| Fehler | Druck wird durch einen Fehler abgebrochen oder Klipper geht in Shutdown/Fehler (Meldung wird mitgeschickt) | optionaler Schalter (sofort) |
| Filament leer | während eines Drucks melden die Sensoren des **aktiven Werkzeugs** kein Filament (entprellt) | nein |
| Tür geöffnet | während eines Drucks sind **alle** Türschalter offen | nein |

Fehler und Filament leer kommen als zeitkritische Nachricht mit hoher Priorität. Die Türschalter werden so gelesen: gedrückt = zu, losgelassen = offen.

Jedes Ereignis löst außerdem ein Home-Assistant-Event aus (`wondermaker_print_finished`, `wondermaker_error`, `wondermaker_filament_runout`, `wondermaker_door_opened`) für eigene Automationen. Die Fotos gibt es als Bild-Entitäten *Foto vom letzten Druck* und *Foto vom letzten Fehler*. Mit dem Button *Testbenachrichtigung senden* auf der Geräteseite kannst du alles sofort ausprobieren.

## Einstellungen (je Drucker)
*Einstellungen → Geräte & Dienste → WonderMaker → Konfigurieren*
- **Abfrageintervall** (Standard 5 s): wie oft der Drucker abgefragt wird.
- **Schichtanzeige verwenden** (Schalter) und **Aktualisierung der Schichtanzeige** (Standard 60 s): Die aktuelle Schicht wird ruhig angezeigt – sie springt nie zurück, kurze Z-Hübe werden ignoriert, und sie ändert sich höchstens in diesem Abstand (beim Start und Ende eines Drucks sofort). Ausgeschaltet zeigen die Schicht-Sensoren keinen Wert.
- **„Voraussichtlich fertig“ anzeigen** (Schalter) und **Aktualisierung „Voraussichtlich fertig“** (Standard 300 s): Die Fertigstellungszeit ändert sich bei jeder Abfrage und füllt Verlauf und Logbuch. Sie wird jetzt nur in diesem Abstand neu berechnet (beim Start und Ende eines Drucks sofort). Ausgeschaltet zeigt der Sensor keinen Wert.

## Hinweise
- Not-Stopp, Abbrechen und die Temperatur-Entitäten wirken sofort – in Automationen mit Bedacht einsetzen.
- Schichten stammen aus den Dateimetadaten; sendet dein Slicer `SET_PRINT_STATS_INFO`, haben diese Werte Vorrang.

Lizenz: MIT
