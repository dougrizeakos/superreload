import os
import shutil

parent_path = os.path.dirname(os.path.abspath(__file__))
mod_b_path = os.path.join(parent_path, "modB.py")
edit_b_path = os.path.join(parent_path, "modB_edited.py")
orig_b_path = os.path.join(parent_path, "modB_orig.py")


def edit_b():
    shutil.copy(mod_b_path, orig_b_path)
    shutil.copy(edit_b_path, mod_b_path)


def restore_b():
    shutil.copy(orig_b_path, mod_b_path)
    os.remove(orig_b_path)
