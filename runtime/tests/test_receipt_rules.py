import argparse
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import AutoWatcher as aw
from receipt_rules import apply_receipt_rules


def item(mark, received="", quantity="10"):
    return {"item_name": "Hàng thử", "invoice_name": "Hàng thử", "line_id": "DE1:1",
            "quantity": quantity, "received_quantity": received, "receipt_mark": mark,
            "catalog_code": "001", "confidence": 95, "needs_review": False, "note": "",
            "english_name": "Test item", "vietnamese_name": "Hàng thử", "unit": "kg",
            "unit_price": "25.000", "line_amount": "250.000", "specification": "", "group_id": ""}


class ReceiptRulesTests(unittest.TestCase):
    catalog = {"001": ("Test item/Hàng thử", "kg")}

    def test_four_confirmed_cases_and_explicit_written_values(self):
        cases = [("cross_with_number", "4,2", 4.2), ("cross_without_number", "", 0),
                 ("check", "", 10), ("unmarked", "", 10), ("written", "0", 0),
                 ("written", "3", 3)]
        for mark, received, expected in cases:
            with self.subTest(mark=mark, received=received):
                source = item(mark, received)
                apply_receipt_rules(source, aw.parse_simple_quantity)
                self.assertEqual(aw.parse_simple_quantity(source["received_quantity"]), aw.Decimal(str(expected)))
                self.assertFalse(source["receipt_needs_review"])
                self.assertEqual(source["quantity"], "10")
                self.assertEqual(aw.delivery_quantity_for_compare(source), aw.Decimal(str(expected)))

    def test_cross_without_number_overrides_ai_copy_of_printed_quantity(self):
        source = item("cross_without_number", "10")
        apply_receipt_rules(source, aw.parse_simple_quantity)
        self.assertEqual(source["received_quantity"], "0")

    def test_unclear_is_not_treated_as_zero_or_full_delivery(self):
        for mark, received, quantity in [("unclear", "10", "10"),
                                         ("cross_with_number", "?", "10"),
                                         ("cross_with_number", "", "10"),
                                         ("written", "mờ", "10"), ("check", "", "mờ")]:
            with self.subTest(mark=mark, received=received, quantity=quantity):
                source = item(mark, received, quantity)
                apply_receipt_rules(source, aw.parse_simple_quantity)
                self.assertTrue(source["receipt_needs_review"])
                self.assertEqual(source["received_quantity"], "")
                self.assertIsNone(aw.delivery_quantity_for_compare(source))

    def test_legacy_data_without_mark_is_not_guessed(self):
        source = item("unmarked")
        del source["receipt_mark"]
        apply_receipt_rules(source, aw.parse_simple_quantity)
        self.assertEqual(source["received_quantity"], "")
        self.assertNotIn("receipt_needs_review", source)

    def test_invalid_mark_is_rejected(self):
        with self.assertRaises(ValueError):
            apply_receipt_rules(item("made_up"), aw.parse_simple_quantity)

    def test_pr_items_are_not_given_actual_receipts(self):
        source = item("not_applicable")
        document = {"document_type": "pr", "reference_id": "PR1", "supplier_name": "",
                    "items": [source]}
        aw.validate_batch_document(document)
        self.assertEqual(source["received_quantity"], "")
        self.assertNotIn("receipt_needs_review", source)

    def test_validation_normalizes_delivery_before_cache_save(self):
        document = {"document_type": "delivery", "reference_id": "", "supplier_name": "NCC",
                    "items": [item("cross_without_number")]}
        aw.validate_batch_document(document)
        cached = json.loads(json.dumps(document))
        aw.validate_batch_document(cached)
        self.assertEqual(cached["items"][0]["received_quantity"], "0")

    def test_batch_compare_overrides_ai_match_with_zero_receipt(self):
        pr = [{"line_id": "PR1:1", "quantity": "10"}]
        delivery = [item("cross_without_number")]
        comparison = {"status": "match", "summary": "AI nói khớp", "rows": [{
            "pr_line_ids": ["PR1:1"], "delivery_line_ids": ["DE1:1"],
            "status": "match", "note": ""}]}
        checked = aw.validate_batch_comparison(comparison, pr, delivery)
        self.assertEqual(checked["rows"][0]["status"], "mismatch")

    def test_batch_compare_cannot_claim_match_when_receipt_unclear(self):
        pr = [{"line_id": "PR1:1", "quantity": "10"}]
        delivery = [item("unclear")]
        comparison = {"status": "match", "summary": "", "rows": [{
            "pr_line_ids": ["PR1:1"], "delivery_line_ids": ["DE1:1"],
            "status": "match", "note": ""}]}
        checked = aw.validate_batch_comparison(comparison, pr, delivery)
        self.assertEqual(checked["rows"][0]["status"], "uncertain")
        self.assertEqual(checked["status"], "uncertain")

    def test_pair_compare_uses_receipt_mark_and_preserves_for_report(self):
        delivery = item("cross_without_number")
        data = {"documents": [
            {"source_image": 1, "document_type": "pr", "items": [{"item_name": "Hàng thử", "quantity": "10"}]},
            {"source_image": 2, "document_type": "delivery", "items": [delivery]}],
            "comparison": {"status": "match", "summary": "", "rows": [
                {"pr_line": 1, "delivery_line": 1, "status": "match", "note": ""}]}}
        extracted, comparison = aw.validate_pair_analysis(data)
        self.assertEqual(comparison["status"], "mismatch")
        self.assertEqual(extracted["items"][0]["received_quantity"], "0")

    def test_report_and_final_keep_zero_distinct_from_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TongHop.xlsx"
            sources = [item("cross_without_number"), item("check"), item("cross_with_number", "4.2")]
            rows = aw.validate_rows({"items": sources}, self.catalog)
            aw.write_result(path, Path("test.jpg"), rows)
            final = aw.reviewed_delivery_rows(path, self.catalog)[0]
            self.assertEqual([r["received"] for r in final], [0, 10, 4.2])
            self.assertEqual([r["amount"] for r in final], [250000] * 3)
            unknown = aw.validate_rows({"items": [item("unclear")]}, self.catalog)
            self.assertEqual(unknown[0][5], "CẦN KIỂM TRA")
            self.assertEqual(unknown[0][13], "CHƯA RÕ")
            aw.write_result(path, Path("test.jpg"), unknown)
            with self.assertRaisesRegex(ValueError, "chưa rõ số thực nhận"):
                aw.reviewed_delivery_rows(path, self.catalog)

    def test_cached_resolver_restores_mark_and_zero_from_ocr(self):
        source = item("cross_without_number")
        resolved = {"items": [{"line_id": "DE1:1", "received_quantity": "10"}]}
        checked = aw.restore_delivery_source_fields(resolved, [source])
        self.assertEqual(checked["items"][0]["received_quantity"], "0")

    def test_rule_change_invalidates_ocr_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rules = root / "NhaCungCap.json"
            rules.write_text('{"version":1,"suppliers":[]}', encoding="utf-8")
            args = argparse.Namespace(output=root, rules=rules)
            before = aw.batch_document_cache_path(Path("image.jpg"), b"same-image", args, {}, "same-model")
            with patch.object(aw, "receipt_rules_fingerprint", return_value=b"changed-confirmed-rule"):
                after = aw.batch_document_cache_path(Path("image.jpg"), b"same-image", args, {}, "same-model")
            self.assertNotEqual(before, after)

    def test_ocr_receives_examples_and_target_image_with_receipt_contract(self):
        from types import SimpleNamespace
        document = {"document_type": "delivery", "reference_id": "", "supplier_name": "NCC",
                    "items": [item("cross_without_number")]}
        response = SimpleNamespace(status="completed", output_text=json.dumps(document))
        with patch.object(aw.genai, "Client") as factory:
            client = factory.return_value.__enter__.return_value
            client.interactions.create.return_value = response
            checked = aw.request_batch_document("unused", "model", b"target-image", {}, 3)
            sent = client.interactions.create.call_args.kwargs
        images = [x for x in sent["input"] if x["type"] == "image"]
        self.assertEqual(len(images), 5)
        import base64
        self.assertEqual(base64.b64decode(images[-1]["data"]), b"target-image")
        self.assertIn("receipt_mark", sent["response_format"]["schema"]["properties"]["items"]["items"]["required"])
        self.assertEqual(checked["items"][0]["received_quantity"], "0")

    def test_legacy_single_image_keeps_receipt_fields_after_code_matching(self):
        from types import SimpleNamespace
        extracted = {"supplier_name": "NCC", "items": [
            {"invoice_name": "Hàng thử", "group_id": "", "quantity": "10",
             "received_quantity": "", "receipt_mark": "check"}]}
        matched = {"items": [{"invoice_name": "Hàng thử", "catalog_code": "001",
                              "confidence": 95, "needs_review": False, "note": ""}]}
        with patch.object(aw.genai, "Client") as factory:
            client = factory.return_value.__enter__.return_value
            client.interactions.create.side_effect = [
                SimpleNamespace(status="completed", output_text=json.dumps(value))
                for value in [extracted, matched]]
            result = aw.request_items("unused", "model", b"image", self.catalog, 3,
                                      {"001": ("1410", "Trái cây")}, {"suppliers": []})
        row = aw.validate_rows(result, self.catalog)[0]
        self.assertEqual(row[12:14], [10, 10])
