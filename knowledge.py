"""Read-only business knowledge inventory, plus audited pair activation."""
import json,hashlib
from pathlib import Path
from receiving_link_memory import record_id,set_active,supplier as supplier_key

LABELS={'supplier_aliases':'Bí danh NCC','supplier':'Nhà cung cấp','supplier_names':'Tên gọi NCC','confirmed_items':'Tên hàng và mã','unit_conversions':'Quy đổi đơn vị','packaging_rules':'Đóng gói','pr_link_rules':'Cặp PR – phiếu giao','pr_spec_equivalences':'Quy cách tương đương','pr_spec_rules':'Quy cách đã nhớ','warehouse_rules':'Quy tắc phân kho','vocabulary':'Tên hàng tương đương','warehouse_departments':'Kho và bộ phận','requester_warehouses':'Kho theo người yêu cầu','alcohol_warehouse_code':'Kho hàng rượu','direct_kitchen_rule':'Hàng giao thẳng bếp'}


def inventory(profile):
    rules=json.loads((Path(profile)/'NhaCungCap.json').read_text(encoding='utf-8-sig'))
    names={s.get('id'):s.get('name','') for s in rules.get('suppliers',[])}
    display={supplier_key(s.get('name',''),rules):s.get('name','') for s in rules.get('suppliers',[])}
    for record in rules.get('pr_link_rules',[]):
        if record.get('supplier_name'):display.setdefault(record.get('key',{}).get('supplier'),record['supplier_name'])
    rows=[]
    def add(kind,record,supplier='',title='',summary='',reason='',source='NhaCungCap.json',pair=False):
        supplier=display.get(supplier,display.get(supplier_key(supplier,rules),supplier)) if supplier else ''
        raw=json.dumps(record,ensure_ascii=False,sort_keys=True)
        identity=record_id(record) if pair else hashlib.sha256((kind+supplier+raw).encode()).hexdigest()
        basis=(reason or record.get('reason',record.get('basis',''))) if isinstance(record,dict) else reason
        rows.append(dict(id=identity,type=kind,label=LABELS.get(kind,kind),supplier=supplier or 'Chung / chưa gắn NCC',title=title or LABELS.get(kind,kind),summary=summary,reason=basis,active=record.get('active',True) if isinstance(record,dict) else True,pair=pair,source=source,record=record))
    for s in rules.get('suppliers',[]):
        name=s.get('name','')
        base={k:v for k,v in s.items() if k not in ('aliases','confirmed_items')}
        add('supplier',base,name,name,'Nhóm hàng và chính sách NCC')
        for alias in s.get('aliases',[]):add('supplier_names',{'alias':alias},name,str(alias),'Tên gọi của NCC')
        for item in s.get('confirmed_items',[]):add('confirmed_items',item,name,item.get('invoice_name',''),str(item.get('catalog_code','')))
    for kind,value in rules.items():
        if kind in ('version','suppliers'):continue
        records=value if isinstance(value,list) else [value]
        for record in records:
            if not isinstance(record,dict):
                add(kind,record,summary=str(record));continue
            key=record.get('key') or {};pr=key.get('pr') or {};delivery=key.get('delivery') or {}
            supplier=record.get('supplier_name') or names.get(record.get('supplier_id')) or names.get(key.get('supplier')) or key.get('supplier','')
            if kind=='supplier_aliases':supplier=record.get('invoice_name','')
            title=record.get('pr_name') or record.get('pr_item_name') or record.get('invoice_name') or key.get('item_name') or pr.get('item_name') or LABELS.get(kind,kind)
            summary=record.get('delivery_name') or record.get('delivery_item_name') or delivery.get('Tên hàng trên phiếu (Ảnh)') or str(record.get('catalog_code') or record.get('supplier_code') or '')
            if kind=='packaging_rules':summary='1 gói = '+str(record.get('pack_size',''))+' '+str(key.get('unit',''))
            if kind=='unit_conversions':summary='1 '+str(record.get('delivery_unit',''))+' = '+str(record.get('factor',''))+' '+str(record.get('pr_unit',''))+' · '+summary
            reason=''
            if kind=='pr_spec_rules':
                notes=[];basis=[]
                for name,label in (('conversion','Quy đổi'),('packaging','Đóng gói')):
                    part=record.get(name)
                    if isinstance(part,dict):
                        notes.append(label+': '+str(part.get('value','')))
                        if part.get('reason'):basis.append(part['reason'])
                summary=' · '.join([summary,*notes]);reason=' · '.join(basis)
            add(kind,record,supplier,title,summary,reason,pair=kind=='pr_link_rules')
    folder=Path(profile)/'.receiving'/'vocabulary'
    for path in sorted(folder.glob('*.json')):
        try:record=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError):continue
        if record.get('confirmed') is not True:continue
        add('vocabulary',record,title=' ↔ '.join(record.get('names',[])),summary=record.get('explanation',''),source='Từ vựng đã xác nhận')
    return {'items':rows}


def update_pair(profile,payload):
    set_active(profile,None,payload.get('rule'),payload.get('active'),payload.get('reason'))
    return {'saved':True}
