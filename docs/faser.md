# Implementeringsfaser

Hver fase har noen korte brukerhistorier og et klart kriterium for når den er ferdig. Ikke start på en ny fase før kriteriet for den forrige er oppfylt.

## Fase 0 · Grunnmur ✅

- Som utvikler vil jeg måle en kommando lokalt med RAPL, slik at jeg får netto joule med spredning.
- Som eier vil jeg legge en analyse i kø via API-et, slik at laptopen kan kjøre den senere.

**Ferdig når:** worker-testene er grønne, og hele flyten (kø → worker → resultat med CO₂) er testet lokalt mot Postgres.

## Fase 1 · I drift

- Som eier vil jeg åpne dashboardet på Vercel fra hvor som helst, slik at jeg ser analysene uten å være hjemme.
- Som eier vil jeg at laptopen henter jobber av seg selv etter en omstart, slik at den kan stå uten tilsyn.
- Som eier vil jeg se om workeren lever, slik at jeg forstår hvorfor en jobb står i kø.

**Ferdig når:** en analyse lagt inn fra mobilen blir målt på laptopen og vises i dashboardet uten manuelle steg, og jobber som har stått i `running` i over en time settes tilbake i kø.

## Fase 2 · Trygg kjøring

- Som eier vil jeg at målt kode kjører i en sandkasse uten nettverk, slik at et ondsinnet repo ikke når hjemmenettet mitt.
- Som eier vil jeg ha faste CPU- og minnegrenser per analyse, slik at målinger kan sammenlignes.

**Ferdig når:** kode som prøver å nå nettet feiler, og energioverheaden fra Docker er målt og dokumentert.

## Fase 3 · Hvor går energien

- Som utvikler vil jeg se hvilke funksjoner som bruker mest energi, slik at jeg vet hvor jeg skal begynne.
- Som utvikler vil jeg se en flammegraf der fargen viser energi, slik at jeg forstår kallstrukturen.

**Ferdig når:** Python-kode får hotspots via py-spy, andelene summerer til 100 %, og profileringen kjører i en egen kjøring.

## Fase 4 · Forslag

- Som utvikler vil jeg få konkrete forslag med fil og linje, rangert etter besparelse, slik at jeg vet hva jeg skal endre.
- Som utvikler vil jeg bekrefte et forslag med en ny måling, slik at estimatet blir et målt tall.

**Ferdig når:** minst 8 Semgrep-regler for Python finnes, hver med testcase; funn er koblet til hotspots; og «Mål med endringen» kjører en patch og viser målt forskjell.

## Fase 5 · Over tid

- Som utvikler vil jeg at en GitHub Action stopper en PR som øker energien over en terskel, slik at regresjoner fanges før merge.
- Som eier vil jeg se energi per commit som en trend, slik at jeg ser når koden ble tyngre.
- Som leser av rapporten vil jeg at CO₂ bygger på faktisk karbonintensitet for tidspunktet, slik at tallet er riktig.

**Ferdig når:** Action-en er publisert, dashboardet (React + Vite) viser trend per commit, og Electricity Maps brukes med cache og fast faktor som reserve.

## Fase 6 · Bredde

- Som utvikler i Java eller C# vil jeg analysere koden min, slik at verktøyet ikke bare er for Python.
- Som eier vil jeg legge til flere workere (Pi 5, bare metal i skyen) uten å endre API-et, slik at kapasiteten kan vokse.

**Ferdig når:** async-profiler og dotnet-trace gir hotspots i samme format som py-spy, `PmicBackend` er implementert, og to workere henter fra køen samtidig uten konflikter.
