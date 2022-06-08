import unittest
import superreload
from .. import modA, modB, utils

# prefix tests that need to go before reload with aaa


class Test(unittest.TestCase):
    def aaa_test_start_conditions(self):
        self.assertEqual(modB.b_func(), "b")
        self.assertEqual(modA.b_direct(), modB.b_func())
        self.assertEqual(modA.b_through_mod(), modB.b_func())

    def test_reload(self):
        try:
            utils.edit_b()
            superreload.reload(modB)
            self.assertEqual(modB.b_func(), "b_edit")
            self.assertEqual(modA.b_direct(), modB.b_func())
            self.assertEqual(modA.b_through_mod(), modB.b_func())
        except:
            raise
        finally:
            utils.restore_b()
