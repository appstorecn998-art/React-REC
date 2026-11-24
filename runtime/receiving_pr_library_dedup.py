"""Hide proven unposted page-subsets; never merge documents or ledger balances."""
from collections import defaultdict

def compact_cards(cards):
    from receiving_pr_number_identity import scoped_document_key
    from receiving_pr_library import images_for
    from receiving_image_archive import source_digest
    groups=defaultdict(list);proofs={};hidden=set()
    for card in cards:
        key=scoped_document_key(card['record'])
        if key and len(key)==4 and key[2] and key[3]:groups[key].append(card)
        try:proofs[card['key']]=frozenset(source_digest(p) for p in images_for(card['record']))
        except (OSError,ValueError,KeyError):proofs[card['key']]=None
    for group in groups.values():
        for card in group:
            if card.get('has_ledger'):continue
            pages=proofs[card['key']]
            if not pages:continue
            candidates=[other for other in group if other['key']!=card['key'] and proofs[other['key']] and pages<proofs[other['key']] and other['count']>=card['count']]
            if not candidates:continue
            candidates.sort(key=lambda c:(not c.get('has_ledger'),-len(proofs[c['key']]),c['key']))
            best=candidates[0]
            # An ambiguous same-size full set must remain visible for review.
            equally_good=[c for c in candidates if bool(c.get('has_ledger'))==bool(best.get('has_ledger')) and len(proofs[c['key']])==len(proofs[best['key']])]
            if len({proofs[c['key']] for c in equally_good})>1:continue
            hidden.add(card['key']);best.setdefault('hidden_page_keys',[]).append(card['key'])
        visible=[c for c in group if c['key'] not in hidden]
        for card in visible:
            notes=[]
            if card.get('hidden_page_keys'):notes.append(f"Bộ đầy đủ {len(proofs[card['key']])} trang · đã ẩn {len(card['hidden_page_keys'])} bản lẻ")
            if len(visible)>1:notes.append('Có bản khác cùng số/ngày/NCC/bộ phận — cần đối chiếu ảnh')
            card['duplicate_note']=' · '.join(notes)
    return [c for c in cards if c['key'] not in hidden]
