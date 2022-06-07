# superreload https://github.com/dougrizeakos/superreload
# Copyright (C) 2022 Doug Rizeakos.

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import imp
import sys
import inspect
import gc
from functools import partial

class ModuleReloader(object):
    def is_external_member(self, mod, member):
        if inspect.isclass(member) or inspect.isfunction(member):
            if member.__module__ != mod.__name__:
                return True
        return False

    def get_external_members(self, mod):
        predicate = partial(self.is_external_member, mod)
        return inspect.getmembers(mod, predicate=predicate)

    def get_modules_to_update(self, mod):
        update_map = {}
        other_mods = [m for m_name, m in sys.modules.items() 
                      if m and m_name != mod.__name__]
        # Get all external members other modules and see if they 
        # reference anything in the current module.
        for other_mod in other_mods:
            members = {n: m for n, m in self.get_external_members(other_mod)
                       if m.__module__ == mod.__name__}
            if members:
                update_map[other_mod] = members
        return update_map
        
    def _find_subclasses_slow(self, classType):
        subclasses = []
        for other_mod in sys.modules.values():
            for name, obj in inspect.getmembers(other_mod, inspect.isclass):
                if (obj is not classType) and (classType in inspect.getmro(obj)):
                    subclasses.append((obj, name))
        return subclasses

    def get_subclasses(self, klass):
        # Fix me (maybe). subclasses call only works with objects inheriting 
        # 'object' in python2. could test and fallback to searching for subclasses?
        return type.__subclasses__(klass)

    def update_other_modules_refs(self, mod):
        modules_to_update = self.get_modules_to_update(mod)
        for mod_to_update, members_to_update in modules_to_update.items():
            external_members_update_map = {}
            for member_name, old_member in members_to_update.items():
                # Get the name from the old_member object because it should 
                # match the name in the reloaded module. member_name could 
                # be different if the mod_to_update used 'as' in the import
                new_member = mod.__dict__.get(old_member.__name__)
                # Fix me. Better error logging.
                if not new_member:
                    print("can't find member")
                    continue
                external_members_update_map[member_name] = new_member
            mod_to_update.__dict__.update(external_members_update_map)

    def update_subclasses(self, old_class, new_class):
        for subclass in self.get_subclasses(old_class):
            new_bases = []
            for base in subclass.__bases__:
                if base.__module__ == new_class.__module__:
                    if base.__name__ == new_class.__name__:
                        new_bases.append(new_class)
                else:
                    new_bases.append(base)
            subclass.__bases__ = tuple(new_bases)

    def update_instances(self, old_class, new_class):
        for ref in gc.get_referrers(old_class):
            if type(ref) is old_class:
                try:
                    ref.__class__ = new_class
                # Fixme better error logging
                except:
                    print("couldn't update instance")

    def superreload(self, mod):
        old_classes = [m for m in mod.__dict__.values() if inspect.isclass(m)]
        imp.reload(mod)
        self.update_other_modules_refs(mod)

        for old_class in old_classes:
            new_class = mod.__dict__.get(old_class.__name__)
            # Fix me. Better error reporting
            if not new_class:
                print("can't find new class")
                continue
            self.update_subclasses(old_class, new_class)
            self.update_instances(old_class, new_class)

def reload(mod):
    ModuleReloader().superreload(mod)
