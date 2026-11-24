"""Physical PR columns with stable logical shortage/REC_ID sync identities."""
import re
from receiving_sheets import HEADERS,padded

PHYSICAL_HEADERS=HEADERS[:4]+['Số PR','Ngày PR']+HEADERS[4:]+['REC_ID']


def pr_fields(title):
    match=re.fullmatch(r'PR\s+(.+?)\s*·\s*(\d{2}/\d{2}/\d{4})',str(title).strip())
    return list(match.groups()) if match else ['','']


def physical_values(values):
    row=padded(values)
    if row[:11]==HEADERS:return PHYSICAL_HEADERS[:]
    return row[:4]+pr_fields(row[3])+row[4:]


def logical_rows(rows):
    if len(rows)<4:return rows
    header=rows[3]
    if header[4:6]!=['Số PR','Ngày PR']:return rows
    if header[:13]!=PHYSICAL_HEADERS[:13] or (len(header)>13 and header[13] not in ('','REC_ID')):
        raise ValueError('Tiêu đề PR/Ngày PR đã đổi; chưa đồng bộ để tránh sai cột.')
    result=[list(r) for r in rows[:3]]
    for raw in rows[3:]:
        row=(list(raw)+['']*14)[:14]
        result.append(row[:4]+row[6:])
    return result


def formatting(sid,last):
    requests=[]
    widths={0:40,1:88,2:185,4:58,5:88,6:280,7:46,8:66,9:68,10:55,11:225,12:140}
    for col,width in widths.items():
        requests.append({'updateDimensionProperties':{'range':{'sheetId':sid,'dimension':'COLUMNS','startIndex':col,'endIndex':col+1},'properties':{'pixelSize':width,'hiddenByUser':False},'fields':'pixelSize,hiddenByUser'}})
    for col in (3,13):
        requests.append({'updateDimensionProperties':{'range':{'sheetId':sid,'dimension':'COLUMNS','startIndex':col,'endIndex':col+1},'properties':{'hiddenByUser':True},'fields':'hiddenByUser'}})
    requests.append({'repeatCell':{'range':{'sheetId':sid,'startRowIndex':3,'endRowIndex':max(4,last),'startColumnIndex':0,'endColumnIndex':13},'cell':{'userEnteredFormat':{'wrapStrategy':'WRAP','verticalAlignment':'MIDDLE'}},'fields':'userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment'}})
    requests.append({'autoResizeDimensions':{'dimensions':{'sheetId':sid,'dimension':'ROWS','startIndex':3,'endIndex':max(4,last)}}})
    return requests
