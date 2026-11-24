"""Local bilingual line matching. No price/quantity-based or unit conversions."""
import re
import unicodedata
from decimal import Decimal
from receiving_review import normalized,has_code

FIELDS=('item_name','english_name','vietnamese_name','Tên hàng trên phiếu (Ảnh)','Tên chuẩn hệ thống')
FILLER={'bag','pack','packs','btl','bottle','can','box','goi','bich','hop','chai','tui','kg','gr','g','ml','l','pcs','x','seasoning'}

def raw_text(value):
    value=unicodedata.normalize('NFD',str(value or '').lower().replace('đ','d'))
    return ''.join(c for c in value if unicodedata.category(c)!='Mn')

def parts(item):
    result=[]
    for field in FIELDS:
        for text in str(item.get(field) or '').split('/'):
            from receiving_product_identity import linguistic_parts
            text=linguistic_parts(text)
            text=re.sub(r'\d+(?:[.,]\d+)?\s*(?:kg|gr|g|ml|lit|l)\b',' ',text)
            text=re.sub(r'\d+(?:[.,]\d+)?',' ',text)
            words=set(normalized(text).split())-FILLER
            if words:result.append(words)
    return result

def specification(item):
    # Use source descriptions rather than catalog labels to detect contradictions.
    text=' '.join(raw_text(item.get(f)) for f in ('item_name','specification','Tên hàng trên phiếu (Ảnh)'))
    values={}
    for match in re.finditer(r'(\d+(?:[.,]\d+)?)\s*(kg|gr|g|ml|lit|l)(?![a-z])',text):
        number=Decimal(match[1].replace(',','.'));unit=match[2]
        kind='mass' if unit in ('kg','gr','g') else 'volume'
        if unit in ('kg','l','lit'):number*=1000
        values.setdefault(kind,set()).add(number)
    for match in re.finditer(r'(?:x|hop|thung)\s*(\d+)\s*(?:packs?|goi|hop|chai|bich)',text):
        values.setdefault('pack_count',set()).add(Decimal(match[1]))
    return values

def spec_conflict(a,b):
    left,right=specification(a),specification(b)
    # A pack count and a weight describe different aspects, not a conflict.
    if (('mass' in left and 'volume' in right) or ('volume' in left and 'mass' in right)) and not (left.keys() & right.keys()):return True
    return any(left[k].isdisjoint(right[k]) for k in left.keys() & right.keys())

def pasta_identity(item):
    # Use source descriptions for shape, never a potentially generic catalog
    # label (Linguine can have "Mi Spaghetti" as its Vietnamese catalog alias).
    raw=item.get('item_name') or item.get('Tên hàng trên phiếu (Ảnh)') or ''
    words=set(normalized(raw).split());shapes=set()
    from difflib import SequenceMatcher
    for shape in ('spaghetti','linguine','penne','fusilli','fettuccine','macaroni','lasagna'):
        if any(w==shape or (len(w)>=6 and SequenceMatcher(None,w,shape).ratio()>=.86) for w in words):shapes.add(shape)
    return shapes

def pasta_score(a,b):
    from difflib import SequenceMatcher
    left_shapes,right_shapes=pasta_identity(a),pasta_identity(b)
    if not left_shapes or left_shapes!=right_shapes:return 0
    if spec_conflict(a,b):return 0
    # Shape alone cannot infer a brand: require its independent long token.
    left=normalized(a.get('item_name') or a.get('Tên hàng trên phiếu (Ảnh)') or '').split()
    right=normalized(b.get('item_name') or b.get('Tên hàng trên phiếu (Ảnh)') or '').split()
    ignored=set(FILLER)|{'noodles','noodle','spaghetti','linguine','linguinie','penne','rigate','pasta','fusilli','fettuccine','macaroni','lasagna'}
    def brand_word(w):
        return len(w)>=6 and w not in ignored and not any(SequenceMatcher(None,w,shape).ratio()>=.86 for shape in left_shapes)
    numbers=lambda words:set(re.findall(r'(?:no|so)\s*(\d+)', ' '.join(words)))
    if numbers(left) and numbers(right) and numbers(left).isdisjoint(numbers(right)):return 0
    strong=[(x,y) for x in left for y in right if brand_word(x) and brand_word(y) and SequenceMatcher(None,x,y).ratio()>=.86]
    return .95 if strong and specification(a) and specification(a)==specification(b) else 0


def similarity(a,b):
    best=pasta_score(a,b)
    sa,sb=specification(a),specification(b)
    same_size=bool(sa and sa==sb and any(k in sa for k in ('mass','volume')))
    for left in parts(a):
        for right in parts(b):
            common=left & right
            if not common:continue
            if left==right:
                score=.96 if len(left)>1 or len(next(iter(left)))>=5 else .7
            else:
                score=len(common)/len(left|right)
                # Extra descriptive words on one side may be harmless, but a
                # subset must have at least two product words and high coverage.
                if len(common)>=2 and (left<=right or right<=left):
                    score=max(score,.9 if len(common)/max(len(left),len(right))>=.75 else .65)
                # Brand/product words and an identical explicit pack size are
                # stronger evidence than a literal name alone (e.g. Knorr pork
                # meat powder vs catalog "Seasoning Knorr Pork Powder").
                if same_size and len(common)>=3 and (left<=right or right<=left) and len(common)/max(len(left),len(right))>=.75:
                    score=max(score,.93)
            best=max(best,score)
    return best

def product_conflict(a,b):
    def species(item):
        text=' '+normalized(item.get('item_name') or item.get('Tên hàng trên phiếu (Ảnh)') or '')+' '
        groups={'beef':['bo','beef'],'pork':['heo','lon','pork'],'lamb':['cuu','lamb'],'chicken':['ga','chicken'],'duck':['vit','duck']}
        return {k for k,words in groups.items() if any(' '+w+' ' in text for w in words)}
    x,y=species(a),species(b)
    if x and y and x.isdisjoint(y):return True
    from catalog_recall import product_mismatch
    from receiving_product_identity import source
    return bool(product_mismatch(source(a),source(b)) or product_mismatch(source(b),source(a)))

def printed_number(item,pr=False):
    value=str(item.get('source_stt' if pr else 'STT trên phiếu','')).strip()
    return int(value) if value.isdigit() else None


def infer_links(pr_items,rows,manual,exact_names,ordered=False,blocked=()):
    # Each row description has identical normalized names across every pair.
    name_cache={}
    original_names=exact_names
    def exact_names(item):
        key=id(item)
        if key not in name_cache:name_cache[key]=original_names(item)
        return name_cache[key]
    values=dict(rows);mapping={p:r for p,r in manual.items() if p in range(len(pr_items))}
    used={r for r in mapping.values() if r is not None}
    scores={};reasons={};suggestions={}
    for p,item in enumerate(pr_items):
        if p in mapping:continue
        code=str(item.get('catalog_code') or '').strip()
        for row,value in rows:
            if row in used or (p,row) in blocked:continue
            dcode=str(value.get('Mã vật tư') or '').strip() if has_code(value) else ''
            if code and dcode and code!=dcode:continue
            if product_conflict(item,value):continue
            same_code=bool(code and code==dcode)
            shape_a,shape_b=pasta_identity(item),pasta_identity(value)
            if shape_a and shape_b and shape_a!=shape_b and not same_code:continue
            if shape_a and shape_b and not same_code:
                def source_numbers(v):
                    text=raw_text(v.get('item_name') or v.get('Tên hàng trên phiếu (Ảnh)') or '')
                    return set(re.findall(r'(?:no\.?|so)\s*(\d+)',text))
                na,nb=source_numbers(item),source_numbers(value)
                if na and nb and na.isdisjoint(nb):continue
            same_name=bool(exact_names(item)&exact_names(value))
            score=1.0 if same_code else .99 if same_name else similarity(item,value)
            conflict=spec_conflict(item,value)
            if score>=.45:
                scores[p,row]=min(score,.79) if conflict and not same_code else score
                reasons[p,row]='Cùng mã hàng' if same_code else 'Tên khớp' if same_name else 'Tên Anh/Việt và quy cách phù hợp'
    for p,item in enumerate(pr_items):
        if p in mapping:continue
        ranked=sorted([(score,row) for (index,row),score in scores.items() if index==p],reverse=True)
        if not ranked:continue
        score,row=ranked[0]
        competitors=sorted([s for (index,r),s in scores.items() if r==row and index!=p],reverse=True)
        gap=score-ranked[1][0] if len(ranked)>1 else 1
        reverse_gap=score-competitors[0] if competitors else 1
        if score>=.89 and gap>=.1 and reverse_gap>=.1 and row not in used:
            mapping[p]=row;used.add(row)
    # Printed STT is a default hint across suppliers, not a license to pair
    # unrelated products or shift lists after a missing line.
    from collections import Counter
    pc=Counter(printed_number(v,True) for v in pr_items)
    dc=Counter(printed_number(v) for _,v in rows)
    for p,item in enumerate(pr_items):
        if p in mapping:continue
        n=printed_number(item,True)
        if n is None or pc[n]!=1 or dc[n]!=1:continue
        row,value=next((r,v) for r,v in rows if printed_number(v)==n)
        score=scores.get((p,row),0)
        from receiving_product_identity import positional_identity
        if row in used or score<.55 or not positional_identity(item,value) or spec_conflict(item,value) or product_conflict(item,value):continue
        if any(s>score+.1 for (index,r),s in scores.items() if index==p and r!=row and r not in used):continue
        if any(s>score+.1 for (index,r),s in scores.items() if r==row and index!=p):continue
        mapping[p]=row;used.add(row);reasons[p,row]='Cùng STT in trên phiếu và tên phù hợp — cần rà khác biệt'
    # Same-order supplier policy helps only equal-length, anchored lists.
    # Never shift a whole receipt after a missing/extra line or conflicting anchor.
    ordered_rows=[row for row,_ in rows]
    anchors=[(p,r) for p,r in mapping.items() if r is not None]
    aligned=all(p<len(ordered_rows) and ordered_rows[p]==r for p,r in anchors)
    if ordered and len(pr_items)==len(rows) and len(anchors)>=3 and aligned:
        for p,item in enumerate(pr_items):
            if p in mapping:continue
            row=ordered_rows[p]
            score=scores.get((p,row),0)
            from receiving_product_identity import positional_identity
            if row in used or score<.6 or not positional_identity(item,values[row]) or spec_conflict(item,values[row]) or product_conflict(item,values[row]):continue
            # Explicit product/form contradictions must not be overridden by order.
            from catalog_recall import product_mismatch
            source=str(item.get('item_name',''))
            target=str(values[row].get('Tên hàng trên phiếu (Ảnh)',''))
            if product_mismatch(source,target) or product_mismatch(target,source):continue
            stronger=any(s>score+.1 for (index,r),s in scores.items() if index==p and r!=row and r not in used)
            if stronger:continue
            mapping[p]=row;used.add(row)
            reasons[p,row]='Tên phù hợp + thứ tự giao NCC đã xác nhận'
    # Suggestions are recomputed after all assignments; occupied rows and tied
    # candidates are not actionable suggestions, nor can two PRs claim a row.
    claimed=set()
    for score,p,row in sorted(((s,p,r) for (p,r),s in scores.items() if p not in mapping and r not in used),reverse=True):
        if p in suggestions or row in claimed:continue
        alternatives=[s for (index,r),s in scores.items() if index==p and r!=row and r not in used]
        competitors=[s for (index,r),s in scores.items() if r==row and index!=p and index not in mapping]
        if alternatives and score-max(alternatives)<.08:continue
        if competitors and score-max(competitors)<.08:continue
        suggestions[p]=row;claimed.add(row)
    return mapping,reasons,suggestions

# Cache only pure calculations, keyed by all inputs. No disk cache or stale
# supplier policy: ordered/manual/full descriptions are part of the key.
from functools import lru_cache,wraps
import json as _json

def _memo_item(function):
    @lru_cache(maxsize=4096)
    def cached(key):return function(_json.loads(key))
    @wraps(function)
    def call(item):return cached(_json.dumps(item,sort_keys=True,ensure_ascii=False,default=str))
    return call
parts=_memo_item(parts)
specification=_memo_item(specification)
pasta_identity=_memo_item(pasta_identity)
_infer_uncached=infer_links
@lru_cache(maxsize=16)
def _infer_cached(key,exact_names):
    items,rows,manual,ordered,blocked=_json.loads(key)
    mapping,reasons,suggestions=_infer_uncached(items,rows,{int(p):r for p,r in manual.items()},exact_names,ordered,{tuple(pair) for pair in blocked})
    return mapping,reasons,suggestions

def infer_links(pr_items,rows,manual,exact_names,ordered=False,blocked=()):
    key=_json.dumps([pr_items,rows,manual,ordered,sorted(blocked)],sort_keys=True,ensure_ascii=False,default=str)
    return tuple(dict(value) for value in _infer_cached(key,exact_names))
