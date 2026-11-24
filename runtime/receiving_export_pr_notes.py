"""Pending PR is an export annotation, never approval or ledger permission."""
from pathlib import Path


def collect(report):
    from receiving_service import snapshot,day_images
    from receiving_pending_pr import read
    report=Path(report);images=day_images(report.parent);notes=[]
    for sheet,rows in snapshot(report)[1]:
        pending=read(report.parent/'.receiving',sheet,rows,images)
        if pending:notes.append(sheet+' · Chờ PR thay thế: '+pending['reason'])
    return notes


def annotate(path,notes):
    if not notes:return
    from openpyxl import load_workbook
    from openpyxl.styles import Alignment,Font,PatternFill
    book=load_workbook(path)
    try:
        sheet=book.active;row=sheet.max_row+2
        for note in notes:
            sheet.merge_cells(start_row=row,start_column=1,end_row=row,end_column=19)
            cell=sheet.cell(row,1,note);cell.data_type='s'
            cell.alignment=Alignment(wrap_text=True,vertical='center')
            cell.font=Font(name='Arial',size=11,color='9A5A05')
            cell.fill=PatternFill('solid',fgColor='FFF7E6')
            sheet.row_dimensions[row].height=max(32,16*(1+len(note)//100));row+=1
        sheet.print_area='A1:S'+str(row-1)
        book.save(path)
    finally:book.close()
