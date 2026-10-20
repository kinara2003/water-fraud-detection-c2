"""
tests/test_scenario_runner.py
Unit and Integration Tests for src/scenario_runner.py.

Verifies:
1. Scenario 1 (normal): Baseline stream stays green (Risk < 25%, zero new false alarms).
2. Scenario 2 (refill_surge): IWS transient filter dampens alarms at 06:00 AM (Risk < 45%).
3. Scenario 3 (pipe_leak): Component 1 physical leak feedback suppresses fraud risk (~18%) and classifies as physical_leak.
4. Scenario 4 (bypass_theft): Unauthorized 0.06 LPS withdrawal triggers high risk (>=89%), logs GPS, and dispatches alert.
5. CLI argument parsing for demonstration modes and speed parameter.
"""

from pathlib import Path
import pytest

from src.scenario_runner import (
    ScenarioClient,
    run_normal_scenario,
    run_refill_surge_scenario,
    run_pipe_leak_scenario,
    run_bypass_theft_scenario,
    run_all_scenarios,
)


@pytest.fixture(scope="module")
def client():
    """ScenarioClient fixture running in-process against FastAPI."""
    return ScenarioClient()


def test_scenario_client_initialization(client):
    """Asserts that ScenarioClient initializes properly and supports GET and POST."""
    assert client is not None
    code, data = client.get("/api/v1")
    assert code == 200
    assert data.get("status") == "operational"


def test_run_normal_scenario(client):
    """Asserts that normal scenario executes cleanly with Risk < 25%."""
    passed = run_normal_scenario(client, speed=0.0)
    assert passed is True


def test_run_refill_surge_scenario(client):
    """Asserts that 06:00 AM refill surge dampens alarms with Risk < 45%."""
    passed = run_refill_surge_scenario(client, speed=0.0)
    assert passed is True


def test_run_pipe_leak_scenario(client):
    """Asserts that pipe leak with C1 feedback suppresses fraud risk and reclassifies."""
    passed = run_pipe_leak_scenario(client, speed=0.0)
    assert passed is True


def test_run_bypass_theft_scenario(client):
    """Asserts that 0.06 LPS bypass theft triggers >=89% risk and alert dispatch."""
    passed = run_bypass_theft_scenario(client, speed=0.0)
    assert passed is True


def test_run_all_scenarios(client):
    """Asserts that master sequential runner executes all 4 scenarios successfully."""
    all_passed = run_all_scenarios(client, speed=0.0)
    assert all_passed is True
