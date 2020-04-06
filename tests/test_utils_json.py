# -*- coding: utf-8 -*-
import unittest

from streamlink.utils.jsonutil import from_js


class TestUtilsJSON(unittest.TestCase):

    def test_string_literal(self):
        self.assertEqual(
            from_js('{test: "test"}'),
            {"test": "test"}
        )

    def test_string_literal_unary(self):
        # negative strings dont make much sense, in JS the become NaN
        self.assertEqual(
            from_js('{test: -"test"}'),
            {"test": '-"test"'})

    def test_NaN(self):
        self.assertEqual(from_js('{test: NaN}'), {"test": "NaN"})

    def test_int_literal(self):
        self.assertEqual(from_js('{test: 234}'), {"test": 234})
        self.assertEqual(from_js('{test: 0}'), {"test": 0})
        self.assertEqual(from_js('{test: -487783}'), {"test": -487783})
        self.assertEqual(from_js('{test: +487783}'), {"test": 487783})

    def test_boolean_literal(self):
        self.assertEqual(
            from_js('''{test: true}'''),
            {"test": True}
        )
        self.assertEqual(
            from_js('''{test: false}'''),
            {"test": False}
        )

    def test_float_literal(self):
        self.assertEqual(
            from_js('''{test: 1.2}'''),
            {"test": 1.2}
        )
        self.assertEqual(
            from_js('''{test: 0.0}'''),
            {"test": 0.0}
        )
        self.assertEqual(
            from_js('''{test: -1.0}'''),
            {"test": -1.0}
        )

    def test_plain_literal_extra_comma(self):
        self.assertEqual(
            from_js('{test: "test",}'),
            {"test": "test"}
        )

    def test_plain_json_extra_comma(self):
        self.assertEqual(
            from_js('{"test": "test",}'),
            {"test": "test"}
        )

    def test_plain_literal_multi_key(self):
        self.assertEqual(
            from_js('{test: "test", "test2": "test2"}'),
            {"test": "test", "test2": "test2"}
        )

    def test_list_of_literals(self):
        self.assertEqual(
            from_js('{test: [1, 2, 3]}'),
            {"test": [1, 2, 3]}
        )

    def test_list_of_lists_of_literals(self):
        self.assertEqual(
            from_js('{test: [[1], [2], [3]]}'),
            {"test": [[1], [2], [3]]}
        )

    def test_list_of_lists_of_mixed_literals(self):
        self.assertEqual(
            from_js('{test: [[1], 2, ["3"]]}'),
            {"test": [[1], 2, ["3"]]}
        )

    def test_nested_object(self):
        self.assertEqual(
            from_js('''{test: {test: "test"}}'''),
            {"test": {"test": "test"}}
        )

    def test_binary_expression(self):
        self.assertEqual(
            from_js('''{test: 1+2}'''),
            {"test": "1+2"}
        )

    def test_fail_binary_expression(self):
        self.assertRaises(
            ValueError,
            from_js, ('''1+2''',)
        )

    def test_array(self):
        self.assertEqual(from_js('''[1, 2, 3]'''), [1, 2, 3])
        self.assertEqual(from_js('''["1", 2, 3]'''), ["1", 2, 3])
        self.assertEqual(from_js('''[{"test": [1,2,3]}]'''), [{"test": [1, 2, 3]}])

    def test_with_whitespace(self):
        self.assertEqual(from_js('''  [ 1   ,  2 ,    3  ]'''), [1, 2, 3])
        self.assertEqual(from_js('''  {   test   : 1  }'''), {"test": 1})
        self.assertEqual(from_js('''  \n[\n 1\n   ,\n  2\n ,\n    3\n  ]\n'''), [1, 2, 3])
        self.assertEqual(from_js(''' \n\r {   test   :\n\r \n\n1  }'''), {"test": 1})

    def test_fails(self):
        self.assertRaises(
            ValueError,
            from_js, ('[1, 2, 3',)
        )
        self.assertRaises(
            ValueError,
            from_js, ('{',)
        )
