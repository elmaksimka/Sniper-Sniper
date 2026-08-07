from pathlib import Path

import yaml


def test_render_blueprint_has_release_safety_invariants() -> None:
    blueprint = yaml.safe_load(Path("render.yaml").read_text(encoding="utf-8"))
    services = {service["name"]: service for service in blueprint["services"]}
    databases = {
        database["name"]: database for database in blueprint["databases"]
    }

    assert set(services) == {"alpha-engine-api", "alpha-engine-worker"}
    assert set(databases) == {"alpha-engine-postgres"}

    api = services["alpha-engine-api"]
    worker = services["alpha-engine-worker"]
    database = databases["alpha-engine-postgres"]
    api_environment = {item["key"]: item for item in api["envVars"]}

    assert api["type"] == "web"
    assert api["runtime"] == "docker"
    assert api["preDeployCommand"] == "alembic upgrade head"
    assert api["healthCheckPath"] == "/health/ready"
    assert api["autoDeployTrigger"] == "checksPass"
    assert api["maxShutdownDelaySeconds"] == 60
    assert api_environment["HELIUS_API_KEY"]["sync"] is False
    assert api_environment["ADMIN_API_KEY"]["generateValue"] is True

    assert worker["type"] == "worker"
    assert worker["dockerCommand"] == "python -m app.worker"
    assert worker["autoDeployTrigger"] == "checksPass"
    assert worker["maxShutdownDelaySeconds"] == 60

    assert database["plan"] == "basic-256mb"
    assert database["region"] == "frankfurt"
    assert database["postgresMajorVersion"] == "17"
    assert database["ipAllowList"] == []
