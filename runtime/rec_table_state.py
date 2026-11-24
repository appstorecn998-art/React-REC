"""Keep row identity and scroll while a controller replaces table data."""
from PySide6.QtCore import QModelIndex
from PySide6.QtWidgets import QAbstractItemView

def begin(table,keys):
 keys=list(keys);selected=[keys[i.row()] for i in table.selectionModel().selectedRows() if i.row()<len(keys)]
 current=table.currentRow()
 state=(table.blockSignals(True),table.updatesEnabled(),table.verticalScrollBar().value(),table.horizontalScrollBar().value(),selected,keys[current] if 0<=current<len(keys) else None)
 table.setUpdatesEnabled(False)
 return state

def end(table,keys,state):
 blocked,updates,vertical,horizontal,selected,current=state
 keys=list(keys);table.clearSelection();table.setCurrentIndex(QModelIndex())
 if current in keys:table.setCurrentCell(keys.index(current),0)
 from PySide6.QtCore import QItemSelectionModel
 table.clearSelection()
 for key in selected:
  if key in keys:table.selectionModel().select(table.model().index(keys.index(key),0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
 table.verticalScrollBar().setValue(vertical);table.horizontalScrollBar().setValue(horizontal)
 table.blockSignals(blocked);table.setUpdatesEnabled(updates)
