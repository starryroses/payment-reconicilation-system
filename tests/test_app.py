from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_api_report_returns_rupee_strings_and_validation() -> None:
    response = client.get("/api/report")
    assert response.status_code == 200
    payload = response.json()
    assert payload["verdict"] == "RECONCILED_WITH_EXCEPTIONS"
    assert payload["headline_totals"][-1]["amount"] == "0.00"
    assert payload["validation"]["passed"] is True
    assert len(payload["validation"]["found_discrepancies"]) == 2
    assert all(isinstance(row["amount"], str) for row in payload["bridge"])
    assert {item["reason_code"] for item in payload["exceptions"] if item["actionable"]} == {
        "DUPLICATE_BANK",
        "ORPHAN_REFUND",
    }


def test_homepage_renders_summary_bridge_and_validation() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Payment reconciliation" in response.text
    assert "October bridge" in response.text
    assert "Answer key matches the report" in response.text
    assert "Informational" in response.text
    assert "Actionable" in response.text
