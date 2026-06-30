# Facturatie VHS

Deze app is bedoeld voor het vergelijken van aanleverlijsten uit `Digitalisering` en `MAM`, zodat je snel een bruikbaar facturatie-overzicht per contentpartner krijgt.

Op het scherm houden we de uitleg bewust kort. De volledige werkwijze en technische aannames staan hier in de `README`.

## Doel

Gebruik de app wanneer je:

- een of meerdere aanleverlijsten uit `Digitalisering` krijgt
- een aanleverlijst uit `MAM` krijgt
- op basis van `PID` wilt controleren welke records overeenkomen
- de duur uit beide bronnen wilt vergelijken
- een overzicht per `CP` nodig hebt voor controle en facturatie

## Verwachte bestanden

### Digitalisering

De app verwacht in elk Digitalisering-bestand minstens deze kolommen:

- `PID`
- `Total duration of tape`

Je mag meerdere Excel-bestanden tegelijk uploaden. De app voegt ze eerst samen en behandelt ze daarna als een geheel.

### MAM

De app verwacht in het MAM-bestand minstens deze kolommen:

- `CP`
- `PID`
- `file_duration`

## Hoe de koppeling werkt

- `PID` is het koppelveld tussen beide bronnen
- als dezelfde `PID` meerdere keren voorkomt in `Digitalisering`, worden de duurwaarden opgeteld
- als dezelfde `PID` meerdere keren voorkomt in `MAM`, worden de duurwaarden opgeteld
- als een `PID` in `MAM` aan meerdere `CP`-waarden hangt, markeert de app dit als `CP-conflict`

## Wat de app berekent

Per gekoppelde `PID`:

- duur uit `Digitalisering`
- duur uit `MAM`
- verschil tussen beide

Daarna maakt de app een overzicht per `CP` met onder meer:

- totaal aantal video's
- totale duur uit `Digitalisering`
- totale duur uit `MAM`
- totale afwijking

## Resultaten in de export

De Excel-export bevat:

- `Overzicht per CP`
- `PID details`
- `Afwijkingen`
- `Invoerproblemen`

## Regels voor duurvelden

De app ondersteunt meerdere formaten voor duurvelden:

- Excel-waarden kleiner dan `1` worden gelezen als een fractie van een dag
- numerieke waarden groter dan of gelijk aan `1` worden gelezen als seconden
- tekst zoals `HH:MM:SS`, `MM:SS` en `1h2m3s` wordt ondersteund

## Praktische opmerkingen

- `.xls` wordt in deze versie niet ondersteund; sla bestanden eerst op als `.xlsx`
- een nieuwe upload vervangt de huidige selectie in dezelfde uploadzone
- de interface is bewust eenvoudig gehouden; technische detailuitleg staat daarom hier in de `README`

## Openen via dubbelklik op Mac

In deze map staan twee launcher-bestanden:

- `Install Facturatie VHS.command`
- `Start Facturatie VHS.command`

Gebruik ze als volgt:

1. open eenmalig `Install Facturatie VHS.command`
2. wacht tot de installatie van de virtuele omgeving en dependencies klaar is
3. open daarna `Start Facturatie VHS.command`
4. je browser opent automatisch het lokale adres van de app

De app draait dan lokaal op je eigen laptop. Excel-bestanden worden alleen tijdens die sessie verwerkt en niet permanent opgeslagen in het project.

## Lokaal starten

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```
