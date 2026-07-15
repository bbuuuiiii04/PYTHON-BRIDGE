"""Canonical-bytes and hash-join rules for the Phase-0 spectral pilot (spec B2)."""
import hashlib
import math
import unittest

from tools.spectral_pilot import canonical as C


class CanonicalBytesTests(unittest.TestCase):
    def test_sort_keys_is_order_independent(self):
        a = C.canonical_bytes({"b": 1, "a": 2})
        b = C.canonical_bytes({"a": 2, "b": 1})
        self.assertEqual(a, b)
        self.assertEqual(a, b'{"a":2,"b":1}')

    def test_no_whitespace_separators(self):
        self.assertEqual(C.canonical_bytes({"x": [1, 2]}), b'{"x":[1,2]}')

    def test_nonfinite_floats_rejected(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                C.canonical_bytes({"v": bad})

    def test_numpy_scalar_rejected_at_boundary(self):
        import numpy as np
        with self.assertRaises(TypeError):
            C.canonical_bytes({"v": np.float64(1.0)})
        with self.assertRaises(TypeError):
            C.canonical_bytes({"v": np.int64(3)})

    def test_negative_zero_normalized(self):
        self.assertEqual(C.canonical_bytes({"v": -0.0}), C.canonical_bytes({"v": 0.0}))
        self.assertEqual(C.canonical_bytes({"v": -0.0}), b'{"v":0.0}')

    def test_float_repr_round_trip(self):
        b = C.canonical_bytes({"v": 0.1})
        self.assertEqual(b, b'{"v":0.1}')

    def test_non_str_keys_rejected(self):
        with self.assertRaises(TypeError):
            C.canonical_bytes({1: "a"})

    def test_sha256_hex_matches_manual(self):
        obj = {"a": 1, "b": [2, 3]}
        expected = hashlib.sha256(C.canonical_bytes(obj)).hexdigest()
        self.assertEqual(C.sha256_hex(obj), expected)
        self.assertEqual(len(C.sha256_hex(obj)), 64)

    def test_jsonl_line_terminated(self):
        line = C.jsonl_line({"a": 1})
        self.assertTrue(line.endswith(b"\n"))
        self.assertEqual(line, b'{"a":1}\n')

    def test_hash_omitting_excludes_digest_field(self):
        full = {"a": 1, "digest": "x"}
        self.assertEqual(C.hash_omitting(full, "digest"), C.sha256_hex({"a": 1}))


class SelectionHashTests(unittest.TestCase):
    def test_join_uses_unit_separator(self):
        expected = hashlib.sha256(b"seed\x1fbeat").hexdigest()
        self.assertEqual(C.selection_hash("seed", "beat"), expected)

    def test_numbers_render_canonically(self):
        expected = hashlib.sha256("s\x1f128\x1f0.5".encode()).hexdigest()
        self.assertEqual(C.selection_hash("s", 128, 0.5), expected)

    def test_field_order_matters(self):
        self.assertNotEqual(C.selection_hash("a", "b"), C.selection_hash("b", "a"))

    def test_negative_zero_field_normalized(self):
        self.assertEqual(C.selection_hash("s", -0.0), C.selection_hash("s", 0.0))

    def test_bool_field_rejected(self):
        with self.assertRaises(TypeError):
            C.selection_hash("s", True)

    def test_nonfinite_field_rejected(self):
        with self.assertRaises(ValueError):
            C.selection_hash("s", math.inf)

    def test_deterministic(self):
        self.assertEqual(C.selection_hash("s", 1, "x"), C.selection_hash("s", 1, "x"))


if __name__ == "__main__":
    unittest.main()
