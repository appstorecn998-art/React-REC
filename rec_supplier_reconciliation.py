"""Resolve receipt suppliers for reconciliation without rewriting OCR evidence."""
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from difflib import SequenceMatcher
from threading import RLock

from rec_debt_totals import amount
from receiving_service import atomic_json, sheet_signature, snapshot
from supplier_directory import load_supplier_directory, supplier_aliases
from supplier_rules import normalize_name

guard = RLock()
UNKNOWN = {'', 'chua ro', 'chua ro ncc', 'ncc chua ro', 'khong xac dinh'}


def tax_number(raw):
    value = str(raw or '').strip()
    return value if re.fullmatch(r'[0-9]{10}(?:-?[0-9]{3})?', value) else ''


class SupplierResolver:
    def __init__(self, profile, store):
        self.rules_path = profile / 'NhaCungCap.json'
        self.overrides_path = store / '.receiving' / 'supplier-confirmations.json'
        self.directory, taxes = load_supplier_directory(profile / 'DanhMuc.xlsm', include_tax=True)
        self.rules = json.loads(self.rules_path.read_text(encoding='utf-8-sig'))
        self.aliases = supplier_aliases(self.rules, self.directory)
        self.names = defaultdict(set)
        self.taxes = defaultdict(set)
        for code, name in self.directory.items():
            self.names[normalize_name(name)].add(code)
            tax = tax_number(taxes.get(code)).replace('-', '')
            if tax:
                self.taxes[tax].add(code)
        self.overrides = (json.loads(self.overrides_path.read_text(encoding='utf-8'))
                          if self.overrides_path.exists() else {})

    def resolve(self, receipt_id, version, names, taxes):
        keys = {normalize_name(name) for name in names} - UNKNOWN
        name_matches = [self.names[key] | ({self.aliases[key]} if key in self.aliases else set())
                        for key in keys]
        tax_matches = [self.taxes.get(tax.replace('-', ''), set()) for tax in taxes]
        known = set().union(*name_matches, *tax_matches)
        manual = self.overrides.get(receipt_id, {})
        reason = 'Tên OCR chưa khớp danh mục'
        code = ''
        if manual.get('version') == version and manual.get('code') in self.directory:
            code, reason = manual['code'], 'Đã xác nhận cho phiếu'
        elif len(known) > 1 or len(taxes) > 1:
            reason = 'Các thông tin trên phiếu trỏ đến nhiều nhà cung cấp'
        elif len(known) == 1 and tax_matches and all(tax_matches):
            code, reason = next(iter(known)), 'Khớp mã số thuế'
        elif len(known) == 1 and name_matches and all(name_matches) and not taxes:
            code, reason = next(iter(known)), 'Khớp tên chính thức hoặc tên đã duyệt'
        elif taxes:
            reason = 'Cần kiểm lại mã số thuế'
        if code:
            candidates = []
        elif known:
            candidates = sorted(known)
        else:
            scores = []
            for candidate, name in self.directory.items():
                options = [normalize_name(name)] + [alias for alias, target in self.aliases.items() if target == candidate]
                score = max((SequenceMatcher(None, key, option).ratio()
                             for key in keys for option in options), default=0)
                if score >= .55:
                    scores.append((score, candidate))
            candidates = [code for _, code in sorted(scores, reverse=True)[:3]]
        return dict(code=code or None, name=self.directory.get(code), reason=reason,
                    candidates=[dict(code=candidate, name=self.directory[candidate]) for candidate in candidates])

    def receipts(self, reports, month=None):
        for day, report in reports.items():
            if month and day[:7] != month:
                continue
            for sheet, rows in snapshot(report)[1]:
                if not rows:
                    continue
                receipt_id = f'{day}::{sheet}'
                # Warehouse/time edits preserve supplier confirmation. A change
                # to source rows or supplier evidence requires review again.
                evidence = [(index, {key: row.get(key) for key in (
                    'Tên hàng trên phiếu (Ảnh)', 'Ảnh nguồn', 'SHA-256 ảnh nguồn',
                    'Nhà cung cấp', 'Nhà cung cấp trên chứng từ', 'Mã số thuế bên bán'
                )}) for index, row in rows]
                version = sheet_signature(sheet, evidence)
                names = sorted({str(row.get(key) or '').strip() for _, row in rows
                                for key in ('Nhà cung cấp', 'Nhà cung cấp trên chứng từ')} - {''})
                taxes = sorted({tax.replace('-', '') for _, row in rows
                                for raw in str(row.get('Mã số thuế bên bán') or '').split(';')
                                if (tax := tax_number(raw))})
                total = Decimal(0)
                missing = 0
                for _, row in rows:
                    quantity, price = amount(row.get('Thực nhận')), amount(row.get('Đơn giá'))
                    if quantity is None or price is None:
                        missing += 1
                    else:
                        total += quantity * price
                yield dict(id=receipt_id, day=day, sheet=sheet, version=version, rawNames=names,
                           taxNumbers=taxes, provisional=format(total, 'f'), missingRows=missing,
                           supplier=self.resolve(receipt_id, version, names, taxes))

    def confirm(self, reports, payload):
        receipt_id, code = payload.get('id'), payload.get('code')
        if not isinstance(receipt_id, str) or not isinstance(code, str) or code not in self.directory:
            raise ValueError('Chọn phiếu và mã có trong danh mục nhà cung cấp.')
        day = receipt_id.partition('::')[0]
        receipt = next((r for r in self.receipts({day: reports[day]}) if r['id'] == receipt_id), None) if day in reports else None
        if not receipt or receipt['version'] != payload.get('version'):
            raise ValueError('Phiếu đã thay đổi. Tải lại trước khi xác nhận.')
        reason = payload.get('reason')
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
            raise ValueError('Nhập lý do xác nhận, tối đa 500 ký tự.')
        alias = payload.get('alias')
        if alias is not None:
            if not isinstance(alias, str) or alias not in receipt['rawNames']:
                raise ValueError('Chọn tên đọc trên chính phiếu này.')
            key = normalize_name(alias)
            if key in UNKNOWN or len(key.split()) < 2:
                raise ValueError('Tên quá ngắn hoặc chung chung. Hãy xác nhận riêng phiếu.')
            targets = self.names[key] | ({self.aliases[key]} if key in self.aliases else set())
            if targets - {code}:
                raise ValueError('Tên này đang thuộc mã nhà cung cấp khác.')
            # Compare the exact effect of the proposed rule, including tax
            # conflicts and existing manual confirmations.
            before = list(self.receipts(reports))
            self.aliases[key] = code
            affected = [
                {**row, 'proposedSupplier': updated}
                for row in before if key in {normalize_name(n) for n in row['rawNames']}
                and (updated := self.resolve(row['id'], row['version'], row['rawNames'], row['taxNumbers']))
                != row['supplier'] and updated['code'] != row['supplier']['code']
            ]
            confirmation = hashlib.sha256(json.dumps(
                [receipt_id, receipt['version'], code, key, affected], sort_keys=True,
                ensure_ascii=False).encode()).hexdigest()
            if payload.get('previewToken') != confirmation:
                return dict(saved=False, previewToken=confirmation, affected=affected)
            if not targets:
                self.rules.setdefault('supplier_aliases', []).append(dict(
                    invoice_name=alias, supplier_code=code, reason=reason.strip(),
                    confirmed_at=datetime.now(timezone.utc).isoformat()))
                atomic_json(self.rules_path, self.rules)
        else:
            self.overrides[receipt_id] = dict(code=code, version=receipt['version'],
                                             reason=reason.strip(), at=datetime.now(timezone.utc).isoformat(),
                                             previous=self.overrides.get(receipt_id))
            atomic_json(self.overrides_path, self.overrides)
        return dict(saved=True, scope='alias' if alias is not None else 'receipt')


def reconciliation(profile, store, reports, month):
    if not isinstance(month, str) or not re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', month):
        raise ValueError('Chọn kỳ theo dạng YYYY-MM.')
    with guard:
        resolver = SupplierResolver(profile, store)
        groups = {}
        for receipt in resolver.receipts(reports, month):
            supplier = receipt['supplier']
            code = supplier['code']
            group = groups.setdefault(code, dict(code=code, name=supplier['name'] or 'Chưa xác định nhà cung cấp',
                                                receipts=[], provisional=Decimal(0), missingRows=0))
            group['receipts'].append(receipt)
            group['provisional'] += Decimal(receipt['provisional'])
            group['missingRows'] += receipt['missingRows']
        for group in groups.values():
            group['provisional'] = format(group['provisional'], 'f')
        return dict(month=month, periodBasis='reportDay', suppliers=list(groups.values()),
                    directory=[dict(code=code, name=name) for code, name in resolver.directory.items()])
