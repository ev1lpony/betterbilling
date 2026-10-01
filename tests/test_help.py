from copy import deepcopy

import pytest
from PySide6.QtCore import Qt, QUrl
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLineEdit, QVBoxLayout, QWidget

from help_ui import HelpDialog, TOPICS
import settings


@pytest.fixture
def guide(qapp):
    dialog = HelpDialog()
    yield dialog
    dialog.close()
    qapp.processEvents()


def test_help_has_all_context_topics_and_is_modeless(guide):
    assert set(TOPICS) == {"first_invoice", "services", "costs", "saving", "keyboard", "files"}
    assert guide.topic_list.count() == 6
    assert not guide.isModal()
    assert guide.windowModality() == Qt.NonModal


@pytest.mark.parametrize("key", list(TOPICS))
def test_each_topic_opens_readable_content(guide, qapp, key):
    guide.show_topic(key)
    qapp.processEvents()
    assert guide.isVisible()
    assert guide.topic_list.currentItem().data(Qt.UserRole) == key
    assert TOPICS[key]["title"] in guide.content.toPlainText()
    paragraph = guide.content.document().begin().next()
    assert paragraph.begin().fragment().charFormat().fontPointSize() >= 12
    assert not guide.content.openExternalLinks()
    assert not guide.content.openLinks()


def test_internal_links_change_topics_without_external_navigation(guide, qapp):
    guide.show_topic("services")
    guide.content.anchorClicked.emit(QUrl("help:saving"))
    qapp.processEvents()
    assert guide.topic_list.currentItem().data(Qt.UserRole) == "saving"
    text = guide.content.toPlainText()
    guide.content.anchorClicked.emit(QUrl("https://example.com"))
    guide.content.anchorClicked.emit(QUrl("file:///C:/outside.txt"))
    guide.content.anchorClicked.emit(QUrl("help:unknown"))
    assert guide.content.toPlainText() == text


def test_unknown_context_falls_back_to_first_invoice(guide):
    guide.show_topic("unknown")
    assert guide.topic_list.currentItem().data(Qt.UserRole) == "first_invoice"


def test_help_does_not_write_settings_or_invoice_folders(guide, monkeypatch):
    original = deepcopy(settings._cache)

    def forbidden_write(*args, **kwargs):
        raise AssertionError("Help must not write preferences")

    monkeypatch.setattr(settings, "save_settings", forbidden_write)
    for key in TOPICS:
        guide.show_topic(key)
    assert settings._cache == original
    assert not settings.SETTINGS_FILE.exists()
    assert not settings.DATA_DIR.exists()


@pytest.mark.parametrize("close_action", ["escape", "button", "window"])
def test_close_returns_to_same_draft_and_preserves_selection(qapp, close_action):
    parent = QWidget()
    layout = QVBoxLayout(parent)
    draft = QLineEdit("Review IRS notice")
    layout.addWidget(draft)
    parent.show()
    parent.activateWindow()
    draft.setFocus()
    draft.setSelection(7, 3)
    qapp.processEvents()
    assert draft.hasFocus()

    dialog = HelpDialog(parent)
    dialog.show_topic("services")
    qapp.processEvents()
    # A later context request while Help is open must not lose the draft focus.
    dialog.show_topic("keyboard")
    if close_action == "escape":
        QTest.keyClick(dialog, Qt.Key_Escape)
    elif close_action == "button":
        QTest.mouseClick(dialog.close_button, Qt.LeftButton)
    else:
        dialog.close()
    qapp.processEvents()
    assert not dialog.isVisible()
    assert draft.hasFocus()
    assert draft.text() == "Review IRS notice"
    assert draft.selectionStart() == 7
    assert draft.selectedText() == "IRS"
    parent.close()
    qapp.processEvents()


def test_help_is_clear_that_continue_does_not_add_a_draft(guide):
    guide.show_topic("keyboard")
    text = guide.content.toPlainText()
    assert "does not add an unfinished entry" in text
    guide.show_topic("saving")
    text = guide.content.toPlainText()
    assert "It does not update the PDF" in text
    assert "Further saves update the new copy" in text


def test_help_uses_current_visible_button_names(guide):
    guide.show_topic("first_invoice")
    text = guide.content.toPlainText()
    assert "New invoice" in text
    assert "Continue to costs" in text
    assert "Review invoice" in text
    assert "Include a flat service fee" in text
    assert "Next" not in text
    assert "Done" not in text
    guide.show_topic("saving")
    text = guide.content.toPlainText()
    assert "Open an invoice" in text
    assert "Open selected invoice" in text
    assert "Save as new" in text
