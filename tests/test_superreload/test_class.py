import unittest
import superreload
from .. import modA, modB, utils

# prefix tests that need to go before reload with aaa


class Test(unittest.TestCase):
    def aaa_test_start_conditions(self):
        self.assertEqual(modB.ClassB().b_func(), "b")

    def test_reload(self):
        try:
            utils.edit_b()
            instance_b = modB.ClassB()
            superreload.reload(modB)
            new_val = "b_edit"

            # Test an old instance
            self.assertEqual(instance_b.b_func(), new_val)
            # Test a global instance
            self.assertEqual(modA.insance_a.b_func(), new_val)
            # Test a new instance
            self.assertEqual(modA.ClassA().b_func(), new_val)

            # Check if modules are in sync
            self.assertEqual(modB.ClassB, modA.RenamedB)
            self.assertEqual(modB.ClassB, modA.get_class_b())

            # Make sure isinstance works
            self.assertTrue(isinstance(instance_b, modB.ClassB))
            self.assertTrue(isinstance(modA.insance_a, modB.ClassB))
            self.assertTrue(isinstance(modA.ClassA(), modB.ClassB))
        except:
            raise
        finally:
            utils.restore_b()
