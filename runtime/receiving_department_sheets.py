"""Department routing layered over REC's existing managed-row sync contract."""
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from receiving_sheets import HEADERS,plan,fingerprint,padded,unverified_values

TABS={'KC':'Kitchen','FB':'FB','FO':'FO','HK':'HK','ENG':'ENG','SPA':'SPA','KID CLUB':'Kid Club','CANTEEN':'Canteen','STEWARD':'Steward','FIN':'Fin'}

def canonical(value):
    from supplier_rules import normalize_name
    key=normalize_name(str(value or '')).replace(' ','')
    return {'kc':'KC','bep':'KC','kitchen':'KC','fb':'FB','fandb':'FB','foodbeverage':'FB','fo':'FO','frontoffice':'FO','letan':'FO','hk':'HK','housekeeping':'HK','eng':'ENG','engineering':'ENG','spa':'SPA','kidclub':'KID CLUB','kidsclub':'KID CLUB','canteen':'CANTEEN','steward':'STEWARD','stewarding':'STEWARD','fin':'FIN','finance':'FIN'}.get(key)

def routes(summary,records,library):
    departments=defaultdict(set)
    unknown=set()
    for record in records:
        if not record.get('active') or (not record.get('valid') and 'uncertain_indices' not in record):continue
        values={int(i):v for i,v in record.get('source_rows',[])}
        for index,source in record.get('allocation_rows',{}).items():
            if source is None or str(index) in record.get('uncertain_indices',[]):continue
            key=(record['order_id'],int(index))
            for physical in source if isinstance(source,(list,tuple)) else [source]:
                dept=canonical(values.get(int(physical),{}).get('Bộ phận'))
                if dept:departments[key].add(dept)
                else:unknown.add(key)
    result={};issues=[]
    for row in summary:
        key=(row['order_id'],int(row['index']));found=set(departments[key])
        # PR metadata also routes items not delivered in any receipt yet.
        record=library.get(row['order_id'],{})
        item=next((v for i,v in enumerate(record.get('items',[])) if i==int(row['index'])),{})
        pr_dept=canonical(item.get('pr_department') or record.get('department'))
        if not found and pr_dept:found.add(pr_dept)
        if len(found)==1 and key not in unknown:result[key]=next(iter(found))
        else:issues.append({'name':row['name'],'order_id':row['order_id'],'index':row['index'],'reason':'Bộ phận mâu thuẫn giữa các lần nhận' if len(found)>1 else 'Chưa xác định bộ phận'})
    return result,issues

class TabClient:
    def __init__(self,client,title):self.client=client;self.title=title
    def read(self):return self.client.read(self.title)
    def write(self,data):return self.client.write(data)
    def write_and_delete(self,data,rows):return self.client.write_and_delete(data,rows)

def preview(client,summary,records,suppliers,library,progress=None):
    from receiving_sheets_layout import logical_rows

    progress=progress or (lambda message:None)
    progress("Đang chuẩn bị và đọc danh sách tab Google Sheets…")
    assignment,issues=routes(summary,records,library)
    complete={ (row['order_id'],int(row['index'])) for row in summary
               if row.get('remaining') is not None and Fraction(row['remaining'])==0
               and not row.get('history_unverified') and not row.get('source_unverified') }
    # No destination is needed to remove a verified, fully received shortage.
    issues=[issue for issue in issues if (issue['order_id'],int(issue['index'])) not in complete]
    meta=client.request('GET','',params={'fields':'sheets.properties'})
    titles={s['properties']['title'] for s in meta['sheets']}
    tabs=dict(TABS)
    kitchen=next((s['properties']['title'] for s in meta['sheets'] if s['properties']['sheetId']==0),None)
    if not kitchen:raise ValueError('Không tìm thấy tab Bếp gốc (gid=0).')
    tabs['KC']=kitchen
    available=[title for title in tabs.values() if title in titles]
    progress(f'Đang đọc {len(available)} tab Google Sheets…')
    raw_tabs=client.read_tabs(available)
    remotes={title:logical_rows(raw) for title,raw in raw_tabs.items()}
    # REC_ID is globally unique. Never silently choose between two copies.
    managed={}
    for title,remote in remotes.items():
        for index,row in enumerate(remote[4:],5):
            key=padded(row)[11]
            if key:
                if key in managed:raise ValueError('REC_ID trùng giữa các tab. Kiểm tra trước khi đồng bộ: '+str(key))
                managed[key]=(title,index,padded(row))
    def rid(row):return 'REC-'+fingerprint([row['order_id'],row['index']])[:32]
    plans=[];skipped=0;history=[]
    for dept,title in tabs.items():
        original=remotes.get(title,[['Theo dõi hàng thiếu · '+title],[],[],HEADERS+['REC_ID']])
        remote=[list(row) for row in original]
        # Protect records assigned elsewhere from orphan handling in plan().
        local=[row for row in summary if assignment.get((row['order_id'],int(row['index'])))==dept]
        local_keys={rid(row) for row in local}
        foreign={key for key,(tab,_,_) in managed.items() if tab==title and key not in local_keys}
        for i,row in enumerate(remote[4:],4):
            if padded(row)[11] in foreign:
                remote[i]=padded(row);remote[i][11]=''
        local=[dict(row,title=pr_display_title(library.get(row['order_id'],{}),row['title'])) for row in local]
        part=plan("'"+title.replace("'","''")+"'",remote,local,records,suppliers,renumber=False)
        raw=raw_tabs.get(title)
        part['remote_hash']=fingerprint(raw)
        part['pr_columns']=raw is None or raw[3][4:6]==['Số PR','Ngày PR']
        part['pr_values']=[values[4:6] for values in raw] if raw and part['pr_columns'] else []
        part['original_rows']=original
        part['department']=dept;part['tab']=title;part['create']=title not in titles
        # Existing unknown-history rows stay untouched; do not block other valid shortages.
        part['history_review']=[]
        skipped+=part['skipped']
        for change in part['changes']:
            change['department']=dept;change['tab']=title
        plans.append(part)
    by_tab={p['tab']:p for p in plans}
    # Remove verified closed items wherever REC last synced them.
    for row in summary:
        line=(row['order_id'],int(row['index']))
        key=rid(row)
        department=assignment.get(line)
        existing=managed.get(key)
        if not existing:continue
        old_title,index,old=existing
        desired=tabs.get(department)
        if not row.get('history_unverified') and (row.get('source_unverified') or row.get('remaining') is None):
            if desired!=old_title:
                values=unverified_values(old,row)
                if values!=old:
                    by_tab[old_title]['changes'].append(dict(action='Đánh dấu cần rà',row=index,name=row['name'],supplier=old[2],values=values,old=old,tab=old_title))
            continue
        if line in complete:
            if desired==old_title:continue  # Already planned on this tab.
            action='Xóa dòng đã ngừng giao bù' if row.get('reason') else 'Xóa dòng đã nhận đủ'
        else:
            if not desired or desired==old_title or row.get('history_unverified'):
                continue
            target=next((c for c in by_tab[desired]['changes'] if c['values'][11]==key and not c.get('delete')),None)
            if target is None:continue
            if by_tab[desired]['pr_columns']!=by_tab[old_title]['pr_columns']:
                by_tab[desired]['changes'].remove(target)
                issues.append(dict(name=row['name'],order_id=row['order_id'],index=row['index'],reason='Hai tab dùng mẫu cột khác nhau'))
                continue
            target['values'][10]=old[10]
            if not target['values'][1]:target['values'][1]=old[1]
            target['action']='Chuyển từ '+old_title
            target['move_from']=(old_title,index,old)
            action='Chuyển sang '+desired
        deletion=dict(action=action,row=index,name=row['name'],supplier=old[2],values=old[:],old=old,delete=True,tab=old_title)
        by_tab[old_title]['changes'].append(deletion)
    for part in plans:
        raw=raw_tabs.get(part['tab'],[])
        managed_width=14 if part['pr_columns'] else 12
        for change in part['changes'][:]:
            if not change.get('delete') or not change['action'].startswith('Xóa dòng'):continue
            if any(cell not in ('',None) for cell in raw[change['row']-1][managed_width:]):
                part['changes'].remove(change)
                issues.append(dict(name=change['name'],order_id='',index=change['row'],reason='Dòng đã đủ có dữ liệu ngoài cột REC trên tab '+part['tab']))
        deleted={c['row'] for c in part['changes'] if c.get('delete')}
        if not deleted:continue
        changed={c['row']:c for c in part['changes'] if not c.get('delete')}
        for index,values in enumerate(part['original_rows'][4:],5):
            old=padded(values);key=old[11]
            if index in deleted or not str(key).startswith('REC-'):continue
            sequence=index-4-sum(d<index for d in deleted)
            if index in changed:changed[index]['values'][0]=sequence
            elif old[0]!=sequence:
                values=old[:];values[0]=sequence
                change=dict(action='Đánh lại STT',row=index,name=old[4],supplier=old[2],values=values,old=old,department=part['department'],tab=part['tab'])
                part['changes'].append(change)
        for c in part['changes']:
            if c['old'] is None:c['values'][0]=c['row']-4-sum(d<c['row'] for d in deleted)
    for part in plans:
        part['changes'][:]=[c for c in part['changes'] if c.get('delete') or c.get('old')!=c['values']]
    all_changes=[c for part in plans for c in part['changes']]
    # Unroutable rows remain untouched and are visible as skipped.
    skipped+=len(issues)
    return {'parts':plans,'changes':all_changes,'skipped':skipped,'history_review':history,'department_issues':issues,'title':'Theo bộ phận','remote_titles':sorted(titles)}

def apply_preview(client,value,progress=None):
    progress=progress or (lambda message:None)
    progress("Đang kiểm tra lại nguồn trước khi gửi…")
    if value.get('history_review'):raise ValueError('Còn dòng đã đồng bộ chưa xác minh lịch sử; giữ nguyên Sheets.')
    # Recheck every tab before the first write to avoid acting on a stale preview.
    meta=client.request('GET','',params={'fields':'sheets.properties'})
    titles={s['properties']['title'] for s in meta['sheets']}
    current=client.read_tabs([p['tab'] for p in value['parts'] if not p['create'] and p['tab'] in titles])
    for p in value['parts']:
        if p['create']:
            if p['tab'] in titles:raise ValueError('Tab vừa được tạo sau xem trước; tải lại trước khi ghi.')
        elif fingerprint(current.get(p['tab']))!=p['remote_hash']:raise ValueError('Google Sheets đã đổi sau khi xem trước: '+p['tab'])
    # Create tabs, update rows, and move managed rows in one atomic batch.
    from receiving_sheets_layout import physical_values, pr_fields
    properties={s['properties']['title']:s['properties'] for s in meta['sheets']}
    used={s['sheetId'] for s in properties.values()};requests=[]
    def cells(values):
        result=[]
        for v in values:
            entry={} if v is None or v=='' else {'userEnteredValue':{'boolValue':v}} if isinstance(v,bool) else {'userEnteredValue':{'numberValue':v}} if isinstance(v,(int,float)) else {'userEnteredValue':{'stringValue':str(v)}}
            result.append(entry)
        return result
    def update(sid,row,col,values):
        requests.append({'updateCells':{'start':{'sheetId':sid,'rowIndex':row,'columnIndex':col},'rows':[{'values':cells(values)}],'fields':'userEnteredValue'}})
    for p in value['parts']:
        title=p['tab']
        if p['create']:
            sid=max(used or {0})+1;used.add(sid)
            properties[title]={'sheetId':sid,'gridProperties':{'rowCount':1000,'columnCount':14}}
            requests.append({'addSheet':{'properties':{'sheetId':sid,'title':title,'gridProperties':{'rowCount':1000,'columnCount':14,'frozenRowCount':4}}}})
            update(sid,0,0,['Theo dõi hàng thiếu · '+title]);update(sid,3,0,physical_values(HEADERS+['REC_ID']))
        else:sid=properties[title]['sheetId']
        maximum=max([c['row'] for c in p['changes']]+[4]);capacity=properties[title].get('gridProperties',{}).get('rowCount',1000)
        if maximum>capacity:requests.append({'appendDimension':{'sheetId':sid,'dimension':'ROWS','length':maximum-capacity}})
        key_column=13 if p['pr_columns'] else 11
        if p['add_key'] and p['changes']:
            columns=properties[title]['gridProperties']['columnCount']
            if columns<=key_column:
                requests.append({'appendDimension':{'sheetId':sid,'dimension':'COLUMNS','length':key_column+1-columns}})
                properties[title]['gridProperties']['columnCount']=key_column+1
            update(sid,3,key_column,['REC_ID'])
        if any('lịch sử chưa xác minh' in str(c['values'][9]) for c in p['changes'] if not c.get('delete')):
            requests.append({'updateDimensionProperties':{'range':{'sheetId':sid,'dimension':'COLUMNS','startIndex':11,'endIndex':12},'properties':{'hiddenByUser':False,'pixelSize':280},'fields':'hiddenByUser,pixelSize'}})
    for p in value['parts']:
        destination=properties[p['tab']]
        sid=destination['sheetId']
        for change in p['changes']:
            if change.get('delete'):continue
            row=change['row']-1
            values=change['values']
            old=change['old']
            pr_values=p['pr_values'][row] if row<len(p['pr_values']) else []
            if change.get('move_from'):
                source_tab, source_row, old=change['move_from']
                source=properties[source_tab]
                source_values=next(part['pr_values'] for part in value['parts'] if part['tab']==source_tab)
                pr_values=source_values[source_row-1] if source_values else []
                width=source['gridProperties']['columnCount']
                columns=destination['gridProperties']['columnCount']
                if width>columns:
                    requests.append({'appendDimension':{'sheetId':sid,'dimension':'COLUMNS','length':width-columns}})
                    destination['gridProperties']['columnCount']=width
                requests.append({'cutPaste':{
                    'source':{'sheetId':source['sheetId'],'startRowIndex':source_row-1,'endRowIndex':source_row,'startColumnIndex':0,'endColumnIndex':width},
                    'destination':{'sheetId':sid,'rowIndex':row,'columnIndex':0},
                    'pasteType':'PASTE_NORMAL',
                }})
            if old is None:
                update(sid,row,0,physical_values(values) if p['pr_columns'] else values)
                continue
            for column,(previous,current) in enumerate(zip(old,values)):
                if previous!=current and column!=10:
                    update(sid,row,column+2 if p['pr_columns'] and column>=4 else column,[current])
            if p['pr_columns'] and old[3]!=values[3] and all(pr_fields(values[3])):
                for offset,current in enumerate(pr_fields(values[3])):
                    if offset>=len(pr_values) or pr_values[offset]!=current:
                        update(sid,row,4+offset,[current])
    for p in value['parts']:
        sid=properties[p['tab']]['sheetId']
        for row in sorted({c['row'] for c in p['changes'] if c.get('delete')},reverse=True):
            requests.append({'deleteDimension':{'range':{'sheetId':sid,'dimension':'ROWS','startIndex':row-1,'endIndex':row}}})
    from receiving_sheets import table_borders
    for p in value['parts']:
        if not p['changes'] or not p['pr_columns']:continue
        last=max([len(p['original_rows']),4]+[c['row'] for c in p['changes'] if not c.get('delete')])
        last-=len({c['row'] for c in p['changes'] if c.get('delete')})
        requests.append(table_borders(properties[p['tab']]['sheetId'],last))
        from receiving_sheets_layout import formatting
        requests.extend(formatting(properties[p['tab']]['sheetId'],last))
    if requests:
        progress(f"Đang gửi {len(value['changes'])} thay đổi trong một giao dịch · chờ Google xác nhận…")
        client.request('POST',':batchUpdate',json={'requests':requests})
        progress(f"Google Sheets đã xác nhận {len(value['changes'])} thay đổi")
    else:progress('Không có thay đổi cần gửi')
    return len(value['changes'])


def pr_display_title(record,fallback):
    from receiving_pr_number_identity import document_key
    key=document_key(record)
    if not key:return fallback
    from datetime import date
    return 'PR '+str(record['number']).strip()+' · '+date.fromisoformat(key[1]).strftime('%d/%m/%Y')
