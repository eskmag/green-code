# green-code

Verktøy som kjører eksisterende kode på ekte maskinvare, måler energien med RAPL, finner hvor i koden energien går, og rangerer endringer etter hvor mye kjøretid og CO₂ de sparer.

Eier: Eskil (student, UiB). Kommuniser på norsk bokmål. UI-tekst og kommentarer på norsk, identifikatorer og filnavn på engelsk.

## Arkitektur

- **Vercel** (`api/index.py`, `public/`): FastAPI som én Python-funksjon i `fra1`, pluss statisk dashboard. All trafikk til `/api/*` rutes til funksjonen via `vercel.json`.
- **Neon PostgreSQL** (via Vercel Marketplace): all data, og jobbkøen. Køen er tabellen `analyses` med `FOR UPDATE SKIP LOCKED`. Det finnes ingen Redis.
- **Worker** (`worker/`): kjører på en Intel-laptop med Ubuntu Server. Spør API-et etter jobber over HTTPS (pull), måler og laster opp. Ingen åpne porter.
- **Målebackends** implementerer `EnergyBackend` i `worker/greencode_worker/energy.py`: `rapl` (teller), `pmic` (Pi 5, planlagt), `powermetrics` (Mac, planlagt), `estimate` (fallback).

## Mappestruktur

```
api/index.py                  API, skjema og beregninger
public/index.html             dashboard
worker/greencode_worker/      energy.py, runner.py, client.py, cli.py
worker/tests/                 pytest
deploy/                       systemd-filer og env-eksempel for laptopen
```

## Kommandoer

```bash
# Worker-tester
cd worker && pip install -e '.[dev]' && pytest

# API-tester (ekte Postgres, tømmer tabellene; aldri mot produksjon)
pip install -r requirements-dev.txt
DATABASE_URL=postgresql://postgres@localhost:5432/postgres pytest tests

# API lokalt (krever Postgres)
pip install -r requirements.txt uvicorn
DATABASE_URL=postgresql://postgres@localhost:5432/postgres ADMIN_TOKEN=adm WORKER_TOKEN=wrk \
  uvicorn api.index:app --reload --port 8077

# Worker mot lokalt API
GREENCODE_API_URL=http://localhost:8077 GREENCODE_WORKER_TOKEN=wrk greencode-worker run --once

# Mål en kommando uten API
greencode-worker measure "python3 bench.py" -n 5 --idle 5
```

## Måleregler (domenet; ikke bryt disse)

- Tomgangseffekt måles før kjøringene og trekkes fra: `netto = joule − tomgang_W × sekunder`.
- Oppvarmingskjøringer telles aldri med.
- Profilering skjer i en egen kjøring, aldri samtidig med energimålingen.
- Rådata (`runs`) lagres alltid. Oppsummeringen regnes ut på serveren i `summarize()`.
- Ferdige resultater endres aldri. En ny måling er en ny analyse.
- Estimater (besparelser, `estimate`-backend) vises som spenn og merkes med presisjon.
- Feltnavn har enheten i navnet: `joules_net_median`, `seconds_median`, `co2_mg`.
- RAPL: summer bare pakkedomenene (`intel-rapl:N`), håndter at telleren går rundt via `max_energy_range_uj`.

## Konvensjoner

- Workeren bruker bare Python-standardbiblioteket. Spør før du legger til en avhengighet der.
- API-et holdes i én fil til det passerer rundt 500 linjer. Deles det opp, må Vercel-bygget verifiseres før merge.
- Skjemaendringer skrives som idempotente `CREATE ... IF NOT EXISTS` / `ALTER ... ADD COLUMN IF NOT EXISTS` i `SCHEMA` til et migrasjonsverktøy innføres.
- API-tester kjører mot ekte Postgres, ikke mocks.
- Feilmeldinger til brukeren er på norsk og sier hva som gikk galt og hva man kan gjøre.
- Små commits med norske commit-meldinger.

## Sikkerhet

- Workeren kjører fremmed kode. Etter fase 2 kjører all målt kode i Docker med `--network none`, CPU- og minnegrenser.
- Bare `https://`-repoer godtas. Bare `ADMIN_TOKEN` kan legge inn analyser, bare `WORKER_TOKEN` kan hente jobber.
- Tokens finnes bare i miljøvariabler. Aldri i kode, logger eller commits.
- Workeren kjører som brukeren `greencode`, aldri som root.

## Ikke gjør

- Ikke legg til Redis, Celery eller en egen kø-tjeneste.
- Ikke bruk vanlige sky-VM-er til referansemålinger (de har ikke RAPL).
- Ikke åpne porter på laptopen. Workeren skal alltid hente, aldri ta imot.
- Ikke start på en ny fase før akseptkriteriene for den nåværende er oppfylt.

## Status

Nåværende fase: **Fase 1 – I drift**. Fase 0 (API, kø, worker med RAPL, dashboard) er ferdig og testet lokalt.
Fasene og brukerhistoriene ligger i arkitekturskissen og i `docs/faser.md` når den finnes.
