"""Shared semantic colors; labels remain meaningful without color."""
from PySide6.QtGui import QColor,QBrush

COLORS={'ready':'#168057','done':'#168057','warning':'#ad781b','running':'#6054d8','error':'#b3364e','neutral':'#8a95a8'}

def status_item(item,text,kind):
    item.setText('● '+text)
    item.setForeground(QBrush(QColor(COLORS[kind])))
    item.setToolTip(text)
    return item
