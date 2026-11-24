"""Review all delivery assignments once; uncertain pairs remain explicit suggestions."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QComboBox,QDialogButtonBox,QHeaderView
from receiving_pr_match import similarity,product_conflict,spec_conflict,parts

def proposals(items,rows,results):
    def suggestion_score(item,value):
        score=similarity(item,value)
        # A shared product word can propose a pair, but never auto-confirm it.
        if any(a & b for a in parts(item) for b in parts(value)):score=max(score,.45)
        return score
    mapped={r['row']:r['pr_index'] for r in results if r.get('pr_index') is not None and r.get('row') is not None}
    used=set(mapped.values());result=[]
    for row,value in rows:
        ranked=sorted([(suggestion_score(item,value),p) for p,item in enumerate(items) if not product_conflict(item,value)],reverse=True)
        suggestion=next((p for score,p in ranked if p not in used and score>=.45),None)
        result.append((row,value,mapped.get(row),suggestion))
    return result

def choose(w,items,rows,results,links,conversions=None):
    dialog=QDialog(w);dialog.setWindowTitle('Duyệt ghép hàng loạt');layout=QVBoxLayout(dialog)
    layout.addWidget(QLabel('Rà các cặp đề xuất rồi áp dụng một lần. Không tự xác nhận đơn vị, lượng hoặc giá.'))
    table=QTableWidget(len(rows),3);table.setHorizontalHeaderLabels(['Dòng trên phiếu giao','Hàng trên PR','Căn cứ']);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);table.verticalHeader().hide();layout.addWidget(table)
    combos=[];original={r['pr_index']:r['row'] for r in results if r.get('pr_index') is not None and r.get('row') is not None}
    extra={r:p for p,entry in (conversions or {}).items() for r in entry.get('lot_rows',[]) }
    for i,(row,value,current,suggestion) in enumerate(proposals(items,rows,results)):
        table.setItem(i,0,QTableWidgetItem(str(value.get('Tên hàng trên phiếu (Ảnh)') or '')))
        combo=QComboBox();combo.addItem('Chưa gán',None)
        for p,item in enumerate(items):combo.addItem(str(p+1)+' · '+str(item.get('item_name') or ''),p)
        current=extra.get(row,current)
        target=current if current is not None else suggestion
        combo.setCurrentIndex(max(0,combo.findData(target)));table.setCellWidget(i,1,combo);combos.append((row,combo))
        label='Cặp hiện tại' if current is not None else 'Gợi ý theo tên — cần duyệt' if suggestion is not None else 'Chưa có gợi ý chắc chắn'
        if target is not None and spec_conflict(items[target],value):label+='; khác quy cách'
        table.setItem(i,2,QTableWidgetItem(label));table.setRowHeight(i,62)
    status=QLabel();layout.addWidget(status)
    buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.button(QDialogButtonBox.Save).setText('Áp dụng các cặp đã chọn');layout.addWidget(buttons)
    def validate(*args):
        chosen={}
        for row,combo in combos:
            if combo.currentData() is not None:chosen.setdefault(combo.currentData(),[]).append(row)
        try:
            from receiving_lot_rows import grouped
            grouped(rows,{p:rs[0] for p,rs in chosen.items()},{p:{'lot_rows':rs} for p,rs in chosen.items() if len(rs)>1})
            valid=True;message='Chỉ các dòng có tên trên phiếu giống nhau 100% và cùng mã/ĐVT/giá/NCC mới được gán chung món PR; lượng sẽ được cộng, không gộp dòng gốc.'
        except ValueError as exc:valid=False;message=str(exc)
        buttons.button(QDialogButtonBox.Save).setEnabled(valid);status.setText(message)
    for _,combo in combos:combo.currentIndexChanged.connect(validate)
    validate();buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);dialog.resize(1000,650)
    if dialog.exec()!=QDialog.Accepted:return None
    selected={}
    for row,c in combos:
        if c.currentData() is not None:selected.setdefault(c.currentData(),[]).append(row)
    selected={p:(rs if len(rs)>1 else rs[0]) for p,rs in selected.items()}
    # Explicitly unmap prior pairs that the reviewer removed.
    for p in original:
        if p not in selected:selected[p]='unknown'
    return selected
