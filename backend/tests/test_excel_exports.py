import csv
import io
from decimal import Decimal
from io import BytesIO

import pytest
from admin_client import AuthenticatedTestClient as TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID
from app.core.question_sets import LEARNING_CONTENT_VERSIONS
from app.db.session import get_db
from app.main import app
from app.models import Base, Participant
from app.seed.seed_questions import seed_database
from app.services.excel_export import write_xlsx


XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
METRIC_NUMERIC_COLUMNS = {
    "value", "n", "mean", "median", "numerator", "denominator", "eligible_count", "missing_count", "not_applicable_count",
}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'excel-exports.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    with factory() as db:
        seed_database(db)

    def dependency():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = dependency
    monkeypatch.setattr(get_settings(), "export_dir", str(tmp_path / "exports"))
    try:
        yield TestClient(app), factory
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def _csv_rows(response):
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


def _workbook_rows(response):
    workbook = load_workbook(BytesIO(response.content), read_only=True, data_only=False)
    try:
        sheet = workbook.active
        return sheet.title, list(sheet.iter_rows(values_only=True))
    finally:
        workbook.close()


def _normalize_csv_value(column, value):
    if value == "":
        return None
    if column in METRIC_NUMERIC_COLUMNS or column == "response_time_sec":
        number = Decimal(value)
        return int(number) if number == number.to_integral_value() else float(number)
    return value


def _assert_xlsx_matches_csv(xlsx_response, csv_response, sheet_title):
    assert xlsx_response.status_code == 200, xlsx_response.text
    assert xlsx_response.headers["content-type"].startswith(XLSX_MEDIA_TYPE)
    assert xlsx_response.headers["content-disposition"].endswith('.xlsx"')
    actual_title, actual_rows = _workbook_rows(xlsx_response)
    expected_rows = _csv_rows(csv_response)
    assert actual_title == sheet_title
    assert actual_rows[0] == tuple(expected_rows[0])
    assert len(actual_rows) == len(expected_rows)
    for actual, expected in zip(actual_rows[1:], expected_rows[1:], strict=True):
        assert tuple(actual) == tuple(
            _normalize_csv_value(column, value)
            for column, value in zip(expected_rows[0], expected, strict=True)
        )


def _add_participant(factory):
    participant = Participant(
        display_code="P001",
        group_condition="proposed",
        consent_checked=True,
        current_step="pretest",
        learning_content_version=LEARNING_CONTENT_VERSIONS["standard"],

        experiment_spec_version=CURRENT_EXPERIMENT_SPEC_VERSION,
        protocol_id=CURRENT_PROTOCOL_ID,
    )
    with factory() as db:
        db.add(participant)
        db.commit()
        return participant.id


def test_excel_exports_match_existing_csv_data(isolated):
    client, factory = isolated
    participant_id = _add_participant(factory)

    overview_xlsx = client.get("/api/admin/logs/overview.xlsx")
    overview_csv = client.get("/api/admin/logs/overview.csv")
    _assert_xlsx_matches_csv(overview_xlsx, overview_csv, "全体ログ")

    participant_xlsx = client.get(f"/api/admin/participants/{participant_id}/logs.xlsx")
    participant_csv = client.get(f"/api/admin/participants/{participant_id}/logs.csv")
    _assert_xlsx_matches_csv(participant_xlsx, participant_csv, "被験者ログ")

    for name, sheet_title in (
        ("hypothesis_metrics", "参加者別"),
        ("hypothesis_group_summary", "群別"),
    ):
        xlsx = client.get(f"/api/admin/export/{name}.xlsx")
        csv_response = client.get(f"/api/admin/export/{name}.csv")
        _assert_xlsx_matches_csv(xlsx, csv_response, sheet_title)


def test_excel_exports_handle_empty_and_unknown_data(isolated):
    client, _ = isolated
    overview = client.get("/api/admin/logs/overview.xlsx")
    csv_response = client.get("/api/admin/logs/overview.csv")
    _assert_xlsx_matches_csv(overview, csv_response, "全体ログ")
    assert len(_workbook_rows(overview)[1]) == 1

    assert client.get("/api/admin/participants/missing/logs.xlsx").status_code == 404
    assert client.get("/api/admin/export/hypothesis_metrics.xlsx?question_set_mode=easy").status_code == 422
    assert client.get("/api/admin/export/unknown.xlsx").status_code == 404


def test_xlsx_stores_formula_like_values_as_literal_text(tmp_path):
    path = write_xlsx(
        tmp_path / "literal.xlsx",
        columns=["comment", "count"],
        rows=[{"comment": "=1+1", "count": 2}],
        sheet_title="Export",
    )
    workbook = load_workbook(path, read_only=False, data_only=False)
    try:
        cell = workbook.active["A2"]
        assert cell.value == "=1+1"
        assert cell.data_type == "s"
        assert workbook.active["B2"].value == 2
    finally:
        workbook.close()
