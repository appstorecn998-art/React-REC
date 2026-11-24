"""Modern Qt desktop front-end for the local Auto Receiving workflow.

The window is deliberately a thin UI layer.  Excel writes, review hashes,
backups and publish conflict checks remain in ``receiving_service``.  Image
brightening and page cropping are preview-only; source photographs are never
overwritten.
"""
from __future__ import annotations
from receiving_pr_image_identity import pr_images_match
from receiving_image_archive import image_name, source_digest

import json
import hashlib
import codecs
import re
import time
import os
import subprocess
import sys
from collections import OrderedDict
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import (QAbstractTableModel, QDate, QItemSelectionModel, QModelIndex, QObject, QPoint, QProcess, QTimer, QEvent,
                            QRunnable, QRect, QRectF, QSize, Qt, QThreadPool, Signal,
                            Slot)
from PySide6.QtGui import QAction, QColor, QFont, QFontDatabase, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QInputDialog,
    QApplication, QCalendarWidget, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QFrame, QGraphicsPixmapItem, QGraphicsScene,
    QGraphicsView, QGroupBox, QGridLayout, QHBoxLayout, QLabel, QListView, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QStatusBar, QTableView, QToolButton, QVBoxLayout, QWidget, QPlainTextEdit,
    QAbstractItemView, QStyledItemDelegate, QStyle, QStackedWidget, QProgressBar,
    QTableWidget, QTableWidgetItem, QTabWidget,
)

from fluent_blue import Button, Switch, Input, Select, Checkbox
from receiving_preview import prepare_preview
from receiving_ledger_ui import LedgerUI
from receiving_pr_library_ui import PRLibraryUI
from receiving_review import has_code, numeric_issues, ranked_codes, normalized, choose_region, crop_region
from receiving_service import (
    atomic_json, close_day, day_images, digest, display_rows, edit_row,
    import_images, invoice_images, paths, sheet_signature, snapshot, accounting_root, EDITABLE, mutate_invoice,
)


ACCOUNTING_DEFAULT = Path.home() / "Desktop" / "Công việc" / "Kế toán" / "Phieu giao hang hang thang"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


def app_root() -> Path:
    from rec_runtime import initialize
    return initialize()


def read_settings(root: Path) -> dict:
    path = root / ".receiving" / "settings.json"
    if not path.exists():
        return {"destination": str(ACCOUNTING_DEFAULT)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"destination": str(ACCOUNTING_DEFAULT)}
    except (OSError, ValueError):
        return {"destination": str(ACCOUNTING_DEFAULT)}


def save_settings(root: Path, destination: str) -> None:
    atomic_json(root / ".receiving" / "settings.json", {"destination": destination})


def day_from_widget(widget: QDateEdit) -> date:
    qday = widget.date()
    return date(qday.year(), qday.month(), qday.day())


class WorkerSignals(QObject):
    progress = Signal(str)
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class CleanCellDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        option.state &= ~QStyle.State_HasFocus
        super().paint(painter, option, index)

class PRAlertDelegate(CleanCellDelegate):
    def paint(self,painter,option,index):
        if not index.data(Qt.UserRole+12):return super().paint(painter,option,index)
        painter.save();painter.setClipRect(option.rect)
        painter.fillRect(option.rect,index.data(Qt.BackgroundRole))
        painter.setFont(index.data(Qt.FontRole) or option.font)
        foreground=index.data(Qt.ForegroundRole)
        painter.setPen(foreground.color() if foreground is not None else QColor('#172b4d'))
        alignment=int(index.data(Qt.TextAlignmentRole) or (Qt.AlignLeft|Qt.AlignVCenter))
        painter.drawText(option.rect.adjusted(8,6,-8,-6),alignment|int(Qt.TextWordWrap),str(index.data(Qt.DisplayRole) or ''))
        if option.state & QStyle.State_Selected:
            painter.setPen(QPen(QColor('#2563d9'),2));painter.drawLine(option.rect.bottomLeft(),option.rect.bottomRight())
        painter.restore()


class RowStripView(QGraphicsView):
    def wheelEvent(self,event):
        factor=1.2 if event.angleDelta().y()>0 else 1/1.2
        if .05 <= self.transform().m11()*factor <= 8:
            self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse); self.scale(factor,factor)
        event.accept()


class DepartmentDelegate(CleanCellDelegate):
    def __init__(self, window):
        super().__init__(window.table)
        self.window = window

    def createEditor(self, parent, option, index):
        if index.model().visible[index.column()] != 'Bộ phận':
            return super().createEditor(parent, option, index)
        try:
            directory = self.window.get_warehouses()
        except Exception as exc:
            QMessageBox.warning(self.window, 'Không đọc được danh mục kho', str(exc)); return None
        editor = QComboBox(parent)
        editor.addItem('Chưa chọn kho / bộ phận', '')
        for code, (name, department) in directory.items():
            editor.addItem(f'{department or "Chưa có bộ phận"} · {name} · {code}', code)
        editor.activated.connect(lambda _: self.commitData.emit(editor))
        editor.activated.connect(lambda _: self.closeEditor.emit(editor))
        editor.setMinimumWidth(220)
        QTimer.singleShot(0, editor.showPopup)
        return editor

    def setEditorData(self, editor, index):
        if not isinstance(editor, QComboBox): return super().setEditorData(editor, index)
        code = str(index.model().row_values(index.row()).get('Mã kho') or '')
        editor.setCurrentIndex(editor.findData(code))

    def setModelData(self, editor, model, index):
        if not isinstance(editor, QComboBox): return super().setModelData(editor, model, index)
        code = editor.currentData()
        old = str(model.row_values(index.row()).get('Mã kho') or '')
        if code is not None and code != old:
            model.editRequested.emit((model.source_row(index.row()), {'Mã kho': code}))


class CalendarDateEdit(QPushButton):
    dateChanged = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        from rec_workdays import previous_workday
        self._date = QDate(previous_workday(date.today()))
        self.popup = QFrame(self, Qt.Popup)
        layout = QVBoxLayout(self.popup); layout.setContentsMargins(8,8,8,8)
        from rec_workdays import WorkdayCalendar
        self.calendar = WorkdayCalendar(self.popup)
        self.calendar.setGridVisible(False)
        self.calendar.setMinimumSize(350,290)
        layout.addWidget(self.calendar)
        self.calendar.clicked.connect(self.choose_date)
        self.calendar.activated.connect(self.choose_date)
        self.calendar.installEventFilter(self)
        self.clicked.connect(self.show_calendar)
        icon = QPixmap(28,28); icon.fill(Qt.transparent)
        painter = QPainter(icon); painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor('#2156bd'),2))
        painter.drawRoundedRect(3,5,22,20,3,3)
        for x1,y1,x2,y2 in [(3,11,25,11),(9,3,9,8),(19,3,19,8),(8,16,11,16),(17,16,20,16),(8,21,11,21),(17,21,20,21)]:
            painter.drawLine(x1,y1,x2,y2)
        painter.end(); self.setIcon(QIcon(icon))
        self.setIconSize(QSize(26,26))
        self.update_text()

    def eventFilter(self, obj, event):
        if obj == self.calendar and event.type() == QEvent.Wheel:
            event.accept(); return True
        return super().eventFilter(obj, event)

    def wheelEvent(self, event):
        event.accept()

    def date(self):
        return self._date

    def setDate(self, value):
        value = QDate(value.year, value.month, value.day) if isinstance(value,date) else QDate(value)
        if not value.isValid() or value.dayOfWeek()>5 or value == self._date: return
        self._date = value; self.calendar.setSelectedDate(value); self.update_text()
        self.dateChanged.emit(value)

    def update_text(self):
        self.setText(self._date.toString('dd/MM/yyyy'))

    def choose_date(self, value):
        if value.dayOfWeek()>5:
            self.calendar.setSelectedDate(self._date);return
        self.popup.hide(); self.setDate(value)

    def show_calendar(self):
        self.calendar.setSelectedDate(self._date)
        self.calendar.setCurrentPage(self._date.year(),self._date.month())
        self.popup.adjustSize(); self.place_calendar(); self.popup.show()
        self.calendar.setFocus()

    def place_calendar(self):
        popup = self.popup
        bounds = self.window().frameGeometry().intersected(self.screen().availableGeometry())
        point = self.mapToGlobal(QPoint(self.width(), self.height()))
        x = max(bounds.left(), min(point.x()-popup.width(), bounds.right()-popup.width()+1))
        y = max(bounds.top(), min(point.y(), bounds.bottom()-popup.height()+1))
        popup.move(x, y)


class CatalogModel(QAbstractTableModel):
    def __init__(self, catalog, parent=None):
        super().__init__(parent)
        self.entries = [(str(code), str(v[0]), str(v[1])) for code, v in catalog.items()]
        self.search_text = [normalized(code+' '+name) for code,name,unit in self.entries]
        self.indices = list(range(len(self.entries)))

    def filter(self, query):
        words = normalized(query).split()
        indices = [i for i,text in enumerate(self.search_text) if all(w in text for w in words)] if words else list(range(len(self.entries)))
        self.beginResetModel(); self.indices = indices; self.endResetModel()

    def rowCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self.indices)
    def columnCount(self, parent=QModelIndex()): return 0 if parent.isValid() else 3
    def data(self, index, role=Qt.DisplayRole):
        if index.isValid() and role in (Qt.DisplayRole, Qt.ToolTipRole):
            return self.entries[self.indices[index.row()]][index.column()]
        return None
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal: return ['Mã hàng', 'Tên chuẩn hệ thống', 'ĐVT'][section]


class Worker(QRunnable):
    def __init__(self, function, *args, **kwargs):
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            self.signals.result.emit(self.function(*self.args, **self.kwargs))
        except Exception as exc:  # never show a traceback in the user-facing UI
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()


class ReceiptTableModel(QAbstractTableModel):
    editRequested = Signal(object)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.columns: list[str] = []
        self.rows: list[tuple[int, dict]] = []
        self.original_rows = []
        self.review_issues = {}
        self.visible: list[str] = []
        self.hidden_columns = {
            "Ghi chú", "Độ khớp AI đề xuất", "Trạng thái", "Nguồn chọn mã",
            "Chi tiết đối chiếu PR", "Chi tiết đối chiếu", "Đối chiếu PR",
            "Người đề nghị PR", "Căn cứ PR phân kho", "Ảnh nguồn", "SHA-256 ảnh nguồn",
            "Các ảnh cùng phiếu",
            "Thành tiền gốc (trước công thức)", "Thành tiền trên phiếu", "STT trên phiếu",
            "Tổng tiền phiếu (cộng Thành tiền)", "Tổng tiền trên phiếu (Số lượng × Đơn giá)",
        }
        self.core = [
            "Tên hàng trên phiếu (Ảnh)", "Mã vật tư", "Tên chuẩn hệ thống", "Đơn vị tính",
            "Độ khớp AI đề xuất", "Trạng thái", "Ghi chú", "Số lượng", "Thực nhận",
            "Nguồn chọn mã", "Đối chiếu PR", "Chi tiết đối chiếu PR", "Nhà cung cấp", "Nhóm đối chiếu",
            "Đơn giá", "Thành tiền", "Ngày giao hàng", "Thời gian chụp", "Mã kho", "Tên kho", "Bộ phận",
            "Người đề nghị PR", "Căn cứ PR phân kho", "Ngày nhận hàng xác nhận", "Ảnh nguồn",
            "Tổng tiền phiếu (cộng Thành tiền)", "STT trên phiếu", "SHA-256 ảnh nguồn",
            "Thành tiền gốc (trước công thức)", "Thành tiền trên phiếu",
            "Tổng tiền trên phiếu (Số lượng × Đơn giá)",
        ]
        self.compact = ["Thời gian chụp", "STT trên phiếu", "Tên hàng trên phiếu (Ảnh)", "Đơn vị tính", "Số lượng", "Thực nhận", "Đơn giá", "Thành tiền"]
        self.labels = {
            "STT trên phiếu": "STT", "Tên hàng trên phiếu (Ảnh)": "Mặt hàng",
            "Mã vật tư": "Mã hàng", "Đơn vị tính": "ĐVT", "Số lượng": "SL giao",
            "Thực nhận": "SL nhận", "Đơn giá": "Đơn giá", "Thành tiền": "Thành tiền",
            "Tổng tiền phiếu (cộng Thành tiền)": "Tổng thực nhận",
            "Tổng tiền trên phiếu (Số lượng × Đơn giá)": "Tổng trên phiếu",
        }

    def set_rows(self, rows, show_all=False, columns=None):
        self.beginResetModel()
        self.rows = display_rows(rows)
        self.original_rows = rows
        available = list(dict.fromkeys(h for _, values in self.rows for h in values if h))
        self.columns = [h for h in self.core if h in available] + [h for h in available if h not in self.core]
        selected = list(columns) if columns is not None else (self.columns if show_all else [h for h in self.columns if h in self.compact])
        self.visible = [h for h in selected if h not in self.hidden_columns and not h.startswith('SHA-256')]
        self.endResetModel()

    def row_values(self, row: int) -> dict:
        return self.original_rows[row][1]

    def flags(self, index):
        flags = super().flags(index)
        if index.isValid() and self.visible[index.column()] in (EDITABLE | {'Bộ phận'}):
            flags |= Qt.ItemIsEditable
        return flags

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.EditRole and index.isValid():
            header = self.visible[index.column()]
            if header not in EDITABLE:
                return False
            original = self.row_values(index.row()).get(header)
            text = str(value)
            if text != ("" if original is None else str(original)):
                self.editRequested.emit((self.source_row(index.row()), {header: text}))
            return True
        return False

    def source_row(self, row: int) -> int:
        return self.rows[row][0]

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.visible)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.rows):
            return None
        header = self.visible[index.column()]
        value = self.rows[index.row()][1].get(header)
        if role == Qt.EditRole:
            raw = self.original_rows[index.row()][1].get(header)
            return "" if raw is None else str(raw)
        if role == Qt.ToolTipRole:
            if header=='Đơn giá' and self.rows[index.row()][1].get('Thuế suất VAT đã tách'):
                data=self.rows[index.row()][1]
                return 'Giá trước thuế: '+str(value)+'\nGiá NCC gốc gồm VAT: '+str(data.get('Giá NCC gồm VAT gốc'))+'\nĐã tách VAT '+str(data.get('Thuế suất VAT đã tách'))+'%'
            if header == 'Tên chuẩn hệ thống' and not has_code(self.original_rows[index.row()][1]):
                return 'Chưa chọn mã; giữ tên trên phiếu để tra danh mục.'
            reasons = self.review_issues.get(self.rows[index.row()][0], [])
            if reasons: return ('' if value is None else str(value)) + '\nCần kiểm: ' + '; '.join(reasons)
            return "" if value is None else str(value)
        if role == Qt.DisplayRole:
            if header == 'Tên chuẩn hệ thống' and not has_code(self.original_rows[index.row()][1]):
                return ''
            if value is None:
                return "Chọn bộ phận ▾" if header == 'Bộ phận' else ""
            if header == 'Đơn vị tính':
                from receiving_sheets import display_unit
                return display_unit(value)
            if header == 'Bộ phận':
                return (str(value) if str(value).strip() else 'Chọn bộ phận') + ' ▾'
            if header=='Thời gian chụp':
                text=str(value or '')
                try:
                    from datetime import time
                    return time.fromisoformat(text).strftime('%H:%M')
                except ValueError:return text
            if header == "Tên hàng trên phiếu (Ảnh)" and "Mã vật tư" not in self.visible:
                code = self.rows[index.row()][1].get("Mã vật tư") or "Chưa có mã"
                return f"{value}\n{code}"
            if header in {"Đơn giá", "Thành tiền", "Thành tiền trên phiếu"} and isinstance(value, (int, float)):
                return f"{value:,.2f}".rstrip("0").rstrip(".")
            return str(value)
        if role == Qt.TextAlignmentRole:
            return self.alignment(header)
        if role == Qt.BackgroundRole:
            values = self.rows[index.row()][1]
            issue = (not values.get("Mã vật tư") or values.get("Mã vật tư") == "CHUA CO MA"
                     or values.get("Thực nhận") is None or values.get("Đơn giá") is None
                     or "KIỂM" in str(values.get("Trạng thái", "")))
            if issue:
                return QColor("#fff7e6")
            if index.row() % 2:
                return QColor("#f8fbff")
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.TextAlignmentRole and orientation == Qt.Horizontal and section < len(self.visible):
            return self.alignment(self.visible[section])
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and section < len(self.visible):
            return self.labels.get(self.visible[section], self.visible[section])
        if orientation == Qt.Vertical:
            return str(section + 1)
        return None

    @staticmethod
    def alignment(header):
        if header in {"STT trên phiếu", "Đơn vị tính"}:
            return int(Qt.AlignCenter)
        if header in {"Số lượng", "Thực nhận", "Đơn giá", "Thành tiền", "Thành tiền trên phiếu", "Thành tiền gốc (trước công thức)"} or header.startswith('Tổng tiền'):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return int(Qt.AlignLeft | Qt.AlignVCenter)


class PreviewView(QGraphicsView):
    """A cursor-anchored, bounded preview viewer for large receipt photos."""
    imageChanged = Signal(str)
    previewReady = Signal(str)

    def __init__(self, parent=None):
        self._scene = QGraphicsScene()
        super().__init__(self._scene, parent)
        self.setRenderHints(QPainter.SmoothPixmapTransform | QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#edf2f7"))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.item: QGraphicsPixmapItem | None = None
        self.source_path: Path | None = None
        self._original_qimage = None
        self.preview_label = ""
        self.light = True
        self.crop = True
        self.request_id = 0
        self.cache = OrderedDict()
        self.pending_images = {}
        self.prefetch_failures = set()
        self.workers = []
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.fitted = True
        self.magnifier = False
        self.lens_point = None
        self.focus_region = None
        self.preview_info = {}
        self.setMouseTracking(True); self.viewport().setMouseTracking(True)

    @property
    def original(self):
        # Compatibility for pixel inspection; keep only Qt's RGB buffer in RAM.
        qimage=self._original_qimage
        if qimage is None:return None
        from PIL import Image
        return Image.frombytes('RGB',(qimage.width(),qimage.height()),bytes(qimage.constBits()),'raw','RGB',qimage.bytesPerLine())

    def set_magnifier(self, enabled):
        self.magnifier = enabled; self.lens_point = None; self.viewport().update()

    def set_focus_region(self, path=None, box=None):
        self.focus_region = (Path(path), box) if path is not None and box is not None and Path(path) == self.source_path else None
        self.viewport().update()

    def focus_rect(self):
        if not self.item or not self.focus_region or self.focus_region[0] != self.source_path: return None
        info = self.preview_info
        size = info.get('original_size')
        if not size: return None
        crop = info.get('crop_box') or (0,0,*size)
        sx = self.item.pixmap().width() / (crop[2]-crop[0])
        sy = self.item.pixmap().height() / (crop[3]-crop[1])
        x0,y0,x1,y1 = self.focus_region[1]
        rect = QRectF((x0-crop[0])*sx,(y0-crop[1])*sy,(x1-x0)*sx,(y1-y0)*sy)
        rect = rect.intersected(self.item.boundingRect())
        return rect if not rect.isEmpty() else None

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.item: return
        painter = QPainter(self.viewport()); painter.setRenderHint(QPainter.Antialiasing)
        focus = self.focus_rect()
        if focus is not None:
            full = QPainterPath(); full.addPolygon(self.mapFromScene(self.item.boundingRect()))
            hole = QPainterPath(); hole.addPolygon(self.mapFromScene(focus))
            painter.fillPath(full.subtracted(hole), QColor(0,0,0,155))
            painter.setPen(QPen(QColor('#3b82f6'),2)); painter.drawPolygon(self.mapFromScene(focus))
        if self.magnifier and self.lens_point is not None:
            source = self.mapToScene(self.lens_point)
            if self.item.boundingRect().contains(source):
                radius = min(105, self.viewport().width()//3, self.viewport().height()//3)
                cx = max(radius+4,min(self.viewport().width()-radius-4,self.lens_point.x()+radius+25))
                cy = max(radius+4,min(self.viewport().height()-radius-4,self.lens_point.y()-radius-20))
                lens = QRectF(cx-radius,cy-radius,2*radius,2*radius)
                clip = QPainterPath();clip.addEllipse(lens)
                painter.save();painter.setClipPath(clip);painter.fillRect(lens,Qt.white)
                painter.translate(cx,cy)
                zoom = max(1.,self.transform().m11()*3)
                painter.scale(zoom,zoom);painter.drawPixmap(-source,self.item.pixmap());painter.restore()
                painter.setPen(QPen(QColor('#2563d9'),3));painter.drawEllipse(lens)
        painter.end()

    def mouseMoveEvent(self,event):
        self.lens_point = event.position().toPoint() if not event.buttons() else None
        super().mouseMoveEvent(event);self.viewport().update()

    def leaveEvent(self,event):
        self.lens_point = None;self.viewport().update();super().leaveEvent(event)

    def clear_image(self, message="Chọn một phiếu để xem ảnh"):
        self.focus_region = None; self.lens_point = None
        self.request_id += 1
        self.source_path = None
        self.item = None
        self._original_qimage = None
        self.scene().clear()
        self.imageChanged.emit(message)
        self.previewReady.emit("")

    def set_options(self, light, crop):
        if (light, crop) == (self.light, self.crop):
            return
        self.light, self.crop = light, crop
        if self.source_path:
            self.set_image(self.source_path, force=True)

    def set_image(self, path: Path, force=False):
        try:
            source_stat = path.stat()
            current_key = (str(path), source_stat.st_mtime_ns, source_stat.st_size, self.light, self.crop, getattr(self,'contrast',False))
        except OSError:
            current_key = None
        if not force and self.source_path == path and self.item is not None and current_key == getattr(self, "display_key", None):
            return
        self.request_id += 1
        token = self.request_id
        if self.source_path != path: self.focus_region = None
        self.lens_point = None
        self.source_path = path
        self.item = None
        self.scene().clear()
        self._original_qimage = None
        self.imageChanged.emit(path.name)
        self.setCursor(Qt.WaitCursor)
        self.previewReady.emit("Đang chuẩn bị ảnh…")
        try:
            info = path.stat()
            key = (str(path), info.st_mtime_ns, info.st_size, self.light, self.crop, getattr(self,'contrast',False))
        except OSError as exc:
            self._failed(str(exc)); return
        if key in self.cache:
            self.cache.move_to_end(key)
            self._loaded((token, key, *self.cache[key]))
            return
        self._prepare_image(path, key, token)

    def prefetch(self, path):
        # Speculation never queues behind a visible image or starts a second job.
        if self.workers:return
        path=Path(path)
        try:
            st=path.stat()
            key=(str(path),st.st_mtime_ns,st.st_size,self.light,self.crop,getattr(self,'contrast',False))
        except OSError:return
        if key not in self.cache and key not in self.prefetch_failures:self._prepare_image(path,key,None)

    def _prepare_image(self, path, key, token):
        if key in self.pending_images:
            if token is not None:self.pending_images[key]=token
            return
        self.pending_images[key]=token
        light,crop,contrast=key[3:]
        def load():
            image,info=prepare_preview(path,light=light,crop=crop)
            if contrast:
                from PIL import ImageEnhance
                image=ImageEnhance.Contrast(image).enhance(1.3)
            st=path.stat()
            if (st.st_mtime_ns,st.st_size)!=key[1:3]:raise ValueError('Ảnh thay đổi khi đang tải')
            qimage=QImage(image.tobytes('raw','RGB'),image.width,image.height,image.width*3,QImage.Format_RGB888).copy()
            return token,key,info,qimage
        worker=Worker(load)
        worker.signals.result.connect(self._prepared)
        def failed(message):
            requested=self.pending_images.get(key)
            if requested is None:
                if len(self.prefetch_failures)>=64:self.prefetch_failures.clear()
                self.prefetch_failures.add(key)
            if requested is not None and requested==self.request_id:self._failed(message)
        worker.signals.error.connect(failed)
        self.workers.append(worker)
        def finished():
            self.pending_images.pop(key,None)
            if worker in self.workers:self.workers.remove(worker)
        worker.signals.finished.connect(finished)
        self.pool.start(worker)

    @Slot(object)
    def _prepared(self, payload):
        self._loaded((self.pending_images.get(payload[1]),*payload[1:]))

    @Slot(object)
    def _loaded(self, payload):
        token,key,info,qimage=payload
        try:
            st=Path(key[0]).stat()
            if (st.st_mtime_ns,st.st_size)!=key[1:3]:
                if token is not None and token==self.request_id:self._failed('Ảnh thay đổi khi đang tải')
                return
        except OSError as exc:
            if token is not None and token==self.request_id:self._failed(str(exc))
            return
        self.cache[key]=(info,qimage)
        self.cache.move_to_end(key)
        # Retain one RGB buffer per image, capped by bytes and count; no disk cache.
        def cache_bytes():return sum(qi.sizeInBytes() for _,qi in self.cache.values())
        while self.cache and (len(self.cache)>3 or cache_bytes()>64*1024*1024):self.cache.popitem(last=False)
        if token is None or token!=self.request_id or not self.source_path:return
        self._original_qimage=qimage;self.preview_info=info;self.display_key=key
        self.preview_label=info.get('label','')
        self.item=self.scene().addPixmap(QPixmap.fromImage(qimage))
        w,h=qimage.width(),qimage.height()
        self.scene().setSceneRect(-w,-h,w*3,h*3)
        self.setCursor(Qt.ArrowCursor)
        self.previewReady.emit(self.preview_label+' · Ảnh gốc được giữ nguyên')
        self.fit_image()

    def _failed(self, message: str):
        self.scene().clear()
        self.item = None
        self._original_qimage = None
        self.setCursor(Qt.ArrowCursor)
        self.previewReady.emit("Chưa xem được ảnh. Có thể thử mở ảnh gốc bằng ứng dụng ảnh trên máy.")
        self.imageChanged.emit(f"Không xem được ảnh: {message}")

    def fit_image(self):
        if self.item:
            self.resetTransform()
            self.fitInView(self.item, Qt.KeepAspectRatio)
            self.centerOn(self.item)
            self.fitted = True

    def zoom_at(self, factor, point=None):
        if not self.item:
            return
        point = point or self.viewport().rect().center()
        current = self.transform().m11()
        desired = max(.015, min(12., current * factor))
        old_pos = self.mapToScene(point)
        self.scale(desired / current, desired / current)
        new_pos = self.mapToScene(point)
        self.translate(new_pos.x() - old_pos.x(), new_pos.y() - old_pos.y())
        self.fitted = False

    def wheelEvent(self, event):
        if not self.item:
            event.ignore()
            return
        factor = 1.18 if event.angleDelta().y() > 0 else 1 / 1.18
        self.zoom_at(factor, event.position().toPoint())
        event.accept()

    def mouseDoubleClickEvent(self, event):
        self.fit_image()
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fitted:
            self.fit_image()


class InboxSwitch(Switch):
    """Fluent switch retaining the existing toggled/isChecked contract."""
    def __init__(self,parent=None):
        super().__init__('Tự nhận và đọc ảnh',parent)
        self.setAccessibleName('Tự nhận và đọc ảnh')
        self.setToolTip('Bật để tự lấy và đọc ảnh; tắt để ngừng nhận tự động.')


class PRLineCombo(QComboBox):
    """Scrolling the comparison must never change its line assignments."""
    def wheelEvent(self, event):
        event.ignore()


class EditDialog(QDialog):
    def __init__(self, values: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sửa dòng nhận hàng")
        self.setMinimumWidth(720)
        self.fields = {}
        outer = QVBoxLayout(self); outer.setContentsMargins(24, 20, 24, 20); outer.setSpacing(14)
        heading = QLabel("Thông tin dòng nhận hàng"); heading.setObjectName("section"); outer.addWidget(heading)
        form = QFormLayout(); form.setSpacing(10); outer.addLayout(form)
        editable = [
            "Nhà cung cấp", "Ngày nhận hàng xác nhận", "Ngày giao hàng", "Thời gian chụp",
            "Tên hàng trên phiếu (Ảnh)", "Mã vật tư", "Đơn vị tính", "Số lượng",
            "Thực nhận", "Đơn giá", "Mã kho", "Ghi chú",
        ]
        for header in editable:
            if header not in values:
                continue
            from fluent_blue import Input
            editor = Input()
            editor.setText("" if values.get(header) is None else str(values.get(header)))
            form.addRow(header, editor)
            self.fields[header] = editor
        self.warehouse_choice = None
        if 'Mã kho' in values and parent is not None and hasattr(parent, 'get_warehouses'):
            directory = parent.get_warehouses()
            self.warehouse_choice = QComboBox()
            self.warehouse_choice.addItem('Chưa chọn kho / bộ phận', '')
            for code, (name, department) in directory.items():
                self.warehouse_choice.addItem(f'{department or "Chưa có bộ phận"} · {name} · {code}', code)
            self.warehouse_choice.setCurrentIndex(self.warehouse_choice.findData(str(values.get('Mã kho') or '')))
            form.insertRow(0, 'Bộ phận / kho', self.warehouse_choice)
            self.fields['Mã kho'].setReadOnly(True)
            warehouse_name = QLineEdit(str(values.get('Tên kho') or '')); warehouse_name.setReadOnly(True)
            form.insertRow(1, 'Tên kho', warehouse_name)
            def changed(index):
                code = self.warehouse_choice.itemData(index)
                if code is None: return
                self.fields['Mã kho'].setText(code)
                warehouse_name.setText(directory.get(code, ('', ''))[0])
            self.warehouse_choice.currentIndexChanged.connect(changed)
        hint = QLabel("Số dùng dấu chấm thập phân; mã hợp lệ sẽ lấy tên chuẩn và ĐVT từ danh mục.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        form.addRow(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Lưu thay đổi")
        buttons.button(QDialogButtonBox.Save).setObjectName("primary")
        buttons.button(QDialogButtonBox.Cancel).setText("Hủy")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        from rec_edit_layout import arrange
        arrange(self,outer,form)

    def changes(self, original: dict) -> dict:
        return {h: editor.text() for h, editor in self.fields.items()
                if editor.text() != ("" if original.get(h) is None else str(original.get(h)))}


# Avoid a long import list above while keeping the edit dialog easy to scan.
from PySide6.QtWidgets import QLineEdit


class ReadingProgress(QWidget):
    """Live view of engine output; OCR completion is distinct from saved invoices."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self); layout.setContentsMargins(12, 12, 12, 12); layout.setSpacing(12)
        self.heading = QLabel('Tiến độ đọc ảnh'); self.heading.setObjectName('section'); layout.addWidget(self.heading)
        from rec_progress_ring import ProgressRing
        self.ring=ProgressRing();layout.addWidget(self.ring)
        self.stage = QLabel('Đang chuẩn bị…'); self.stage.setWordWrap(True); layout.addWidget(self.stage)
        self.counts = QLabel(); self.counts.setWordWrap(True); layout.addWidget(self.counts)
        self.elapsed = QLabel(); self.elapsed.setObjectName('muted'); layout.addWidget(self.elapsed)
        self.bar = QProgressBar(); self.bar.setRange(0, 0); layout.addWidget(self.bar)
        self.alert = QLabel(); self.alert.setWordWrap(True); self.alert.setObjectName('warning'); self.alert.hide(); layout.addWidget(self.alert)
        layout.addWidget(QLabel('Diễn biến xử lý', objectName='section'))
        self.activity = QPlainTextEdit(); self.activity.setReadOnly(True); self.activity.setMaximumBlockCount(1200); layout.addWidget(self.activity, 1)
        self.timer = QTimer(self); self.timer.setInterval(1000); self.timer.timeout.connect(self.tick)
        self.started = None; self.total = 0; self.saved = set(); self.skipped = set(); self.read = set(); self.invoices = 0
        self.errors = []; self.warning_count = 0; self.tail = ''

    def start(self, total):
        self.total = total; self.saved = set(); self.skipped = set(); self.read = set(); self.invoices = 0
        self.errors = []; self.warning_count = 0; self.tail = ''; self.finished_ok=False; self.started = time.monotonic();self.ring.set_progress(None)
        self.activity.clear(); self.alert.hide(); self.bar.setRange(0,0)
        self.heading.setText('Đang đọc ảnh'); self.stage.setText('Khởi động bộ đọc và tải danh mục…')
        self.timer.start(); self.update_counts(); self.tick()

    def tick(self):
        if self.started is None: return
        seconds = int(time.monotonic() - self.started)
        self.elapsed.setText(f'Thời gian đã chạy: {seconds//60:02d}:{seconds%60:02d} · Theo dõi bước xử lý bên trên')

    def completion_percent(self):
        if getattr(self, 'finished_ok', False) and not self.errors:
            return 100
        return min(99, 100 * len(self.saved | self.skipped) / max(1, self.total))

    def update_counts(self):
        done = len(self.saved | self.skipped)
        self.counts.setText(f'{self.total} ảnh đầu vào · {len(self.read)} ảnh đã đọc trong lượt này\n'
                            f'{self.invoices} phiếu vừa lưu · {len(self.saved)} ảnh thuộc phiếu vừa lưu · {len(self.skipped)} ảnh bỏ qua vì đã lưu/trùng')
        if self.total:
            self.bar.setRange(0, self.total); self.bar.setValue(min(done,self.total))
            self.ring.set_progress(self.completion_percent())
            self.bar.setFormat('%v / %m ảnh đã lưu hoặc bỏ qua' + (' · đang hoàn tất lượt' if done>=self.total and not getattr(self,'finished_ok',False) else ''))

    def consume(self, text, final=False):
        self.tail += text
        lines = self.tail.split('\n'); self.tail = lines.pop()
        if final and self.tail:
            lines.append(self.tail); self.tail = ''
        for line in lines:
            line = line.strip()
            if not line: continue
            self.activity.appendPlainText(line)
            message = re.sub(r'^\d{2}:\d{2}:\d{2}\s+', '', line)
            found = re.search(r'Tìm thấy (\d+) ảnh', message)
            if found: self.total = int(found.group(1))
            found = re.search(r'Đã đọc (.+?): \d+ dòng', message)
            if found: self.read.add(found.group(1).casefold())
            found = re.search(r'Bỏ qua (?:ảnh đã lưu|bản ảnh trùng nội dung): (.+?)(?: \(|\.$|$)', message)
            if found: self.skipped.add(found.group(1).casefold())
            found = re.search(r'ĐÃ LƯU (.+?): \d+ dòng', message)
            if found:
                self.invoices += 1
                self.saved.update(part.strip().casefold() for part in found.group(1).split(','))
            lower = message.casefold()
            if any(token in lower for token in ['chưa đọc xong', 'chưa xử lý được:', 'error:', 'traceback', 'không khởi động được']):
                self.errors.append(message); self.alert.setText('Có lỗi: ' + message); self.alert.show()
            elif any(token in lower for token in ['warning', 'cảnh báo', 'cần rà', 'thiếu', 'không có mã', 'chưa có mã']):
                self.warning_count += 1
                if not self.errors: self.alert.setText('Cần chú ý: ' + message); self.alert.show()
            self.stage.setText(message)
            self.update_counts()

    def finish(self, code):
        self.consume('', final=True); self.timer.stop(); self.tick();self.finished_ok=(code==0)
        self.ring.set_progress(self.completion_percent())
        self.bar.setRange(0, max(1, self.total)); self.bar.setValue(min(len(self.saved | self.skipped), self.total))
        if code == 0:
            self.heading.setText('Đã kết thúc lượt đọc · Rà bảng kết quả trước khi xuất')
        else:
            self.heading.setText('Lượt đọc chưa hoàn tất')
            if not self.errors: self.alert.setText('Bộ đọc đã dừng vì lỗi. Xem diễn biến bên dưới; các phiếu đã lưu được giữ.'); self.alert.show()
        if code==0:self.bar.setValue(max(1,self.total))
        self.stage.setText(f'{len(self.errors)} thông báo lỗi · {self.warning_count} thông báo cần chú ý. '
                           'Ảnh đã đọc chưa đồng nghĩa phiếu đã lưu; bước đối chiếu/ghép trang có thể còn chờ.')


class ReceivingWindow(PRLibraryUI, LedgerUI, QMainWindow):
    def __init__(self, root: Path | None = None, day: date | None = None, auto_load=True, *, destination=None):
        super().__init__()
        if QApplication.style().objectName().lower()!="fusion":QApplication.setStyle("Fusion")
        # Qt's offscreen platform does not always discover Windows fonts.
        # Explicit loading also keeps saved previews faithful to the desktop.
        for filename in (() if QApplication.instance().property("recFontsLoaded") else ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf")):
            font_path = Path(os.environ.get("WINDIR", "C:/Windows"))/"Fonts"/filename
            if font_path.exists(): QFontDatabase.addApplicationFont(str(font_path))
        QApplication.instance().setProperty("recFontsLoaded",True)
        self.root = Path(root or app_root())
        if str(self.root) not in sys.path:
            sys.path.append(str(self.root))
        settings = read_settings(self.root)
        self.destination = Path(destination or settings.get("destination") or ACCOUNTING_DEFAULT)
        self.portable_workspace = destination is not None
        self.portable_store = self.destination.resolve() if self.portable_workspace else None
        self.thread_pool = QThreadPool.globalInstance()
        self._workers: list[Worker] = []
        self.busy = False
        from rec_workdays import previous_workday
        self.day = previous_workday(day or date.today())
        self.report: Path | None = None
        self.folder: Path | None = None
        self.source_hash = None
        self.data: list[tuple[str, list]] = []
        self.data_by_sheet = {}
        self.sheet_names = []
        self.images: list[Path] = []
        self.image_to_sheets = {}
        self.reviews = {}
        self.signatures = {}
        self.current_sheet = ""
        self.current_image: Path | None = None
        self.reference_mode = False
        self.reference_image = None
        self.receipt_image = None
        self.loaded_day = None
        self.row_to_restore = None
        self.catalog = None
        self.numeric_flags = {}
        self.location_data = OrderedDict()
        self.location_pending = set()
        self.location_process = None
        self.location_failures = set()
        self.location_request = 0
        self.local_review_enabled = False
        self._warehouse_cache = None
        self.pending_status = ""
        self.process: QProcess | None = None
        self.setWindowTitle("REC Software · Kiểm tra phiếu và báo cáo ngày")
        self.resize(1500, 920)
        self.setMinimumSize(1120, 720)
        self._build_ui()
        self._apply_theme()
        from rec_fluent_ui import install_interface
        install_interface(self)
        from rec_selection_focus import SelectionFocus
        self.selection_focus=SelectionFocus(self)
        self.statusBar().messageChanged.connect(self._visible_status)
        from rec_progress_ring import ProgressRing
        self.operation_ring=ProgressRing(self);self.operation_ring.move(max(0,self.centralWidget().width()-80),12);self.operation_ring.hide();self.operation_ring.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.operation_banner=QFrame(self);self.operation_banner.setObjectName('operationBanner');bl=QHBoxLayout(self.operation_banner);bl.setContentsMargins(12,6,12,6);self.operation_banner_label=QLabel('');self.operation_banner_bar=QProgressBar();self.operation_banner_bar.setRange(0,0);self.operation_banner_bar.setFixedWidth(180);bl.addWidget(self.operation_banner_label);bl.addWidget(self.operation_banner_bar);self.operation_banner.setStyleSheet("QFrame#operationBanner{background:#fff;border:1px solid #dcd7f5;border-radius:8px;} QLabel{color:#5548c3;font-size:12px;} QProgressBar{height:6px;background:#eeecf8;border:0;border-radius:3px;} QProgressBar::chunk{background:#6054d8;border-radius:3px;}");self.operation_banner.hide()
        self._setup_inbox()
        self._restore_inbox_preference(auto_load)
        from receiving_preferences import restore_window
        restore_window(self)
        if auto_load: self.open_day()

    def _visible_status(self,message):
        if not message:return
        self.last_operation_status=message
        if hasattr(self,'operation_status'):self.operation_status.setText(message)
        if hasattr(self,'operation_banner_label') and self.busy:self.operation_banner_label.setText(message);self.operation_banner.adjustSize();self.operation_banner.raise_()
        if self.busy:return  # progress already has its own visible panel
        if message.startswith(('Đã','Chưa','Không','Ảnh chưa','Sổ đã')):
            self.show_top_notice('Trạng thái REC',message)

    def _setup_inbox(self):
        from receiving_inbox import Inbox
        self.inbox=Inbox(self.root/'.receiving'/'inbox-state.json')
        self.inbox_active=False
        config=self.root/'.receiving'/'inbox-settings.json'
        try:self.inbox_source=Path(json.loads(config.read_text(encoding='utf-8'))['source'])
        except (OSError,ValueError,KeyError):self.inbox_source=self.root.parent/'DN_Image'
        self.inbox_folder.setToolTip(str(self.inbox_source))
        self.inbox_timer=QTimer(self);self.inbox_timer.setInterval(5000);self.inbox_timer.timeout.connect(self._poll_inbox);self.inbox_timer.start()

    def _restore_inbox_preference(self,activate=True):
        # Each application launch starts in automatic mode; QA can opt out.
        # Keep the Fluent switch's internal animation signal active.
        self.inbox_toggle.toggled.disconnect(self.toggle_inbox)
        try:self.inbox_toggle.setChecked(bool(activate) and not self.inbox.blocked)
        finally:self.inbox_toggle.toggled.connect(self.toggle_inbox)
        self._sync_manual_controls()
        if self.inbox.warning:
            self.inbox_status.setText(self.inbox.warning)
            QTimer.singleShot(0,lambda:self.show_top_notice('Lịch sử nhận ảnh',self.inbox.warning,variant='warning'))
        elif activate:
            self.inbox_status.setText('Đang theo dõi ảnh mới')

    def _sync_manual_controls(self):
        allowed=not self.busy and not self.inbox_toggle.isChecked()
        for button in (self.add_button,self.read_button):
            button.setVisible(not self.inbox_toggle.isChecked())
            button.setEnabled(allowed)
            button.setToolTip('Tắt Tự nhận và đọc ảnh để thao tác thủ công' if self.inbox_toggle.isChecked() else '')

    def configure_inbox(self):
        selected=QFileDialog.getExistingDirectory(self,'Chọn thư mục tự nhận ảnh',str(self.inbox_source))
        if selected:
            self.inbox_source=Path(selected);self.inbox.observed.clear()
            atomic_json(self.root/'.receiving'/'inbox-settings.json',{'source':selected,'enabled':self.inbox_toggle.isChecked()})
            self.inbox_folder.setToolTip(selected)
            if hasattr(self,'settings_source'):self.settings_source.setText(selected)

    def show_top_notice(self,title,message,variant='info'):
        from fluent_blue import Alert
        if getattr(self,'top_notice',None) is not None:
            self.alert_layout.removeWidget(self.top_notice)
            self.top_notice.hide();self.top_notice.deleteLater()
        self.top_notice=Alert(title,message,parent=self.alert_host,variant=variant,closable=True,dense=True)
        self.top_notice.closed.connect(self.alert_host.hide)
        self.alert_layout.addWidget(self.top_notice,0,Qt.AlignRight)
        self._place_notice();self.alert_host.show();self.alert_host.raise_();self.top_notice.show()
        if not hasattr(self,'notice_timer'):
            self.notice_timer=QTimer(self);self.notice_timer.setSingleShot(True)
            self.notice_timer.timeout.connect(self.alert_host.hide)
        self.notice_timer.start(8000)

    def _place_notice(self):
        if getattr(self,'top_notice',None) is None:return
        parent=getattr(self,'notice_overlay_parent',None)
        if parent is None:return
        width=min(520,max(180,parent.width()-32))
        self.alert_host.setFixedWidth(width);self.top_notice.setFixedWidth(max(140,width-16))
        self.alert_host.layout().setContentsMargins(8,8,8,8)
        self.alert_host.adjustSize();height=self.alert_host.sizeHint().height()
        self.alert_host.resize(width,min(height,max(80,parent.height()-32)))
        self.alert_host.move(max(8,parent.width()-width-16),max(8,parent.height()-self.alert_host.height()-16));self.alert_host.raise_()

    def resizeEvent(self,event):
        super().resizeEvent(event);self._place_notice()
        if hasattr(self,'operation_ring'):self.operation_ring.move(max(0,self.centralWidget().width()-80),12);self.operation_ring.raise_()
        if hasattr(self,'operation_banner') and self.busy:self.operation_banner.move(max(12,(self.width()-self.operation_banner.width())//2),8);self.operation_banner.raise_()

    def toggle_inbox(self, enabled):
        self._sync_manual_controls()
        if hasattr(self,"inbox_source"):
            atomic_json(self.root/".receiving"/"inbox-settings.json",{"source":str(self.inbox_source),"enabled":bool(enabled)})
        if enabled:
            self.show_top_notice('Đã bật tự nhận ảnh',f'Ảnh mới và ảnh chưa xử lý được gửi Gemini (có thể tính phí), lưu vào ngày {self.day:%d/%m/%Y}. Bạn vẫn duyệt trước khi ghi sổ hoặc xuất. Thư mục: {self.inbox_source}')
        else:self.show_top_notice('Đã tắt tự nhận ảnh','Không nhận thêm ảnh tự động. Lượt đọc đang chạy sẽ tiếp tục để giữ kết quả.')
        self.inbox_status.setText('Đang theo dõi ảnh mới' if enabled else 'Tự động: đang tắt')

    def _pause_inbox(self,message):
        self.set_busy(False)
        self.inbox_toggle.setChecked(False);self.inbox_status.setText(message)
        self.show_top_notice('Tự đọc ảnh đã dừng',message+' · Kiểm tra rồi bật lại tại Nhận ảnh.',variant='warning')

    def _poll_inbox(self):
        if date.today().weekday()>4:return
        if self.inbox.blocked:return
        if not self.inbox_toggle.isChecked() or self.busy or self.inbox_active or QApplication.activeModalWidget():return
        self.inbox_active=True
        scan_day,scan_destination=self.day,self.destination
        job=Worker(self.inbox.scan,self.inbox_source)
        def scanned(batch):
            if not batch or self.busy or (self.day,self.destination)!=(scan_day,scan_destination):
                self.inbox_active=False;return
            from datetime import date
            if self.day<date.today():
                answer=QMessageBox.question(self,'Ảnh mới — đang chọn ngày cũ',
                    f'Có {len(batch)} ảnh mới. Bạn muốn thêm vào ngày cũ {self.day:%d/%m/%Y}?\nChọn Có: thêm vào ngày cũ. Chọn Không: chuyển sang hôm nay {date.today():%d/%m/%Y}.',
                    QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
                if answer!=QMessageBox.Yes:
                    from PySide6.QtCore import QDate
                    self.inbox_active=False
                    self.date_edit.setDate(QDate.currentDate())
                    return
            self.set_busy(True,'Đang nhận '+str(len(batch))+' ảnh vào ngày '+self.day.strftime('%d/%m/%Y')+'…')
            task=Worker(self.inbox.prepare,self.inbox_source,self.root,self.day,self.destination)
            task.kwargs['progress']=task.signals.progress.emit;task.signals.progress.connect(self.statusBar().showMessage)
            def prepared(result):
                self.set_busy(False)
                if (self.day,self.destination)!=(scan_day,scan_destination):return
                if result:
                    self.inbox_status.setText(f'Đang đọc {len(result)} ảnh mới…');self.read_images(automatic=True)
            def failed(error):self.set_busy(False);self._pause_inbox('Tự đọc đã dừng: '+str(error))
            task.signals.result.connect(prepared);task.signals.error.connect(failed)
            task.signals.finished.connect(lambda:setattr(self,'inbox_active',False));self._start_worker(task)
        def scan_failed(error):
            self.inbox_active=False;self._pause_inbox('Tự đọc đã dừng: '+str(error))
        job.signals.result.connect(scanned);job.signals.error.connect(scan_failed);self._start_worker(job)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(22, 18, 22, 0)
        outer.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Kiểm tra phiếu và báo cáo ngày")
        title.setObjectName("title")
        subtitle = QLabel("Rà phiếu, đối chiếu số thực nhận và chuẩn bị báo cáo trong ngày")
        subtitle.setObjectName("muted")
        title_row = QHBoxLayout()
        title_row.addWidget(title)
        title_box.addLayout(title_row)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()
        self.date_edit = CalendarDateEdit()
        self.date_edit.setDate(self.day)
        self.date_edit.dateChanged.connect(lambda: self.open_day())
        self.date_edit.setObjectName('titleDate')
        self.date_edit.setToolTip('Chọn ngày nhận hàng')
        self.date_edit.setFixedWidth(325)
        title_row.addWidget(self.date_edit); title_row.addStretch()
        self.root_button = Button("Thư mục kế toán",icon="folder")
        self.root_button.clicked.connect(self.choose_destination)
        header.addWidget(self.root_button)
        outer.addLayout(header)

        action_panel=QFrame();action_panel.setObjectName("actionPanel");action_panel.setFixedHeight(48)
        actions = QHBoxLayout(action_panel);actions.setContentsMargins(10,8,10,8);actions.setSpacing(8)
        self.add_button = Button("Chọn ảnh chứng từ",icon="plus")
        self.add_button.clicked.connect(self.add_images)
        self.read_button = Button("Đọc ảnh và lập bảng",variant="primary",icon="play")
        self.read_button.setObjectName("primary")
        self.read_button.clicked.connect(self.read_images)
        self.reload_button = Button("Cập nhật từ Excel",icon="refresh")
        self.reload_button.setToolTip('Đọc lại dữ liệu Excel đã lưu vào bảng đang xem')
        self.reload_button.clicked.connect(self.open_day)
        actions.addWidget(self.add_button); actions.addWidget(self.read_button); actions.addWidget(self.reload_button)
        self.merge_button = Button("Gộp các trang phiếu",icon="layers")
        self.merge_button.setToolTip('Ghép nhiều ảnh thuộc cùng một phiếu giao hàng')
        self.merge_button.clicked.connect(self.merge_images)
        actions.addWidget(self.merge_button)
        self.shortage_button = Button('Hàng thiếu / giao bù')
        self.shortage_button.clicked.connect(self.show_shortage_ledger)
        actions.addWidget(self.shortage_button)
        actions.addStretch()
        self.inbox_toggle=InboxSwitch();self.inbox_toggle.toggled.connect(self.toggle_inbox)
        self.inbox_folder=Button('Thư mục nhận ảnh',icon='folder');self.inbox_folder.clicked.connect(self.configure_inbox)
        self.inbox_status=QLabel('Tự động: đang tắt');self.inbox_status.setObjectName('muted');self.inbox_status.setWordWrap(True)
        self.inbox_status.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
        inbox_row=QHBoxLayout();inbox_row.setSpacing(8)
        inbox_row.addWidget(self.inbox_toggle);inbox_row.addWidget(self.inbox_folder);inbox_row.addWidget(self.inbox_status);inbox_row.addStretch()
        for button in [self.add_button,self.read_button,self.reload_button,self.merge_button,self.shortage_button,self.inbox_folder]:
            button.setStyleSheet('')
        self.summary=QLabel('Đang tải…');self.summary.setObjectName('muted');title_box.addWidget(self.summary)
        self.receipt_toolbar=QHBoxLayout()
        outer.addLayout(self.receipt_toolbar)
        outer.addWidget(action_panel)
        inbox_host=QWidget();inbox_host.setObjectName("inboxHost");inbox_host.setLayout(inbox_row);inbox_host.setFixedHeight(38);inbox_row.setContentsMargins(0,0,0,0)
        outer.addWidget(inbox_host)

        body = QSplitter(Qt.Horizontal); self.body_split = body
        body.setChildrenCollapsible(False)
        sidebar = QFrame(); sidebar.setObjectName("panel")
        side_layout = QVBoxLayout(sidebar); side_layout.setContentsMargins(12, 12, 12, 12)
        side_layout.addWidget(QLabel("PHIẾU TRONG NGÀY", objectName="section"))
        self.filter_box = QComboBox()
        self.filter_box.addItems(["Tất cả phiếu", "Chưa kiểm tra", "Đã kiểm tra", "Thiếu mã", "Thiếu giá"])
        self.filter_box.currentIndexChanged.connect(self.filter_receipts)
        side_layout.addWidget(self.filter_box)
        self.receipt_list = QListWidget()
        self.receipt_list.setObjectName("receiptList")
        self.receipt_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.receipt_list.setWordWrap(True)
        self.receipt_list.currentRowChanged.connect(self.select_receipt)
        side_layout.addWidget(self.receipt_list, 4)
        self.unread_heading = Button("Ảnh chưa có trong báo cáo")
        self.unread_heading.setCheckable(True)
        self.unread_heading.toggled.connect(lambda shown: self.image_list.setVisible(shown))
        side_layout.addWidget(self.unread_heading)
        self.image_list = QListWidget(); self.image_list.currentRowChanged.connect(self.select_image)
        side_layout.addWidget(self.image_list, 2)
        self.receipt_panel = sidebar
        sidebar.setParent(self)
        sidebar.hide()

        workspace = QWidget(); work_layout = QVBoxLayout(workspace); work_layout.setContentsMargins(0, 0, 0, 0)
        nav = QHBoxLayout()
        self.previous = Button("← Phiếu trước"); self.previous.clicked.connect(lambda: self.move_receipt(-1))
        self.next = Button("Phiếu sau →"); self.next.clicked.connect(lambda: self.move_receipt(1))
        self.sheet_combo = QComboBox(); self.sheet_combo.currentTextChanged.connect(self.select_sheet)
        self.position = QLabel("—"); self.position.setObjectName("muted")
        nav.addWidget(self.previous); nav.addWidget(self.next); nav.addWidget(self.sheet_combo, 1); nav.addWidget(self.position)
        for widget in [self.previous, self.next, self.sheet_combo, self.position]: widget.hide()

        split = QSplitter(Qt.Horizontal); self.work_split = split; split.setChildrenCollapsible(False)
        image_panel = QFrame(); image_panel.setObjectName("panel")
        image_layout = QVBoxLayout(image_panel); image_layout.setContentsMargins(10, 10, 10, 10)
        image_head = QHBoxLayout(); self.image_title = QLabel("Chưa có ảnh"); self.image_title.setObjectName("section")
        fit = Button("Xem toàn ảnh"); fit.clicked.connect(lambda: self.preview.fit_image())
        self.reference_toggle = Button('PR')
        self.reference_toggle.clicked.connect(self.toggle_reference_images)
        image_head.addWidget(self.image_title, 1); image_head.addWidget(self.reference_toggle); image_head.addWidget(fit)
        image_layout.addLayout(image_head)
        self.image_header=image_head
        self.page_combo = QComboBox()
        self.page_combo.currentIndexChanged.connect(self.select_page)
        self.page_combo.hide()
        from rec_image_navigation import PageArrows

        self.image_title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.preview = PreviewView(); self.preview.imageChanged.connect(self.image_title.setText)
        image_layout.addWidget(self.preview, 1)
        self.page_arrows=PageArrows(self.preview,self.page_combo)
        self.region_title = QLabel('Chọn một dòng để xem vùng ảnh đối chiếu.'); self.region_title.setWordWrap(True); self.region_title.setObjectName('muted')
        self.region_title.hide()
        region_bar=QHBoxLayout(); region_bar.addStretch()
        self.region_expand=Button('Xem vùng ảnh lớn'); self.region_expand.setEnabled(False)
        self.region_expand.clicked.connect(lambda: self.open_region_dialog(self.region_qimage) if getattr(self,'region_qimage',None) is not None else None)
        self.region_expand.setText('Vùng ảnh lớn')
        self.region_view = RowStripView(self); self.region_scene = QGraphicsScene(self.region_view)
        self.region_view.setScene(self.region_scene); self.region_view.setFixedHeight(96)
        self.region_view.setRenderHint(QPainter.SmoothPixmapTransform)
        self.region_view.setDragMode(QGraphicsView.ScrollHandDrag)
        # Small region strip replaced by a reusable non-modal large viewer.
        enhancements = QHBoxLayout()
        self.light_check = QCheckBox("Làm sáng ảnh tối"); self.light_check.setChecked(True)
        self.crop_check = QCheckBox("Cắt viền thừa"); self.crop_check.setChecked(True)
        self.original_check = QCheckBox("Ảnh gốc")
        for check in [self.light_check, self.crop_check, self.original_check]:
            enhancements.addWidget(check); check.toggled.connect(self.preview_options)
        for check in [self.light_check, self.crop_check, self.original_check]: check.hide()
        self.preview_note = QLabel(""); self.preview_note.setWordWrap(True)
        self.preview_note.setObjectName("muted"); self.preview_note.hide()
        self.preview.previewReady.connect(self.preview_note.setText)
        zoom_bar = QHBoxLayout()
        self.magnifier_button = Button('Kính lúp',icon='search');self.magnifier_button.setCheckable(True)
        self.magnifier_button.setToolTip('Bật rồi rê chuột trên ảnh để phóng to chữ; kéo chuột vẫn di chuyển ảnh.')
        self.magnifier_button.toggled.connect(self.preview.set_magnifier)
        self.magnifier_button.hide()
        for label, factor in [("−", 1/1.2), ("+", 1.2)]:
            button = Button(label); button.setFixedWidth(35)
            button.clicked.connect(lambda _, f=factor: self.preview.zoom_at(f)); button.hide()
        self.region_expand.hide()
        more = QToolButton(); more.setText('Chỉnh ảnh'); more.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(more)
        for check in [self.light_check, self.crop_check, self.original_check]:
            action = menu.addAction(check.text()); action.setCheckable(True); action.setChecked(check.isChecked())
            action.toggled.connect(check.setChecked); check.toggled.connect(action.setChecked)
        more.setMenu(menu); more.hide()
        self.preview.setToolTip('Lăn chuột để phóng to; kéo ảnh để di chuyển.')
        self.bright_switch=Switch('Tăng sáng',checked=self.light_check.isChecked())
        self.contrast_check=Switch('Tăng tương phản')
        self.bright_switch.toggled.connect(self.light_check.setChecked)
        self.light_check.toggled.connect(self.bright_switch.setChecked)
        self.contrast_check.toggled.connect(self.preview_options)
        self.crop_switch=Switch('Cắt viền thừa',checked=self.crop_check.isChecked())
        self.original_switch=Switch('Ảnh gốc',checked=self.original_check.isChecked())
        self.crop_switch.toggled.connect(self.crop_check.setChecked);self.crop_check.toggled.connect(self.crop_switch.setChecked)
        self.original_switch.toggled.connect(self.original_check.setChecked);self.original_check.toggled.connect(self.original_switch.setChecked)
        adjustments=QHBoxLayout();adjustments.addWidget(self.bright_switch);adjustments.addWidget(self.contrast_check);adjustments.addWidget(self.crop_switch);adjustments.addWidget(self.original_switch);adjustments.addStretch()
        image_layout.addLayout(adjustments)
        # No extra zoom/magnifier/menu row.
        split.addWidget(image_panel)

        data_panel = QFrame(); data_panel.setObjectName("panel")
        data_layout = QVBoxLayout(data_panel); data_layout.setContentsMargins(12, 12, 12, 12)
        meta = QHBoxLayout(); self.invoice_meta = QLabel("Chưa chọn phiếu"); self.invoice_meta.setObjectName("section")
        self.review_label = QLabel("Chưa kiểm tra"); self.review_label.setObjectName("warning")
        meta.addWidget(self.invoice_meta, 1); data_layout.addLayout(meta)
        self.image_header.insertWidget(1,self.review_label)
        self.review_label.setToolTip('Trạng thái kiểm tra phiếu')
        self.invoice_meta.setWordWrap(True)
        self.details = QLabel(); self.details.setWordWrap(True); self.details.setObjectName("invoiceDetails")
        self.details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.details.hide()
        controls = QGridLayout(); controls.setHorizontalSpacing(8); controls.setVerticalSpacing(8)
        self.show_all = QCheckBox("Hiện đủ cột"); self.show_all.setChecked(True); self.show_all.stateChanged.connect(self.refresh_table)
        self.show_all.hide()
        edit = Button("Sửa dòng"); edit.clicked.connect(self.edit_current)
        lookup = Button("Tra mã hàng"); lookup.clicked.connect(self.lookup_code)
        controls.addWidget(lookup, 0, 0); controls.addWidget(edit, 0, 1)
        self.progress_toggle = Button('Xem tiến độ đọc')
        self.progress_toggle.setCheckable(True); self.progress_toggle.hide()
        self.progress_toggle.toggled.connect(self.toggle_read_progress)
        controls.addWidget(self.progress_toggle, 1, 2)
        self.compare_pr_button = Button('Đối chiếu PR')
        self.compare_pr_button.clicked.connect(self.compare_current_pr)
        controls.addWidget(self.compare_pr_button, 0, 4)
        self.bulk_department = Button('Bộ phận cho cả phiếu')
        self.bulk_department.clicked.connect(self.assign_invoice_department)
        self.delete_button = Button('Xóa dòng')
        self.delete_button.clicked.connect(self.delete_current_row)
        controls.addWidget(self.bulk_department, 0, 2); controls.addWidget(self.delete_button, 0, 3)
        for button in [lookup, edit, self.bulk_department, self.delete_button, self.compare_pr_button, self.progress_toggle]:
            button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            button.setObjectName('compact')
        controls.setColumnStretch(5, 1)
        self.filter_box.setView(QListView())
        self.table_edit_button=edit;self.table_lookup_button=lookup
        for button in [lookup,edit,self.bulk_department,self.delete_button,self.progress_toggle]:button.hide()
        controls.removeWidget(self.compare_pr_button);meta.addWidget(self.compare_pr_button)
        self.supplier_invoice_button=Button('Đổi NCC cả phiếu');self.supplier_invoice_button.setObjectName('invoiceSupplier');self.supplier_invoice_button.clicked.connect(self.assign_invoice_supplier);self.supplier_invoice_button.hide()
        self.bulk_pr_button=Button('Hoàn tất đợt kiểm');self.bulk_pr_button.setObjectName('bulkPRRefresh');self.bulk_pr_button.clicked.connect(self.refresh_all_pr);meta.addWidget(self.bulk_pr_button)
        self.table_controls=controls
        checks=QHBoxLayout()
        self.only_numbers=QCheckBox('Chỉ dòng cần rà'); self.only_numbers.toggled.connect(self.apply_number_filter)
        self.next_number=Button('',icon='chevron-right',tooltip='Chuyển đến dòng cần kiểm tra tiếp theo'); self.next_number.clicked.connect(self.next_numeric_row)
        self.number_summary=QLabel(); self.number_summary.setObjectName('reviewCount')
        meta.addWidget(self.only_numbers);meta.addWidget(self.number_summary);meta.addWidget(self.next_number)
        self.next_number.setFixedWidth(32)
        # Compact numeric controls share the table heading.
        self.next_step = QLabel(); self.next_step.setObjectName('muted'); self.next_step.setWordWrap(True)
        self.next_step.hide()
        self.table = QTableView(); self.table.setModel(ReceiptTableModel(self)); self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setItemDelegate(DepartmentDelegate(self))
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.horizontalScrollBar().setSingleStep(24)
        self.table.horizontalScrollBar().setTracking(True)
        self.table.verticalScrollBar().setSingleStep(24)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().hide(); self.table.verticalHeader().setDefaultSectionSize(58)
        self.table.setShowGrid(False)
        self.table.model().editRequested.connect(self.save_row_changes)
        self.table.selectionModel().currentRowChanged.connect(self.row_selected)
        self.table.clicked.connect(self.open_department)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_row_menu)
        self.table.setAlternatingRowColors(True); self.table.horizontalHeader().setStretchLastSection(False)
        self.read_stack = QStackedWidget()
        self.read_stack.addWidget(self.table)
        self.read_progress = ReadingProgress()
        self.read_stack.addWidget(self.read_progress)
        self.region_view.setFixedHeight(96)
        self.region_view.setObjectName('inlineRowImage')
        self.region_view.setToolTip('Ảnh phóng to của dòng đang chọn · Cuộn để zoom, kéo để di chuyển')
        data_layout.addWidget(self.region_view)
        self.region_view.show();self.region_view.setFixedHeight(96)
        data_layout.setSpacing(6)
        self.review_tabs=QTabWidget();self.review_tabs.addTab(self.read_stack,'Phiếu giao')
        self.pr_host=QWidget();self.pr_host_layout=QVBoxLayout(self.pr_host);self.pr_host_layout.setContentsMargins(0,0,0,0)
        self.pr_placeholder=QLabel('Bấm Đối chiếu PR để tải kết quả cho phiếu đang xem.');self.pr_host_layout.addWidget(self.pr_placeholder)
        self.review_tabs.addTab(self.pr_host,'Đối chiếu PR');data_layout.addWidget(self.review_tabs,1)
        self.review_tabs.currentChanged.connect(self._review_tab_changed)
        self.row_detail = QLabel("Chọn dòng để xem nội dung cần kiểm.")
        self.row_detail.setWordWrap(True); self.row_detail.setObjectName("rowReview")
        self.row_detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        data_layout.addWidget(self.row_detail)
        totals = QHBoxLayout()
        self.paper_total_label = QLabel(''); self.paper_total_label.setObjectName('total')
        self.paper_total_label.setWordWrap(True)
        self.total_label = QLabel(""); self.total_label.setObjectName("total"); self.total_label.setWordWrap(True)
        self.total_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        totals.addWidget(self.paper_total_label, 1); totals.addWidget(self.total_label, 1)
        data_layout.addLayout(totals)
        split.addWidget(data_panel); split.setSizes([560, 760])
        work_layout.addWidget(split, 1)
        body.addWidget(workspace); body.setSizes([1230])
        outer.addWidget(body, 1)

        footer = QHBoxLayout()
        self.output_info = QLabel(""); self.output_info.setObjectName("muted"); self.output_info.setWordWrap(True)
        self.output_info.hide()
        folder_button = Button("Mở thư mục ngày",icon="folder"); folder_button.clicked.connect(self.open_folder)
        folder_button.setToolTip("Mở thư mục chứa báo cáo của ngày đang xem")
        self.approve_button = Button("Xác nhận",icon="check"); self.approve_button.clicked.connect(self.approve)
        self.publish_button = Button("Xuất phiếu giao hàng.xlsx",variant="primary",icon="download"); self.publish_button.setObjectName("primary"); self.publish_button.clicked.connect(self.publish)
        self.image_header.addWidget(self.approve_button)
        self.approve_button.setToolTip("Xác nhận hoặc bỏ xác nhận kiểm tra phiếu đang xem")
        folder_button.hide(); self.publish_button.hide();footer.addStretch()
        # No footer: export lives in the header; log lives in settings.
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Sẵn sàng")
        QTimer.singleShot(0, self._initial_split_sizes)
        for shortcut, callback in [("Alt+Left", lambda: self.move_receipt(-1)), ("Alt+Right", lambda: self.move_receipt(1)), ("F5", self.open_day), ("F2", self.edit_current)]:
            action = QAction(self); action.setShortcut(shortcut); action.triggered.connect(callback); self.addAction(action)
        self.log_dialog = QDialog(self); self.log_dialog.setWindowTitle("Nhật ký đọc phiếu"); self.log_dialog.resize(850, 420)
        log_layout = QVBoxLayout(self.log_dialog)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setPlaceholderText('Chưa có nhật ký trong phiên này. Khi đọc ảnh, tiến trình và lỗi xử lý sẽ hiển thị ở đây.'); self.log.setMaximumBlockCount(1500); log_layout.addWidget(self.log)
        log_action = QAction("Nhật ký", self); log_action.triggered.connect(self.log_dialog.show)
        self.log_button=Button('Nhật ký',icon='form',tooltip='Xem tiến trình và lỗi đọc ảnh trong phiên hiện tại')
        self.log_button.clicked.connect(self.log_dialog.show)
        self.log_button.hide()
        self.statusBar().hide()
        self.statusBar().setSizeGripEnabled(False)

    def _log_button(self, action):
        button = QToolButton(); button.setDefaultAction(action); return button

    def _initial_split_sizes(self):
        self.body_split.setSizes([1250])
        self.work_split.setSizes([430, 780])

    def _apply_theme(self):
        self.setStyleSheet("""
        QPushButton#titleDate { background: #edf3ff; border: 1px solid #b4cae9; font-size: 18pt; font-weight: 700; color: #102a56; padding: 6px 12px; border-radius: 8px; }
        QPushButton#titleDate:hover { background: #dce9ff; border-color: #2563d9; }
        QPushButton#compact { padding: 5px 10px; min-height: 20px; }
        QComboBox QAbstractItemView { background: white; color: #243447; border: 1px solid #cbd7e6; padding: 5px; outline: 0; selection-background-color: #eaf1ff; selection-color: #174ea6; }
        QComboBox QAbstractItemView::item { min-height: 32px; padding: 4px 10px; border: 0; }
        QComboBox QAbstractItemView::item:hover { background: #f0f5ff; }
        QTableWidget#prCompare { background: white; border: 1px solid #e5e7eb; border-radius: 6px; gridline-color: #edf1f6; }
        QTableWidget#prCompare::item { padding: 8px; border-bottom: 1px solid #edf1f6; }
        QToolButton { background: white; border: 1px solid #cbd7e6; border-radius: 6px; padding: 8px; }
        QToolButton:hover { background: #edf3ff; border-color: #7095cf; }
        QMenu { background: white; color: #172b4d; border: 1px solid #cbd7e6; padding: 6px; }
        QMenu::item { padding: 10px 22px 10px 30px; min-width: 160px; }
        QMenu::item:selected { background: #eaf1ff; color: #174ea6; border-radius: 4px; }
        QMenu::indicator { width: 18px; height: 18px; }
        QMenu::indicator:checked { background: #2563d9; border: 3px solid #dbeafe; border-radius: 4px; }
        QMenu::indicator:unchecked { border: 1px solid #b5c3d6; border-radius: 4px; background: white; }
        QWidget { font-family: 'Segoe UI Variable', 'Segoe UI'; font-size: 10pt; color: #172b4d; }
        QMainWindow, QWidget { background: #f3f4f6; }
        QLabel, QCheckBox { background: transparent; }
        QLabel#title { font-size: 22pt; font-weight: 700; color: #102a56; }
        QLabel#muted { color: #65758b; }
        QLabel#invoiceDetails { font-size: 12pt; color: #334155; padding: 5px 0; }
        QLabel#rowReview { font-size: 11pt; font-weight: 600; color: #854d0e; background: #fff7e6; border: 1px solid #f0d19b; border-radius: 6px; padding: 10px; }
        QLabel#reviewCount { font-size: 11pt; font-weight: 600; color: #334155; }
        QLabel#section { font-weight: 700; color: #1b3761; }
        QFrame#step, QFrame#panel { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 14px; }
        QLabel#stepHeading { color: #2156bd; font-weight: 700; letter-spacing: 1px; }
        QPushButton { background: #ffffff; border: 1px solid #e2e5ea; border-radius: 9px; padding: 8px 13px; }
        QPushButton:hover { border-color: #4a7eea; background: #f0f5ff; }
        QPushButton#primary { background: #2563d9; color: white; border: 1px solid #2563d9; font-weight: 700; }
        QPushButton#primary:hover { background: #1d4ed8; }
        QListWidget, QTableView { background: #ffffff; border: 0; alternate-background-color: #fafbfc; }
        QListWidget::item { padding: 10px 8px; border-bottom: 1px solid #edf1f6; }
        QListWidget::item:selected { background: #e6efff; color: #1546a0; border-left: 3px solid #2563d9; }
        QListWidget::item:focus { outline: none; border: 0; }
        QListWidget { outline: none; }
        QListWidget#receiptList::item { padding: 4px 0; border: 0; background: transparent; }
        QListWidget#receiptList::item:selected { border: 0; background: transparent; }
        QFrame#receiptCard { background: white; border: 1px solid #e4eaf3; border-radius: 8px; }
        QFrame#receiptCard[selected="true"] { background: #eef2ff; border: 1px solid #c7d2fe; }
        QLabel#supplierName { font-weight: 700; color: #16345e; }
        QLabel#receiptSource { color: #718198; font-size: 9pt; }
        QLabel#pendingChip { background: #fff3d9; color: #9a6008; border-radius: 4px; padding: 3px 7px; font-size: 9pt; }
        QLabel#checkedChip { background: #e8f5ee; color: #16734a; border-radius: 4px; padding: 3px 7px; font-size: 9pt; }
        QHeaderView::section { background: #f3f4f6; color: #475569; padding: 8px; border: 0; font-weight: 700; }
        QTableView::item { padding: 6px; }
        QLabel#warning { color: #ae6500; background: #fff4d9; padding: 5px 9px; border-radius: 5px; }
        QLabel#ok { color: #164eae; background: #eaf1ff; padding: 5px 9px; border-radius: 5px; }
        QLabel#total { font-size: 16pt; font-weight: 700; color: #102a56; padding-top: 8px; }
        QDateEdit, QComboBox { background: white; border: 1px solid #cbd7e6; border-radius: 6px; padding: 7px 9px; }
        QCheckBox { color: #52657d; }
        QLineEdit, QPlainTextEdit { background: white; color: #243447; border: 1px solid #d5deea; border-radius: 5px; padding: 5px 7px; selection-background-color: #dbe7fa; selection-color: #172b4d; }
        QLineEdit:focus { border: 1px solid #7da4e6; }
        QTableView { selection-background-color: #eaf1fc; selection-color: #172b4d; }
        QTableView::item:selected { background: #eaf1fc; color: #172b4d; }
        QTableView QLineEdit { padding: 2px 4px; border-radius: 3px; background: white; color: #172b4d; }
        QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
        QScrollBar::handle:vertical { background: #c3cedd; min-height: 32px; border-radius: 4px; }
        QScrollBar:horizontal { background: #e5ecf5; height: 20px; margin: 0; border-radius: 5px; }
        QScrollBar::handle:horizontal { background: #8198b7; min-width: 64px; border-radius: 5px; }
        QScrollBar::handle:horizontal:hover { background: #426b9e; }
        QScrollBar::handle:horizontal:pressed { background: #2563d9; }
        QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
        QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
        QComboBox::drop-down, QDateEdit::drop-down { border: 0; width: 24px; }
        QComboBox::down-arrow, QDateEdit::down-arrow { image: url(CHEVRON_URL); width: 12px; height: 12px; }
        QCalendarWidget { background: white; min-width: 330px; }
        QCalendarWidget QToolButton { background: #f0f4fa; color: #203a60; padding: 6px; }
        QCalendarWidget QAbstractItemView { background: white; color: #243447; selection-background-color: #dbe7fa; selection-color: #172b4d; font-size: 10pt; }
        QDialog { background: #f8fafc; }
        QToolTip { background: white; color: #334155; border: 1px solid #dbe3ed; padding: 6px; }
        QFrame#actionPanel { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px; }
        QFrame#topNotice { background: #17233c; border: 1px solid #334766; border-radius: 14px; }
        QFrame#topNotice QLabel { color: #f8fafc; background: transparent; font-size: 10pt; }
        QFrame#topNotice QLabel#noticeTitle { font-size: 12pt; font-weight: 700; }
        QFrame#topNotice QPushButton { background: #293954; color: white; border: 0; padding: 0; border-radius: 8px; }
        QTableView { outline: none; }
        """.replace("CHEVRON_URL", Path(__file__).with_name("receiving-chevron.svg").as_posix()))

    def set_busy(self, value: bool, message: str = ""):
        self.busy = value
        if not value:
            from rec_workflow_status import schedule
            schedule(self)
        self._busy_generation=getattr(self,'_busy_generation',0)+1
        generation=self._busy_generation
        def show_progress():
            if not self.busy or generation!=self._busy_generation:return
            if getattr(self,'_reading_progress_active',False):return
            if hasattr(self,'operation_banner'):
                self.operation_banner.adjustSize()
                self.operation_banner.move(max(12,(self.width()-self.operation_banner.width())//2),8)
                self.operation_banner.show();self.operation_banner.raise_()
            if hasattr(self,'operation_ring'):
                self.operation_ring.set_progress(None);self.operation_ring.show()
        if hasattr(self,'operation_banner'):
            self.operation_banner_label.setText(message or 'Đang xử lý…')
        if value:
            QTimer.singleShot(180,show_progress)
        else:
            if hasattr(self,'operation_banner'):self.operation_banner.hide()
            if hasattr(self,'operation_ring'):self.operation_ring.hide();self.operation_ring.timer.stop()
        if hasattr(self,'pr_panel'):self.pr_panel.setEnabled(not value)
        for widget in [self.add_button, self.read_button, self.reload_button, self.approve_button, self.publish_button, self.date_edit, self.root_button, self.inbox_folder, self.table, self.merge_button, self.bulk_department, self.delete_button]:
            widget.setEnabled(not value)
        self._sync_manual_controls()
        reading=value and getattr(self,'_reading_progress_active',False)
        if reading:
            for widget in [self.table,self.receipt_list,self.receipt_picker,self.receipt_search,self.previous,self.next]:widget.setEnabled(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers if reading else QAbstractItemView.DoubleClicked|QAbstractItemView.EditKeyPressed)
        if message:
            self.statusBar().showMessage(message)
            if hasattr(self,'operation_banner_label') and self.busy:self.operation_banner_label.setText(message);self.operation_banner.raise_()

    def _start_worker(self, worker: Worker):
        # QRunnable is deleted by QThreadPool after run(). Keep the Python
        # wrapper alive until its finished signal has been delivered.
        self._workers.append(worker)
        worker.signals.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        self.thread_pool.start(worker)

    def open_day(self):
        if self.busy:
            return
        if not self._leave_pr():
            self.date_edit.blockSignals(True);self.date_edit.setDate(self.day);self.date_edit.blockSignals(False);return
        self.day = day_from_widget(self.date_edit)
        self.set_busy(True, "Đang tải báo cáo và danh sách ảnh…")
        worker = Worker(self._load_day, self.day, self.destination, self.root)
        worker.signals.result.connect(self._day_loaded)
        worker.signals.error.connect(lambda message: self._load_failed(message))
        worker.signals.finished.connect(lambda: self.set_busy(False))
        self._start_worker(worker)

    @staticmethod
    def _load_day(day_value: date, destination: Path, root=None):
        folder, report = paths(root or app_root(), day_value, destination)
        source_hash, data = snapshot(report)
        images = day_images(report.parent)
        signatures = {name: sheet_signature(name, rows) for name, rows in data}
        review_path = folder / "reviewed.json"
        try:
            reviews = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {}
        except (OSError, ValueError):
            reviews = {}
        return folder, report, source_hash, data, images, signatures, reviews

    def _load_failed(self, message: str):
        from rec_feedback_states import show
        self.statusBar().showMessage('Chưa tải được: '+message)
        show(self,'load-error',message,self.open_day)

    def _day_loaded(self, payload):
        if self.portable_store is not None and not Path(payload[1]).resolve().is_relative_to(self.portable_store):
            raise ValueError('Phiếu nguồn nằm ngoài dữ liệu React REC.')
        if getattr(self,'_open_review_after_load',False):
            self._open_review_after_load=False
            QTimer.singleShot(0,lambda:self.fluent_nav.set_current('Kiểm tra phiếu'))
        self.reference_mode = False
        self.reference_image = None
        self.receipt_image = None
        self.reference_toggle.setText('PR')
        previous_sheet = self.current_sheet if self.loaded_day == self.day else ""
        self.folder, self.report, self.source_hash, self.data, self.images, self.signatures, self.reviews = payload
        self.loaded_day = self.day
        self.data_by_sheet = dict(self.data)
        self.sheet_names = [name for name, _ in self.data]
        self.image_to_sheets = {}
        for name, rows in self.data:
            for ref in invoice_images(name, rows):
                self.image_to_sheets.setdefault(ref, []).append(name)
        self.sheet_combo.blockSignals(True); self.sheet_combo.clear(); self.sheet_combo.addItems(self.sheet_names); self.sheet_combo.blockSignals(False)
        self.image_list.blockSignals(True); self.image_list.clear()
        for image in self.images:
            linked = bool(self.image_to_sheets.get(image_name(image)))
            item = QListWidgetItem(("Ảnh phiếu · " if linked else "PR · ") + image.name); item.setData(Qt.UserRole, str(image)); self.image_list.addItem(item)
            item.setHidden(linked)
        self.image_list.blockSignals(False)
        unread = sum(not bool(self.image_to_sheets.get(image_name(p))) for p in self.images)
        self.unread_heading.setText(f"Ảnh PR kèm theo · {unread}")
        self.reference_toggle.setEnabled(unread > 0)
        self.reference_toggle.setToolTip('Bấm để xem ảnh PR đã ghép hoặc chọn ảnh PR cho phiếu này.')
        self.unread_heading.setVisible(unread > 0)
        self.image_list.setVisible(unread > 0 and self.unread_heading.isChecked())
        self.summary.setText(f"{len(self.images)} ảnh  ·  {len(self.data)} phiếu  ·  {sum(self.approved(n) for n, _ in self.data)} đã kiểm")
        self.output_info.setText(f"Nguồn: {self.report.name}\nXuất: Phieu giao hang {self.day.day}-{self.day.month}-{self.day.year}.xlsx\n{self.report.parent}")
        self.current_sheet = previous_sheet
        self.filter_receipts()
        if not self.receipt_list.count():
            self.select_sheet("")
            if self.images and not self.data:
                self.image_list.setCurrentRow(0)
        self.statusBar().showMessage(self.pending_status or '')
        if not self.data and not self.images and hasattr(self,'main_pages'):
            from rec_feedback_states import show
            show(self,'empty',retry=lambda:self.fluent_nav.set_current('Tiếp nhận ảnh'))
        # Loading a populated day from the empty/error screen must reveal it.
        # Do not steal focus if the user has navigated elsewhere during loading.
        elif hasattr(self,'main_pages') and self.main_pages.currentWidget() is getattr(self,'feedback_state_page',None):
            self.main_pages.setCurrentWidget(self.receipt_page)
        self.pending_status = ""
        catalog_file = self.root/'DanhMuc.xlsm'
        if self.catalog is None and catalog_file.exists() and not getattr(self,'_catalog_loading',False):
            self._catalog_loading=True
            def load_catalog():
                import AutoWatcher as aw
                return aw.load_catalog_data(catalog_file)[0]
            def catalog_ready(catalog):
                self.catalog=catalog
                self.update_numeric_flags()
            task=Worker(load_catalog); task.signals.result.connect(catalog_ready)
            task.signals.finished.connect(lambda: setattr(self,'_catalog_loading',False))
            self._start_worker(task)

    def filter_receipts(self):
        if not hasattr(self, "receipt_list"):
            return
        wanted = self.filter_box.currentText() if hasattr(self, "filter_box") else "Tất cả phiếu"
        current = self.current_sheet
        self.receipt_list.blockSignals(True); self.receipt_list.clear()
        from rec_receipt_order import ordered
        for name, rows in ordered(self.folder,self.data):
            values = [v for _, v in rows]
            missing_code = any(not v.get("Mã vật tư") or v.get("Mã vật tư") == "CHUA CO MA" for v in values)
            missing_price = any(v.get("Đơn giá") is None for v in values)
            from rec_receipt_check_status import status as check_status
            state,fully_checked=check_status(self,name)
            if wanted == "Chưa kiểm tra" and fully_checked: continue
            if wanted == "Đã kiểm tra" and not fully_checked: continue
            if wanted == "Thiếu mã" and not missing_code: continue
            if wanted == "Thiếu giá" and not missing_price: continue
            supplier = str(values[0].get("Nhà cung cấp") or "NCC chưa rõ") if values else "NCC chưa rõ"

            item = QListWidgetItem()
            item.setToolTip(f"{supplier}\n{name} · {state}")
            item.setData(Qt.UserRole, name); self.receipt_list.addItem(item)
            card = QFrame(); card.setObjectName("receiptCard")
            card.setAttribute(Qt.WA_TransparentForMouseEvents)
            layout = QVBoxLayout(card); layout.setContentsMargins(10,10,10,10); layout.setSpacing(6)
            from rec_fluent_ui import short_supplier
            title = QLabel(short_supplier(supplier,self.root)); title.setObjectName("supplierName"); title.setWordWrap(True)
            title_font = QFont("Segoe UI", 10); title_font.setBold(True); title.setFont(title_font)
            title.setMinimumWidth(0); title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            layout.addWidget(title)
            refs = invoice_images(name, rows)
            source = QLabel(f"{name} · {len(rows)} dòng · {len([p for p in self.images if image_name(p) in refs])} ảnh")
            source.setObjectName("receiptSource"); layout.addWidget(source)
            chip = QLabel(state); chip.setObjectName("checkedChip" if fully_checked else "pendingChip")
            chip.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed); layout.addWidget(chip)
            height = title.fontMetrics().boundingRect(QRect(0,0,150,1500), Qt.TextWordWrap, supplier).height() + 8
            title.setMinimumHeight(height)
            item.setSizeHint(QSize(200, max(110, height + 85)))
            self.receipt_list.setItemWidget(item, card)
        self.receipt_list.blockSignals(False)
        for i in range(self.receipt_list.count()):
            if self.receipt_list.item(i).data(Qt.UserRole) == current:
                self.receipt_list.setCurrentRow(i); return
        if self.receipt_list.count():
            self.receipt_list.setCurrentRow(0)
        else:
            self.select_sheet("")

    def approved(self, name: str) -> bool:
        return bool(self.signatures.get(name)) and self.reviews.get(name) == self.signatures.get(name)

    def select_receipt(self, index: int):
        if index < 0 or index >= self.receipt_list.count():
            return
        self.select_sheet(self.receipt_list.item(index).data(Qt.UserRole))

    def move_receipt(self, delta: int):
        row = self.receipt_list.currentRow()
        self.receipt_list.setCurrentRow(max(0, min(self.receipt_list.count() - 1, row + delta)))

    def preview_options(self):
        contrast=self.contrast_check.isChecked() and not self.original_check.isChecked()
        changed=contrast!=getattr(self.preview,'contrast',False)
        self.preview.contrast=contrast
        self.preview.set_options(self.light_check.isChecked() and not self.original_check.isChecked(), self.crop_check.isChecked() and not self.original_check.isChecked())
        if changed and self.preview.source_path:self.preview.set_image(self.preview.source_path,force=True)

    def _review_tab_changed(self,index):
        if hasattr(self,'row_detail'):self.row_detail.setVisible(index==0 and bool(self.row_detail.text()))
        if index==1 and not self.busy:
            if not self.current_sheet or not self.data_by_sheet.get(self.current_sheet):
                self.pr_placeholder.setText('Chưa có phiếu để đối chiếu PR.');self.pr_placeholder.show()
            elif getattr(self,'pr_sheet',None)!=self.current_sheet or not hasattr(self,'pr_panel'):
                if not self.receipt_references():
                    self.pr_placeholder.setText('Chưa ghép PR. Bấm nút PR trên ảnh để chọn PR của phiếu này.');self.pr_placeholder.show()
                else:self.compare_current_pr()
        if index==0 and getattr(self,'pr_dirty',lambda:False)():
            if not self._leave_pr():
                self.review_tabs.blockSignals(True);self.review_tabs.setCurrentIndex(1);self.review_tabs.blockSignals(False)

    def _leave_pr(self):
        if getattr(self,'pr_dirty',lambda:False)() and getattr(self,'pr_save_draft',None):
            if self.pr_save_draft():return True
        from rec_feedback_states import leave_comparison
        return leave_comparison(self)

    def select_sheet(self, name: str):
        if name!=self.current_sheet:
            if not self._leave_pr():
                self.sheet_combo.blockSignals(True);self.sheet_combo.setCurrentText(self.current_sheet);self.sheet_combo.blockSignals(False)
                return
            self.pr_dirty=lambda:False
            if hasattr(self,'pr_panel'):
                self.pr_panel.hide();self.pr_panel.setParent(None);self.pr_panel.deleteLater();del self.pr_panel
            if hasattr(self,'review_tabs'):self.review_tabs.setCurrentIndex(0);self.pr_placeholder.show()
        self.reference_mode = False
        self.reference_toggle.setText('PR')
        if name != self.current_sheet:
            self.clear_row_region()
        if name not in self.sheet_names:
            self.current_sheet = ""
            self.table.model().set_rows([], self.show_all.isChecked())
            self.invoice_meta.setText("Chọn phiếu có dữ liệu để kiểm tra")
            self.review_label.setText("Chưa có dữ liệu")
            self.total_label.setText("")
            self.paper_total_label.setText('')
            self.position.setText("Chưa có dữ liệu")
            self.previous.setEnabled(False); self.next.setEnabled(False)
            self.preview.clear_image()
            self.page_combo.blockSignals(True); self.page_combo.clear(); self.page_combo.blockSignals(False)
            return
        self.current_sheet = name
        self.sheet_combo.blockSignals(True); self.sheet_combo.setCurrentText(name); self.sheet_combo.blockSignals(False)
        index = self.sheet_names.index(name)
        self.receipt_list.blockSignals(True)
        for i in range(self.receipt_list.count()):
            if self.receipt_list.item(i).data(Qt.UserRole) == name:
                self.receipt_list.setCurrentRow(i); break
        self.receipt_list.blockSignals(False)
        for i in range(self.receipt_list.count()):
            card = self.receipt_list.itemWidget(self.receipt_list.item(i))
            if card:
                card.setProperty("selected", self.receipt_list.item(i).data(Qt.UserRole) == name)
                card.style().unpolish(card); card.style().polish(card)
        visible_index = self.receipt_list.currentRow()
        self.previous.setEnabled(visible_index > 0); self.next.setEnabled(visible_index < self.receipt_list.count() - 1)
        self.position.setText(f"Phiếu {visible_index + 1} / {self.receipt_list.count()}")
        self.refresh_table()
        self.update_pr_status()
        rows = self.data_by_sheet.get(name, [])
        refs = invoice_images(name, rows)
        from receiving_service import invoice_pages
        candidates = invoice_pages(name,rows,self.images)
        self.page_combo.blockSignals(True); self.page_combo.clear()
        for page, path in enumerate(candidates, 1):
            self.page_combo.addItem(f"Trang {page}/{len(candidates)} · {path.name}", str(path))
        self.page_combo.hide();self.page_arrows.sync()
        self.page_combo.blockSignals(False)
        self.image_list.blockSignals(True); self.image_list.clearSelection()
        if candidates:
            image = self.current_image if self.current_image in candidates else candidates[0]
            idx = self.images.index(image); self.image_list.setCurrentRow(idx); self.current_image = image
            self.preview.set_image(image)
            self.page_combo.blockSignals(True); self.page_combo.setCurrentIndex(candidates.index(image)); self.page_combo.blockSignals(False)
        else:
            self.current_image = None; self.preview.clear_image("Không tìm thấy ảnh của phiếu này")
        self.image_list.blockSignals(False)
        self.page_arrows.sync()
        if hasattr(self,"sync_source_page"):self.sync_source_page()

    def update_pr_status(self):
        from rec_workflow_status import schedule
        schedule(self)
        from receiving_no_po import active
        if active(self.folder,self.current_sheet,self.data_by_sheet.get(self.current_sheet,[]),self.images):
            self.review_tabs.setTabText(1,'Không PR/PO · Theo dõi thủ công');self.compare_pr_button.setToolTip('Phiếu không có PR/PO. Bạn tự theo dõi thiếu hàng trên Google Sheets.');return
        text='PR · Chưa đối chiếu'
        try:
            path=self.reference_link_path().with_suffix('.comparison.json')
            saved=json.loads(path.read_text(encoding='utf-8'))
            if saved.get('signature')==sheet_signature(self.current_sheet,self.data_by_sheet.get(self.current_sheet,[])) and pr_images_match(saved.get('images'), self.receipt_references()):
                count=sum(bool(set(r.get('alerts',[]))-{'previous_receipt_invalid'}) or ('pr_index' not in r and not r.get('deposit')) for r in saved.get('results',[]))
                history_count=sum('previous_receipt_invalid' in r.get('alerts',[]) for r in saved.get('results',[]))
                text='PR · Đã lưu đối chiếu'+(' · '+str(count)+' dòng cần rà' if count else ' · Lần này không lệch')+(' · Nguồn lần nhận khác cần cập nhật' if history_count else '')
            else:text='PR · Nguồn đổi, cần rà lại'
        except (OSError,ValueError,KeyError,TypeError):pass
        from rec_pr_review import decorate_tab
        decorate_tab(self,text)
        self.compare_pr_button.setToolTip(text+'; lưu đối chiếu không đồng nghĩa đã ghi sổ.')
        from rec_receipt_check_status import status as check_status
        for i in range(self.receipt_list.count()):
            item=self.receipt_list.item(i);name=item.data(Qt.UserRole);card=self.receipt_list.itemWidget(item)
            if card is None:continue
            label,checked=check_status(self,name)
            for chip in card.findChildren(QLabel):
                if chip.objectName() in ('checkedChip','pendingChip'):
                    chip.setText(label);chip.setObjectName('checkedChip' if checked else 'pendingChip')
                    chip.style().unpolish(chip);chip.style().polish(chip)


    def refresh_all_pr(self):
        from rec_bulk_ledger_ui import show
        show(self)

    def compare_current_pr(self):
        if self.busy: return
        # Cached/library reads are synchronous, so expose the same visible
        # progress state before touching disk or matching data.
        self.set_busy(True, 'Đang tải dữ liệu PR và chuẩn bị đối chiếu…')
        QApplication.processEvents()
        images = self.receipt_references()
        if not images:
            self.set_busy(False)
            QMessageBox.information(self, 'Chưa ghép PR', 'Bấm nút PR bên trên ảnh, chọn các trang PR của phiếu này rồi bấm Lưu ghép PR.'); return
        if digest(self.report) != self.source_hash:
            self.set_busy(False)
            QMessageBox.warning(self, 'Excel đã thay đổi', 'Tải lại Excel trước khi đối chiếu.'); return
        try:
            saved=json.loads(self.reference_link_path().with_suffix('.comparison.json').read_text(encoding='utf-8'))
            if saved.get('version')==1 and pr_images_match(saved.get('images'), images) and isinstance(saved.get('pr_items'),list) and saved['pr_items'] and all(isinstance(item,dict) for item in saved['pr_items']):
                self.statusBar().showMessage('Đã tải kết quả PR đã lưu; đang dựng bảng đối chiếu…');QApplication.processEvents();self.show_pr_comparison(saved['pr_items'],self.data_by_sheet[self.current_sheet],images);self.set_busy(False);return
        except (OSError,ValueError,KeyError,TypeError):pass
        try:
            stored=self.stored_pr_items(images)
            if stored:
                self.statusBar().showMessage('Đã tải PR từ thư viện; đang dựng bảng đối chiếu…');QApplication.processEvents();self.show_pr_comparison(stored,self.data_by_sheet[self.current_sheet],images);self.set_busy(False);return
        except (OSError,ValueError,KeyError,TypeError) as exc:
            self.set_busy(False);QMessageBox.warning(self,'Chưa đọc được thư viện PR',str(exc));return
        from receiving_pr import read_pr
        sheet = self.current_sheet
        rows = self.data_by_sheet[sheet]
        source_hash = self.source_hash
        self.set_busy(True, 'Đang đọc PR đã ghép; sẽ thử lại một lần nếu quá thời gian chờ…')
        QApplication.processEvents()
        worker = Worker(read_pr, self.root, self.folder, images)
        worker.kwargs['progress'] = worker.signals.progress.emit
        worker.signals.progress.connect(self.statusBar().showMessage)
        worker.signals.progress.connect(lambda message: self.compare_pr_button.setText('Đang đọc PR…'))
        self.compare_pr_button.setEnabled(False)
        def ready(items):
            if self.current_sheet != sheet or digest(self.report) != source_hash:
                QMessageBox.warning(self, 'Nguồn thay đổi', 'Kết quả đọc PR đã được lưu; tải lại phiếu và đối chiếu lại.'); return
            self.show_pr_comparison(items, rows, images)
        worker.signals.result.connect(ready)
        retry_bundle=[False]
        def failed_pr(message):
            from rec_pr_bundle import offer
            if 'Các trang có số PR khác nhau' in message and self.current_sheet==sheet and digest(self.report)==source_hash:
                try:retry_bundle[0]=offer(self,self.folder,images)
                except (OSError,ValueError) as exc:message=str(exc)
                if retry_bundle[0]:return
            QMessageBox.warning(self,'Chưa đối chiếu PR',message)
        worker.signals.error.connect(failed_pr)
        def finished():
            self.set_busy(False)
            self.compare_pr_button.setText('Đối chiếu PR')
            self.compare_pr_button.setEnabled(True)
            if retry_bundle[0]:QTimer.singleShot(0,self.compare_current_pr)
        worker.signals.finished.connect(finished)
        self._start_worker(worker)

    def show_pr_comparison(self, items, rows, images, preserved=None):
        try:self.remember_pr(items,images)
        except (OSError,ValueError,TypeError) as exc:
            QMessageBox.warning(self,'Chưa lưu được PR vào thư viện',str(exc));return
        from receiving_pr import compare as compare_current
        from receiving_cumulative import context,apply as cumulative_view
        import receiving_ledger as ledger
        refs=invoice_images(self.current_sheet,rows)
        hashes=sorted(set(digest(p) for p in self.images if image_name(p) in refs))
        from receiving_document_identity import receipt_identity
        from receiving_pr_library import identity
        receipt_id=receipt_identity([p for p in self.images if image_name(p) in refs],self.ledger_path());order_id=identity(images,self.pr_library_directory())
        order_id=ledger.resolve_order(self.ledger_path(),order_id)
        validation_cache={}
        previous,uncertain,prior_count=context(self.ledger_path(),order_id,receipt_id,lambda p:self._ledger_valid(p,validation_cache))
        comparison_cache={}
        def compare(*args,**kwargs):
            from copy import deepcopy
            from rec_runtime import user_root
            rule_path=user_root()/'NhaCungCap.json'
            try:stamp=(rule_path.stat().st_mtime_ns,rule_path.stat().st_size)
            except OSError:stamp=None
            key=json.dumps([args,kwargs,stamp],sort_keys=True,default=str,ensure_ascii=False)
            if comparison_cache.get('key')!=key:
                comparison_cache.update(key=key,value=cumulative_view(compare_current(*args,**kwargs),previous,uncertain,prior_count))
            return deepcopy(comparison_cache['value'])

        from rec_fluent_ui import FluentButtonBox
        signature = sheet_signature(self.current_sheet, rows)
        image_hashes = {image_name(p): source_digest(p) for p in images}
        path = self.reference_link_path().with_suffix('.comparison.json')
        from rec_pr_review import sources as review_sources
        review_opened_sources=review_sources(self)
        links = {}; conversions = {}
        try:
            saved = json.loads(path.read_text(encoding='utf-8'))
            if saved.get('signature') == signature and pr_images_match(saved.get('images'), images):
                links = {int(k):v for k,v in saved.get('links',{}).items()}
                conversions={int(k):v for k,v in saved.get('conversions',{}).items()}
        except (OSError, ValueError, TypeError): pass
        if preserved is not None:
            links,conversions=preserved
        if not self._leave_pr():return
        if hasattr(self,'pr_panel'):
            self.pr_panel.hide();self.pr_panel.setParent(None);self.pr_panel.deleteLater()
        self.pr_placeholder.hide()
        dialog=QWidget(self.pr_host_layout.parentWidget());dialog.setUpdatesEnabled(False);self.pr_panel=dialog;self.pr_host_layout.addWidget(dialog)
        self.pr_sheet=self.current_sheet
        baseline=[json.dumps([links,conversions],sort_keys=True,default=str)]
        self.pr_dirty=lambda:json.dumps([links,conversions],sort_keys=True,default=str)!=baseline[0]
        def discard():
            original=json.loads(baseline[0]);links.clear();links.update({int(k):v for k,v in original[0].items()});conversions.clear();conversions.update({int(k):v for k,v in original[1].items()});render()
        self.pr_discard=discard
        layout = QVBoxLayout(dialog);layout.setContentsMargins(0,0,0,0);layout.setSpacing(6)
        heading = QLabel('Phiếu giao đã kiểm tra — chỉ rà chênh lệch PR bên dưới' if self.approved(self.current_sheet) else 'Phiếu giao chưa kiểm tra — xác minh tên, lượng, giá trên ảnh trước khi ghi sổ'); heading.setObjectName('section');layout.addWidget(heading)
        note = QLabel('PR là phiếu yêu cầu mua hàng. Lượng nhận và đơn giá được quy về đơn vị trên PR để so sánh. Nếu khác đơn vị, chọn dòng rồi bấm Quy đổi đơn vị.'); note.setObjectName('muted'); note.setWordWrap(True);note.hide()
        note.setToolTip('Lượng thiếu chỉ tính trong phiếu này; chưa tự quy đổi VAT/chiết khấu. Hệ số đơn vị cần xác nhận theo đúng mặt hàng.')
        if prior_count:
            cumulative_note=QLabel('Giao nhiều lần: đã có '+str(prior_count)+' lần nhận khác trong sổ. Thiếu/dư tính theo tổng; Thực nhận là riêng phiếu này.');cumulative_note.setWordWrap(True);layout.addWidget(cumulative_note)
        alert_summary=QLabel();alert_summary.setObjectName('section');layout.addWidget(alert_summary)
        legend=QLabel('<span style="color:#b91c1c">■ Đỏ: lệch giá</span> &nbsp; <span style="color:#9a3412">■ Cam: giao thiếu</span> &nbsp; <span style="color:#7e22ce">■ Tím: giao dư</span> &nbsp; <span style="color:#854d0e">■ Vàng: cần xác minh / quy đổi</span> &nbsp; <span style="color:#2563d9">▎Xanh: dòng đang chọn</span>')
        legend.hide();legend.setWordWrap(True);legend.setObjectName('prColorLegend');
        tools=QHBoxLayout();layout.addLayout(tools)
        only_review=Checkbox('Chỉ dòng cần rà');only_review.setChecked(True);tools.addWidget(only_review);tools.addStretch()
        expanded=Checkbox('Chi tiết số lượng / giá');expanded.setObjectName('prExpanded');tools.addWidget(expanded)
        table = QTableWidget(); table.setColumnCount(14)
        table.setObjectName('prCompare'); table.setShowGrid(False); table.setAlternatingRowColors(True)
        table.setItemDelegate(PRAlertDelegate(table))
        table.verticalHeader().hide(); table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setHorizontalHeaderLabels(['Hàng PR / phiếu','Dòng phiếu giao','ĐVT PR','SL đặt','SL giao','Thực nhận','Giá PR','Giá phiếu','Còn thiếu','Kết quả cần rà','Ảnh PR / dòng','Kết quả đối chiếu','Đã nhận trước','Tổng sau lần này'])
        def columns():
            for col in (2,4,6,7,8,9):table.setColumnHidden(col,not expanded.isChecked())
            table.setColumnHidden(10,True)
            table.setColumnHidden(12,False);table.setColumnHidden(13,False)
            table.horizontalHeader().setStretchLastSection(True)
        expanded.toggled.connect(columns);columns()
        table.setEditTriggers(QAbstractItemView.NoEditTriggers); table.setWordWrap(True)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel); layout.addWidget(table, 1)
        detail = QLabel('Chọn dòng để xem đầy đủ kết quả và nguồn ảnh.'); detail.setObjectName('rowReview'); detail.setWordWrap(True);detail.setFixedHeight(62); detail.setTextInteractionFlags(Qt.TextSelectableByMouse); detail.hide()
        table.itemSelectionChanged.connect(lambda: detail.setText(table.item(table.currentRow(),9).toolTip()) if table.currentRow() >= 0 and table.item(table.currentRow(),9) else None)
        order_choice=QComboBox();order_choice.addItem('Theo phiếu giao','delivery');order_choice.addItem('Theo PR','pr');order_choice.setToolTip('Chỉ đổi thứ tự xem, không thay đổi cặp ghép hoặc STT gốc.');tools.addWidget(order_choice)
        self.pr_order_choice=order_choice
        rendered_results=[]
        def filter_rows():
            for i,result in enumerate(rendered_results):
                needs=not result.get('deposit') and (bool(result.get('alerts')) or 'pr_index' not in result or result.get('row') is None or bool(result.get('suggested_row') and result.get('row') is None))
                table.setRowHidden(i,only_review.isChecked() and not needs)
        only_review.toggled.connect(filter_rows)
        pr_editors={}
        def get_editor(row,col):return pr_editors.get(row) if col==1 else None
        self.pr_editors=pr_editors
        def render():
            dialog.setUpdatesEnabled(False);table.blockSignals(True)
            for editor in pr_editors.values():editor.deleteLater()
            pr_editors.clear()
            selected=table.currentRow();selected_key=(rendered_results[selected].get('pr_index'),rendered_results[selected].get('row')) if 0<=selected<len(rendered_results) else None;scroll=table.verticalScrollBar().value()
            from receiving_units import approved_conversion
            try:rules=json.loads((self.root/'NhaCungCap.json').read_text(encoding='utf-8'))
            except (OSError,ValueError):rules={}
            preliminary=compare(items,rows,links)
            for r in preliminary:
                p=r.get('pr_index');source_row=r.get('row')
                if p is not None and source_row is not None and p not in conversions:
                    value=dict(rows)[source_row]
                    rule=approved_conversion(rules,value.get('Nhà cung cấp'),source_row,items[p],value)
                    if rule:conversions[p]=rule
            results = compare(items, rows, links,conversions)
            from receiving_pr_order import ordered
            results=ordered(results,items,rows,order_choice.currentData())
            rendered_results[:]=results
            from receiving_alerts import presentation
            alert_summary.setText('  ·  '.join(f'{label}: {sum(flag in r.get("alerts",[]) for r in results)}' for flag,label in [('price','Lệch giá'),('short','Giao thiếu'),('over','Giao dư')]))
            table.setRowCount(len(results))
            for i, result in enumerate(results):
                warning=presentation(result)
                fields = ['name',None,'unit','ordered','delivered','received','price','delivery_price','remaining','status','source','alert_label','previous_received','total_received']
                for col, field in enumerate(fields):
                    if field is None: continue
                    value = warning['label'] or str(result.get('status') or 'Cần kiểm tra').split(';')[0] if field == 'alert_label' else result.get(field)
                    text = '' if value is None else str(value)
                    if field=='unit':
                        from receiving_sheets import display_unit
                        text=display_unit(value)
                    if field=='alert_label' and result.get('purchase_approval'):text+=' · Đóng gói đã duyệt'
                    if field=='ordered' and result.get('purchase_approval'):text=str(result.get('requested'))+' → '+str(value)
                    if col==0:
                        from receiving_pr_order import label
                        text=label(result,items)
                    if col in (6,7) and value is not None:
                        text=format(value,',f');text=text.rstrip('0').rstrip('.') if '.' in text else text
                    cell = QTableWidgetItem(text)
                    tooltip=warning['label'] + '\n' + str(result.get('status','')) + '\nNguồn: ' + str(result.get('source','')) if col == 9 else text
                    if result.get('conversion_label') and col in (4,5,7):
                        raw=result.get({4:'original_delivered',5:'original_received',7:'original_price'}[col])
                        tooltip=f'Gốc trên phiếu: {raw}\n'+result['conversion_label']
                    cell.setToolTip(tooltip)
                    if col in range(3,9): cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    if warning['background']:
                        cell.setBackground(QColor(warning['background']));cell.setData(Qt.UserRole+12,True)
                        if col == 11:font=cell.font();font.setBold(True);cell.setFont(font)
                    if col in warning['cells']:
                        bg,fg=warning['cells'][col];cell.setBackground(QColor(bg));cell.setForeground(QColor(fg))
                        font=cell.font();font.setBold(True);cell.setFont(font)
                    table.setItem(i,col,cell)
                if 'pr_index' in result:
                    p = result['pr_index']; choice = PRLineCombo();choice.setFocusPolicy(Qt.ClickFocus)

                    suggestion=result.get('suggested_row')
                    choice.addItem(f'Chưa gán · gợi ý dòng {suggestion-1}' if result.get('row') is None and suggestion is not None else 'Chưa xác định', 'unknown'); choice.addItem('Không giao trong phiếu này', None)
                    candidates=sorted(rows,key=lambda pair:pair[0]!=suggestion)
                    for row, value in candidates:
                        prefix='Tự gán · ' if row==result.get('row') and p not in links else 'Gợi ý · ' if row==suggestion and result.get('row') is None else ''
                        choice.addItem(prefix+f"Dòng {row-1} · {value.get('Tên hàng trên phiếu (Ảnh)','')}", row)
                    choice.setToolTip(result.get('match_reason') or 'Gợi ý chưa được áp dụng. Chọn dòng sau khi kiểm tra tên/quy cách.')
                    target = links.get(p, result.get('row') if result.get('row') is not None else 'unknown')
                    choice.setCurrentIndex(choice.findData(target))
                    label=QTableWidgetItem(choice.currentText());label.setToolTip(choice.currentText());table.setItem(i,1,label)
                    def changed(index, p=p, choice=choice, target=target):
                        value = choice.itemData(index)
                        if value not in ('unknown',None):
                            current=compare(items,rows,links,conversions)
                            if any(r.get('pr_index') is not None and r['pr_index']!=p and r.get('row')==value for r in current):
                                choice.blockSignals(True);choice.setCurrentIndex(choice.findData(target));choice.blockSignals(False)
                                QMessageBox.information(dialog,'Dòng giao đã được sử dụng','Dòng giao này đã ghép với một dòng PR khác. Bỏ ghép ở dòng cũ trước khi chuyển sang dòng này.');return
                        if value == 'unknown': links.pop(p,None)
                        else: links[p] = value
                        conversions.pop(p,None)
                        QTimer.singleShot(0, render)
                    choice.currentIndexChanged.connect(changed)
                    if result.get('row') is None and p not in links and suggestion is not None:
                        holder=QWidget();cell_layout=QVBoxLayout(holder);cell_layout.setContentsMargins(5,4,5,4);cell_layout.setSpacing(4)
                        cell_layout.addWidget(choice)
                        use=Button(f'Dùng gợi ý dòng {suggestion-1}')
                        use.setObjectName('useSuggestion');use.setMinimumHeight(34);choice.setMinimumHeight(34)
                        source=dict(rows).get(suggestion,{})
                        use.setToolTip('Gán dòng này theo gợi ý: '+str(source.get('Tên hàng trên phiếu (Ảnh)',''))+'\nKiểm tra tên và quy cách sau khi gán. Chưa lưu đối chiếu hoặc ghi sổ.')
                        occupied=any(r.get('row')==suggestion for r in results if r.get('pr_index') is not None and r.get('pr_index')!=p)
                        if occupied:
                            use.setEnabled(False);use.setToolTip('Dòng gợi ý đã được ghép với một dòng PR khác. Kiểm tra lại trước khi chọn trong danh sách.')
                        use.clicked.connect(lambda checked=False,choice=choice,suggestion=suggestion:choice.setCurrentIndex(choice.findData(suggestion)))
                        cell_layout.addWidget(use);holder.setParent(dialog);holder.hide();pr_editors[i]=holder
                    else:choice.setParent(dialog);choice.hide();pr_editors[i]=choice
            for col,width in enumerate([180,200,65,60,65,75,95,95,65,300,180,280]): table.setColumnWidth(col,width)
            table.setColumnHidden(10,True)
            table.setColumnHidden(12,False);table.setColumnHidden(13,False)
            if table.isVisible():table.resizeRowsToContents()
            for i in range(table.rowCount()):
                widget=get_editor(i,1)
                minimum=widget.sizeHint().height()+8 if widget is not None else 48
                table.setRowHeight(i,max(48,minimum,table.rowHeight(i)))
            columns();filter_rows()
            selected=next((i for i,r in enumerate(rendered_results) if (r.get('pr_index'),r.get('row'))==selected_key),-1)
            if 0<=selected<table.rowCount():table.selectRow(selected)
            table.verticalScrollBar().setValue(scroll)
            if hasattr(dialog,"refresh_compare_view"):dialog.refresh_compare_view()
            table.blockSignals(False);dialog.setUpdatesEnabled(True)
            if hasattr(dialog,'draft_timer') and self.pr_dirty():dialog.draft_timer.start()
        order_choice.currentIndexChanged.connect(render)
        render()
        baseline[0]=json.dumps([links,conversions],sort_keys=True,default=str)
        def edit_conversion():
            current=table.currentRow()
            p=rendered_results[current].get('pr_index') if 0<=current<len(rendered_results) else None
            if p is None:
                QMessageBox.information(dialog,'Chọn dòng PR','Chọn dòng PR cần quy đổi.');return
            result=rendered_results[current];source_row=result.get('row')
            if source_row is None:
                QMessageBox.information(dialog,'Chưa gán dòng','Chọn dòng giao tương ứng trước khi xác nhận quy đổi.');return
            value=dict(rows)[source_row];item=items[p]
            from rec_unit_conversion_page import open_page
            def confirmed(rule):
                conversions[p]=dict(conversions.get(p) or {},**rule)
                render()
            price_sheet=self.current_sheet;price_report=self.report
            def save_conversion_price(price):
                if self.busy:return False
                if self.current_sheet!=price_sheet or self.report!=price_report:
                    raise ValueError('Phiếu đã đổi. Mở lại Quy đổi ĐVT trước khi nhập giá.')
                if not self._leave_pr():return False
                self.save_row_changes((source_row,{'Đơn giá':price}))
                return True
            open_page(self,item,value,source_row,conversions.get(p,{}) or {},confirmed,
                      on_save_price=save_conversion_price)
        def mark_unreceived():
            current=compare(items,rows,links,conversions)
            from rec_pr_review import outside_rows
            if outside_rows(current):
                QMessageBox.information(dialog,'Ghép các món trên phiếu trước','Còn món trên phiếu giao chưa ghép với PR. Chọn dòng PR tương ứng cho các món đã giao trước, rồi đánh dấu các dòng còn lại.');return
            pending=[r for r in compare(items,rows,links,conversions) if r.get('pr_index') is not None and r.get('row') is None and r.get('pr_index') not in links]
            if not pending:
                QMessageBox.information(dialog,'Không có dòng cần đánh dấu','Mỗi món đã được ghép với dòng giao hoặc xác nhận không giao trong phiếu này.');return
            answer=QMessageBox.question(dialog,'Xác nhận các món không giao trong phiếu này',f'Phiếu này chỉ có một phần hàng?\nXác nhận {len(pending)} món còn lại không giao trong phiếu này?\nDòng đã nhận sẽ giữ nguyên. Chỉ áp dụng cho phiếu này; không xóa lượng đã nhận ở phiếu trước.',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
            if answer!=QMessageBox.Yes:return
            for result in pending:
                p=result['pr_index'];links[p]=None;conversions.pop(p,None)
            render()
        buttons = FluentButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        convert_button=Button('Quy đổi đơn vị');convert_button.clicked.connect(edit_conversion);convert_button.setToolTip('Đổi lượng và đơn giá giữa hai đơn vị; không tăng lượng PR đã duyệt.')
        bulk_unreceived=Button('Các món còn lại không có trong phiếu giao');bulk_unreceived.setObjectName('bulkUnreceived');bulk_unreceived.setToolTip('Chỉ áp dụng cho phiếu đang mở. Giữ các món đã ghép; các món còn lại nhận thêm 0. Lượng đã nhận ở những phiếu trước không thay đổi.')
        bulk_unreceived.clicked.connect(mark_unreceived);tools.insertWidget(1,bulk_unreceived)
        buttons.button(QDialogButtonBox.Save).setText('Lưu đối chiếu'); buttons.button(QDialogButtonBox.Cancel).setText('Phiếu giao')
        buttons.removeButton(buttons.button(QDialogButtonBox.Cancel))
        buttons.button(QDialogButtonBox.Save).setObjectName('secondary')
        buttons.button(QDialogButtonBox.Save).setStyleSheet('QPushButton { background: white; color: #243447; border: 1px solid #cbd7e6; }')
        record = buttons.addButton('Xác nhận và ghi sổ', QDialogButtonBox.ActionRole)
        record.setObjectName('primary')
        record.setToolTip('Lưu số thực nhận để theo dõi tổng đã nhận và hàng còn thiếu qua nhiều ngày. Ghi lại cùng phiếu chỉ cập nhật lần nhận cũ.')
        buttons.button(QDialogButtonBox.Save).setToolTip('Lưu cách ghép dòng và quy đổi cho phiếu này. Không cộng số lượng vào sổ theo dõi nhận hàng.')
        def record_now():
            if self.busy or self.current_sheet!=self.pr_sheet:return
            from rec_pr_review import eligible
            current=compare(items,rows,links,conversions)
            if not eligible(current):
                pending=[str(r.get('name') or 'Dòng chưa ghép')+': '+str(r.get('status') or '') for r in current if r.get('pr_index') is None and not r.get('deposit') and (r.get('received') is None or r.get('received')!=0) or set(r.get('alerts',[]))-{'short','previous_receipt_invalid'}]
                QMessageBox.warning(self,'Chưa thể hoàn tất rà', '\n'.join(pending) or 'Cần ghép rõ từng món PR và dòng phiếu giao.');return
            if not save():return
            from rec_pr_review import confirm,sources
            try:
                confirm(self,path,current,review_opened_sources)
                baseline[0]=json.dumps([links,conversions],sort_keys=True,default=str)
                self.update_pr_status();dialog.refresh_compare_view()
                self.statusBar().showMessage('Đã kiểm xong phiếu, chờ ghi sổ. Kiểm các phiếu còn lại rồi bấm Hoàn tất đợt kiểm ở thanh trên.')
            except (OSError,ValueError,TypeError) as exc:QMessageBox.warning(self,'Chưa đưa phiếu vào hàng chờ',str(exc))
        record.clicked.connect(record_now)
        row_actions=QHBoxLayout()
        choose=QAction('Chọn dòng giao…',dialog);choose.setObjectName('prChooseRow')
        suggest=QAction('Dùng gợi ý dòng',dialog);suggest.setObjectName('prUseSuggestion')
        def active_choice():
            widget=get_editor(table.currentRow(),1)
            return widget if isinstance(widget,PRLineCombo) else widget.findChild(PRLineCombo) if widget else None
        def choose_row():
            current=table.currentRow()
            if not 0<=current<len(rendered_results):return
            result=rendered_results[current];p=result.get('pr_index');choice=active_choice()
            pending_row=None
            if p is None and result.get('row') is not None:
                # An unmatched delivery line has no PR editor of its own.
                # Let the user choose the PR explicitly, then use its original
                # mapping editor and duplicate/conflict validation.
                from PySide6.QtWidgets import QInputDialog
                candidates=[(i,r['pr_index']) for i,r in enumerate(rendered_results) if r.get('pr_index') is not None]
                labels=[str(items[index].get('source_line') or index+1)+' · '+str(items[index].get('item_name') or 'Hàng PR') for _,index in candidates]
                if not labels:return
                label,ok=QInputDialog.getItem(dialog,'Gán dòng giao vào PR','Chọn hàng PR tương ứng với '+str(result.get('name') or 'dòng giao đang chọn'),labels,0,False)
                if not ok:return
                editor_row,p=candidates[labels.index(label)]
                widget=get_editor(editor_row,1)
                choice=widget if isinstance(widget,PRLineCombo) else widget.findChild(PRLineCombo) if widget else None
                pending_row=result['row']
            if choice is None or p is None:return
            from rec_pr_mapping_dialog import choose as choose_mapping
            occupied={r['row'] for r in rendered_results if r.get('pr_index') is not None and r.get('pr_index')!=p and r.get('row') is not None}
            displayed=choice
            if pending_row is not None:
                displayed=QComboBox()
                for i in range(choice.count()):displayed.addItem(choice.itemText(i),choice.itemData(i))
                displayed.setCurrentIndex(displayed.findData(pending_row))
            index=choose_mapping(self,items[p],displayed,rows,occupied)
            if index is not None:choice.setCurrentIndex(index)
        def use_suggestion():
            widget=get_editor(table.currentRow(),1)
            use=widget.findChild(QPushButton,'useSuggestion') if widget else None
            if use and use.isEnabled():use.click()
        def edit_packaging():
            current=table.currentRow()
            results=rendered_results
            if not 0<=current<len(results):return
            result=results[current];p=result.get('pr_index');source=result.get('row')
            if p is None or source is None:
                QMessageBox.information(dialog,'Chọn dòng đã ghép','Ghép đúng dòng NCC trước khi duyệt đóng gói.');return
            value=dict(rows)[source];supplier=str(value.get('Nhà cung cấp') or '').strip()
            from rec_packaging_page import open_page
            def apply_packaging(rule):
                entry=dict(conversions.get(p) or {})
                if rule is None:entry.pop('purchase_approval',None)
                else:entry['purchase_approval']=rule
                if entry:conversions[p]=entry
                else:conversions.pop(p,None)
                render()
            open_page(self,items[p],value,source,conversions.get(p,{}) or {},apply_packaging)
        def edit_receipt_correction():
            results=rendered_results;current=table.currentRow()
            if not 0<=current<len(results):return
            result=results[current];p=result.get('pr_index');row=result.get('row')
            if p is None or row is None:
                QMessageBox.information(dialog,'Chọn dòng đã ghép','Chọn một dòng PR đã ghép với phiếu giao.');return
            value=dict(rows)[row];old=(conversions.get(p) or {}).get('receipt_correction',{})
            from rec_quantity_correction_page import open_page
            def apply_correction(rule):
                entry=dict(conversions.get(p) or {})
                if rule is None:entry.pop('receipt_correction',None)
                else:entry['receipt_correction']=rule
                if entry:conversions[p]=entry
                else:conversions.pop(p,None)
                render()
            open_page(self,items[p],value,row,conversions.get(p,{}) or {},apply_correction)
        correction_button=Button('NCC ghi sai lượng/ĐVT');correction_button.setObjectName('receiptQuantityCorrection');correction_button.clicked.connect(edit_receipt_correction)
        def edit_price():
            current=table.currentRow();results=rendered_results
            if not 0<=current<len(results):return
            result=results[current];p=result.get('pr_index');row=result.get('row')
            if p is None or row is None:return
            if 'unit' in result.get('alerts',[]) or result.get('receipt_correction') or 'receipt_correction' in result.get('alerts',[]):
                QMessageBox.information(dialog,'Xác định đơn vị trước','Xác nhận quy đổi và đơn giá tính theo ĐVT PR trước khi duyệt giá. Dòng NCC sai lượng/ĐVT vẫn cần rà riêng.');return
            entry=dict(conversions.get(p) or {});old=entry.get('price_approval') or {}
            from rec_price_approval_page import open_page
            def apply_price(rule):
                conversions[p]=dict(conversions.get(p) or {},price_approval=rule)
                render()
            open_page(self,items[p],dict(rows)[row],row,entry,result.get('delivery_price'),apply_price)
        price_button=Button('Xác nhận giá mới');price_button.clicked.connect(edit_price)
        def separate_vat():
            current=table.currentRow()
            if self.busy or not 0<=current<len(rendered_results):return
            result=rendered_results[current];row=result.get('row')
            if row is None:
                QMessageBox.information(dialog,'Chọn dòng giao','Chọn món đã ghép với dòng phiếu giao để tách VAT.');return
            options=['Giá NCC đã gồm VAT 8%','Giá NCC đã gồm VAT 10%','Bỏ tách VAT — khôi phục giá NCC gốc']
            selected,ok=QInputDialog.getItem(dialog,'Tính giá trước thuế',str(result.get('name',''))+'\nREC lưu kho bằng giá trước thuế; giữ giá NCC gốc để kiểm tra.',options,0,False)
            if not ok:return
            rate=(8,10,0)[options.index(selected)]
            value=dict(rows).get(row,{})
            if rate==0 and not value.get('Thuế suất VAT đã tách'):
                QMessageBox.information(dialog,'Chưa tách VAT','Dòng này chưa có quyết định tách VAT để khôi phục.');return
            report,expected,sheet=self.report,self.source_hash,self.current_sheet
            self.write_in_background(lambda:edit_row(report,expected,sheet,row,{},self.catalog or {},vat_rate=rate),row)
        vat_button=Button('Tách VAT 8% / 10%');vat_button.setObjectName('separateVAT');vat_button.clicked.connect(separate_vat)
        row_actions.addWidget(vat_button)
        dialog.vat_button=vat_button

        def edit_overreceipt():
            current=table.currentRow()
            if not 0<=current<len(rendered_results):return
            result=rendered_results[current];p=result.get('pr_index');row=result.get('row')
            if p is None or row is None:return
            if result.get('ordered') is None or result.get('received') is None or result.get('total_received',result['received'])<=result['ordered']:
                QMessageBox.information(dialog,'Duyệt nhận dư','Chọn dòng có lượng thực nhận lớn hơn lượng PR.');return
            from rec_overreceipt_dialog import show
            entry=dict(conversions.get(p) or {})
            def apply_over(rule):
                updated=dict(conversions.get(p) or {})
                if rule is None:updated.pop('overreceipt_approval',None)
                else:updated['overreceipt_approval']=rule
                conversions[p]=updated;render()
            show(dialog,row,items[p],dict(rows)[row],entry,result['ordered'],result['received'],apply_over,result.get('previous_received') or 0)
        overreceipt_button=Button('Duyệt nhận dư');overreceipt_button.setObjectName('approveOverreceipt');overreceipt_button.clicked.connect(edit_overreceipt)

        def edit_substitution():
            current=table.currentRow()
            if not 0<=current<len(rendered_results):return
            result=rendered_results[current];p=result.get('pr_index');row=result.get('row')
            if p is None or row is None:return
            value=dict(rows).get(row,{})
            from rec_substitution_page import open_page
            def approved(rule):
                conversions[p]=dict(conversions.get(p) or {},substitution_approval=rule);render()
            open_page(self,items[p],value,row,dict(conversions.get(p) or {}),approved)
        def edit_pr_quantity():
            current=table.currentRow()
            if not 0<=current<len(rendered_results):return
            p=rendered_results[current].get('pr_index')
            if p is None:return
            from PySide6.QtWidgets import QInputDialog
            from receiving_pr_quantity import approve as approve_quantity
            entry=dict(conversions.get(p) or {})
            value,ok=QInputDialog.getText(self,'Nhập số lượng trên PR','Số lượng đặt theo ảnh PR (giữ đúng ĐVT PR):',text=str((entry.get('pr_quantity') or {}).get('quantity') or items[p].get('quantity') or ''))
            if not ok:return
            reason,ok=QInputDialog.getText(self,'Căn cứ sửa lượng PR','Căn cứ / người xác nhận số trên PR:')
            if not ok:return
            try:
                if digest(self.report)!=self.source_hash:raise ValueError('Nguồn đã đổi. Mở lại đối chiếu.')
                rule=approve_quantity(items[p],entry,value,reason)
                entry.pop('purchase_approval',None);entry['pr_quantity']=rule;conversions[p]=entry;render()
            except ValueError as exc:QMessageBox.warning(self,'Chưa lưu số lượng PR',str(exc))
        def edit_deposit():
            from PySide6.QtWidgets import QInputDialog
            index=table.currentRow()
            if not 0<=index<len(rendered_results):return
            result=rendered_results[index];row=result.get('row')
            if row is None or result.get('pr_index') is not None:
                QMessageBox.information(self,'Tiền cọc ngoài PR','Chọn dòng phiếu giao chưa gán PR. Nếu đã gán nhầm, bỏ gán trước.');return
            from receiving_deposit import approve,key
            slot=key(row)
            if result.get('deposit'):
                if QMessageBox.question(self,'Bỏ xác nhận tiền cọc','Bỏ xác nhận tiền cọc của dòng này?',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes:
                    conversions.pop(slot,None);render()
                return
            reason,ok=QInputDialog.getText(self,'Xác nhận tiền cọc vỏ / bao bì','Khoản cọc ngoài PR, không tính vào lượng bia/hàng nhận. Giữ nguyên tiền trên phiếu. Nhập căn cứ / người xác nhận:')
            if not ok:return
            try:
                conversions[slot]=approve(row,dict(rows)[row],reason);render()
            except ValueError as exc:QMessageBox.warning(self,'Chưa xác nhận cọc',str(exc))
        dialog.edit_deposit=edit_deposit
        def confirm_spec():
            from PySide6.QtWidgets import QInputDialog
            choice=active_choice()
            if choice is None:return
            index=table.currentRow()
            if not 0<=index<len(rendered_results):return
            result=rendered_results[index];p=result.get("pr_index");row=result.get("row")
            if p is None or row is None:return
            value=dict(rows)[row]
            reason,ok=QInputDialog.getText(self,'Xác nhận cùng sản phẩm / quy cách','Chỉ xác nhận khi hai cách ghi là cùng sản phẩm và cùng một quy cách. Không đổi giá, lượng hay hệ số. Căn cứ / người xác nhận:')
            if not ok:return
            try:
                from receiving_spec_equivalence import remember
                remember(self.root,items[p],value,reason);render()
            except (OSError,ValueError) as exc:QMessageBox.warning(self,'Chưa lưu xác nhận quy cách',str(exc))
        dialog.confirm_spec=confirm_spec
        dialog.edit_substitution=edit_substitution
        dialog.edit_pr_quantity=edit_pr_quantity

        pack_button=Button('Duyệt lượng mua theo gói');pack_button.setObjectName('purchasePackaging');pack_button.clicked.connect(edit_packaging);pack_button.setToolTip('Duyệt tăng lượng mua do NCC bán nguyên gói; có thể tăng chi phí. Không phải đổi đơn vị.')
        def update_actions():
            choice=active_choice();choose.setEnabled(choice is not None)
            if hasattr(self,"pr_manual_button"):
                current=table.currentRow()
                unmatched=0<=current<len(rendered_results) and rendered_results[current].get('pr_index') is None and rendered_results[current].get('row') is not None
                self.pr_manual_button.setEnabled(choice is not None or (unmatched and bool(items)))
                self.pr_manual_button.setToolTip('Chọn hàng PR để gán dòng giao này' if unmatched else 'Gán hàng PR đang chọn với dòng giao')
            widget=get_editor(table.currentRow(),1)
            use=widget.findChild(QPushButton,'useSuggestion') if widget else None
            suggest.setEnabled(use is not None and use.isEnabled());suggest.setVisible(use is not None and use.isEnabled())
            is_pr=0<=table.currentRow()<len(rendered_results) and rendered_results[table.currentRow()].get('pr_index') is not None
            convert_button.setEnabled(is_pr)
            pack_button.setEnabled(is_pr)
            price_button.setEnabled(is_pr)
            correction_button.setEnabled(is_pr)
            for i in range(table.rowCount()):
                widget=get_editor(i,1)
                if widget:widget.hide()
        def sync_selected_row(*_):
            results=rendered_results;i=table.currentRow()
            if 0<=i<len(results):
                source=results[i].get('row')
                if source is not None:
                    model=self.table.model()
                    for j in range(model.rowCount()):
                        if model.source_row(j)==source:
                            self.table.setCurrentIndex(model.index(j,0));break
                else:self.clear_row_region()
        choose.triggered.connect(choose_row);suggest.triggered.connect(use_suggestion)
        table.itemSelectionChanged.connect(update_actions)
        table.cellClicked.connect(sync_selected_row)
        table.activated.connect(sync_selected_row)
        save_button=buttons.button(QDialogButtonBox.Save)
        buttons.removeButton(save_button);buttons.removeButton(record)
        save_button.clicked.connect(lambda:buttons.accepted.emit())
        manual_button=Button('Gán dòng giao');manual_button.setObjectName('manualPRLink')
        self.pr_manual_button=manual_button
        manual_button.clicked.connect(choose_row)
        table.cellDoubleClicked.connect(lambda row,col:choose_row() if col==1 else None)
        row_actions.addWidget(manual_button);row_actions.addStretch();row_actions.addWidget(price_button);row_actions.addWidget(correction_button);row_actions.addWidget(pack_button);row_actions.addWidget(convert_button);row_actions.addWidget(save_button);row_actions.addWidget(record)
        buttons.hide()
        layout.addLayout(row_actions)
        update_actions()
        def save(automatic=False):
            if self.busy:return False
            if getattr(self,'pr_panel',None) is not dialog or self.current_sheet!=self.pr_sheet:return False
            try:
                if digest(self.report) != self.source_hash: raise ValueError('Excel đã thay đổi. Tải lại và đối chiếu lại.')
                if not pr_images_match(image_hashes,self.receipt_references()): raise ValueError('Liên kết PR đã thay đổi. Đối chiếu lại.')
                payload = {'version':1,'signature':signature,'images':image_hashes,'links':links,'conversions':conversions,
                           'pr_items':items,'results':compare(items,rows,links,conversions)}
                from receiving_price_approval import audit
                audit(path,conversions)
                atomic_json(path, json.loads(json.dumps(payload,default=str)))
                from receiving_link_memory import remember
                learned_count=remember(self.root,items,rows,links)
                baseline[0]=json.dumps([links,conversions],sort_keys=True,default=str)
                self.update_pr_status()
                if hasattr(dialog,'refresh_compare_view'):dialog.refresh_compare_view()
                self.statusBar().showMessage('Đã lưu đối chiếu PR và nhớ các cặp gán tay cho đúng NCC/quy cách; chưa thay đổi lượng/giá.');return True
            except Exception as exc:
                if automatic:self.statusBar().showMessage('Chưa tự lưu nháp: '+str(exc))
                else:QMessageBox.warning(self,'Chưa lưu đối chiếu',str(exc))
                return False

        dialog.draft_timer=QTimer(dialog);dialog.draft_timer.setSingleShot(True);dialog.draft_timer.setInterval(700)
        def autosave():
            if self.pr_dirty() and getattr(self,'pr_panel',None) is dialog:
                if self.busy:dialog.draft_timer.start()
                else:save(automatic=True)
        dialog.draft_timer.timeout.connect(autosave)
        self.pr_save_draft=lambda:save(automatic=True)
        dialog.confirm_pr_review=record_now
        vocabulary_status=QLabel('Tên chưa rõ: tra cứu nền theo STT; tối đa 4 cặp/lượt. Chỉ gửi tên hàng, không gửi ảnh.');vocabulary_status.setWordWrap(True);layout.addWidget(vocabulary_status)
        vocabulary_apply=Button('Xem tên tương đương đã tra cứu');vocabulary_apply.hide();layout.addWidget(vocabulary_apply)
        vocabulary_evidence=[]
        def start_vocabulary():
            if self.pr_sheet!=self.current_sheet or getattr(self,'pr_panel',None) is not dialog:return
            from receiving_vocabulary import candidates,lookup
            pending=candidates(items,rows,links,compare(items,rows,links,conversions))
            if not pending:vocabulary_status.hide();return
            vocabulary_status.setText('Đang tra tên tương đương trên mạng… Bạn có thể tiếp tục kiểm tra.')
            def work():
                result=[]
                for p,row,a,b in pending:
                    evidence=lookup(self.root,a,b)
                    if evidence['equivalent']:result.append((p,row,evidence))
                return result
            job=Worker(work)
            def ready(result):
                if self.pr_sheet!=self.current_sheet or getattr(self,'pr_panel',None) is not dialog:return
                if digest(self.report)!=self.source_hash:return
                for p,row,evidence in result:
                    if evidence.get('confirmed') and p not in links and not any(r.get('row')==row for r in compare(items,rows,links,conversions)):
                        links[p]=row
                if any(e.get('confirmed') for _,_,e in result):render()
                vocabulary_evidence[:]=[(p,row,e) for p,row,e in result if p not in links];vocabulary_apply.setVisible(bool(vocabulary_evidence))
                vocabulary_status.setText('Đã tra cứu: '+str(len(result))+' cặp có nguồn hỗ trợ. Xem nguồn trước khi áp dụng.' if result else 'Chưa đủ căn cứ tên tương đương; giữ chưa ghép.')
            def failed(_):
                if getattr(self,'pr_panel',None) is dialog:vocabulary_status.setText('Chưa tra cứu được từ vựng; dữ liệu hiện tại được giữ. Mở lại đối chiếu để thử tiếp.')
            job.signals.result.connect(ready);job.signals.error.connect(failed);self._start_worker(job)
        def apply_vocabulary():
            if self.busy or getattr(self,'pr_panel',None) is not dialog:return
            if digest(self.report)!=self.source_hash or sheet_signature(self.current_sheet,rows)!=signature:
                QMessageBox.warning(dialog,'Nguồn đã đổi','Mở lại đối chiếu trước khi áp dụng.');return
            for p,row,evidence in vocabulary_evidence:
                if p in links:continue
                current=compare(items,rows,links,conversions)
                if any(r.get('row')==row for r in current):continue
                detail=' ↔ '.join(evidence['names'])+'\n\n'+evidence['explanation']+'\n\n'+'\n'.join(s['title']+': '+s['url'] for s in evidence['sources'])+'\n\nXác nhận hai tên là cùng mặt hàng cho dòng này? Không tự xác nhận đơn vị, lượng hoặc giá.'
                if QMessageBox.question(dialog,'Tên tương đương có nguồn tra cứu',detail,QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes:
                    from receiving_vocabulary import remember
                    remember(self.root,evidence);links[p]=row;conversions.pop(p,None)
            render();vocabulary_apply.hide()
        vocabulary_apply.clicked.connect(apply_vocabulary)
        QTimer.singleShot(0,start_vocabulary)
        self.pr_save=save
        buttons.accepted.connect(save);buttons.rejected.connect(lambda:self.review_tabs.setCurrentIndex(0))
        for i in range(table.rowCount()):
            widget=get_editor(i,1)
            if widget:widget.hide()
        table.setFocusPolicy(Qt.NoFocus)
        self.review_tabs.blockSignals(True);self.review_tabs.setCurrentIndex(1);self.review_tabs.blockSignals(False)
        table.clearSelection();table.setCurrentIndex(QModelIndex());only_review.setFocus()
        def quick_link(p,row):
            if self.busy or self.current_sheet!=self.pr_sheet or getattr(self,"pr_panel",None) is not dialog:return
            if digest(self.report)!=self.source_hash:
                QMessageBox.warning(self,'Nguồn đã đổi','Tải lại phiếu trước khi gán dòng.');return
            editor_row=next((i for i,r in enumerate(rendered_results) if r.get('pr_index')==p),None)
            if editor_row is None:return
            widget=get_editor(editor_row,1)
            choice=widget if isinstance(widget,PRLineCombo) else widget.findChild(PRLineCombo) if widget else None
            if choice is None:return
            index=choice.findData(row)
            if index>=0:choice.setCurrentIndex(index)
            return choice.currentData()
        def bulk_link():
            from rec_pr_bulk_links import choose
            selected=choose(self,items,rows,rendered_results,links,conversions)
            if selected is None:return
            for p,row in selected.items():
                if row=='unknown':links.pop(p,None)
                else:links[p]=row[0] if isinstance(row,list) else row
                conversions.pop(p,None)
                if isinstance(row,list):conversions[p]={'lot_rows':row}
            render()
        dialog.bulk_link=bulk_link
        dialog.quick_link=quick_link
        def no_topup(index):
            if self.busy or not 0<=index<len(items):return
            entry=conversions.setdefault(index,{})
            reopening=bool(entry.get('no_topup') and entry['no_topup'].get('action')!='reopen')
            reason,ok=QInputDialog.getText(dialog,'Tiếp tục giao bù' if reopening else 'Không cần giao bù','Món: '+str(items[index].get('item_name',''))+'\nNgười/bộ phận xác nhận và lý do:')
            if not ok:return
            try:
                from receiving_no_topup import decision
                entry['no_topup']=decision(items[index],reason)
                if reopening:entry['no_topup']['action']='reopen'
                for result in rendered_results:
                    if result.get('pr_index')==index:result['no_topup']=entry['no_topup']
                dialog.refresh_no_topup(index)
            except ValueError as exc:QMessageBox.warning(dialog,'Chưa xác nhận',str(exc))
        dialog.no_topup=no_topup
        self.pr_compare_table=table
        from rec_pr_compare_layout import install as install_compare_layout
        install_compare_layout(self,dialog,table,rendered_results,items,prior_count,order_choice,only_review,expanded,
            [manual_button,convert_button,pack_button,correction_button,price_button,overreceipt_button],save_button,record,detail,vocabulary_status,vocabulary_apply)
        from copy import deepcopy
        dialog.comparison_state=lambda:deepcopy(dict(items=items,images=image_hashes,links=links,conversions=conversions,results=rendered_results))
        dialog.setUpdatesEnabled(True);dialog.update()
    def reference_link_path(self):
        refs = invoice_images(self.current_sheet, self.data_by_sheet.get(self.current_sheet, []))
        identities = sorted((image_name(p), source_digest(p)) for p in self.images if image_name(p) in refs)
        if not identities or not self.folder: raise ValueError('Chọn phiếu có ảnh nguồn trước khi ghép PR.')
        key = hashlib.sha256(json.dumps(identities).encode()).hexdigest()
        stable = self.folder / '.receiving' / 'manual-pr-links' / (key + '.json')
        if stable.exists(): return stable
        # Retain links created during the transition to archive storage.
        current = sorted((image_name(p), digest(p)) for p in self.images if image_name(p) in refs)
        alternate = stable.with_name(hashlib.sha256(json.dumps(current).encode()).hexdigest()+'.json')
        return alternate if alternate.exists() else stable

    def receipt_references(self):
        try:
            path = self.reference_link_path()
            if not path.exists(): return []
            data = json.loads(path.read_text(encoding='utf-8'))
            if data.get('source')=='pr-library':
                from receiving_pr_library import load,images_for
                record=load(self.pr_library_directory()).get(data.get('library_key'))
                if not record or record['images']!=data.get('paths'):return []
                return images_for(record)
            saved={image_name(name):key for name,key in data.get('images', {}).items()}
            return [p for p in self.images if image_name(p) in saved and (saved[image_name(p)]==source_digest(p) or saved[image_name(p)]==digest(p))]
        except (OSError, ValueError, TypeError):
            return []

    def save_receipt_references(self, selected, *, expected=None):
        allowed = [p for p in self.images if not self.image_to_sheets.get(image_name(p))]
        if any(p not in allowed for p in selected): raise ValueError('Ảnh PR không còn trong danh sách ảnh kèm theo.')
        from rec_pr_link_write import write_link
        write_link(self.reference_link_path(), {'version': 1, 'source': 'manual', 'sheet': self.current_sheet,
                    'images': {image_name(p): source_digest(p) for p in selected}},expected=expected,action='confirmed-manual-selection')

    def pr_image_owners(self):
        owners = {}
        hashes = {image_name(p): source_digest(p) for p in self.images}
        for sheet, rows in self.data_by_sheet.items():
            refs = invoice_images(sheet, rows)
            identities = sorted((name, hashes[name]) for name in refs if name in hashes)
            if not identities: continue
            key = hashlib.sha256(json.dumps(identities).encode()).hexdigest()
            path = self.folder / '.receiving' / 'manual-pr-links' / (key + '.json')
            if not path.exists():
                current=sorted((image_name(p),digest(p)) for p in self.images if image_name(p) in refs)
                path=path.with_name(hashlib.sha256(json.dumps(current).encode()).hexdigest()+'.json')
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                for name, image_hash in data.get('images', {}).items():
                    if any(image_name(p)==image_name(name) and image_hash in (source_digest(p),digest(p)) for p in self.images):
                        owners.setdefault(image_name(name), []).append(sheet)
            except (OSError, ValueError, TypeError, AttributeError): pass
        return owners

    def choose_receipt_references(self):
        if not self.current_sheet:
            QMessageBox.information(self, 'Chưa chọn phiếu', 'Chọn phiếu cần ghép PR trước.'); return
        dialog = QDialog(self); dialog.setWindowTitle('Ghép PR · ' + self.current_sheet); dialog.resize(1100, 780)
        use_saved=Button('Chọn PR đã lưu / đang giao dở');use_saved.setObjectName('chooseSavedPR')
        def saved_pr():
            dialog.reject()
            QTimer.singleShot(0,lambda:__import__('rec_pr_assign_picker').show(self))
        use_saved.clicked.connect(saved_pr)

        layout = QVBoxLayout(dialog)
        heading = QLabel('Chọn PR cho phiếu ' + self.current_sheet); heading.setObjectName('section'); layout.addWidget(heading)
        hint = QLabel('Bấm tên để xem ảnh · Tích ô để ghép PR · Bỏ tích để gỡ'); hint.setObjectName('muted'); layout.addWidget(hint)
        layout.addWidget(use_saved)
        split = QSplitter(Qt.Horizontal); split.setChildrenCollapsible(False); layout.addWidget(split, 1)
        listing = QListWidget(); listing.setMinimumWidth(220); split.addWidget(listing)
        listing.setSelectionMode(QAbstractItemView.SingleSelection)
        panel = QWidget(); panel_layout = QVBoxLayout(panel); panel_layout.setContentsMargins(0, 0, 0, 0)
        preview = PreviewView(); panel_layout.addWidget(preview, 1)
        bar = QHBoxLayout()
        for title, callback in [('−', lambda: preview.zoom_at(1/1.2)), ('+', lambda: preview.zoom_at(1.2)), ('Xem toàn ảnh', preview.fit_image)]:
            button = QPushButton(title); button.clicked.connect(callback); bar.addWidget(button)
        panel_layout.addLayout(bar); split.addWidget(panel); split.setSizes([260, 800])
        selected = self.receipt_references()
        selection_path=self.reference_link_path()
        selection_before=selection_path.read_bytes() if selection_path.exists() else None
        selection_context=(self.current_sheet,str(self.report),self.source_hash)
        owners = self.pr_image_owners()
        linked_note = QLabel(); linked_note.setWordWrap(True); linked_note.setObjectName('warning')
        panel_layout.insertWidget(0, linked_note)
        for path in self.images:
            if self.image_to_sheets.get(image_name(path)): continue
            linked = owners.get(image_name(path), [])
            text = path.name + ('\nĐã ghép: ' + ', '.join(linked) if linked else '\nCHƯA GHÉP')
            item = QListWidgetItem(text); item.setData(Qt.UserRole, str(path))
            font = item.font(); font.setBold(not linked); item.setFont(font)
            item.setForeground(QColor('#8290a3' if linked else '#174ea6'))
            item.setBackground(QColor('#f6f7f9' if linked else '#edf4ff'))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if path in selected else Qt.Unchecked)
            listing.addItem(item)
        def show_image(item, old):
            if not item: return
            path = Path(item.data(Qt.UserRole)); preview.set_image(path)
            linked = owners.get(image_name(path), [])
            linked_note.setText('PR đã ghép với phiếu: ' + ', '.join(linked) if linked else 'PR chưa được ghép với phiếu nào.')
        listing.currentItemChanged.connect(show_image)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('Lưu ghép PR'); buttons.button(QDialogButtonBox.Save).setObjectName('primary')
        buttons.button(QDialogButtonBox.Cancel).setText('Hủy')
        count = QLabel(); count.setObjectName('section')
        def update_count():
            count.setText(f"Đã chọn {sum(listing.item(i).checkState() == Qt.Checked for i in range(listing.count()))} ảnh PR")
        listing.itemChanged.connect(update_count); update_count(); layout.addWidget(count)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        if listing.count():
            first = next((listing.item(i) for i in range(listing.count()) if listing.item(i).checkState() == Qt.Checked), listing.item(0))
            listing.setCurrentItem(first)
        from rec_pr_images_layout import arrange_images
        arrange_images(dialog,listing,panel,preview,use_saved,buttons,count,owners,self)
        if dialog.exec() == QDialog.Accepted:
            try:
                chosen = [Path(listing.item(i).data(Qt.UserRole)) for i in range(listing.count()) if listing.item(i).checkState() == Qt.Checked]
                if selection_context!=(self.current_sheet,str(self.report),self.source_hash) or self.reference_link_path()!=selection_path:
                    raise ValueError('Phiếu đang chọn đã đổi. Mở lại cửa sổ ghép PR.')
                if set(chosen)==set(selected):
                    preview.pool.waitForDone();return
                if selection_before is not None:
                    answer=QMessageBox.question(self,'Thay PR đã gán?','Bạn đang thay bộ PR của phiếu '+self.current_sheet+'. Bản đối chiếu đã duyệt có thể cần rà lại. Tiếp tục?',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
                    if answer!=QMessageBox.Yes:
                        preview.pool.waitForDone();return
                self.save_receipt_references(chosen,expected=selection_before)
                if self.reference_mode: self.toggle_reference_images()
                self.reference_image = None
                self.statusBar().showMessage(f'Đã lưu liên kết {len(chosen)} ảnh PR cho {self.current_sheet}.')
            except Exception as exc: QMessageBox.warning(self, 'Chưa lưu ghép PR', str(exc))
        preview.pool.waitForDone() if hasattr(preview, 'pool') else None

    def toggle_reference_images(self):
        if self.reference_mode:
            self.reference_mode = False
            self.reference_toggle.setText('PR')
            self.current_image = self.receipt_image
            self.select_sheet(self.current_sheet)
            return
        candidates = self.receipt_references()
        if not candidates:
            self.choose_receipt_references()
            candidates = self.receipt_references()
            if not candidates: return
        self.receipt_image = self.current_image
        self.reference_mode = True
        self.reference_toggle.setText('Phiếu giao hàng')
        self.clear_row_region()
        self.page_combo.blockSignals(True); self.page_combo.clear()
        for i, path in enumerate(candidates, 1):
            self.page_combo.addItem(f'PR {i}/{len(candidates)} · {path.name}', str(path))
        selected = self.reference_image if self.reference_image in candidates else candidates[0]
        self.page_combo.setCurrentIndex(candidates.index(selected))
        self.page_combo.blockSignals(False); self.page_combo.hide();self.page_arrows.sync()
        self.reference_image = selected; self.current_image = selected
        if hasattr(self,"sync_source_page"):self.sync_source_page()
        self.preview.set_image(selected)
        self.region_title.setText('Đây là ảnh PR đã ghép với phiếu đang kiểm tra.')

    def select_page(self, index):
        path = self.page_combo.itemData(index)
        if not path: return
        if self.reference_mode:
            self.reference_image = Path(path); self.current_image = Path(path)
            self.preview.set_image(Path(path)); return
        for i, image in enumerate(self.images):
            if str(image) == path:
                self.select_image(i); return

    def select_image(self, index: int):
        if index < 0 or index >= len(self.images):
            return
        image = self.images[index]
        matches = self.image_to_sheets.get(image_name(image), [])
        if not matches and self.current_sheet:
            self.choose_receipt_references(); return
        self.current_image = image
        if len(matches) == 1:
            self.select_sheet(matches[0])
            self.image_list.blockSignals(True); self.image_list.setCurrentRow(index); self.image_list.blockSignals(False)
        elif self.current_sheet not in matches:
            self.select_sheet("")
            self.image_list.blockSignals(True); self.image_list.setCurrentRow(index); self.image_list.blockSignals(False)
            self.statusBar().showMessage("Ảnh chưa liên kết duy nhất với phiếu; bảng để trống để tránh rà nhầm.")
        self.current_image = image; self.preview.set_image(image)

    def refresh_table(self):
        rows = self.data_by_sheet.get(self.current_sheet, [])
        model: ReceiptTableModel = self.table.model()
        model.set_rows(rows, self.show_all.isChecked())
        self.update_numeric_flags()
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.ElideNone)
        for column, header in enumerate(model.visible):
            width = 240 if header in {"Tên hàng trên phiếu (Ảnh)", "Tên chuẩn hệ thống", "Ghi chú"} else (45 if header == "STT trên phiếu" else (80 if header in {"Số lượng", "Thực nhận", "Đơn vị tính"} else 120))
            self.table.setColumnWidth(column, width)
        self.table.resizeRowsToContents()
        for row in range(model.rowCount()):
            self.table.setRowHeight(row, max(48, min(96, self.table.rowHeight(row))))
        first = rows[0][1] if rows else {}
        supplier = str(first.get("Nhà cung cấp") or self.current_sheet or "Chưa chọn phiếu")
        received = str(first.get("Ngày nhận hàng xác nhận") or first.get("Ngày giao hàng") or "")
        self.invoice_meta.setText(supplier + (f"  ·  {received}" if received else ""))
        info = []
        for header, label in [("Ngày giao hàng", "Ngày giao"), ("Ngày nhận hàng xác nhận", "Ngày nhận"), ("Mã kho", "Kho"), ("Bộ phận", "Bộ phận")]:
            values = list(dict.fromkeys(str(v.get(header)) for _, v in rows if v.get(header) is not None and str(v.get(header)).strip()))
            info.append(label + ": " + (", ".join(values) if values else "Chưa có"))
        self.details.setText("   ·   ".join(info) + (f"\n{len(rows)} dòng" if rows else ""))
        self.review_label.setText("Đã kiểm tra" if self.approved(self.current_sheet) else "Chưa kiểm tra")
        self.approve_button.setText('Bỏ xác nhận' if self.approved(self.current_sheet) else 'Xác nhận')
        self.review_label.setObjectName("ok" if self.approved(self.current_sheet) else "warning")
        self.review_label.style().unpolish(self.review_label); self.review_label.style().polish(self.review_label)
        pending = sum(not self.approved(name) for name in self.sheet_names)
        self.next_step.setText(f'Còn {pending} phiếu chưa kiểm tra. Rà và xác nhận từng phiếu trước khi xuất ngày.' if pending else 'Tất cả phiếu đã kiểm tra. Bấm Xuất phiếu giao hàng.xlsx để tạo file gửi.')
        amounts = [v.get("Thành tiền") for _, v in display_rows(rows)]
        total = sum(amounts) if amounts and all(isinstance(v, (int, float)) for v in amounts) else None
        self.total_label.setText((f"Tổng tiền: {total:,.0f} đ" if total is not None else "Tổng tiền: chưa đủ dữ liệu") if rows else "")
        paper_values = [v.get('Tổng tiền trên phiếu (Số lượng × Đơn giá)') for _, v in model.rows]
        paper_values = [v for v in paper_values if v is not None and v != '']
        paper_total = paper_values[0] if paper_values and all(isinstance(v, (int,float)) and v == paper_values[0] for v in paper_values) else None
        self.paper_total_label.setText((f'Tổng trên phiếu: {paper_total:,.0f} đ' if paper_total is not None else 'Tổng trên phiếu: chưa đủ dữ liệu') if rows else '')
        if self.row_to_restore is not None:
            for i, (row, _) in enumerate(rows):
                if row == self.row_to_restore: self.table.selectRow(i); break
            self.row_to_restore = None
        self.table.viewport().update()
        if rows and self.table.currentIndex().isValid():
            self.row_selected(self.table.currentIndex(), QModelIndex())
        else:
            self.row_detail.clear();self.row_detail.hide()

    def build_row_menu(self,pos):
        index=self.table.indexAt(pos)
        if index.isValid():self.table.setCurrentIndex(index)
        menu=QMenu(self)
        valid=index.isValid() and not self.busy
        for label,callback in [('Sửa dòng',self.edit_current),('Tra mã cho dòng',self.lookup_code),('Xóa dòng',self.delete_current_row)]:
            action=menu.addAction(label);action.setEnabled(valid);action.triggered.connect(callback)
        menu.addSeparator()
        action=menu.addAction('Gán bộ phận cho cả phiếu…')
        action.setEnabled(bool(self.current_sheet) and not self.busy);action.triggered.connect(self.assign_invoice_department)
        action=menu.addAction('Không có PR/PO — theo dõi thủ công…');action.setEnabled(bool(self.current_sheet) and not self.busy);action.triggered.connect(self.toggle_no_po)
        action=menu.addAction('Đặt tên NCC ngắn gọn…');action.setEnabled(bool(self.current_sheet) and not self.busy);action.triggered.connect(self.edit_supplier_nickname)
        action=menu.addAction('Đổi NCC cho cả phiếu…');action.setEnabled(bool(self.current_sheet) and not self.busy);action.triggered.connect(self.assign_invoice_supplier)
        return menu

    def show_row_menu(self,pos):
        menu=self.build_row_menu(pos)
        menu.exec(self.table.viewport().mapToGlobal(pos));menu.deleteLater()

    def open_department(self, index):
        if not self.busy and index.isValid() and self.table.model().visible[index.column()] == 'Bộ phận':
            self.table.edit(index)

    def clear_row_region(self):
        self.preview.set_focus_region()
        self.location_request += 1
        self.region_scene.clear(); self.region_view.hide()
        self.region_qimage=None; self.region_expand.setEnabled(False)
        self.region_view.setFixedHeight(96)
        self.region_title.setText('Chọn một dòng để xem vùng ảnh đối chiếu.')
        if hasattr(self,'row_region_dialog'):self.row_region_dialog.hide()

    def row_selected(self, current, previous):
        if hasattr(self,'row_region_dialog'):self.row_region_dialog.hide()
        if not current.isValid():
            self.clear_row_region(); return
        values = self.table.model().row_values(current.row())
        self.location_request += 1
        self.region_view.hide()
        self.region_expand.setEnabled(False); self.region_qimage=None
        self.region_view.setFixedHeight(96)
        reasons=self.numeric_flags.get(self.table.model().source_row(current.row()),[])
        self.row_detail.setText('Cần kiểm: ' + '; '.join(reasons) if reasons else '');self.row_detail.setVisible(bool(reasons))
        if self.reference_mode: return
        ref = Path(str(values.get("Ảnh nguồn") or "")).name.casefold()
        ref=image_name(ref)
        matches = [p for p in self.images if image_name(p) == ref]
        if len(matches) == 1:
            self.current_image = matches[0]
            self.image_list.blockSignals(True); self.image_list.setCurrentRow(self.images.index(matches[0])); self.image_list.blockSignals(False)
            self.preview.set_image(matches[0])
            self.preview.set_focus_region()
        else:
            self.region_title.setText('Không xác định được một ảnh nguồn duy nhất cho dòng này; chọn trang để đối chiếu.')

    def update_numeric_flags(self):
        self.numeric_flags=numeric_issues(self.data_by_sheet.get(self.current_sheet,[]),self.catalog)
        self.table.model().review_issues=self.numeric_flags
        if hasattr(self,'only_numbers'): self.apply_number_filter()

    def apply_number_filter(self):
        model=self.table.model()
        count=sum(bool(reasons) for reasons in self.numeric_flags.values())
        from rec_receipt_search import normalize
        search=getattr(self,'receipt_item_search',None)
        terms=normalize(search.text() if search is not None else '').split()
        shown=[]
        for i,(row,values) in enumerate(model.rows):
            text=normalize(' '.join(str(values.get(k) or '') for k in ('Tên hàng trên phiếu (Ảnh)','Tên chuẩn hệ thống','Mã vật tư')))
            hidden=(self.only_numbers.isChecked() and not self.numeric_flags.get(row)) or not all(term in text for term in terms)
            self.table.setRowHidden(i,hidden)
            if not hidden:shown.append(i)
        label=getattr(self,'receipt_item_count',None)
        if label is not None:label.setText(f'{len(shown)} / {model.rowCount()} dòng')
        if terms and self.table.currentIndex().row() not in shown:
            self.table.clearSelection();self.table.setCurrentIndex(QModelIndex())
            if shown:self.table.setCurrentIndex(model.index(shown[0],0))
        self.number_summary.setText(f'{count}/{model.rowCount()}')
        self.number_summary.setToolTip(f'{count} trên {model.rowCount()} dòng cần kiểm tra số liệu')
        self.next_number.setEnabled(any(self.numeric_flags.get(r) and not self.table.isRowHidden(i) for i,(r,_) in enumerate(model.rows)))

    def next_numeric_row(self):
        model=self.table.model(); start=self.table.currentIndex().row()
        candidates=[i for i,(r,_) in enumerate(model.rows) if self.numeric_flags.get(r) and not self.table.isRowHidden(i)]
        if not candidates: return
        row=next((i for i in candidates if i>start),candidates[0])
        column=model.visible.index('Thực nhận') if 'Thực nhận' in model.visible else 0
        index=model.index(row,column); self.table.setCurrentIndex(index); self.table.scrollTo(index,QAbstractItemView.PositionAtCenter)

    def locate_current_row(self, path, values):
        if not self.local_review_enabled: return
        from receiving_locations import initial_region
        match = initial_region(path,self.folder,values)
        if match is not None:
            self.show_row_region(path,values,{'initial_match':match},self.location_request);return
        stat=path.stat(); key=(str(path),stat.st_mtime_ns,stat.st_size)
        token=self.location_request
        if key in self.location_data:
            self.show_row_region(path,values,self.location_data[key],token); return
        if key in self.location_failures:
            self.region_title.setText('Chưa định vị được dòng trên trang này. Rà ảnh đầy đủ; số liệu không bị đổi.'); return
        self.region_title.setText('Đang dò vị trí dòng bằng OCR cục bộ… Lần đầu đang khởi động bộ nhận chữ trên máy.')
        if key in self.location_pending and self.location_process is not None and getattr(self.location_process,'location_key',None)==key: return
        if self.location_process is not None:
            # A newly selected page supersedes the old request. Keep OCR in an
            # isolated helper so imports/CPU work cannot block the GUI or close.
            self.location_process.kill()
        process=QProcess(self); self.location_process=process; process.location_key=key
        self.location_pending.add(key)
        def located(data):
            now=path.stat()
            if (str(path),now.st_mtime_ns,now.st_size)!=key: return
            self.location_data[key]=data
            while len(self.location_data)>3: self.location_data.popitem(last=False)
            current=self.table.currentIndex()
            if not current.isValid(): return
            selected=self.table.model().row_values(current.row())
            ref=Path(str(selected.get('Ảnh nguồn') or '')).name.casefold()
            ref=image_name(ref)
            if ref==image_name(path) and self.current_image==path:
                self.show_row_region(path,selected,data,self.location_request)
        def failed():
            self.location_failures.add(key)
            if self.current_image==path:
                self.region_title.setText('Chưa định vị được dòng bằng OCR cục bộ. Dùng ảnh đầy đủ để rà; số liệu không bị đổi.')
        def done(code):
            self.location_pending.discard(key)
            if self.location_process is not process:
                process.deleteLater(); return
            self.location_process=None
            try:
                if code!=0: raise ValueError('Local OCR failed')
                located(json.loads(bytes(process.readAllStandardOutput()).decode('utf-8')))
            except (ValueError,OSError): failed()
            process.deleteLater()
        from rec_runtime import process_command
        program,arguments=process_command('locate',[path,self.folder/'row-locations'],self.root)
        process.setProgram(program);process.setArguments(arguments)
        process.finished.connect(lambda code,status: done(code))
        process.errorOccurred.connect(lambda error: done(1) if error==QProcess.FailedToStart else None)
        timeout=QTimer(process); timeout.setSingleShot(True); timeout.setInterval(120000)
        timeout.timeout.connect(process.kill); process.started.connect(timeout.start)
        process.start()

    def show_row_region(self,path,values,data,token):
        if not self.local_review_enabled:return
        if token!=self.location_request:return
        if not hasattr(self,'region_render_cache'):self.region_render_cache=OrderedDict()
        # Use bytes, not timestamp alone: cached UI must refer to this exact image.
        content_hash=hashlib.sha256(Path(path).read_bytes()).digest()
        render_key=(content_hash,str(values.get('Tên hàng trên phiếu (Ảnh)')),str(values.get('STT trên phiếu') or ''),json.dumps(data,sort_keys=True,ensure_ascii=False))
        cached=self.region_render_cache.get(render_key)
        if cached is not None:
            self.region_render_cache.move_to_end(render_key)
            match,qimage=cached
            self.preview.set_focus_region(path,match['box'])
            self.region_qimage=qimage;self.region_expand.setEnabled(True)
            self.region_title.setText(f'Vùng gợi ý “{match["text"]}” · Kiểm đúng dòng trước khi đọc số.')
            self.open_region_dialog(qimage);return
        match=data.get('initial_match') or choose_region(data['words'],values.get('Tên hàng trên phiếu (Ảnh)'),data['size'],with_anchor=True)
        if match is None:
            self.preview.set_focus_region();self.region_scene.clear()
            self.region_title.setText('Chưa định vị chắc chắn tên hàng. Rà ảnh đầy đủ.');return
        # Display the selected row from the already loaded page immediately.
        # The original-resolution straightened crop replaces it atomically later.
        self.preview.set_focus_region(path,match['box'])
        rect=self.preview.focus_rect()
        if rect is not None and self.preview.item is not None:
            immediate=self.preview.item.pixmap().copy(rect.toAlignedRect()).toImage()
            if not immediate.isNull():
                self.region_qimage=immediate
                self.open_region_dialog(immediate)
        else:
            self.region_scene.clear()  # never leave an unrelated row on screen
        self.region_title.setText('Đang chuẩn bị vùng ảnh của dòng đã chọn…')
        # Coalesce rapid clicks; CPU/image IO never run on the GUI thread.
        if not hasattr(self,'region_pool'):
            self.region_pool=QThreadPool(self);self.region_pool.setMaxThreadCount(1)
        folder=self.folder
        def prepare():
            if token!=self.location_request:return None
            match=data.get('initial_match') or choose_region(data['words'],values.get('Tên hàng trên phiếu (Ảnh)'),data['size'],with_anchor=True)
            if match is None:return (None,None)
            image=crop_region(path,match['box'],match['anchor'])
            if token!=self.location_request:return None
            image.thumbnail((1800,500))
            qimage=QImage(image.tobytes('raw','RGB'),image.width,image.height,image.width*3,QImage.Format_RGB888).copy()
            if 'initial_match' not in data:
                from receiving_locations import save_verified_region
                try:save_verified_region(path,folder,values,match,data['size'])
                except OSError:pass
            return match,qimage
        def display(result):
            if token!=self.location_request or result is None:return
            match,qimage=result
            if match is None:
                self.region_title.setText('Chưa định vị chắc chắn tên hàng. Rà ảnh đầy đủ.');return
            self.region_render_cache[render_key]=(match,qimage)
            while len(self.region_render_cache)>24 or sum(im.sizeInBytes() for _,im in self.region_render_cache.values())>16*1024*1024:
                self.region_render_cache.popitem(last=False)
            self.preview.set_focus_region(path,match['box'])
            self.region_qimage=qimage;self.region_expand.setEnabled(True)
            self.region_title.setText(f'Vùng gợi ý “{match["text"]}” · Kiểm đúng dòng trước khi đọc số.')
            self.open_region_dialog(qimage)
        def launch():
            if token!=self.location_request:return
            job=Worker(prepare);self._workers.append(job)
            job.signals.result.connect(display)
            job.signals.error.connect(lambda _:self.region_title.setText('Chưa mở được vùng ảnh; chọn lại để thử.') if token==self.location_request else None)
            job.signals.finished.connect(lambda:self._workers.remove(job) if job in self._workers else None)
            self.region_pool.start(job)
        QTimer.singleShot(0,launch)

    def open_region_dialog(self,qimage):
        if not self.local_review_enabled:return
        # Replace pixels in-place instead of clear/add (which painted a blank frame).
        self.region_view.setUpdatesEnabled(False)
        try:
            item=getattr(self,'region_pixmap_item',None)
            if item is None or item not in self.region_scene.items():
                self.region_scene.clear()
                item=self.region_scene.addPixmap(QPixmap.fromImage(qimage))
                self.region_pixmap_item=item
            else:item.setPixmap(QPixmap.fromImage(qimage))
            self.region_scene.setSceneRect(item.boundingRect())
            self.region_view.show();self.region_view.resetTransform()
            self.region_view.fitInView(item,Qt.KeepAspectRatio)
            current=self.region_view.transform().m11()
            factor=min(1.2,max(1.,(self.region_view.viewport().height()-4)/max(1,qimage.height()*current)))
            self.region_view.scale(factor,factor)
        finally:self.region_view.setUpdatesEnabled(True)

    def add_images(self):
        if self.busy or self.inbox_toggle.isChecked():return
        files, _ = QFileDialog.getOpenFileNames(self, "Chọn ảnh phiếu giao của ngày đang làm", "", "Ảnh (*.jpg *.jpeg *.png *.webp *.heic *.heif)")
        if not files:
            return
        try:
            added = import_images(self.root, self.day, files, self.destination)
            self.statusBar().showMessage(f"Đã thêm {len(added)} ảnh; ảnh trùng nội dung được bỏ qua.")
            self.open_day()
        except Exception as exc:
            QMessageBox.warning(self, "Chưa thêm ảnh", str(exc))

    def choose_destination(self):
        if self.portable_workspace:
            return
        selected = QFileDialog.getExistingDirectory(self, "Chọn thư mục Phieu giao hang hang thang", str(self.destination))
        if selected:
            self.destination = accounting_root(selected)
            save_settings(self.root, str(self.destination))
            if hasattr(self,'settings_destination'):self.settings_destination.setText(str(self.destination))
            self.open_day()

    def read_images(self, automatic=False):
        automatic=automatic is True
        selection=getattr(self,'_workspace_read_selection',None) if not automatic else None
        if self.busy or (not automatic and self.inbox_toggle.isChecked()):return
        self._automatic_read=automatic
        if not automatic and not (selection if selection is not None else self.images):
            QMessageBox.information(self, "Chưa có ảnh", "Thêm ảnh vào ngày đang làm trước.")
            return
        answer = QMessageBox.Yes if automatic else QMessageBox.question(self, "Đọc ảnh qua Gemini", f"Đọc {len(selection if selection is not None else self.images)} ảnh trong ngày {self.day:%d/%m/%Y}. Ảnh chưa có kết quả đọc đã lưu có thể được gửi đến Gemini và tính phí. Tiếp tục?")
        if answer != QMessageBox.Yes:
            return
        worker_script = Path(__file__).with_name("receiving_app.py")
        if not getattr(sys,"frozen",False) and not worker_script.exists():
            QMessageBox.warning(self, "Thiếu bộ xử lý", f"Không tìm thấy {worker_script}. Cài bản Qt vào Auto trước khi đọc ảnh.")
            return
        self.set_busy(True, "Đang đọc ảnh; kết quả đã có vẫn được giữ nếu lượt này lỗi…")
        self.read_progress.start(len(selection if selection is not None else self.images))
        if hasattr(self,'workspace_reading'):
            self.progress_toggle.hide()
        else:
            self.progress_toggle.show(); self.progress_toggle.setChecked(True)
        self._log_decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.log.clear()
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.setWorkingDirectory(str(self.root))
        from rec_runtime import process_command
        program,arguments=process_command('worker',[self.day.isoformat(),str(self.destination)]+(['--auto'] if automatic else []),self.root)
        if selection is not None:
            from PySide6.QtCore import QProcessEnvironment
            from receiving_service import digest
            import json
            env=QProcessEnvironment.systemEnvironment()
            env.insert('REC_SELECTED_IMAGE_HASHES',json.dumps(sorted({digest(p) for p in selection})))
            self.process.setProcessEnvironment(env)
        self.process.setProgram(program);self.process.setArguments(arguments)
        self.process.readyReadStandardOutput.connect(self._read_log)
        self.process.finished.connect(lambda *_: self._read_finished())
        self.process.errorOccurred.connect(self._process_error)
        self.process.start()

    def toggle_read_progress(self, show):
        self.read_stack.setCurrentIndex(1 if show else 0)
        self.progress_toggle.setText('Xem bảng kết quả' if show else 'Xem tiến độ đọc')
        self.row_detail.setVisible(not show)
        self.total_label.setVisible(not show); self.paper_total_label.setVisible(not show)

    def _read_log(self):
        if self.process is None: return
        text = self._log_decoder.decode(bytes(self.process.readAllStandardOutput()))
        self.read_progress.consume(text)
        if text.strip():
            self.log.appendPlainText(text.rstrip())
            self.statusBar().showMessage(text.strip().splitlines()[-1][:240])

    def _process_error(self, error):
        if error == QProcess.FailedToStart:
            self.pending_status = "Không khởi động được bộ đọc ảnh. Kiểm tra Python và mở lại ứng dụng."
            self.read_progress.consume(self.pending_status + '\n'); self.read_progress.finish(1)
            self.process = None; self.set_busy(False); self._pause_inbox("Không khởi động được bộ đọc ảnh; tự động đã tắt."); self.open_day()

    def _read_finished(self):
        if self.process is None: return
        self._read_log()
        self.read_progress.consume(self._log_decoder.decode(b'', final=True))
        code = self.process.exitCode() if self.process else 1
        self.read_progress.finish(code)
        self.process = None; self.set_busy(False)
        if getattr(self,'_automatic_read',False):
            if code==0:
                try:self.inbox.finish(day=self.day.isoformat(),report=str(self.report));self.inbox_status.setText('Đã lưu bảng chờ kiểm tra; đang chờ ảnh mới')
                except OSError:self._pause_inbox('Không lưu được trạng thái nhận ảnh. Kiểm tra quyền ghi trước khi bật lại.')
            else:self._pause_inbox('Đọc ảnh chưa xong — đã tạm dừng. Xem nhật ký, xử lý lỗi rồi bật lại để thử tiếp.')
        self.pending_status = "Đọc xong; rà kết quả trước khi xuất." if code == 0 else "Chưa đọc xong; kết quả đã lưu vẫn giữ. Xem nhật ký rồi chạy tiếp."
        if code == 0 and not self.read_progress.errors:
            self.progress_toggle.setChecked(False)
        if getattr(self,'_automatic_read',False):
            from rec_read_result import show_result
            self._open_review_after_load=show_result(self,code)
        self.open_day()

    def approve(self):
        if self.busy: return
        if not self.current_sheet or not self.report:
            QMessageBox.information(self, "Chưa chọn phiếu", "Chọn một phiếu có dữ liệu trước."); return
        if digest(self.report) != self.source_hash:
            QMessageBox.warning(self, "Excel đã thay đổi", "Bấm Tải lại Excel rồi kiểm tra dữ liệu mới nhất."); return
        undo = self.approved(self.current_sheet)
        if not undo:
            from rec_department_guard import department_message
            message=department_message(self.data_by_sheet.get(self.current_sheet,[]))
            if message:
                QMessageBox.warning(self,'Chưa chọn bộ phận',message);return
        if not undo:
            from rec_missing_source import missing,refresh
            if missing(self):
                refresh(self);self.main_pages.setCurrentWidget(self.receipt_page)
                return
        prompt = f'Bỏ xác nhận {self.current_sheet} để rà lại? Phiếu sẽ cần xác nhận lại trước khi xuất.' if undo else f"Đã kiểm tra đủ tên, mã, đơn vị, giá, ngày và số thực nhận của {self.current_sheet}?\n\nThao tác này không xuất Excel."
        from rec_review_dialogs import confirm_review
        if confirm_review(self,self.current_sheet,self.data_by_sheet.get(self.current_sheet,[]),undo)!=QMessageBox.Yes:
            return
        try:
            reviewed_sheet = self.current_sheet
            if not undo:
                from rec_department_guard import require_departments
                require_departments(self.data_by_sheet.get(reviewed_sheet,[]))
                if digest(self.report)!=self.source_hash:raise ValueError('Báo cáo đã đổi. Tải lại trước khi xác nhận.')
            reviews = dict(self.reviews)
            if undo: reviews.pop(reviewed_sheet, None)
            else: reviews[reviewed_sheet] = self.signatures[reviewed_sheet]
            atomic_json(self.folder / "reviewed.json", reviews)
            self.reviews = reviews
            if undo:__import__('rec_auto_sheets').start(self)
            self.filter_receipts()
            self.refresh_table()
            self.summary.setText(f'{len(self.images)} ảnh · {len(self.data)} phiếu · {sum(self.approved(n) for n,_ in self.data)} đã kiểm')
            pending = sum(not self.approved(name) for name in self.sheet_names)
            self.statusBar().showMessage(f'Đã bỏ xác nhận {reviewed_sheet}. Cần rà và xác nhận lại trước khi xuất.' if undo else (f'Đã xác nhận {reviewed_sheet}. Còn {pending} phiếu cần kiểm tra.' if pending else 'Đã kiểm tra tất cả phiếu. Bấm Xuất phiếu giao hàng.xlsx.'))
        except Exception as exc:
            QMessageBox.warning(self, "Chưa xác nhận", str(exc))

    def edit_current(self):
        if self.busy: return
        index = self.table.currentIndex()
        if not index.isValid() or not self.report:
            QMessageBox.information(self, "Chưa chọn dòng", "Chọn một dòng trong bảng trước."); return
        model: ReceiptTableModel = self.table.model(); source_row = model.source_row(index.row()); original = model.row_values(index.row())
        try: dialog = EditDialog(original, self)
        except Exception as exc:
            QMessageBox.warning(self, 'Không đọc được danh mục kho', str(exc)); return
        if dialog.exec() != QDialog.Accepted:
            return
        changes = dialog.changes(original)
        if not changes:
            return
        self.save_row_changes((source_row, changes))

    def save_row_changes(self, payload):
        if self.busy: return
        source_row, changes = payload
        if not self.report or not self.current_sheet:
            return
        report, expected, sheet = self.report, self.source_hash, self.current_sheet
        def save():
            import AutoWatcher as aw
            if 'Mã vật tư' in changes and self.catalog is None:
                self.catalog, _ = aw.load_catalog_data(self.root / "DanhMuc.xlsm")
            edit_row(report, expected, sheet, source_row, changes, self.catalog or {},
                     self.get_warehouses() if 'Mã kho' in changes else None)
        self.write_in_background(save, source_row)

    def write_in_background(self, operation, row=None):
        if self.busy: return
        from copy import deepcopy
        pr_state=None
        if getattr(self,'pr_sheet',None)==self.current_sheet and hasattr(getattr(self,'pr_panel',None),'comparison_state'):
            if self.pr_dirty() and not self.pr_save_draft():return
            pr_state=self.pr_panel.comparison_state()
        old_rows=deepcopy(self.data_by_sheet.get(self.current_sheet,[]))
        refresh_pr=[False]
        scroll = (self.table.horizontalScrollBar().value(), self.table.verticalScrollBar().value())
        selected = self.table.currentIndex().column()
        sheet = self.current_sheet
        report = self.report
        self.set_busy(True, 'Đang lưu thay đổi…')
        def work():
            operation()
            return snapshot(report)
        def saved(payload):
            source_hash, data = payload
            self.source_hash = source_hash; self.data = data; self.data_by_sheet = dict(data)
            self.signatures = {name: sheet_signature(name,rows) for name,rows in data}
            # Keep other sheets and the image viewport in place; redraw this table only.
            self.current_sheet = sheet
            self.image_to_sheets = {}
            for name, rows in data:
                for ref in invoice_images(name, rows): self.image_to_sheets.setdefault(ref, []).append(name)
            self.refresh_table()
            if row is not None:
                for i,(r,_) in enumerate(self.data_by_sheet.get(sheet,[])):
                    if r == row:
                        self.table.setCurrentIndex(self.table.model().index(i,max(0,selected))); break
            self.table.horizontalScrollBar().setValue(scroll[0]); self.table.verticalScrollBar().setValue(scroll[1])
            for i in range(self.receipt_list.count()):
                item = self.receipt_list.item(i)
                if item.data(Qt.UserRole) == sheet:
                    card = self.receipt_list.itemWidget(item)
                    if card:
                        for label in card.findChildren(QLabel):
                            if label.objectName() in ('checkedChip','pendingChip'):
                                from rec_receipt_check_status import status as check_status
                                text,checked=check_status(self,sheet);label.setText(text);label.setObjectName('checkedChip' if checked else 'pendingChip')
                                label.style().unpolish(label); label.style().polish(label)
                            elif label.objectName() == 'receiptSource':
                                label.setText(f'{sheet} · {len(self.data_by_sheet[sheet])} dòng')
                    break
            self.summary.setText(f'{len(self.images)} ảnh · {len(self.data)} phiếu · {sum(self.approved(n) for n,_ in data)} đã kiểm')
            if self.filter_box.currentText() != 'Tất cả phiếu': self.filter_receipts()
            refresh_pr[0]=pr_state is not None
            self.statusBar().showMessage('Đã lưu. Phiếu này cần xác nhận kiểm tra lại.')
        task=Worker(work); task.signals.result.connect(saved)
        def failed_save(message):
            from rec_feedback_states import show
            show(self,'source-changed' if 'đổi' in message.lower() else 'save-error',message,lambda:self.write_in_background(operation,row))
        task.signals.error.connect(failed_save)
        def finish_save():
            self.set_busy(False)
            if refresh_pr[0] and self.current_sheet==sheet:
                from rec_pr_refresh import rebuild
                rebuild(self,pr_state,old_rows)
        task.signals.finished.connect(finish_save)
        self._start_worker(task)

    def toggle_no_po(self):
        if self.busy or not self.current_sheet or not self._leave_pr():return
        from receiving_no_po import active,set_mode
        rows=self.data_by_sheet.get(self.current_sheet,[])
        from rec_no_po_dialog import choose
        enabled=choose(self,active(self.folder,self.current_sheet,rows,self.images))
        if enabled is None:return
        try:
            if digest(self.report)!=self.source_hash:raise ValueError('Báo cáo đã đổi; tải lại trước khi đánh dấu.')
            set_mode(self.folder,self.current_sheet,rows,self.images,enabled);self.update_pr_status()
            self.statusBar().showMessage('Đã cập nhật chế độ PR/PO. Dữ liệu phiếu và số nhận được giữ nguyên.')
        except (OSError,ValueError) as exc:QMessageBox.warning(self,'Chưa cập nhật',str(exc))

    def edit_supplier_nickname(self):
        if self.busy or not self.current_sheet:return
        suppliers=sorted({str(v.get('Nhà cung cấp') or '').strip() for _,v in self.data_by_sheet.get(self.current_sheet,[]) if v.get('Nhà cung cấp')})
        if len(suppliers)!=1:
            QMessageBox.information(self,'Chọn NCC','Phiếu cần có một NCC duy nhất để đặt tên hiển thị.');return
        from receiving_preferences import nickname,set_nickname
        from rec_fluent_ui import short_supplier
        from PySide6.QtWidgets import QInputDialog
        supplier=suppliers[0]
        label,ok=QInputDialog.getText(self,'Tên NCC ngắn gọn',supplier+'\nTên dùng trên giao diện (để trống để dùng tên tự động):',text=nickname(self.root,supplier) or short_supplier(supplier))
        if not ok:return
        try:
            set_nickname(self.root,supplier,label)
            self.open_day()
        except (OSError,ValueError) as exc:QMessageBox.warning(self,'Chưa lưu tên hiển thị',str(exc))

    def assign_invoice_supplier(self):
        from rec_invoice_assignment import show
        return show(self,'supplier')

    def assign_invoice_department(self):
        from rec_invoice_assignment import show
        return show(self,'warehouse')

    def delete_current_row(self):
        from rec_delete_row_page import show
        return show(self)

    def get_warehouses(self):
        from warehouse_directory import load_warehouse_directory
        catalog=self.root/'DanhMuc.xlsm'; rules=self.root/'NhaCungCap.json'
        signature=tuple((str(path),path.stat().st_mtime_ns,path.stat().st_size) for path in [catalog,rules] if path.exists())
        if self._warehouse_cache is None or self._warehouse_cache[0]!=signature:
            self._warehouse_cache=(signature,load_warehouse_directory(catalog))
        return self._warehouse_cache[1]

    def lookup_code(self):
        if self.busy: return
        if self.catalog is None:
            self.set_busy(True, "Đang tải danh mục ở nền…")
            def load():
                import AutoWatcher as aw
                return aw.load_catalog_data(self.root / "DanhMuc.xlsm")[0]
            def ready(catalog):
                self.catalog = catalog; self.set_busy(False); QTimer.singleShot(0, self.lookup_code)
            task = Worker(load); task.signals.result.connect(ready)
            task.signals.error.connect(lambda message: QMessageBox.warning(self, "Không đọc được danh mục", message))
            task.signals.finished.connect(lambda: self.set_busy(False))
            self._start_worker(task); return
        dialog = QDialog(self); dialog.setWindowTitle("Tra toàn danh mục"); dialog.resize(900, 560)
        layout = QVBoxLayout(dialog); search = QLineEdit(); search.setPlaceholderText("Nhập mã hoặc tên hàng…"); layout.addWidget(search)
        selected_index=self.table.currentIndex()
        selected_row=self.table.model().source_row(selected_index.row()) if selected_index.isValid() else None
        selected_values=self.table.model().row_values(selected_index.row()) if selected_index.isValid() else {}
        query=str(selected_values.get('Tên hàng trên phiếu (Ảnh)') or '')
        hint=QLabel('Gợi ý theo tên trên phiếu; kiểm tra quy cách, thương hiệu và ĐVT trước khi chọn mã.'); hint.setWordWrap(True); hint.setObjectName('muted'); layout.addWidget(hint)
        table = QTableView(); model = CatalogModel(self.catalog, dialog)
        table.setItemDelegate(CleanCellDelegate(table)); table.verticalHeader().hide(); table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setModel(model); table.setSelectionBehavior(QTableView.SelectRows); table.setColumnWidth(1, 600); layout.addWidget(table)
        if query:
            search.setText(query)
            model.beginResetModel(); model.indices=ranked_codes(query,model.entries); model.endResetModel()
            hint.setText(f'{len(model.indices)} ứng viên gợi ý theo tên dòng đang chọn. Có thể sửa từ khóa để tìm toàn danh mục; không tự chọn mã.')
        debounce = QTimer(dialog); debounce.setSingleShot(True); debounce.setInterval(180)
        debounce.timeout.connect(lambda: model.filter(search.text()))
        search.textChanged.connect(lambda _: debounce.start())
        copy = QPushButton("Sao chép mã đã chọn"); layout.addWidget(copy)
        def copy_code():
            index = table.currentIndex()
            if index.isValid(): QApplication.clipboard().setText(str(model.data(model.index(index.row(), 0))))
        copy.clicked.connect(copy_code)
        apply=QPushButton('Dùng mã cho dòng đang chọn'); apply.setObjectName('primary'); apply.setEnabled(selected_row is not None); layout.addWidget(apply)
        def apply_code():
            index=table.currentIndex()
            if not index.isValid() or selected_row is None: return
            code=str(model.data(model.index(index.row(),0)))
            if QMessageBox.question(dialog,'Chọn mã hàng',f'Áp mã {code} cho “{query}”?\nTên chuẩn và ĐVT lấy từ danh mục. Tên trên phiếu giữ nguyên.')!=QMessageBox.Yes: return
            dialog.accept(); self.save_row_changes((selected_row,{'Mã vật tư':code}))
        apply.clicked.connect(apply_code)
        dialog.exec()

    def merge_images(self):
        if self.busy: return
        if not self.report:
            QMessageBox.information(self, "Chưa có báo cáo", "Chọn ngày đã có báo cáo tổng hợp trước."); return
        names = sorted({str(values.get("Ảnh nguồn")) for _, rows in self.data for _, values in rows if values.get("Ảnh nguồn")})
        if len(names) < 2:
            QMessageBox.information(self, "Chưa đủ ảnh", "Cần ít nhất hai ảnh đã có trong báo cáo để ghép cùng một phiếu."); return
        dialog = QDialog(self); dialog.setWindowTitle("Ghép các trang của một phiếu"); dialog.resize(1000, 660)
        layout = QVBoxLayout(dialog); layout.setContentsMargins(24,20,24,20); layout.setSpacing(12)
        hint = QLabel("Tích các ảnh thuộc cùng một phiếu. Kiểm tra số phiếu, ngày và số trang; cùng nhà cung cấp chưa đủ để ghép."); hint.setWordWrap(True); layout.addWidget(hint)
        search=Input();search.setPlaceholderText('Tìm tên ảnh hoặc nhà cung cấp…');layout.addWidget(search)
        panes=QSplitter(Qt.Horizontal);layout.addWidget(panes,1)
        items=QListWidget();items.setObjectName('mergeImages');items.setSelectionMode(QAbstractItemView.SingleSelection);items.setSpacing(4);items.addItems(names);panes.addWidget(items)
        preview_box=QWidget();preview_layout=QVBoxLayout(preview_box);preview_layout.setContentsMargins(12,0,0,0)
        preview=QLabel('Chọn một dòng để xem ảnh');preview.setAlignment(Qt.AlignCenter);preview.setMinimumSize(240,280);preview_layout.addWidget(preview,1)
        preview_name=QLabel();preview_name.setWordWrap(True);preview_layout.addWidget(preview_name)
        chosen=QLabel('Chưa chọn ảnh');chosen.setWordWrap(True);preview_layout.addWidget(chosen);panes.addWidget(preview_box);panes.setSizes([530,420])
        image_paths={image_name(p):p for p in self.images}
        def show_preview(index):
            item=items.item(index)
            if item is None:return
            name=item.data(Qt.UserRole);path=image_paths.get(image_name(Path(name)))
            from PySide6.QtGui import QImageReader
            reader=QImageReader(str(path)) if path else None
            if reader:reader.setAutoTransform(True)
            pix=QPixmap.fromImage(reader.read()) if reader else QPixmap()
            preview.clear()
            if pix.isNull():preview.setText('Không tìm thấy ảnh nguồn')
            else:preview.setPixmap(pix.scaled(360,420,Qt.KeepAspectRatio,Qt.SmoothTransformation))
            preview_name.setText(item.text())
        items.currentRowChanged.connect(show_preview)
        search.textChanged.connect(lambda text:[items.item(i).setHidden(text.casefold() not in items.item(i).text().casefold()) for i in range(items.count())])
        for i, name in enumerate(names):
            linked = self.image_to_sheets.get(image_name(Path(name)), [])
            supplier = ", ".join(str(self.data_by_sheet[s][0][1].get("Nhà cung cấp") or s) for s in linked if self.data_by_sheet.get(s))
            items.item(i).setText(name + ("\n" + supplier if supplier else ""))
            items.item(i).setData(Qt.UserRole, name)
            items.item(i).setFlags(items.item(i).flags()|Qt.ItemIsUserCheckable)
            items.item(i).setCheckState(Qt.Unchecked)
            items.item(i).setSizeHint(QSize(300,60))
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel); layout.addWidget(buttons)
        buttons.button(QDialogButtonBox.Save).setText("Ghép các ảnh đã chọn"); buttons.button(QDialogButtonBox.Save).setObjectName("primary")
        buttons.button(QDialogButtonBox.Cancel).setText("Hủy")
        buttons.rejected.connect(dialog.reject)
        def update_chosen():
            selected=[items.item(i).data(Qt.UserRole) for i in range(items.count()) if items.item(i).checkState()==Qt.Checked]
            chosen.setText(f'Đã chọn {len(selected)} ảnh\n'+' · '.join(Path(n).name for n in selected))
            buttons.button(QDialogButtonBox.Save).setEnabled(len(selected)>=2)
            buttons.button(QDialogButtonBox.Save).setText(f'Ghép {len(selected)} ảnh đã chọn')
        items.itemChanged.connect(update_chosen);update_chosen();items.setCurrentRow(0)
        def save():
            selected = [items.item(i).data(Qt.UserRole) for i in range(items.count()) if items.item(i).checkState()==Qt.Checked]
            if len(selected) < 2:
                QMessageBox.information(dialog, "Chưa đủ ảnh", "Chọn ít nhất hai ảnh."); return
            try:
                from manual_invoice_links import merge_saved_invoices
                from multi_delivery import output_lock
                with output_lock(self.report):
                    if digest(self.report) != self.source_hash:
                        raise ValueError("Excel đã đổi; tải lại trước khi ghép để giữ sửa tay mới nhất.")
                    merge_saved_invoices(self.report, selected)
                dialog.accept(); self.pending_status = "Đã ghép ảnh; tải lại để kiểm tra từng trang."; self.open_day()
            except Exception as exc:
                QMessageBox.warning(dialog, "Chưa ghép", str(exc))
        from rec_review_dialogs import arrange
        arrange(dialog,'Ghép các trang của một phiếu','Chọn ít nhất hai ảnh thuộc đúng một chứng từ; cùng NCC không đủ để kết luận cùng phiếu.')
        from rec_merge_layout import arrange_merge
        arrange_merge(dialog,items,panes,preview_box,search,hint,chosen,buttons)
        buttons.accepted.connect(save); dialog.exec()

    def open_folder(self):
        target = self.report.parent if self.report else self.destination
        if target.exists(): os.startfile(str(target))

    def publish(self):
        from rec_export_page import show
        return show(self)

    def closeEvent(self, event):
        if getattr(getattr(self,'debt_page',None),'running',False) or getattr(getattr(getattr(self,'debt_page',None),'review',None),'saving',False):
            QMessageBox.information(self,'Đang đọc công nợ','Chờ hàng đợi công nợ hoàn tất để giữ các kết quả đang ghi.');event.ignore();return
        if not self._leave_pr():event.ignore();return
        if self.busy:
            QMessageBox.information(self, "Đang xử lý", "Đợi bước hiện tại kết thúc để giữ kết quả đang ghi.")
            event.ignore(); return
        self.preview.pool.waitForDone()
        if self.location_process is not None:
            self.location_process.kill(); self.location_process.waitForFinished(1000)
        self.location_request+=1
        if hasattr(self,"region_pool"):self.region_pool.waitForDone()
        self.thread_pool.waitForDone()
        self.inbox_timer.stop()
        QApplication.instance().removeEventFilter(self.selection_focus)
        from receiving_preferences import save_window
        try:save_window(self)
        except OSError:pass
        event.accept()


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Auto Receiving desktop")
    parser.add_argument("--day", type=date.fromisoformat, help="Ngày mở, YYYY-MM-DD")
    parser.add_argument("--no-auto",action="store_true")
    parser.add_argument("--smoke",action="store_true")
    args = parser.parse_args()
    app = QApplication.instance() or QApplication(sys.argv)
    window = ReceivingWindow(day=args.day, auto_load=not (args.smoke or args.no_auto))
    window.show()
    if args.smoke:QTimer.singleShot(1500,app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
