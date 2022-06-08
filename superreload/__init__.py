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

import gc
import logging
import imp
import inspect
import sys
import traceback
import types

logger = logging.getLogger(__name__)


class ModuleReloader(object):
    def _find_subclasses_slow(self, class_type):
        # type: (type) -> list[type]
        """Find all subclasses of a type by tracing sys.modules. Faster
        to call type.__subclasses__(klass), but it doesn't work in python-2
        for old-style classes

        Args:
            class_type (type): Class type to find direct sublcasses.

        Returns:
            list[type]: subclass types.
        """
        subclasses = []
        for other_mod in sys.modules.values():
            for name, obj in inspect.getmembers(other_mod, inspect.isclass):
                if (obj is not class_type) and (
                    class_type in inspect.getmro(obj)
                ):
                    subclasses.append((obj, name))
        return subclasses

    def get_member_references(self, mod, ref_mod):
        # type: (types.ModuleType, types.ModuleType) -> dict[str, object]
        """Get all members of mod that reference ref_mod. Python holds copies
        when functions and classes are imported via 'from ... import ...'.
        Find the copies that mod holds of members of ref_mod.

        Args:
            mod (module): Module being searched for references of ref_Mod
            ref_mod (module): Module being referenced

        Returns:
            dict[str, object]: Map of member name to member being referenced.
        """
        # inspect.getmembers throws import errors on some mods. ex) six.moves
        return {
            name: member
            for name, member in mod.__dict__.items()
            if (inspect.isclass(member) or inspect.isfunction(member))
            and member.__module__ == ref_mod.__name__
        }

    def get_modules_to_update(self, mod):
        # type: (types.ModuleType) -> dict[str, object]
        """Get a map of other module names to member functions that need to be
        updated after mod is reloaded.

        Args:
            mod (module): Module being reloaded.

        Returns:
            dict[str, object]: A map of module names to member functions and
                and objects that need to be updated to the new members of mod.
        """
        update_map = {}
        for other_mod in self.get_other_modules(mod):
            members = self.get_member_references(other_mod, mod)
            if members:
                update_map[other_mod] = members
        return update_map

    def get_other_modules(self, mod):
        # type: (types.ModuleType) -> list[types.ModuleType]
        """Get all modules in sys.modules that aren't mod.

        Args:
            mod (module): Module to skip.

        Returns:
            list[module]: Map of module name to module.
        """
        return [
            m
            for m_name, m in sys.modules.items()
            if m and m_name != mod.__name__
        ]

    def get_subclasses(self, klass):
        # type: (type) -> list[type]
        """Get all subclasses of klass

        Args:
            class_type (type): Class type to find direct sublcasses.

        Returns:
            list[type]: subclass types.
        """
        # Fix me (maybe). subclasses call only works with objects inheriting
        # 'object' in python2. could test and fallback to searching for subclasses?
        # Getting subclasses this way since it also work
        return type.__subclasses__(klass)

    def superreload(self, mod):
        # type: (types.ModuleType) -> None
        """Reloads mod and updates any modules in sys.modules that holds
        copies of its members, anything that subclasses member classes, and
        any instances of the classes.

        Args:
            mod (module): Module to reload.
        """
        old_classes = [m for m in mod.__dict__.values() if inspect.isclass(m)]
        imp.reload(mod)
        self.update_other_modules_refs(mod)

        for old_class in old_classes:
            new_class = mod.__dict__.get(old_class.__name__)
            # If a class has been removed, we won't find it in the new mod
            # dict. Skip it for now, but probably a good idea to log it.
            if not new_class:
                logger.debug(
                    "Could not find {0} in new class {1}.",
                    old_class.__name__,
                    new_class,
                )
                continue
            self.update_subclasses(old_class, new_class)
            self.update_instances(old_class, new_class)

    def update_instances(self, old_class, new_class):
        # type: (type, type) -> None
        """Attempts to update any instances of old_class to new_class. Some
        types (like metaclasses) do not support dynamic retyping.

        Args:
            old_class (type): Old class type to find instances
            new_class (type): New type to upgrade them to.
        """
        for ref in gc.get_referrers(old_class):
            if type(ref) is old_class:
                try:
                    ref.__class__ = new_class
                # Failure to update an instance to a new class is
                # a considered a non-critical fail. Log it and continue.
                except:
                    logger.debug("Could not update instance.")
                    logger.debug(traceback.format_exc())

    def update_other_modules_refs(self, mod):
        # type: (types.ModuleType) -> None
        """Updates any modules in sys.modules that holds
        copies of mod's members

        Args:
            mod (mod): Module being reloaded to find references of.
        """
        modules_to_update = self.get_modules_to_update(mod)
        for mod_to_update, members_to_update in modules_to_update.items():
            external_members_update_map = {}
            for member_name, old_member in members_to_update.items():
                # Get the name from the old_member object because it should
                # match the name in the reloaded module. member_name could
                # be different if the mod_to_update used 'as' in the import
                new_member = mod.__dict__.get(old_member.__name__)
                # If the new member isn't found it should probably result in
                # an import error?
                if not new_member:
                    logger.debug(
                        "Could not find {0} in reloaded mod {1}.",
                        old_member.__name__,
                        mod,
                    )
                    continue
                external_members_update_map[member_name] = new_member
            mod_to_update.__dict__.update(external_members_update_map)

    def update_subclasses(self, old_class, new_class):
        # type: (type, type) -> None
        """Find subclasses of old_class and update them to new_class

        Args:
            old_class (type): Old Class to find subclasses
            new_class (type): New Class to update to
        """
        for subclass in self.get_subclasses(old_class):
            new_bases = []
            for base in subclass.__bases__:
                if base.__module__ == new_class.__module__:
                    if base.__name__ == new_class.__name__:
                        new_bases.append(new_class)
                else:
                    new_bases.append(base)
            subclass.__bases__ = tuple(new_bases)


def reload(mod):
    # type: (types.ModuleType) -> None
    """Simple entry point for module reloading. Calls
    ModuleReloader().superreload(mod)

    Args:
        mod (module): Module to reload
    """
    ModuleReloader().superreload(mod)
