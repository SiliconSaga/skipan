from app.config import Settings


def test_from_env_reads_and_defaults(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "proj")
    monkeypatch.setenv("SKIPAN_BOARD_SHEET_ID", "board123")
    monkeypatch.setenv("SKIPAN_SKIPTA_SHEET_ID", "skipta456")
    monkeypatch.setenv("SKIPAN_MODEL_NAMES", "gemini-2.5-flash, gemini-2.0-flash-001")
    s = Settings.from_env()
    assert s.project_id == "proj"
    assert s.board_sheet_id == "board123" and s.skipta_sheet_id == "skipta456"
    assert s.model_names == ["gemini-2.5-flash", "gemini-2.0-flash-001"]
    assert s.rain_threshold == 50 and s.lookback_days == 14
    assert s.region == "us-east1" and s.base_url == "http://localhost:8001"
