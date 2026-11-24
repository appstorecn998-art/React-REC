"""Readable receipt summaries without mixing different units into one total."""
from fractions import Fraction

def received_items(receipt,lines):
    result=[]
    for index,quantity in sorted(receipt.get('allocations',{}).items(),key=lambda pair:int(pair[0])):
        if Fraction(quantity)==0:continue
        i=int(index);line=lines[i] if i<len(lines) else {}
        result.append((line.get('name','Dòng PR '+str(i+1)),str(quantity),str(line.get('unit','')).capitalize()))
    return result

def short_order(title,oid):
    return title.split(' · ')[0]+' · #'+oid[:8]
