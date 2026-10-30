# Oppstartsprompt for fase 1

Lim inn i Claude Code fra rotmappen i repoet.

```text
Du jobber i repoet green-code. Les CLAUDE.md, README.md og docs/faser.md før du gjør noe annet.

Fase 0 er ferdig. Vi starter på Fase 1 – I drift. Brukerhistoriene og akseptkriteriene står i docs/faser.md.

Gjør dette i rekkefølge, og stopp for godkjenning mellom hvert punkt:
1. Lag en plan for Fase 1: hvilke filer som endres, nye endepunkter og skjemaendringer.
2. Legg til worker-heartbeat: tabellen workers, POST /api/v1/worker/heartbeat og
   GET /api/v1/workers. Workeren sender heartbeat ved oppstart og mellom hver polling.
   Vis status for workerne i dashboardet.
3. Sett jobber som har stått i 'running' i over en time tilbake i kø, og logg det i error-feltet.
4. Skriv API-tester mot ekte Postgres for claim, result, heartbeat og gjenoppretting av jobber.
5. Oppdater README og statuslinjen i CLAUDE.md.

Regler: følg målereglene og sikkerhetsreglene i CLAUDE.md, ikke legg til avhengigheter
i workeren, og kjør alle tester før du sier at noe er ferdig. Svar på norsk.
```
