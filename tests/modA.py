from . import modB
from .modB import b_func
from .modB import ClassB as RenamedB


class ClassA(RenamedB):
    def a_func(self):
        return "a"


insance_a = ClassA()


def b_direct():
    return b_func()


def b_through_mod():
    return modB.b_func()


def get_class_b():
    from .modB import ClassB

    return ClassB
