import unittest

import superreload

class Test(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(1, 1)
        self.assertNotEqual(1, 0)
