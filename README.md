# green-code

Måler hvor mye energi og CO₂ et program bruker, og finner hvor i koden energien går.

- **Vercel** kjører API-et (FastAPI) og dashboardet.
- **Neon PostgreSQL** (via Vercel Marketplace) lagrer analyser og fungerer som jobbkø.
- **Workere** på egne maskiner henter jobber fra API-et, måler med RAPL og laster opp resultatene. De trenger ingen åpne porter.

```
Dashboard / CLI ──► Vercel (FastAPI) ──► Neon Postgres
                          ▲
                          │ henter jobber, laster opp målinger (HTTPS)
                          │
                   Intel-laptop (RAPL-worker)
```

## Mappestruktur

| Sti | Innhold |
|---|---|
| `api/index.py` | Hele API-et. Vercel ruter `/api/*` hit |
| `public/index.html` | Dashboard (statisk) |
| `worker/` | Python-pakken `greencode-worker`, uten eksterne avhengigheter |
| `deploy/` | systemd-filer for laptopen |

## API

| Metode | Sti | Token |
|---|---|---|
| GET | `/api/health` | – |
| POST | `/api/v1/analyses` | admin |
| GET | `/api/v1/analyses` | admin |
| GET | `/api/v1/analyses/{id}` | admin |
| GET | `/api/v1/workers` | admin |
| POST | `/api/v1/worker/claim` | worker |
| POST | `/api/v1/worker/analyses/{id}/result` | worker |

Interaktiv dokumentasjon ligger på `/api/docs`.

Jobbkøen er tabellen `analyses`. `claim` bruker `FOR UPDATE SKIP LOCKED`, så flere workere kan spørre samtidig uten å få samme jobb. Tabellene opprettes automatisk ved første forespørsel.

Hvert `claim`-kall er også et livstegn: det oppdaterer `workers.last_seen_at`, og dashboardet viser tiden siden sist. Jobber som har stått i `running` i over en time settes tilbake i kø ved neste `claim`. Workeren spør ikke mens den måler, så et lengre opphold i livstegn kan være en pågående måling.

## API-tester

Testene kjører mot ekte Postgres og tømmer tabellene, så pek `DATABASE_URL` på en lokal testdatabase (aldri produksjon):

```bash
pip install -r requirements-dev.txt
DATABASE_URL=postgresql://postgres@localhost:5432/postgres pytest tests
```

## Oppsett på Vercel

1. **Database:** I prosjektet på Vercel, gå til *Storage* → *Create Database* → *Neon*. Velg region Frankfurt (samme som funksjonene i `vercel.json`). Vercel legger inn `DATABASE_URL` automatisk.
2. **Tokens:** Lag to tilfeldige tokens og legg dem inn under *Settings* → *Environment Variables*:
   ```bash
   openssl rand -hex 32   # ADMIN_TOKEN: for deg og dashboardet
   openssl rand -hex 32   # WORKER_TOKEN: for laptopen
   ```
3. Valgfritt: `CARBON_G_PER_KWH` (standard 21) og `CARBON_ZONE` (standard `NO5`).
4. Deploy på nytt, og sjekk at `/api/health` viser `true` på alle tre.

## Oppsett på laptopen (Ubuntu Server)

```bash
# Bruker og installasjon
sudo useradd --system --create-home --home-dir /opt/greencode greencode
sudo -u greencode git clone https://github.com/eskmag/green-code /opt/greencode/src
sudo -u greencode python3 -m venv /opt/greencode/venv
sudo -u greencode /opt/greencode/venv/bin/pip install /opt/greencode/src/worker

# RAPL-tilgang og tjenester
sudo cp /opt/greencode/src/deploy/*.service /etc/systemd/system/
sudo mkdir -p /etc/greencode
sudo cp /opt/greencode/src/deploy/worker.env.example /etc/greencode/worker.env
sudo chown root:greencode /etc/greencode/worker.env && sudo chmod 640 /etc/greencode/worker.env
sudo nano /etc/greencode/worker.env      # lim inn WORKER_TOKEN og adressen
sudo systemctl enable --now greencode-rapl greencode-worker

# Sjekk
sudo -u greencode /opt/greencode/venv/bin/greencode-worker info
journalctl -u greencode-worker -f
```

For stabile målinger:

```bash
sudo apt install linux-tools-common linux-tools-$(uname -r)
sudo cpupower frequency-set -g performance
# Lokket kan lukkes: sett HandleLidSwitch=ignore i /etc/systemd/logind.conf
```

## Måle lokalt uten API (fase 1)

```bash
pip install -e worker
greencode-worker info
greencode-worker measure "python3 -c 'sum(range(10**7))'" -n 5 --idle 5
```

På Mac og andre maskiner uten RAPL brukes et grovt estimat (CPU-tid × watt per kjerne). Det er bare ment for utvikling.

## Sikkerhet

Workeren kjører kode fra repoene du legger i køen. Derfor:

- Bare den som har `ADMIN_TOKEN` kan legge inn analyser.
- Bare `https://`-repoer godtas.
- systemd-tjenesten kjører som en egen bruker uten tilgang til `/home` og med skrivebeskyttet system.
- Docker-sandkasse med `--network none` kommer i fase 2. Fram til da: legg bare inn kode du stoler på.

## Veikart

- [x] Måling med RAPL, tomgangsfratrekk, median og spredning
- [x] API, jobbkø og dashboard på Vercel
- [ ] Docker-sandkasse
- [ ] Profilering med py-spy og energi per funksjon
- [ ] Semgrep-regler og forbedringsforslag
- [ ] Karbonintensitet fra Electricity Maps
- [ ] Trend per commit og GitHub Action

## Tester

```bash
cd worker && pip install -e '.[dev]' && pytest
```
