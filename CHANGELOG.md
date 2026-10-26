# Changelog

## 0.5.3
- „Voraussichtlich fertig“ hat einen eigenen Ein/Aus-Schalter, einheitlich zur Schichtanzeige; Intervall mindestens 1 s (bisherige Einstellung „0 = aus“ bleibt als „aus“ erhalten)

## 0.5.2
- Schichtanzeige hat jetzt einen eigenen Ein/Aus-Schalter („Schichtanzeige verwenden“); Intervall mindestens 1 s
- Türschalter-Umkehr entfernt: gedrückt = Tür zu, losgelassen = Tür offen

## 0.5.1
- Schichtanzeige beruhigt: Wert sinkt nie, kurze Z-Hübe werden ignoriert, Aktualisierung höchstens im einstellbaren Intervall (Standard 60 s, 0 = aus) – deutlich weniger Einträge in Verlauf und Logbuch

## 0.5.0
- Neue Benachrichtigungen (je ein Schalter): **Fehler** (Druckabbruch und Klipper-Shutdown, mit Fehlertext und optionalem Foto), **Filament leer** (aktives Werkzeug, entprellt), **Tür geöffnet** (alle Türschalter offen, nur während eines Drucks)
- Foto bei Druck fertig und bei Fehler getrennt einstellbar; neue Bild-Entität „Foto vom letzten Fehler“
- Neue Ereignisse `wondermaker_error`, `wondermaker_filament_runout`, `wondermaker_door_opened`
- Option, die Türlogik umzukehren

## 0.4.0
- Benachrichtigung bei Druckende direkt in der Integration: Geräte wählbar, Foto vom fertigen Druck per Schalter, Verzögerung einstellbar
- Neue Bild-Entität „Foto vom letzten Druck“ (bleibt nach Neustart erhalten), Ereignis `wondermaker_print_finished`
- Button „Testbenachrichtigung senden“
- Einstellungen als Menü (Allgemein / Benachrichtigung nach Druckende)
- Kamera heißt jetzt „Kamera“ statt „Kamera camera“ (bestehende Entity-IDs bleiben)

## 0.3.1
- „Voraussichtlich fertig“ wird nur noch im einstellbaren Intervall aktualisiert (Option je Drucker, Standard 300 s, 0 = aus) – weniger Einträge in Verlauf und Logbuch

## 0.3.0
- Schichtanzeige wie in Fluidd: Gesamtzahl aus den Dateimetadaten, aktuelle Schicht aus Klipper oder aus der Z-Höhe berechnet
- Neues neutrales Icon und Logo (Orange/Grau, 3D-Drucker mit „WM")
- Repository für HACS vorbereitet (Workflows, Lizenz, englische/deutsche README)

## 0.2.0
- Toolchanger-Unterstützung: aktives Werkzeug, Temperatur und Solltemperatur je Werkzeug T0–T3
- Bauraumheizung (Temperatur und Solltemperatur), Lüfter, Türschalter, Filament-/Dock-Sensoren
- Kamera mit Fallback auf Port 8080, Fortschrittsanzeige repariert

## 0.1.0
- Erste Version: Sensoren, Buttons, Number, Kamera, Vorschaubild, Dienste
