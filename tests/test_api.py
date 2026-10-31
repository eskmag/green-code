from conftest import ADMIN, WORKER

NEW = {"repo_url": "https://github.com/eskmag/green-code", "command": "echo hei", "iterations": 3}


def queue(client):
    r = client.post("/api/v1/analyses", json=NEW, headers=ADMIN)
    assert r.status_code == 201
    return r.json()["id"]


def claim(client, worker_id="w1"):
    return client.post("/api/v1/worker/claim", json={"worker_id": worker_id}, headers=WORKER)


# ---------- Grunnflyt (kø → worker → resultat) ----------

def test_full_flow_gives_net_energy_and_co2(client):
    aid = queue(client)
    job = claim(client).json()
    assert job["id"] == aid

    r = client.post(f"/api/v1/worker/analyses/{aid}/result", headers=WORKER, json={
        "status": "done", "backend": "rapl", "idle_watts": 2.0,
        "runs": [{"joules": 12.0, "seconds": 2.0}, {"joules": 14.0, "seconds": 2.0}]})
    assert r.status_code == 200
    s = r.json()["summary"]
    assert s["joules_net_median"] == 9.0  # median av 8 og 10
    assert s["co2_mg"] > 0

    assert client.get(f"/api/v1/analyses/{aid}", headers=ADMIN).json()["status"] == "done"


def test_claim_returns_204_when_queue_is_empty(client):
    assert claim(client).status_code == 204


# ---------- Hengende jobber ----------

def test_job_running_over_an_hour_is_requeued_and_claimed_again(client, sql):
    aid = queue(client)
    assert claim(client, "w1").json()["id"] == aid
    sql("UPDATE analyses SET started_at = now() - interval '2 hours' WHERE id = %s", (aid,))

    job = claim(client, "w2")

    assert job.status_code == 200
    assert job.json()["id"] == aid
    row = client.get(f"/api/v1/analyses/{aid}", headers=ADMIN).json()
    assert row["status"] == "running"
    assert row["worker_id"] == "w2"


def test_job_running_under_an_hour_is_left_alone(client, sql):
    aid = queue(client)
    claim(client, "w1")
    sql("UPDATE analyses SET started_at = now() - interval '50 minutes' WHERE id = %s", (aid,))

    assert claim(client, "w2").status_code == 204
    assert client.get(f"/api/v1/analyses/{aid}", headers=ADMIN).json()["worker_id"] == "w1"


def test_finished_results_are_never_requeued(client, sql):
    aid = queue(client)
    claim(client)
    client.post(f"/api/v1/worker/analyses/{aid}/result", headers=WORKER, json={
        "status": "failed", "error": "feilet med vilje"})
    sql("UPDATE analyses SET started_at = now() - interval '5 hours' WHERE id = %s", (aid,))

    assert claim(client, "w2").status_code == 204
    assert client.get(f"/api/v1/analyses/{aid}", headers=ADMIN).json()["status"] == "failed"


# ---------- Er workeren i live? ----------

def test_claim_registers_worker_as_seen(client):
    claim(client, "laptop-1")  # tom kø er nok: hvert spørsmål teller som livstegn

    r = client.get("/api/v1/workers", headers=ADMIN)

    assert r.status_code == 200
    workers = r.json()
    assert [w["worker_id"] for w in workers] == ["laptop-1"]
    assert 0 <= workers[0]["seconds_since_seen"] < 10


def test_worker_seen_time_updates_on_every_claim(client, sql):
    claim(client, "laptop-1")
    sql("UPDATE workers SET last_seen_at = now() - interval '10 minutes'")
    assert client.get("/api/v1/workers", headers=ADMIN).json()[0]["seconds_since_seen"] > 500

    claim(client, "laptop-1")

    assert client.get("/api/v1/workers", headers=ADMIN).json()[0]["seconds_since_seen"] < 10


def test_workers_endpoint_needs_admin_token(client):
    assert client.get("/api/v1/workers").status_code == 401
    assert client.get("/api/v1/workers", headers=WORKER).status_code == 401
