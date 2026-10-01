"""An offline guide that leaves the open invoice and its entry fields alone."""

from __future__ import annotations

from html import escape

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


TOPICS: dict[str, dict[str, str]] = {
    "first_invoice": {
        "title": "Make your first invoice",
        "body": """
            <ol>
                <li>Choose <b>New invoice</b>. Enter the client's name,
                    invoice date, and usual hourly rate.</li>
                <li>Choose <b>Continue</b>. Enter a service description, its date,
                    hours, and rate. Choose <b>Add service</b> or press
                    <b>Enter</b> when the entry is ready.</li>
                <li>Check that the entry appears in the table. Add any other
                    services, then choose <b>Continue to costs</b>.</li>
                <li>Add any costs, such as postage or copies. If there are
                    none, choose <b>Review invoice</b> to continue.</li>
                <li>Check the entries and totals. Choose <b>Save + Export
                    PDF</b> to keep an editable invoice and a PDF.</li>
            </ol>
            <h3>Enter dates quickly</h3>
            <p>Use <b>4/30</b>, <b>4/30/25</b>, or <b>4/30/2025</b>.
                Leaving off the year uses the current year.
                A two-digit year of <b>25</b> means <b>2025</b>.</p>
            <h3>Bill a flat fee</h3>
            <p>On the invoice details screen, select <b>Include a flat service fee</b>.
                Enter a description such as <b>Attorney Fees</b> and an amount
                such as <b>$1,500.00</b>. Continue takes you straight to costs.</p>
            <p>To combine hourly work with a flat fee, enter the hourly
                services first. Return to the invoice details, select
                <b>Include a flat service fee</b>, and enter its description and amount.
                Your existing hourly services remain on the invoice.</p>
            <p>See <a href="help:services">Services and rates</a> or
                <a href="help:saving">Save, edit, and export</a>.</p>
        """,
    },
    "services": {
        "title": "Services and rates",
        "body": """
            <p>Enter a description, date, hours, and hourly rate. Choose
                <b>Add service</b> or press <b>Enter</b> when all four are ready.
                The service must appear in the table to be included.</p>
            <p>Hours use decimals: <b>1.50</b> means one hour and thirty
                minutes; <b>0.25</b> means fifteen minutes.
                For example, <b>1.50 hours at $250.00</b> adds
                <b>$375.00</b> to the invoice.</p>
            <h3>Repeat or change an entry</h3>
            <p>Choose <b>Use last entry</b> or press <b>Ctrl+D</b> to fill the form with the last service you
                added. Change the fields you need, then add the new entry.
                The service date stays in place after each addition.</p>
            <p><b>Clear</b> starts a fresh entry without removing services you
                already added.</p>
            <p>Double-click a service's date, description, hours, or rate in
                the table to change it. Amounts update automatically.
                <b>Remove last service</b> removes the most recently added
                service, even when the table shows services in date order.</p>
            <h3>Choose rates</h3>
            <p>Each service can have its own rate. When you change the default
                rate in the invoice details, choose <b>Keep existing service
                rates</b> to leave previous entries as they are, or
                <b>Apply default rate to every service</b> to update them.
                The default is remembered for the next invoice.</p>
            <h3>No-charge services</h3>
            <p>Type <b>0</b> in Hours if the entry has no hours. BetterBilling
                may ask you to type it explicitly to avoid a missing value.
                To record time without charging, enter the hours and set that
                service's rate to <b>$0.00</b>.</p>
            <h3>Duplicate services</h3>
            <p>BetterBilling blocks a service with the same date, description,
                hours, and rate as an existing service. Review also removes
                matching service duplicates when that setting is enabled.</p>
            <p>See <a href="help:first_invoice">Date entry and flat fees</a>
                or <a href="help:keyboard">Keyboard shortcuts</a>.</p>
        """,
    },
    "costs": {
        "title": "Add costs",
        "body": """
            <p>Costs are expenses such as copies or postage. Enter a
                description, quantity, and price for one item. Choose
                <b>Add cost</b> or press <b>Enter</b> when the entry is ready.</p>
            <p>For example, <b>2</b> certified mail items at <b>$9.85</b> each
                add <b>$19.70</b> to the invoice.</p>
            <p>Check that each cost appears in the table. Double-click its
                description, quantity, or unit price to make a correction.
                The amount updates automatically.</p>
            <p>Choose <b>Use last entry</b> or press <b>Ctrl+D</b> to fill the form with the last cost you
                added. Change the fields you need, then add the new entry.</p>
            <p><b>Clear</b> starts a fresh entry without removing costs you
                already added.</p>
            <p>Choose <b>Review invoice</b> to review the invoice. You can continue
                without adding any costs. Fields left in the entry form are
                not included until you choose Add cost or press Enter.</p>
            <p>See <a href="help:saving">Save, edit, and export</a>.</p>
        """,
    },
    "saving": {
        "title": "Save, edit, and export",
        "body": """
            <h3>Choose how to save</h3>
            <ul>
                <li><b>Save</b> keeps the editable invoice. When editing an
                    existing invoice, it updates that record. It does not
                    update the PDF.</li>
                <li><b>Save + Export PDF</b> keeps the editable invoice and
                    creates or updates its PDF. Choose <b>Open PDF</b> in the
                    confirmation to view it.</li>
                <li><b>Save as new</b> creates a separate editable invoice and
                    PDF while preserving the original. Further saves update
                    the new copy.</li>
            </ul>
            <p>New files receive a number in their name when needed to keep
                an existing invoice safe.</p>
            <h3>Edit an earlier invoice</h3>
            <p>Choose <b>Open an invoice</b>, select the invoice, then choose
                <b>Open selected invoice</b>. Change its details or table entries.
                Use Save + Export PDF to update both the editable invoice and
                the PDF, or Save as new to keep a separate copy.</p>
            <p>Keep the editable invoice record as well as its PDF.
                A PDF alone cannot be reopened for editing in BetterBilling.</p>
            <h3>Check unfinished entries</h3>
            <p>Save includes the services and costs already in the tables.
                An unfinished entry form stays marked unsaved. Return to
                Services or Costs, add the entry, and save again to include it.</p>
            <p>BetterBilling asks before discarding unsaved work when you
                start another invoice, open a different invoice, or close the
                application. Invoices are saved when you choose a save button.</p>
            <h3>If an export cannot finish</h3>
            <p>Read the message and correct the indicated field. Some
                characters cannot appear in the invoice font. You can still
                use Save to keep the editable invoice while fixing the PDF.</p>
            <p>See <a href="help:files">Find files and back up your work</a>.</p>
        """,
    },
    "keyboard": {
        "title": "Keyboard shortcuts",
        "body": """
            <ul>
                <li><b>Tab</b> moves to the next field.
                    <b>Shift+Tab</b> moves to the previous field.</li>
                <li><b>Enter</b> adds the ready service or cost from its entry
                    form. Fill all fields before pressing it.</li>
                <li><b>Ctrl+D</b> fills the service or cost form with the last
                    entry you added. Review and change it before adding it.</li>
                <li><b>Ctrl+Enter</b> continues from Services to Costs, or from
                    Costs to Review. It does not add an unfinished entry;
                    use Enter or the Add button first.</li>
                <li><b>F1</b> opens Help for the current step.</li>
                <li><b>Escape</b> closes Help and returns to the field you were
                    using.</li>
            </ul>
            <p>After adding a service or cost, the description field is ready
                for the next entry. Service dates stay in place for fast
                entry of several services on the same day.</p>
            <p>See <a href="help:services">Services and rates</a> or
                <a href="help:costs">Add costs</a>.</p>
        """,
    },
    "files": {
        "title": "Files and backup",
        "body": """
            <p>Choose <b>Invoice files</b> from the main screen to open your
                invoice and PDF folders. Your records stay with the
                BetterBilling folder on this computer or drive.</p>
            <ul>
                <li><b>data/json</b> holds editable invoice records.</li>
                <li><b>data/pdfs</b> holds exported PDFs for viewing,
                    printing, or attaching to an email.</li>
            </ul>
            <p>Use <b>Open an invoice</b> in BetterBilling to change an invoice.
                Use the exported PDF to print or send it with your usual
                email program.</p>
            <h3>Back up your work</h3>
            <p>Close BetterBilling and copy its whole folder, including the
                data folder, to another drive. This keeps editable invoice
                records, exported PDFs, and your settings together.
                Keep the editable records as well as the PDFs.</p>
            <p>BetterBilling currently relies on copies you make or your
                office's existing backup system. There is no automatic backup
                feature in the application.</p>
            <p>Once installed, invoice entry, saving, and this Help guide work
                without an Internet connection.</p>
            <p>See <a href="help:saving">Save, edit, and export</a>.</p>
        """,
    },
}


class HelpDialog(QDialog):
    """Modeless topic guide; show_topic opens it and preserves draft focus."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("HelpDialog")
        self.setWindowTitle("BetterBilling Help")
        self.setModal(False)
        self.setWindowModality(Qt.NonModal)
        self.setFont(QFont("Segoe UI", 11))
        self.resize(960, 680)
        self.setMinimumSize(780, 500)
        self._previous_focus: QWidget | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(16)

        title = QLabel("Help & keyboard shortcuts")
        title.setObjectName("HelpTitle")
        title.setProperty("role", "title")
        title_font = QFont("Segoe UI", 20)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        introduction = QLabel("Choose a topic. Your invoice stays open while you use Help.")
        introduction.setProperty("role", "muted")
        introduction.setWordWrap(True)
        layout.addWidget(introduction)

        body = QHBoxLayout()
        body.setSpacing(20)
        self.topic_list = QListWidget()
        self.topic_list.setObjectName("HelpTopics")
        self.topic_list.setAccessibleName("Help topics")
        self.topic_list.setMinimumWidth(205)
        self.topic_list.setMaximumWidth(245)
        self.topic_list.setSpacing(5)
        self.topic_list.setWordWrap(True)
        self.topic_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for key, topic in TOPICS.items():
            item = QListWidgetItem(topic["title"])
            item.setData(Qt.UserRole, key)
            self.topic_list.addItem(item)
        body.addWidget(self.topic_list)

        self.content = QTextBrowser()
        self.content.setObjectName("HelpContent")
        self.content.setAccessibleName("Selected help topic")
        self.content.setOpenLinks(False)
        self.content.setOpenExternalLinks(False)
        self.content.setFont(QFont("Segoe UI", 12))
        self.content.document().setDefaultFont(QFont("Segoe UI", 12))
        self.content.document().setDefaultStyleSheet(
            "body { font-family: 'Segoe UI'; font-size: 12pt; } "
            "h2 { font-size: 18pt; margin-bottom: 14px; } "
            "h3 { font-size: 13pt; margin-top: 18px; margin-bottom: 8px; } "
            "p, li { line-height: 145%; } "
            "li { margin-bottom: 8px; }"
        )
        body.addWidget(self.content, 1)
        layout.addLayout(body, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        self.close_button = QPushButton("Close help")
        self.close_button.setObjectName("HelpClose")
        self.close_button.setProperty("kind", "secondary")
        self.close_button.setMinimumHeight(38)
        self.close_button.clicked.connect(self.reject)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)

        self.topic_list.currentItemChanged.connect(self._topic_changed)
        self.content.anchorClicked.connect(self._follow_link)
        self.finished.connect(self._restore_focus)
        self.topic_list.setCurrentRow(0)
        self.setTabOrder(self.topic_list, self.content)
        self.setTabOrder(self.content, self.close_button)

    def show_topic(self, topic_key: str) -> None:
        if not self.isVisible():
            self._previous_focus = QApplication.focusWidget()
        selected = topic_key if topic_key in TOPICS else "first_invoice"
        for row in range(self.topic_list.count()):
            if self.topic_list.item(row).data(Qt.UserRole) == selected:
                self.topic_list.setCurrentRow(row)
                break
        self.show()
        self.raise_()
        self.activateWindow()
        self.topic_list.setFocus(Qt.OtherFocusReason)

    def _topic_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        topic = TOPICS[current.data(Qt.UserRole)]
        self.content.setHtml(
            f"<html><body><h2>{escape(topic['title'])}</h2>{topic['body']}</body></html>"
        )
        self.content.verticalScrollBar().setValue(0)

    def _follow_link(self, url: QUrl) -> None:
        if url.scheme() == "help" and url.path() in TOPICS:
            self.show_topic(url.path())

    def _restore_focus(self, _result: int) -> None:
        previous = self._previous_focus
        self._previous_focus = None
        if previous is None:
            return

        def return_to_draft() -> None:
            try:
                if previous.isVisible() and previous.isEnabled():
                    previous.window().activateWindow()
                    previous.setFocus(Qt.OtherFocusReason)
            except RuntimeError:
                # The original field may have been deleted while modeless
                # Help was open. Returning focus must not interrupt closing.
                pass

        QTimer.singleShot(0, return_to_draft)
