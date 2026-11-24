"""Display ordering only; PR indices and matching data never change."""
def ordered(results,items,rows,mode):
    if mode=='pr':return list(results)
    positions={row:i for i,(row,_) in enumerate(rows)}
    return sorted(results,key=lambda r:(0,positions[r['row']]) if r.get('row') in positions else (1,r.get('pr_index',len(items))))

def label(result,items):
    p=result.get('pr_index')
    if p is None:return 'Ngoài PR · '+str(result.get('name',''))
    n=str(items[p].get('source_stt') or p+1)
    return 'PR '+n+' · '+str(result.get('name',''))
