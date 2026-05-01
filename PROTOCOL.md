# Motionblinds BLE — Protocol Documentatie

> **Versie**: 1.1
> **Datum**: 2026-05-01
> **Methode**: Reverse engineering van de Motionblinds BLE Android app (gedecompileerde broncode in `Coulisse-BV/MotionblindsBLE-App`)
> **Auteur**: Coulisse — Chiel Arkink (v1.0); aangevuld 2026-05-01 met response-byte-mapping uit `DeviceSettingActivity`, `AwningLightActivity` en `Constants.java`.

**Wijzigingen t.o.v. v1.0**

- Tijdstempel `getTime()` is **8 bytes** (was: 7) — milliseconde is 2 bytes big-endian, niet 1.
- Timer-tijdstempel `getHexTime()` is **7 bytes** (was: 6) en heeft één vaste byte-volgorde.
- Licht-alleen-query is `03 05 06 02` (was: `03 02 06 02` — typo in v1.0).
- §8 uitgebreid van 4 naar ~25 responses, met byte-mapping per response waar bekend.
- §12 (openstaande vragen) is grotendeels opgelost; resterende open punten blijven duidelijk gemarkeerd.

---

## Inhoudsopgave

1. [Overzicht](#1-overzicht)
2. [Bluetooth Stack & API](#2-bluetooth-stack--api)
3. [UUID-tabel](#3-uuid-tabel)
4. [Verbindingsflow](#4-verbindingsflow)
5. [Encryptie](#5-encryptie)
6. [Pakketformaat](#6-pakketformaat)
7. [Commando-referentie](#7-commando-referentie)
8. [Responses & Callbacks](#8-responses--callbacks)
9. [Foutafhandeling & Retry](#9-foutafhandeling--retry)
10. [Multi-device ondersteuning](#10-multi-device-ondersteuning)
11. [OTA Firmware Update](#11-ota-firmware-update)
12. [Openstaande vragen](#12-openstaande-vragen)

---

## 1. Overzicht

De Motionblinds BLE app communiceert met slimme rolgordijnen en jaloezieën via **Bluetooth Low Energy (BLE)**. De communicatie verloopt over één GATT service met twee characteristics: één voor schrijven (commando's) en één voor notificaties (responses). Alle berichten worden versleuteld met **AES-128-ECB**.

```
+---------------+        BLE (GATT)        +-----------------+
|  Mobiele App  | -----------------------> | Motionblinds    |
| (Android/iOS) |   Write + Notify Char.   |    Apparaat     |
+---------------+                          +-----------------+
```

**Kernkenmerken:**
- Protocol: Bluetooth Low Energy (BLE), GATT-gebaseerd
- Encryptie: AES-128-ECB met vaste sleutel
- Richting: Bidirectioneel (write + notify)
- Multi-device: Ja, meerdere apparaten tegelijk via adres-gebaseerd beheer

---

## 2. Bluetooth Stack & API

| Eigenschap            | Waarde                                       |
|-----------------------|----------------------------------------------|
| Bluetooth type        | BLE (Bluetooth Low Energy)                   |
| Android API           | `BluetoothGatt`, `BluetoothGattCallback`     |
| Transport             | `TRANSPORT_LE` (waarde: `2`)                 |
| Scan mode             | `SCAN_MODE_LOW_LATENCY` (waarde: `2`)        |
| MTU aangevraagd       | 512 bytes                                    |
| MTU default fallback  | 100 bytes                                    |
| Max write payload     | 128 bytes (OTA: 300 bytes)                   |
| Bonding/Pairing       | Gedelegeerd aan Android BT stack             |

**Relevante bronbestanden in de app:**
- `sources/com/coulisse/motion/ble/base/MyBle.java` — Hoofd BLE-communicatieklasse
- `sources/com/coulisse/motion/ble/base/MyBle$gattCallback$1.java` — GATT-callbacks
- `sources/com/coulisse/motion/ble/base/BleConnection.java` — Verbindingsbeheer
- `sources/com/coulisse/motion/ble/base/MultiBleManager.java` — Multi-device beheer
- `sources/com/coulisse/motion/ble/utils/AESUtils.java` — Encryptie
- `sources/com/coulisse/motion/ble/app/Constants.java` — UUID's en commando-constanten
- `sources/com/coulisse/motion/ble/activity/Device/DeviceSettingActivity.java` — Response parsing voor temperatuur, slow-stop, eindpunten, type, snelheid, sensoren
- `sources/com/coulisse/motion/ble/activity/control/AwningLightActivity.java` — Response parsing voor lichtpercentage

---

## 3. UUID-tabel

### 3.1 Hoofd Service & Characteristics

| Naam                     | UUID                                     | Type                       |
|--------------------------|------------------------------------------|----------------------------|
| **Main Service**         | `d973f2e0-b19e-11e2-9e96-0800200c9a66`   | Service                    |
| **Write Characteristic** | `d973f2e2-b19e-11e2-9e96-0800200c9a66`   | Characteristic (Write)     |
| **Notify Characteristic**| `d973f2e1-b19e-11e2-9e96-0800200c9a66`   | Characteristic (Notify)    |
| **CCCD Descriptor**      | `00002902-0000-1000-8000-00805f9b34fb`   | Descriptor                 |

### 3.2 OTA Service & Characteristics

| Naam                  | UUID                                     | Type           |
|-----------------------|------------------------------------------|----------------|
| **OTA Service**       | `8a97f7c0-8506-11e3-baa7-0800200c9a66`   | Service        |
| OTA Image             | `122e8cc0-8508-11e3-baa7-0800200c9a66`   | Characteristic |
| OTA New Image         | `210f99f0-8508-11e3-baa7-0800200c9a66`   | Characteristic |
| OTA Content           | `2691aa80-8508-11e3-baa7-0800200c9a66`   | Characteristic |
| OTA Sequence Number   | `2bdc5760-8508-11e3-baa7-0800200c9a66`   | Characteristic |

---

## 4. Verbindingsflow

### 4.1 Sequence

```
App                                      Apparaat
 |                                          |
 |---- BLE SCAN (SCAN_MODE_LOW_LATENCY) --->|
 |<--- Advertisement -----------------------|
 |                                          |
 |---- connectGatt(TRANSPORT_LE) ---------->|
 |<--- onConnectionStateChange(CONNECTED) --|
 |                                          |
 |---- discoverServices() ----------------->|
 |---- requestMtu(512) -------------------->|
 |<--- onMtuChanged(mtu) -------------------|
 |<--- onServicesDiscovered() --------------|
 |                                          |
 |---- setCharacteristicNotification ------>|  (Notify UUID)
 |---- writeDescriptor(CCCD,                |
 |        ENABLE_NOTIFICATION_VALUE) ------>|
 |<--- onDescriptorWrite() -----------------|
 |                                          |
 |======== GEREED -- bidirectioneel ========|
 |                                          |
 |---- writeCharacteristic(encrypted) ----->|  (Write UUID)
 |<--- onCharacteristicChanged(encrypted) --|  (Notify UUID)
 |                                          |
 |---- gatt.disconnect() ------------------>|
 |---- gatt.close() ----------------------->|
```

### 4.2 Verbindingsstatus codes

| Waarde | Betekenis                              |
|--------|----------------------------------------|
| `0`    | SUCCESS                                |
| `2`    | CONNECTED                              |
| `133`  | Typische Android BLE verbindingsfout   |

---

## 5. Encryptie

### 5.1 Algoritme

| Parameter             | Waarde                                  |
|-----------------------|-----------------------------------------|
| Algoritme             | AES                                     |
| Mode                  | ECB                                     |
| Padding               | PKCS7Padding                            |
| Sleutellengte         | 128-bit (16 bytes)                      |
| **Hardcoded sleutel** | `a3q8r8c135sqbn66`                      |
| Sleutelcodering       | ISO-8859-1                              |
| Input                 | Hex-string → bytes (`HexUtil.toByteArray()`) |
| Output                | Bytes → hex-string (`HexUtil.toHexString()`) |

> **Beveiligingsopmerking:** De AES-sleutel is hardcoded in de app. Dit betekent dat iedereen met toegang tot de APK de versleuteling kan omkeren en commando's kan nabootsen.

### 5.2 Versleutelingsproces

```
1. Bouw plaintext payload op als hex-string
   bijv: "030f0f02"

2. Voeg tijdstempel toe (getTime() — 16 hex chars / 8 bytes; zie §6.1)
   bijv: "030f0f02" + "1804100e1e000000"

3. Converteer hex-string -> bytes
   HexUtil.toByteArray("030f0f02...")

4. Encrypt met AES/ECB/PKCS7
   AESUtils.encrypt(bytes, "a3q8r8c135sqbn66")

5. Converteer encrypted bytes -> hex-string
   HexUtil.toHexString(encrypted)

6. Verstuur via writeCharacteristic()
```

---

## 6. Pakketformaat

### 6.1 Tijdstempel — `getTime()` (8 bytes / 16 hex chars)

Elk gewoon commando wordt uitgebreid met een **8-byte tijdstempel** aan het einde van de payload (vóór encryptie). Bron: `MyBle.getTime()` + `Utils.formatHexNum(value, isMill)`. De `isMill=true` flag op de millisecond-component levert 4 hex-chars op (2 bytes), niet 2.

| Bytes | Inhoud         | Formaat                  | Voorbeeld           |
|-------|----------------|--------------------------|---------------------|
| 0     | Jaar (2 cijfers) | unsigned byte         | `0x18` = 2024       |
| 1     | Maand (1–12)   | unsigned byte            | `0x04` = april      |
| 2     | Dag            | unsigned byte            | `0x10` = 16e        |
| 3     | Uur (24h)      | unsigned byte            | `0x0e` = 14         |
| 4     | Minuut         | unsigned byte            | `0x1e` = 30         |
| 5     | Seconde        | unsigned byte            | `0x00`              |
| 6–7   | Milliseconde   | uint16 big-endian (0–999)| `0x00 0x00`         |

> **Implementatienoot:** v1.0 van dit document gaf 7 bytes met 1 byte voor milliseconden. Dat is onjuist — `formatHexNum(ms, isMill=true)` produceert altijd 4 hex chars (2 bytes), en `getTime()` zet die als laatste twee bytes neer. Implementaties die 7 bytes gebruiken werken vaak nog wel (de motor lijkt tolerant), maar de officiële app produceert 8 bytes. De Python-library `motionblindsble` produceert eveneens 8 bytes.

### 6.2 Timer-tijdstempel — `getHexTime()` (7 bytes / 14 hex chars)

Gebruikt bij timer-commando's (`09 A0 01 …`). Bron: `MyBle.getHexTime()`.

| Bytes | Inhoud                                                |
|-------|-------------------------------------------------------|
| 0     | Weekdag (`00`=zo, `01`=ma, `02`=di, `03`=wo, `04`=do, `05`=vr, `06`=za) |
| 1     | Uur                                                   |
| 2     | Minuut                                                |
| 3     | Seconde                                               |
| 4     | Jaar (laatste 2 cijfers)                              |
| 5     | Maand (1–12)                                          |
| 6     | Dag                                                   |

> **Implementatienoot:** v1.0 gaf 6 bytes met een onduidelijke tabel waarin posities 0..12 voor (gedeeltelijk) hex-chars stonden. Dat is onjuist — alle 7 velden zijn gewone bytes (2 hex chars elk).

### 6.3 Pakketstructuur samenvatting

```
+-------------------------------------------------------+
|  PLAINTEXT PAYLOAD (vóór encryptie)                   |
|                                                       |
|  [Commando bytes] + [Tijdstempel 8 bytes]             |
|                                                       |
|  Voorbeeld: 03 02 03 01 | 18 04 10 0e 1e 00 00 00     |
|             --command--   ----timestamp 8 bytes----   |
+-------------------------------------------------------+
                        |
                  AES-128-ECB
                  PKCS7Padding
                        |
+-------------------------------------------------------+
|  ENCRYPTED PAYLOAD (verstuurd via BLE)                |
|                                                       |
|  16-byte block(s); commando van 4 bytes + 8 byte ts = |
|  12 bytes, met PKCS7-pad tot 16 bytes = 1 AES blok.   |
+-------------------------------------------------------+
```

---

## 7. Commando-referentie

> Alle waarden zijn hexadecimaal. Tijdstempel niet opgenomen (wordt automatisch toegevoegd, zie §6.1).
> Bron: `Constants.Send` companion object in `app/Constants.java`.

### 7.1 Beweging & Bediening

| Actie                  | Hex payload     | Constant                                  |
|------------------------|-----------------|-------------------------------------------|
| Omhoog / Open          | `03 02 03 01`   | `Operation_Open`                          |
| Omlaag / Dicht         | `03 02 03 02`   | `Operation_Close`                         |
| Stop                   | `03 02 03 03`   | `Operation_Stop`                          |
| Punt omhoog            | `03 02 03 04`   | `Operation_Point_Up`                      |
| Punt omlaag            | `03 02 03 05`   | `Operation_Point_Down`                    |
| Derde richting / favoriet | `03 02 03 06` | `Operation_Third_Run`                    |
| Hoek open              | `03 02 03 09`   | `Operation_Angle_Open`                    |
| Hoek dicht             | `03 02 03 0a`   | `Operation_Angle_Close`                   |

### 7.2 Positie instellen

| Actie                   | Hex payload                  | Parameters                              |
|-------------------------|------------------------------|-----------------------------------------|
| Positie (%)             | `05 02 04 40 [POS] 00`       | `POS` = 0x00–0x64 (0–100%)              |
| Hoek + positie          | `05 02 04 60 [POS] [ANG]`    | `ANG` = hoekwaarde (0–180)              |
| Hoek instellen (alleen) | `05 02 04 20 [POS] [ANG]`    | Voor tilt-only blinds                   |

### 7.3 Status & Queries

| Query                          | Hex payload     | Response prefix (zie §8) |
|--------------------------------|-----------------|--------------------------|
| Status (nieuw)                 | `03 05 0f 02`   | `12 04 0f 02`            |
| Status (oud)                   | `03 05 06 04`   | `09 04 06 04`            |
| Type opvragen                  | `03 05 01 10`   | `04 04 01 10`            |
| Richting opvragen              | `03 05 10 80`   | (geen vaste prefix bekend)|
| Richting opvragen (plug)       | `03 05 01 48`   | `04 04 01 48`            |
| Snelheid opvragen              | `03 05 01 0a`   | `04 04 01 0a`            |
| Lichtpercentage opvragen       | `03 05 01 fb`   | `07 04 04 fb`            |
| Lichtstand opvragen (alleen)   | `03 05 06 02`   | `09 04 06 02`            |
| **Temperatuur + lux opvragen** | `03 05 10 fa`   | `13 04 10 fa`            |
| Verticaal opvragen             | `03 05 01 06`   | `04 04 01 06`            |
| Device type punt opvragen      | `03 05 01 8b`   | `04 04 01 8b`            |
| Langzame stop opvragen         | `03 05 04 80`   | `07 04 04 80`            |
| Wind/regen sensor opvragen     | `03 05 01 87`   | `04 04 01 87`            |
| Eindpunten opvragen            | `03 05 01 20`   | `04 04 01 20`            |

### 7.4 Snelheid instellen

| Snelheid | Hex payload             | Constant                |
|----------|-------------------------|-------------------------|
| Laag     | `04 03 01 0a 01`        | `Operation_Speed_Low_Set` |
| Middel   | `04 03 01 0a 02`        | `Operation_Speed_Middle_Set` |
| Hoog     | `04 03 01 0a 03`        | `Operation_Speed_High_Set` |

### 7.5 Licht

| Actie                      | Hex payload                | Parameters                        |
|----------------------------|----------------------------|-----------------------------------|
| Helderheid instellen       | `05 02 07 11 [BRI] 00`     | `BRI` = 0x00–0x64 (0–100%)        |
| Licht aan                  | `03 02 03 71`              | —                                 |
| Licht uit                  | `03 02 03 72`              | —                                 |
| Lichtstand-only query      | `03 05 06 02`              | (zie §7.3)                        |

### 7.6 Sensoren

| Actie                      | Hex payload     |
|----------------------------|-----------------|
| Regen-sensor aan           | `03 02 03 73`   |
| Regen-sensor uit           | `03 02 03 74`   |
| Regen heartbeat aan        | `03 02 03 75`   |
| Regen heartbeat uit        | `03 02 03 76`   |
| Wind-sensor aan            | `03 02 03 77`   |
| Wind-sensor uit            | `03 02 03 78`   |
| Wind+licht+regen aan       | `03 02 03 57`   |
| Wind+licht+regen uit       | `03 02 03 58`   |
| Wind/regen query           | `03 05 01 87`   |

### 7.7 Kalibratie & Eindpunten

| Actie                          | Hex payload     |
|--------------------------------|-----------------|
| Kalibratie begin               | `03 02 03 5c`   |
| Kalibratie einde               | `03 02 03 5d`   |
| Eindpunt omhoog instellen      | `03 02 03 23`   |
| Eindpunt omlaag instellen      | `03 02 03 24`   |
| Eindpunt derde richting        | `03 02 03 25`   |
| Hoek begin                     | `03 02 03 21`   |
| Hoek nul instellen             | `03 02 03 22`   |
| Hoek 90° instellen             | `03 02 03 2b`   |
| Hoek 180° instellen            | `03 02 03 2e`   |
| Hoek omkeren                   | `03 02 03 34`   |
| Auto positie                   | `03 02 03 2f`   |
| Richting instellen             | `03 02 03 17`   |
| Eindpunten query               | `03 05 01 20`   |

### 7.8 Achterkant beweging (TDBU / dubbele blinds)

| Actie                  | Hex payload     |
|------------------------|-----------------|
| Boven-achter open      | `03 02 03 82`   |
| Boven-achter dicht     | `03 02 03 83`   |
| Onder-achter open      | `03 02 03 84`   |
| Onder-achter dicht     | `03 02 03 85`   |

### 7.9 Device type wijzigen

| Actie                      | Hex payload     |
|----------------------------|-----------------|
| Verander naar type E       | `03 02 03 80`   |
| Verander naar type ED      | `03 02 03 81`   |

### 7.10 Langzame stop

| Actie                  | Hex payload     |
|------------------------|-----------------|
| Langzame stop uit      | `03 02 03 41`   |
| Langzame stop aan      | `03 02 03 42`   |

### 7.11 Timer-beheer

| Actie                          | Hex payload                                     | Formaat                              |
|--------------------------------|-------------------------------------------------|--------------------------------------|
| Tijd instellen (nieuw)         | `09 A0 01 [WD][HH][MM][SS][YY][MO][DD]`         | `getHexTime()` 7 bytes (zie §6.2)    |
| Tijd instellen (oud)           | `06 A0 01 [WD][HH][MM][SS][YY][MO][DD]`         | idem                                 |
| Timer toevoegen                | `A0 02 …`                                       | (payload-formaat niet volledig gedocumenteerd) |
| Timer bijwerken                | `A0 03 …`                                       | idem                                 |
| Timer verwijderen              | `03 A0 04 [ID]`                                 | `ID` = timer id                      |
| Timers opvragen                | `02 A0 05`                                      | —                                    |
| Timers opvragen (test)         | `02 A0 07`                                      | —                                    |

### 7.12 Gebruikersbeheer

| Actie                          | Hex payload     |
|--------------------------------|-----------------|
| Gebruikerssleutel instellen    | `02 C0 01`      |
| Gebruiker toevoegen            | `0B C0 02 …`    |
| Gebruiker bijwerken            | `03 C0 03 …`    |
| Gebruiker verwijderen          | `03 C0 04 …`    |
| Gebruikers opvragen            | `02 C0 05`      |
| BLE-verbinding verbreken       | `02 C0 07`      |

### 7.13 Scan-commando's

| Actie                       | Hex payload   |
|-----------------------------|---------------|
| Scan starten                | `02 01 06`    |
| Scan (geen gebruiker)       | `ff 01 05`    |
| Scan (met gebruiker)        | `ff 02 05`    |

### 7.14 OTA-update commando's

| Actie                          | Hex payload          |
|--------------------------------|----------------------|
| OTA begin                      | `14 cd 01`           |
| OTA-status opvragen            | `02 A2 05`           |
| OTA update starten             | `02 cd 05`           |
| OTA-status apparaat            | `02 cd 0c`           |
| OTA data versturen             | `24 cd 08 …`         |
| OTA versie opvragen            | `02 cd 0e`           |
| OTA versienaam                 | `02 cd 20`           |
| OTA query (BLE)                | `02 A1 05`           |

---

## 8. Responses & Callbacks

Responses worden ontvangen via de **Notify Characteristic** (`d973f2e1-…`) als `onCharacteristicChanged()` events. De response is AES-encrypted met dezelfde sleutel en moet gedecrypt worden vóór verwerking.

De **eerste byte** van de gedecrypte payload is in alle bekende gevallen de **lengte van het bericht in bytes**. Alle byte-posities hieronder zijn ten opzichte van het begin van de gedecrypte plaintext (na AES-decrypt + PKCS7-unpad).

### 8.1 Callback events

| Callback                       | Trigger                                | Actie                            |
|--------------------------------|----------------------------------------|----------------------------------|
| `onConnectionStateChange()`    | Verbindingsstatus wijzigt              | Connect/disconnect afhandelen    |
| `onServicesDiscovered()`       | Na `discoverServices()`                | Services en characteristics initialiseren |
| `onMtuChanged()`               | Na MTU-onderhandeling                  | MTU opslaan                      |
| `onCharacteristicRead()`       | Na lees-operatie                       | Data doorgeven aan listener      |
| `onCharacteristicWrite()`      | Na schrijf-operatie                    | Bevestiging verwerken            |
| `onCharacteristicChanged()`    | Notificatie ontvangen                  | **Response verwerken**           |
| `onDescriptorWrite()`          | Na descriptor-schrijf                  | Notificaties bevestigen          |

### 8.2 Response identificatie en byte-mapping

Notatie: response-prefix is de eerste 4 bytes (8 hex chars) van de gedecrypte plaintext. De **bytes**-kolom geeft de byte-offset (0-based) in de gedecrypte plaintext. `bin8(b)` betekent: byte als 8-cijferige MSB-first binary string (`0x80` → `"10000000"`).

#### 8.2.1 Status-feedback en positie

| Prefix          | Constant                       | Bytes              | Betekenis                                                        |
|-----------------|--------------------------------|--------------------|------------------------------------------------------------------|
| `12 04 0f 02`   | `Device_First_Check` / `STATUS`| 4                  | Eindpunten/favoriet info (zie 8.2.2)                             |
|                 |                                | 6                  | Positie (0–100, 0xFF = onbekend)                                 |
|                 |                                | 7                  | Tilt-hoek (0–180)                                                |
|                 |                                | 12                 | Snelheid (`MotionSpeedLevel` 1=Low, 2=Medium, 3=High)            |
|                 |                                | 14–15              | Favoriete-positie-bits (uint16 LE; bit 0x8000 = favoriet ingesteld) |
|                 |                                | 17                 | Batterij: `& 0x7F` = percentage, `& 0x80` = aan het laden, `0xFF` = bedraad |
| `07 04 04 02`   | `Device_Percent` / `FEEDBACK`  | 4                  | Eindpunten-byte (zie 8.2.2)                                      |
|                 |                                | 6                  | Positie (0–100; 0xFF = onbekend)                                 |
|                 |                                | 7                  | Tilt-hoek (0–180)                                                |
| `09 04 06 04`   | `Device_Percent_Receive`       | (positie-bevestiging — exacte byte-volgorde niet gedocumenteerd in app-source) |

#### 8.2.2 Eindpunten en favoriet

| Prefix          | Constant                       | Bytes | Betekenis |
|-----------------|--------------------------------|-------|-----------|
| `04 04 01 20`   | `Device_Position_Set`          | 4     | Een byte met endpoint-flags. **`bin8(b)[0]` (= bit 7) = up gezet, `bin8(b)[1]` (= bit 6) = down gezet, `bin8(b)[2]` (= bit 5) = favoriet gezet.** Dat is de Java-conventie (`Utils.bit(b, n)` = `((1 << (7-n)) & b) != 0`). |

#### 8.2.3 Temperatuur + Lichtwaarde (één response)

| Prefix          | Constant                          | Bytes (laatste 3) | Betekenis |
|-----------------|-----------------------------------|-------------------|-----------|
| `13 04 10 fa`   | `Operation_Temperature_Receive`   | `len-3`           | Temperatuur in °C (unsigned byte) |
|                 |                                   | `len-2..len-1`    | Lux: `((bytes[len-2] << 8) | bytes[len-1]) * 10` |

Bron: `DeviceSettingActivity.updateTemp(hexString)` haalt `hexString.substring(len-6, len-4)` als temp, en `(substring(len-4, len-2) << 8) | substring(len-2)` als raw, en vermenigvuldigt vervolgens met 10 voor lux.

> **Belangrijk:** dit is **één** response op de `030510fa` query. De motor stuurt temperatuur en omgevingslicht samen terug.

#### 8.2.4 Lichtpercentage (set-back van helderheid)

| Prefix          | Constant                       | Bytes  | Betekenis |
|-----------------|--------------------------------|--------|-----------|
| `07 04 04 fb`   | `Light_Percent_Receive`        | 4      | Helderheid 0–100% (unsigned byte) |
| `09 04 06 02`   | `Operation_Light_only_Receive` | (lichtstand-response — bytes-mapping niet vastgelegd in geanalyseerde activities) |

Bron: `AwningLightActivity.onDataChange` rond regel 1269 — `hexString.substring(8, 10)` is byte 4 (= percentage).

#### 8.2.5 Langzame stop (slow-stop)

| Prefix          | Constant                       | Bytes              | Betekenis |
|-----------------|--------------------------------|--------------------|-----------|
| `07 04 04 80`   | `Operation_Slow_Stop_Receive`  | last byte (`len-1`) | `bin8(byte)[4]` = `'0'` betekent **aan**, `'1'` betekent **uit**. |

Bron: `DeviceSettingActivity` regel ~1851: `bin = hexToBin(lastByte); padded = getTwoStringFormat(bin); on = (padded.substring(4,5) == "0")`.

#### 8.2.6 Richting (plug) en omgekeerde

| Prefix          | Constant                       | Bytes  | Betekenis |
|-----------------|--------------------------------|--------|-----------|
| `04 04 01 48`   | `Device_Plug_Dir_Receive`      | 4      | `0x01` = omgekeerde draairichting, anders normaal |

Bron: `DevicePositionAwningActivity.onDataChange` regel ~1477.

#### 8.2.7 Verticaal-status

| Prefix          | Constant                          | Bytes (nibble) | Betekenis |
|-----------------|-----------------------------------|----------------|-----------|
| `04 04 01 06`   | `Device_Vertical_State_Receive`   | low nibble of byte 4 | `'1'` = double vertical, `'0'` = single |

Bron: `DevicePositionVerticalActivity` regel ~723: `hexString.substring(9, 10)` (lage nibble).

#### 8.2.8 Device type (E vs ED)

| Prefix          | Constant                       | Bytes               | Betekenis |
|-----------------|--------------------------------|---------------------|-----------|
| `04 04 01 8b`   | `DeviceType_Point_Receive`     | byte 4 → `bin8(b)[5]` | `'1'` = E, `'0'` = ED |
| `04 04 01 10`   | `Device_Type_Receive`          | byte 4              | Device-type / model identifier (motor-specifieke betekenis; gebruikt door `Utils.isBattery(...)` om te bepalen of motor op accu zit) |

#### 8.2.9 Snelheid (read-back)

| Prefix          | Constant                       | Bytes              | Betekenis |
|-----------------|--------------------------------|--------------------|-----------|
| `04 04 01 0a`   | `Device_Rolling_Speed`         | low nibble byte 4  | Snelheid 1/2/3 (nibble waarde minus 0; in Java: `Integer.parseInt(hexString.substring(9, 10)) - 1` voor 0-based dialoog-index, dus `+1` voor `MotionSpeedLevel`) |

#### 8.2.10 Wind/Licht/Regen-sensor status

| Prefix          | Constant                       | Bytes              | Betekenis |
|-----------------|--------------------------------|--------------------|-----------|
| `04 04 01 87`   | `Wind_Light_Rain_Receive`      | byte 4             | Bit-veld; per-sensor bit-mapping niet expliciet gedocumenteerd in de app — `DeviceSettingActivity.shwowOffDialog(strSubstring2)` rendert het als één gecombineerde toggle. Aanbevolen: ruwe byte loggen tijdens motor-validatie en bits afleiden uit known-state captures. |

#### 8.2.11 Tijd / timers

| Prefix          | Constant      | Bytes  | Betekenis |
|-----------------|---------------|--------|-----------|
| `09 a0 08`      | `Time_Receive`| 3..    | Bevestigt set-time. Layout: zie `getHexTime()` (§6.2). Voor lees-toegang van actuele tijd is geen aparte query gedocumenteerd. |

Timer-CRUD responses zijn niet eenduidig vastgelegd in de geanalyseerde Java-bron; toast-output blijft het primaire pad in de Android app. Voor HA-integratie wordt dit nog niet gemodelleerd.

#### 8.2.12 Gebruikers

| Prefix              | Constant              | Bytes        | Betekenis |
|---------------------|-----------------------|--------------|-----------|
| `0c c0 06 05`       | `Users_Receive`       | 4..          | Lijst gebruikers. Eerste byte van payload = aantal records. Per-record formaat is niet volledig gedocumenteerd in de app-source. |
| `0c c0 06 05 01`    | `Users_Receive_one`   |              | Bevestiging: één gebruiker (specifieke variant). |

#### 8.2.13 OTA-responses

| Prefix          | Constant                  | Betekenis |
|-----------------|---------------------------|-----------|
| `12 cd 21`      | `Device_Verison_Name`     | OTA versienaam (motor) |
| `0c cd 0f`      | `Device_Verison_Msg`      | OTA versie/info bericht |
| `02 cd 02`      | `Device_Refuse_Ota`       | Motor weigert OTA |
| `02 cd 03`      | `Device_agree_Ota`        | Motor accepteert OTA |
| `02 cd 05`      | `Device_Updating`         | Motor staat in update-modus |
| `02 cd 06`      | `Device_Send_Error`       | Foutieve chunk ontvangen |
| `02 cd 07`      | `Device_Send_Correct`     | Chunk ok |
| `02 cd 09`      | `Device_Send_Ok`          | OTA chunk verwerkt |
| `02 cd 0a`      | `Device_Send_Success`     | OTA succes-bevestiging |
| `02 cd 0b`      | `Device_Update_Success`   | Update klaar |
| `04 cd 0d`      | `Device_Send_Lost`        | Chunk-verlies |

---

## 9. Foutafhandeling & Retry

| Mechanisme                    | Waarde            | Details                                    |
|-------------------------------|-------------------|--------------------------------------------|
| Max verbindingspogingen       | **5**             | Automatisch na verbindingsverlies          |
| Delay tussen pogingen         | **1000 ms**       | `Handler.postDelayed()`                    |
| Write error tracking          | `isWriteError`    | Boolean per verbinding                     |
| Transaction counter           | `transacation`    | Synchronisatiemechanisme (zie §12)         |
| Disconnect bij fout           | Ja                | `gatt.disconnect()` + `gatt.close()`       |

### 9.1 Verbindingsherstel flow

```
Verbinding verbroken
        |
        v
poging <= 5 ?
   Ja  -----> wacht 1000ms ---> connectGatt() opnieuw
   Nee -----> Fout rapporteren aan UI
```

---

## 10. Multi-device ondersteuning

De app ondersteunt gelijktijdige verbindingen met meerdere apparaten via `MultiBleManager.java`:

```
Map<String (MAC-adres), BluetoothGatt>
```

| Methode                          | Beschrijving                          |
|----------------------------------|---------------------------------------|
| `connectDevice(context, addr)`   | Verbind met specifiek apparaat        |
| `disconnectDevice(addr)`         | Verbreek verbinding met apparaat      |
| `writeDataToDevice(addr, data)`  | Stuur data naar specifiek apparaat    |
| `disconnectAllDevices()`         | Verbreek alle verbindingen            |

---

## 11. OTA Firmware Update

OTA-updates verlopen via een aparte service (`8a97f7c0-…`) met eigen characteristics. Het proces:

```
1. App stuurt OTA BEGIN commando   (14 cd 01)
2. App vraagt huidige versie op    (02 cd 0e)
3. App stuurt firmware in chunks   (24 cd 08 [data])
4. Apparaat bevestigt per chunk    (via OTA Sequence Number char + 02 cd 07/09)
5. App stuurt voltooiing           (02 cd 0a)
6. Apparaat herstart met nieuwe firmware (02 cd 0b)
```

- Max OTA payload per write: **300 bytes**
- Sequence tracking via `DFU_OTA_EXPECTED_IMAGE_TU_SEQNUM` characteristic
- Per-chunk responses staan in §8.2.13

---

## 12. Openstaande vragen

| Punt                                        | Status                            |
|---------------------------------------------|-----------------------------------|
| Response-pakketstructuur algemeen           | **Opgelost** voor temperatuur/lux, lichtpercentage, slow-stop, richting, eindpunten, device-type, point-type, verticaal, snelheid (zie §8). |
| Byte-betekenis status-responses             | **Opgelost** voor `12 04 0f 02` en `07 04 04 02`. |
| Wind/licht/regen sensor — per-sensor bits   | **Open** — ruwe byte (`04 04 01 87`/byte 4) wordt momenteel als geheel gerapporteerd; per-bit decompositie vereist live captures met bekende sensor-toestanden. |
| Timer-CRUD response-formaten                | **Open** — niet gedecodeerd in de geanalyseerde Java-source; alleen toast-output. |
| Position-confirm `09 04 06 04`              | **Gedeeltelijk** — prefix bekend, exacte byte-volgorde niet vastgelegd. |
| Gebruiker-records (`0c c0 06 05`)           | **Gedeeltelijk** — per-record layout open. |
| `transacation` counter — exacte rol         | **Open** — gebruikt voor synchronisatie van schrijf-operaties; geen impact op protocol-decoding. |
| OTA volledige sequentie                     | **Gedeeltelijk** — handshake bekend (§8.2.13), foutscenario's nog niet volledig in kaart gebracht. |
| Authenticatie bij eerste koppeling          | **Niet gevonden** — vermoedelijk delegatie naar Android BT-stack-pairing; geen application-layer auth. |
| Direction query (`03 05 10 80`) response    | **Open** — geen vaste prefix waargenomen in de app-source; mogelijk komt het via een gedeelde response als de direction-plug (`04 04 01 48`). |

---

## Appendix A — Voorbeeldberichten (hex, plaintext)

```
# Open / Omhoog commando (8-byte timestamp)
Plaintext:  03 02 03 01 18 04 10 0e 1e 00 00 00
            -command--- ----timestamp 8 bytes----
Encrypted:  [16 bytes AES-ECB output]

# Status opvragen (nieuw)
Plaintext:  03 05 0f 02 18 04 10 0e 1e 00 00 00
Encrypted:  [16 bytes AES-ECB output]

# Positie instellen op 50%
Plaintext:  05 02 04 40 32 00 18 04 10 0e 1e 00 00 00
            ----command---- ----timestamp 8 bytes----
            POS=0x32=50%
Encrypted:  [16 bytes AES-ECB output]

# Temperatuur + lux opvragen
Plaintext:  03 05 10 fa 18 04 10 0e 1e 00 00 00
Encrypted:  [16 bytes AES-ECB output]

# Voorbeeld response op temperatuur-query (gedecrypt)
Decrypted:  13 04 10 fa 00 00 00 00 00 00 00 00 00 00 00 16 00 64
            -prefix---  --------------padding---------- TT HH LL
            TT = 0x16 = 22°C
            HH:LL = 0x0064 = 100 -> lux = 100 * 10 = 1000 lux
```

---

## Appendix B — Weekdag-codering

| Dag        | Hex waarde |
|------------|-----------|
| Zondag     | `0x00`    |
| Maandag    | `0x01`    |
| Dinsdag    | `0x02`    |
| Woensdag   | `0x03`    |
| Donderdag  | `0x04`    |
| Vrijdag    | `0x05`    |
| Zaterdag   | `0x06`    |

Bron: `Utils.formatDeviceWeek(int week)` mapt Java's `Calendar.DAY_OF_WEEK` (1=zondag, 7=zaterdag) op de bovenstaande hex-waarden.

---

## Appendix C — Mapping van app-constanten naar HA-integratie

De Home Assistant integratie [`ha-motionblinds_ble`](.) implementeert deze opcodes als volgt:

| App-constant                          | Python (`device.py`)              | HA-entity              |
|---------------------------------------|------------------------------------|------------------------|
| `Operation_Open / Close / Stop`       | `MotionDevice.open/close/stop`     | Cover open/close/stop  |
| `Operation_Percent_Base`              | `MotionDevice.position(int)`       | Cover set position     |
| `Operation_Percent_Angle_Only_Base`   | `MotionDevice.tilt(int)`           | Cover set tilt         |
| `Operation_Third_Run`                 | `MotionDevice.favorite()`          | Favorite-button        |
| `Operation_Speed_*`                   | `MotionDevice.speed(level)`        | Speed select           |
| `Operation_Status_Query_New`          | `MotionDevice.status_query()`      | (interne polling)      |
| `Operation_Temperature_Query`         | `ExtendedMotionDevice.temperature_query()` | Temperature + Illuminance sensors |
| `Operation_Light_Query`               | `ExtendedMotionDevice.brightness_query()`  | Brightness setpoint sensor |
| `Operation_Light_Base`                | `ExtendedMotionDevice.set_brightness(pct)` | Brightness number      |
| `Operation_Open_Light / Close_Light`  | `ExtendedMotionDevice.light_on/off()`      | Light switch           |
| `Operation_Open_Rain / Close_Rain`    | `ExtendedMotionDevice.rain_sensor(bool)`   | Rain sensor switch     |
| `Operation_Open_Wind / Close_Wind`    | `ExtendedMotionDevice.wind_sensor(bool)`   | Wind sensor switch     |
| `Operation_Open_Wind_Light_Rain` etc. | `ExtendedMotionDevice.combo_sensor(bool)`  | Combo sensor switch    |
| `Operation_Slow_Stop_Open / Close`    | `ExtendedMotionDevice.slow_stop(bool)`     | Slow-stop switch       |
| `Operation_Point_Begin / Over`        | `ExtendedMotionDevice.calibration_begin/end()` | Buttons            |
| `Operation_Point_Up_Set / Down_Set / Third_Set` | `ExtendedMotionDevice.set_endpoint_*()` | Buttons             |
| `Operation_Angle_Point_*_Set`         | `ExtendedMotionDevice.set_angle_*()`       | Buttons                |
| `Operation_Point_Angle_Reverse`       | `ExtendedMotionDevice.tilt_reverse()`      | Button                 |
| `Operation_Auto_Position`             | `ExtendedMotionDevice.auto_position()`     | Button                 |
| `Operation_Direction_Set`             | `ExtendedMotionDevice.set_direction()`     | Button                 |
| `Operation_Point_Up / Down`           | `ExtendedMotionDevice.point_up/down()`     | Buttons                |
| `Operation_Up_Back_Open / Close`      | `ExtendedMotionDevice.back_top_open/close()` | Buttons              |
| `Operation_Down_Back_Open / Close`    | `ExtendedMotionDevice.back_bottom_open/close()` | Buttons           |
| `Operation_Change_Device_Type_E / ED` | `ExtendedMotionDevice.set_device_type_e/ed()` | Device-type select  |

Niet (nog) geïmplementeerd in de HA-integratie: timer-CRUD (`A0 02/03/04`), gebruikersbeheer (`C0 02/03/04`), OTA (volledige flow), scan-commando's (`02 01 06` / `ff 0x 05`).

---

*Dit document is gegenereerd door reverse engineering van de gedecompileerde Motionblinds BLE Android applicatie (`Coulisse-BV/MotionblindsBLE-App`). Alle informatie is afkomstig uit de broncode; v1.1 is aangevuld met response-byte-mappings die in v1.0 als "Onbekend" of "Partieel" stonden. Geen actieve network-captures gebruikt — bevestiging tegen een echte motor is aanbevolen voor de byte-level details in §8.2.10 (sensor-bits) en §8.2.11–§8.2.12 (timer/user-records).*
