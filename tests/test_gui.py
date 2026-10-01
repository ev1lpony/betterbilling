"""Offscreen regressions for the invoice workflow, using isolated test data only."""

from copy import deepcopy
from datetime import datetime
import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox, QPushButton

import main
import pdf_gen
import settings
from models import Invoice, parse_user_date
from storage import base_paths, load_invoice_json, save_invoice_json


@pytest.fixture
def dialogs(monkeypatch):
    calls = {name: [] for name in ("warning", "information", "critical", "question")}
    calls["answer"] = QMessageBox.No
    for name in ("warning", "information", "critical"):
        def record(*args, _name=name, **kwargs):
            calls[_name].append(args)
            return QMessageBox.Ok
        monkeypatch.setattr(QMessageBox, name, record)

    def question(*args, **kwargs):
        calls["question"].append(args)
        return calls["answer"]

    monkeypatch.setattr(QMessageBox, "question", question)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    return calls


@pytest.fixture
def workspace(qapp, dialogs):
    window = main.InvoiceWorkspace()
    window.show()
    window.activateWindow()
    qapp.processEvents()
    yield window
    dialogs["answer"] = QMessageBox.Yes
    window.close()
    window.deleteLater()
    qapp.processEvents()


@pytest.fixture
def app_window(qapp, dialogs):
    window = main.MainWindow()
    window.show()
    window.activateWindow()
    qapp.processEvents()
    yield window
    dialogs["answer"] = QMessageBox.Yes
    window.close()
    window.deleteLater()
    qapp.processEvents()


def set_meta(workspace, client="Test Client", date="04/30/2025", rate=250.0):
    workspace.client.setText(client)
    workspace.invoice_date.setText(date)
    workspace.default_rate.setValue(rate)


def add_service(workspace, desc="Review file", date="04/01/2025", hours=1.5, rate=250):
    workspace.s_desc.setText(desc)
    workspace.s_date.setText(date)
    workspace.s_hours.setValue(hours)
    workspace.s_rate.setValue(rate)
    workspace.add_service()


def click_button(page, label):
    matches = [button for button in page.findChildren(QPushButton) if button.text() == label]
    assert len(matches) == 1, f"Expected exactly one {label!r} button on page"
    matches[0].click()


def type_text(field, text):
    """Exercise textEdited, which Qt emits for user edits but not setText."""
    field.setFocus()
    field.selectAll()
    QTest.keyClicks(field, text)


def select_invoice(workspace, path):
    workspace.refresh_invoice_list()
    for index in range(workspace.invoice_list.count()):
        item = workspace.invoice_list.item(index)
        if item.data(Qt.UserRole) == str(path):
            workspace.invoice_list.setCurrentRow(index)
            return
    pytest.fail(f"Saved invoice missing from Open Existing list: {path}")


def test_sorted_service_edits_follow_stable_line_ids(workspace):
    later = workspace.invoice.add_service(datetime(2025, 4, 3), "Later", 1.0)
    earlier = workspace.invoice.add_service(datetime(2025, 4, 1), "Earlier", 2.0)
    workspace._rebuild_service_table()
    assert workspace.s_table.item(0, 0).data(Qt.UserRole) == earlier.line_id
    workspace.s_table.item(0, 2).setText("3.25")
    assert earlier.hours == 3.25
    assert later.hours == 1.0

    workspace.s_table.item(0, 0).setText("4/5/2025")
    assert workspace.s_table.item(1, 0).data(Qt.UserRole) == earlier.line_id
    workspace.s_table.item(1, 1).setText("revised earlier entry")
    assert earlier.desc == "Revised earlier entry"
    assert later.desc == "Later"


def test_duplicate_service_edit_rejected_without_mutating_model(workspace, dialogs):
    first = workspace.invoice.add_service(datetime(2025, 4, 1), "Review file", 1.0)
    second = workspace.invoice.add_service(datetime(2025, 4, 1), "Phone call", 1.0)
    workspace._rebuild_service_table()
    workspace.set_dirty(False)
    workspace.s_table.item(1, 1).setText("review file")
    assert first.desc == "Review file"
    assert second.desc == "Phone call"
    assert len(workspace.invoice.services) == 2
    assert workspace.s_table.item(1, 1).text() == "Phone call"
    assert not workspace.dirty
    assert dialogs["warning"]


@pytest.mark.parametrize("column,attribute", [(2, "hours"), (3, "rate")])
@pytest.mark.parametrize("invalid", ["nan", "inf", "-inf", "1e309", "-1", "garbage"])
def test_invalid_inline_service_number_preserves_model(workspace, dialogs, column, attribute, invalid):
    service = workspace.invoice.add_service(datetime(2025, 4, 1), "Review", 1.5)
    workspace._rebuild_service_table()
    original = getattr(service, attribute)
    workspace.set_dirty(False)
    workspace.s_table.item(0, column).setText(invalid)
    assert getattr(service, attribute) == original
    assert workspace.s_table.item(0, column).text() == f"{original:.2f}"
    assert not workspace.dirty
    assert dialogs["warning"]


@pytest.mark.parametrize("column,attribute", [(1, "qty"), (2, "unit_price")])
@pytest.mark.parametrize("invalid", ["nan", "inf", "-inf", "1e309", "-1", "garbage"])
def test_invalid_inline_cost_number_preserves_model(workspace, dialogs, column, attribute, invalid):
    cost = workspace.invoice.add_cost("Postage", 2, 9.85)
    workspace._rebuild_cost_table()
    original = getattr(cost, attribute)
    workspace.set_dirty(False)
    workspace.c_table.item(0, column).setText(invalid)
    assert getattr(cost, attribute) == original
    assert workspace.c_table.item(0, column).text() == f"{original:.2f}"
    assert not workspace.dirty
    assert dialogs["warning"]


def test_browsing_existing_preserves_unsaved_metadata_and_open_can_be_cancelled(workspace, dialogs):
    path = settings.JSON_DIR / "existing.json"
    save_invoice_json(Invoice("Existing Client", "04/30/2025", 250), path)
    assert not workspace.dirty
    type_text(workspace.client, "Unsaved client")
    assert workspace.dirty
    original_invoice = workspace.invoice
    workspace.go_open_page()
    assert workspace.stack.currentWidget() is workspace.page_open
    assert not dialogs["question"]
    assert workspace.invoice is original_invoice
    assert workspace.dirty
    select_invoice(workspace, path)
    workspace.open_selected()
    assert dialogs["question"]
    assert workspace.invoice is original_invoice
    assert workspace.client.text() == "Unsaved client"
    assert workspace.dirty


def test_new_invoice_cancel_preserves_unsaved_invoice(workspace, dialogs):
    set_meta(workspace)
    workspace.go_services()
    add_service(workspace)
    original_invoice = workspace.invoice
    workspace.start_new_invoice()
    assert dialogs["question"]
    assert workspace.invoice is original_invoice
    assert workspace.client.text() == "Test Client"
    assert len(workspace.invoice.services) == 1


def test_new_invoice_confirm_resets_model_and_pending_forms(workspace, dialogs):
    set_meta(workspace)
    workspace.go_services()
    add_service(workspace)
    workspace.s_desc.setText("Pending service")
    workspace.c_desc.setText("Pending cost")
    original_invoice = workspace.invoice
    dialogs["answer"] = QMessageBox.Yes
    workspace.start_new_invoice()
    assert dialogs["question"]
    assert workspace.invoice is not original_invoice
    assert workspace.invoice.services == []
    assert workspace.invoice.costs == []
    assert workspace.client.text() == ""
    assert workspace.s_desc.text() == ""
    assert workspace.c_desc.text() == ""
    assert workspace.stack.currentWidget() is workspace.page_meta
    assert not workspace.dirty


def test_main_window_new_cancel_does_not_reset_invoice(app_window, dialogs):
    app_window.go_new()
    workspace = app_window.creator.workspace
    set_meta(workspace)
    original_invoice = workspace.invoice
    workspace.set_dirty(True)
    app_window.go_new()
    assert dialogs["question"]
    assert workspace.invoice is original_invoice
    assert workspace.client.text() == "Test Client"


def test_main_window_close_requires_discard_confirmation(app_window, dialogs):
    app_window.go_new()
    workspace = app_window.creator.workspace
    type_text(workspace.client, "Unsaved client")
    event = QCloseEvent()
    app_window.closeEvent(event)
    assert dialogs["question"]
    assert not event.isAccepted()
    assert workspace.client.text() == "Unsaved client"
    dialogs["answer"] = QMessageBox.Yes
    event = QCloseEvent()
    app_window.closeEvent(event)
    assert event.isAccepted()


def test_add_service_keeps_date_for_repeated_entry(workspace):
    set_meta(workspace)
    workspace.go_services()
    add_service(workspace, date="09/07/2025")
    assert len(workspace.invoice.services) == 1
    assert parse_user_date(workspace.s_date.text()) == datetime(2025, 9, 7)
    assert workspace.s_desc.text() == ""
    assert workspace.s_hours.value() == 0


def test_zero_hours_requires_explicit_typing(workspace, dialogs, qapp):
    set_meta(workspace)
    workspace.go_services()
    workspace.s_desc.setText("No charge")
    workspace.s_date.setText("04/01/2025")
    workspace.add_service()
    assert workspace.invoice.services == []
    assert dialogs["warning"]
    editor = workspace.s_hours.lineEdit()
    editor.setFocus()
    editor.selectAll()
    QTest.keyClicks(editor, "0")
    QTest.keyClick(editor, Qt.Key_Return)
    qapp.processEvents()
    assert len(workspace.invoice.services) == 1
    assert workspace.invoice.services[0].hours == 0


def test_ctrl_d_prefills_service_when_entry_field_has_focus(workspace, qapp):
    set_meta(workspace)
    workspace.go_services()
    add_service(workspace, hours=2.25, rate=375)
    workspace.s_desc.setText("Different pending entry")
    workspace.s_desc.setFocus()
    workspace.activateWindow()
    qapp.processEvents()
    QTest.keyClick(workspace.s_desc, Qt.Key_D, Qt.ControlModifier)
    qapp.processEvents()
    assert workspace.s_desc.text() == "Review file"
    assert workspace.s_hours.value() == 2.25
    assert workspace.s_rate.value() == 375
    assert workspace._hours_dirty
    assert len(workspace.invoice.services) == 1


def test_ctrl_d_prefills_cost_when_entry_field_has_focus(workspace, qapp):
    set_meta(workspace)
    workspace.go_services()
    click_button(workspace.page_services, "Done →")
    workspace.c_desc.setText("Postage")
    workspace.c_qty.setValue(2)
    workspace.c_price.setValue(9.85)
    workspace.add_cost()
    workspace.c_desc.setText("Different pending entry")
    workspace.c_desc.setFocus()
    workspace.activateWindow()
    qapp.processEvents()
    QTest.keyClick(workspace.c_desc, Qt.Key_D, Qt.ControlModifier)
    qapp.processEvents()
    assert workspace.c_desc.text() == "Postage"
    assert workspace.c_qty.value() == 2
    assert workspace.c_price.value() == 9.85
    assert len(workspace.invoice.costs) == 1


def test_page_transitions_focus_service_then_cost_description(workspace, qapp):
    set_meta(workspace)
    workspace.invoice_date.setFocus()
    workspace.go_services()
    qapp.processEvents()
    assert workspace.s_desc.hasFocus()
    workspace.s_rate.setFocus()
    click_button(workspace.page_services, "Done →")
    qapp.processEvents()
    assert workspace.stack.currentWidget() is workspace.page_costs
    assert workspace.c_desc.hasFocus()


def test_flat_fee_transition_focuses_cost_description(workspace, qapp):
    set_meta(workspace)
    workspace.flat_fee.setChecked(True)
    workspace.flat_desc.setText("Attorney fees")
    workspace.flat_amount.setValue(1000)
    workspace.flat_amount.setFocus()
    workspace.go_services()
    qapp.processEvents()
    assert workspace.stack.currentWidget() is workspace.page_costs
    assert workspace.c_desc.hasFocus()


def test_open_existing_resets_pending_service_and_cost_forms(workspace, dialogs):
    invoice = Invoice("Loaded Client", "04/30/2025", 350)
    invoice.add_service(datetime(2025, 4, 2), "Saved service", 2.0)
    invoice.add_cost("Saved cost", 3, 4.25)
    path = settings.JSON_DIR / "saved.json"
    save_invoice_json(invoice, path)
    workspace.s_desc.setText("Stale unsaved service")
    workspace.s_hours.setValue(8)
    workspace.s_rate.setValue(999)
    workspace._hours_dirty = True
    workspace.c_desc.setText("Stale unsaved cost")
    workspace.c_qty.setValue(8)
    workspace.c_price.setValue(999)
    dialogs["answer"] = QMessageBox.Yes
    workspace.go_open_page()
    select_invoice(workspace, path)
    workspace.open_selected()
    assert workspace.client.text() == "Loaded Client"
    assert workspace.s_desc.text() == ""
    assert workspace.s_hours.value() == 0
    assert workspace.s_rate.value() == 350
    assert not workspace._hours_dirty
    assert workspace.c_desc.text() == ""
    assert workspace.c_qty.value() == 0
    assert workspace.c_price.value() == 0
    assert workspace.s_table.rowCount() == 1
    assert workspace.c_table.rowCount() == 1
    assert not workspace.dirty


def test_cost_add_inline_edit_review_and_save_roundtrip(workspace, dialogs):
    set_meta(workspace)
    workspace.go_services()
    add_service(workspace)
    click_button(workspace.page_services, "Done →")
    workspace.c_desc.setText("certified mail")
    workspace.c_qty.setValue(2)
    workspace.c_price.setValue(9.85)
    workspace.add_cost()
    cost = workspace.invoice.costs[0]
    assert cost.desc == "Certified mail"
    workspace.c_table.item(0, 1).setText("3")
    assert cost.qty == 3
    assert cost.total == pytest.approx(29.55)
    workspace.go_review()
    assert workspace.stack.currentWidget() is workspace.page_review
    assert "Certified mail" in workspace.preview.toPlainText()
    assert "GRAND TOTAL: 404.55" in workspace.preview.toPlainText()
    workspace.save_current()
    assert not dialogs["critical"]
    assert not workspace.dirty
    assert workspace.edit_mode
    loaded = load_invoice_json(workspace.current_json_path)
    assert loaded.grand_total() == pytest.approx(404.55)
    assert loaded.costs[0].line_id == cost.line_id


def test_save_existing_keeps_original_paths_after_client_rename(workspace, dialogs):
    set_meta(workspace)
    workspace.save_current()
    original_json = workspace.current_json_path
    original_pdf = workspace.current_pdf_path
    type_text(workspace.client, "Renamed Client")
    workspace.save_and_export()
    assert not dialogs["critical"]
    assert workspace.current_json_path == original_json
    assert workspace.current_pdf_path == original_pdf
    assert load_invoice_json(original_json).client_name == "Renamed Client"
    assert original_pdf.read_bytes().startswith(b"%PDF-")
    assert len(list(settings.JSON_DIR.glob("*.json"))) == 1


@pytest.mark.parametrize("save_action", ["save_current", "save_and_export", "save_as_new"])
@pytest.mark.parametrize("occupied", ["json", "pdf", "both"])
def test_new_save_preserves_filename_collisions(workspace, dialogs, save_action, occupied):
    set_meta(workspace)
    workspace.go_services()
    json_path, pdf_path = base_paths(workspace.invoice)
    sentinel_json = b"existing invoice data"
    sentinel_pdf = b"existing PDF data"
    if occupied in ("json", "both"):
        json_path.write_bytes(sentinel_json)
    if occupied in ("pdf", "both"):
        pdf_path.write_bytes(sentinel_pdf)

    getattr(workspace, save_action)()
    assert not dialogs["critical"]
    assert workspace.current_json_path != json_path
    assert workspace.current_pdf_path != pdf_path
    assert workspace.current_json_path.stem == workspace.current_pdf_path.stem
    assert load_invoice_json(workspace.current_json_path).client_name == "Test Client"
    if occupied in ("json", "both"):
        assert json_path.read_bytes() == sentinel_json
    if occupied in ("pdf", "both"):
        assert pdf_path.read_bytes() == sentinel_pdf
    if save_action != "save_current":
        assert workspace.current_pdf_path.read_bytes().startswith(b"%PDF-")


def test_save_as_new_keeps_original_invoice_and_pdf(workspace, dialogs):
    set_meta(workspace)
    workspace.save_and_export()
    original_json, original_pdf = workspace.current_json_path, workspace.current_pdf_path
    original_contents = original_json.read_bytes(), original_pdf.read_bytes()
    workspace.c_desc.setText("Additional cost")
    workspace.c_qty.setValue(1)
    workspace.c_price.setValue(20)
    workspace.add_cost()
    workspace.save_as_new()
    assert not dialogs["critical"]
    assert workspace.current_json_path != original_json
    assert workspace.current_pdf_path != original_pdf
    assert workspace.current_json_path.stem == workspace.current_pdf_path.stem
    assert (original_json.read_bytes(), original_pdf.read_bytes()) == original_contents
    assert load_invoice_json(workspace.current_json_path).total_costs() == 20


def test_failed_pdf_export_preserves_saved_invoice_and_dirty_state(workspace, dialogs, monkeypatch):
    set_meta(workspace)
    workspace.save_and_export()
    original_json, original_pdf = workspace.current_json_path, workspace.current_pdf_path
    original_contents = original_json.read_bytes(), original_pdf.read_bytes()
    type_text(workspace.client, "Unsaved rename")

    def fail_export(*args, **kwargs):
        raise RuntimeError("Injected renderer failure")

    monkeypatch.setattr(pdf_gen, "generate_pdf", fail_export)
    workspace.save_and_export()
    assert dialogs["critical"]
    assert workspace.dirty
    assert workspace.current_json_path == original_json
    assert workspace.current_pdf_path == original_pdf
    assert (original_json.read_bytes(), original_pdf.read_bytes()) == original_contents
    assert workspace.client.text() == "Unsaved rename"


def test_failed_new_export_keeps_unsaved_invoice_without_partial_files(workspace, dialogs, monkeypatch):
    set_meta(workspace)
    workspace.go_services()
    add_service(workspace)

    def fail_export(*args, **kwargs):
        raise RuntimeError("Injected renderer failure")

    monkeypatch.setattr(pdf_gen, "generate_pdf", fail_export)
    workspace.save_and_export()
    assert dialogs["critical"]
    assert workspace.dirty
    assert not workspace.edit_mode
    assert workspace.current_json_path is None
    assert workspace.current_pdf_path is None
    assert workspace.invoice.client_name == "Test Client"
    assert len(workspace.invoice.services) == 1
    assert list(settings.JSON_DIR.iterdir()) == []
    assert list(settings.PDF_DIR.iterdir()) == []


def test_reopen_large_default_rate_and_flat_fee_save_without_clamping(workspace, dialogs):
    original = Invoice("Large imported invoice", "04/30/2025", 25_000_000.75)
    original.flat_fee_desc = "Fixed attorney fees"
    original.flat_fee_amount = 40_000_000.50
    path = settings.JSON_DIR / "large-import.json"
    save_invoice_json(original, path)
    select_invoice(workspace, path)
    workspace.open_selected()
    assert workspace.default_rate.value() == original.default_rate
    assert workspace.flat_amount.value() == original.flat_fee_amount
    assert not workspace.dirty

    workspace.save_current()
    assert not dialogs["warning"]
    assert not dialogs["critical"]
    assert load_invoice_json(path).to_dict() == original.to_dict()
    assert not workspace.dirty


def test_reopen_zero_default_rate_no_charge_invoice_survives_save(workspace, dialogs):
    original = Invoice("No charge invoice", "04/30/2025", 0)
    original.add_service(datetime(2025, 4, 1), "Courtesy consultation", 2, 0)
    path = settings.JSON_DIR / "zero-rate-import.json"
    save_invoice_json(original, path)
    select_invoice(workspace, path)
    workspace.open_selected()
    assert workspace.default_rate.value() == 0
    assert workspace.invoice.total_services() == 0

    workspace.save_current()
    assert not dialogs["warning"]
    assert not dialogs["critical"]
    assert load_invoice_json(path).to_dict() == original.to_dict()
    assert not workspace.dirty


@pytest.mark.parametrize("save_action", ["save_current", "save_and_export", "save_as_new"])
@pytest.mark.parametrize("draft_kind", ["service", "cost"])
def test_save_keeps_unadded_entry_draft_dirty_and_guarded(workspace, dialogs, save_action, draft_kind):
    set_meta(workspace)
    workspace.go_services()
    if draft_kind == "service":
        field = workspace.s_desc
    else:
        click_button(workspace.page_services, "Done →")
        field = workspace.c_desc
    type_text(field, "Pending unadded entry")
    assert workspace.dirty
    original_invoice = workspace.invoice

    getattr(workspace, save_action)()
    assert not dialogs["critical"]
    assert workspace.current_json_path.is_file()
    saved = load_invoice_json(workspace.current_json_path)
    assert saved.services == []
    assert saved.costs == []
    assert field.text() == "Pending unadded entry"
    assert workspace.dirty

    workspace.start_new_invoice()
    assert dialogs["question"]
    assert workspace.invoice is original_invoice
    assert field.text() == "Pending unadded entry"


@pytest.mark.parametrize("column,attribute", [(2, "hours"), (3, "rate")])
def test_inline_service_product_overflow_is_rejected(workspace, dialogs, column, attribute):
    service = workspace.invoice.add_service(datetime(2025, 4, 1), "Review", 2, 250)
    workspace._rebuild_service_table()
    original = getattr(service, attribute)
    workspace.set_dirty(False)
    workspace.s_table.item(0, column).setText("1e308")
    assert dialogs["warning"]
    assert getattr(service, attribute) == original
    assert service.amount == 500
    assert workspace.s_table.item(0, column).text() == f"{original:.2f}"
    assert not workspace.dirty


@pytest.mark.parametrize("column,attribute", [(1, "qty"), (2, "unit_price")])
def test_inline_cost_product_overflow_is_rejected(workspace, dialogs, column, attribute):
    cost = workspace.invoice.add_cost("Postage", 2, 9.85)
    workspace._rebuild_cost_table()
    original = getattr(cost, attribute)
    workspace.set_dirty(False)
    workspace.c_table.item(0, column).setText("1e308")
    assert dialogs["warning"]
    assert getattr(cost, attribute) == original
    assert cost.total == pytest.approx(19.70)
    assert workspace.c_table.item(0, column).text() == f"{original:.2f}"
    assert not workspace.dirty


def test_settings_page_saves_one_complete_snapshot_per_change(qapp, dialogs, monkeypatch):
    calls = []
    original_save = settings.save_settings

    def count_save(data):
        calls.append(deepcopy(data))
        original_save(data)

    monkeypatch.setattr(settings, "save_settings", count_save)
    page = main.SettingsPage(lambda: None)
    try:
        assert calls == []
        page.rate.setValue(375)
        assert len(calls) == 1
        assert calls[0]["general"]["default_rate"] == 375
        assert calls[0]["invoice"]["require_explicit_zero_hours"] is True
        assert calls[0]["pdf"]["thousand_separators"] is True
        assert settings.get("general.default_rate") == 375
        assert not dialogs["critical"]
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_settings_page_write_failure_reports_error_without_changing_cache(qapp, dialogs, monkeypatch):
    page = main.SettingsPage(lambda: None)
    original_settings = deepcopy(settings.load_settings())
    calls = []

    def fail_save(data):
        calls.append(data)
        raise OSError("Injected settings write failure")

    monkeypatch.setattr(settings, "save_settings", fail_save)
    try:
        page.rate.setValue(375)
        assert len(calls) == 1
        assert dialogs["critical"]
        assert "Injected settings write failure" in dialogs["critical"][0][2]
        assert settings.load_settings() == original_settings
    finally:
        page.deleteLater()
        qapp.processEvents()


@pytest.mark.parametrize("flat_amount", [100.005, 0.0])
def test_unrelated_edit_preserves_imported_rate_and_flat_fee_precision(workspace, dialogs, flat_amount):
    original = Invoice("Imported invoice", "04/30/2025", 250.005)
    original.flat_fee_desc = "Fixed attorney fees"
    original.flat_fee_amount = flat_amount
    path = settings.JSON_DIR / "precise-import.json"
    save_invoice_json(original, path)
    select_invoice(workspace, path)
    workspace.open_selected()
    assert workspace.default_rate.value() == 250.005
    assert workspace.flat_amount.value() == flat_amount

    type_text(workspace.client, "Renamed imported invoice")
    workspace.save_current()
    assert not dialogs["warning"]
    assert not dialogs["critical"]
    original.client_name = "Renamed imported invoice"
    assert load_invoice_json(path).to_dict() == original.to_dict()
    assert not workspace.dirty


@pytest.mark.parametrize("rate", [250.005, 25_000_000.375])
def test_settings_reload_preserves_rate_precision_when_another_setting_changes(qapp, dialogs, monkeypatch, rate):
    data = deepcopy(settings.DEFAULTS)
    data["general"]["default_rate"] = rate
    settings.SETTINGS_FILE.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(settings, "_cache", None)
    page = main.SettingsPage(lambda: None)
    try:
        assert page.rate.value() == rate
        page.show_hours.setChecked(False)
        assert not dialogs["critical"]
        persisted = json.loads(settings.SETTINGS_FILE.read_text(encoding="utf-8"))
        assert persisted["general"]["default_rate"] == rate
        assert persisted["pdf"]["show_total_hours"] is False
        monkeypatch.setattr(settings, "_cache", None)
        page.load()
        assert page.rate.value() == rate
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_invalid_filename_setting_review_reports_feedback_without_crashing(workspace, dialogs):
    set_meta(workspace)
    workspace.go_services()
    click_button(workspace.page_services, "Done →")
    settings.set_("pdf.file_naming_template", "../folder/{client}.pdf")
    original_invoice = workspace.invoice

    workspace.go_review()
    assert workspace.invoice is original_invoice
    assert workspace.invoice.client_name == "Test Client"
    assert dialogs["warning"] or dialogs["critical"] or "template" in workspace.filename_hint.text().lower()


@pytest.mark.parametrize("field_name", ["s_desc", "s_date", "s_hours", "s_rate"])
def test_ctrl_return_services_advances_without_adding_pending_entry(workspace, dialogs, qapp, field_name):
    set_meta(workspace)
    workspace.go_services()
    workspace.s_desc.setText("Unadded service draft")
    workspace.s_date.setText("04/01/2025")
    workspace.s_hours.setValue(1.25)
    workspace.s_rate.setValue(250)
    field = getattr(workspace, field_name)
    editor = field.lineEdit() if hasattr(field, "lineEdit") else field
    editor.setFocus()
    workspace.activateWindow()
    qapp.processEvents()

    QTest.keyClick(editor, Qt.Key_Return, Qt.ControlModifier)
    qapp.processEvents()
    assert workspace.stack.currentWidget() is workspace.page_costs
    assert workspace.invoice.services == []
    assert workspace.s_desc.text() == "Unadded service draft"
    assert not dialogs["warning"]
    assert not dialogs["critical"]


@pytest.mark.parametrize("field_name", ["c_desc", "c_qty", "c_price"])
def test_ctrl_return_costs_advances_without_adding_pending_entry(workspace, dialogs, qapp, field_name):
    set_meta(workspace)
    workspace.go_services()
    click_button(workspace.page_services, "Done →")
    workspace.c_desc.setText("Unadded cost draft")
    workspace.c_qty.setValue(2)
    workspace.c_price.setValue(9.85)
    field = getattr(workspace, field_name)
    editor = field.lineEdit() if hasattr(field, "lineEdit") else field
    editor.setFocus()
    workspace.activateWindow()
    qapp.processEvents()

    QTest.keyClick(editor, Qt.Key_Return, Qt.ControlModifier)
    qapp.processEvents()
    assert workspace.stack.currentWidget() is workspace.page_review
    assert workspace.invoice.costs == []
    assert workspace.c_desc.text() == "Unadded cost draft"
    assert not dialogs["warning"]
    assert not dialogs["critical"]


def test_ctrl_d_service_prefill_preserves_extra_precision(workspace, dialogs, qapp):
    set_meta(workspace)
    workspace.go_services()
    original = workspace.invoice.add_service(datetime(2025, 4, 1), "Precise service", 1.005, 250.005)
    workspace._rebuild_service_table()
    workspace.s_desc.setFocus()
    workspace.activateWindow()
    qapp.processEvents()
    QTest.keyClick(workspace.s_desc, Qt.Key_D, Qt.ControlModifier)
    qapp.processEvents()
    assert workspace.s_hours.value() == 1.005
    assert workspace.s_rate.value() == 250.005
    type_text(workspace.s_desc, "Copied precise service")
    workspace.add_service()
    assert not dialogs["warning"]
    assert len(workspace.invoice.services) == 2
    copied = workspace.invoice.services[-1]
    assert copied.hours == original.hours
    assert copied.rate == original.rate
    assert copied.amount == original.amount


def test_ctrl_d_cost_prefill_preserves_extra_precision(workspace, dialogs, qapp):
    set_meta(workspace)
    workspace.go_services()
    click_button(workspace.page_services, "Done →")
    original = workspace.invoice.add_cost("Precise cost", 1.005, 9.855)
    workspace._rebuild_cost_table()
    workspace.c_desc.setFocus()
    workspace.activateWindow()
    qapp.processEvents()
    QTest.keyClick(workspace.c_desc, Qt.Key_D, Qt.ControlModifier)
    qapp.processEvents()
    assert workspace.c_qty.value() == 1.005
    assert workspace.c_price.value() == 9.855
    type_text(workspace.c_desc, "Copied precise cost")
    workspace.add_cost()
    assert not dialogs["warning"]
    assert len(workspace.invoice.costs) == 2
    copied = workspace.invoice.costs[-1]
    assert copied.qty == original.qty
    assert copied.unit_price == original.unit_price
    assert copied.total == original.total
