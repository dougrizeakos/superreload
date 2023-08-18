
import gc
import importlib
import inspect
import logging
import sys
import traceback
from types import BuiltinFunctionType, FunctionType, ModuleType
from typing import Callable, Iterator, Union, Optional

logger = logging.getLogger(__name__)

ClassOrFunction = Union[type, FunctionType]

# 
# method for getting subclasses for py2 objects that don't
# inherit object, left here for reference.
# 
def _find_subclasses_slow_py2(class_type: (type)) -> list[type]:
    subclasses = []
    for other_mod in sys.modules.values():
        for name, obj in inspect.getmembers(other_mod, inspect.isclass):
            if (obj is not class_type) and (
                class_type in inspect.getmro(obj)
            ):
                subclasses.append((obj, name))
    return subclasses

# 
# helper methods pulled out for readability/portability
# 

def _get_full_member_name(member: ClassOrFunction) -> str:
    """Get the full name for a function or class in a module"""
    return member.__module__ + "." + member.__name__


def _get_mro(class_: type) -> tuple[type, ...]:
    """Safely get method resolution order. type + parent types."""
    if not hasattr(class_, "__mro__"):
        return ()
    return class_.__mro__


def _get_subclasses(class_: type) -> list[type]:
    """Get all subclasses of class_"""
    return type.__subclasses__(class_)


def _iter_external_members(mod: ModuleType) -> Iterator[tuple[str, ClassOrFunction]]:
    """Get an iterator over a module's external functions and classes."""
    for member_name, member in _iter_members(mod):
        if member.__module__ != mod.__name__:
            yield (member_name, member)


def _iter_internal_members(mod: ModuleType) -> Iterator[tuple[str, ClassOrFunction]]:
    """Get an iterator over a module's internal functions and classes."""
    for member_name, member in _iter_members(mod):
        if member.__module__ == mod.__name__:
            yield (member_name, member)


def _iter_modules() -> Iterator[ModuleType]:
    """Iterate over valid modules in sys.modules."""
    for mod in sys.modules.values():
        if mod:
            yield mod


def _iter_members(mod: ModuleType) -> Iterator[tuple[str, ClassOrFunction]]:
    """Get an iterator over a module's functions and classes."""
    for member_name, member in mod.__dict__.items():
        if inspect.isclass(member) or inspect.isfunction(member):
            if member.__module__ is not None:
                yield (member_name, member)


class _ModuleUpdator(object):
    _old_members_set = set()  # stashed old member set for quick 'in' checks
    _old_members_map = {}  # stashed old members for updating later
    _reference_cache = {}  # stashed member name to list of objs referring to it
    _instance_cache = {}  # cache of objects to their instances to update

    @classmethod
    def _build_external_reference_cache(cls) -> None:
        """Build cache of member name to list of objs referring to it."""
        cls._reference_cache.clear()
        for mod in _iter_modules():
            for member_name, member in _iter_external_members(mod):
                if member not in cls._old_members_set:
                    continue
                key = _get_full_member_name(member)
                cls._reference_cache.setdefault(key, []).append(
                    (mod, member_name, member)
                )

    @classmethod
    def _build_instance_cache(cls) -> None:
        """Build cache of objects to their instances to update."""
        cls._instance_cache.clear()
        for obj in gc.get_objects():
            if type(obj) in cls._old_members_set:
                cls._instance_cache.setdefault(type(obj), []).append(obj)

    @classmethod
    def _build_old_member_cache(cls, mods: list[ModuleType]) -> None:
        """Build caches to look up old members after reload/update."""
        cls._old_members_set.clear()
        cls._old_members_map.clear()
        for mod in mods:
            for _, member in _iter_members(mod):
                cls._old_members_set.add(member)
            cls._old_members_map[mod.__name__] = mod.__dict__.copy()

    @classmethod
    def build_caches(cls, mods: list[ModuleType]):
        """Builds all internally used caches."""
        cls._build_old_member_cache(mods)
        # The following rely on the old_member cache, so they must go after.
        cls._build_external_reference_cache()
        cls._build_instance_cache()

    @classmethod
    def superreload(cls, mods: list[ModuleType]) -> None:
        """
        Reloads mods and then updates any modules in sys.modules that holds copies of its members
        
        This includes anything that subclasses member classes, and any instances of the classes.
        """
        cls.build_caches(mods)

        max_fails = 10
        fail_counter = {}
        to_reload = mods[:]
        errors = {}
        reloaded_mods = []
        while to_reload:
            mod = to_reload.pop(0)
            # Try to reload, but allow a number of failures. This helps
            # account for new funcitons/classes and avoid trying to trace
            # import dependencies. Last reload allows errors to bubble up.
            print("Reloading {}".format(mod.__name__))
            fails = fail_counter.get(mod, 0)
            if fails < max_fails:
                try:
                    importlib.reload(mod)
                    reloaded_mods.append(mod)
                except:
                    cur_fails = fails + 1
                    if cur_fails == max_fails:
                        print("\tFailed. No more retries. Skipping.")
                        errors[mod] = traceback.format_exc()

                    else:
                        txt = (
                            "Failed. Adding to the end of the list. n retries: "
                        )
                        print("\t" + txt + str(max_fails - cur_fails))
                        fail_counter[mod] = cur_fails
                        to_reload.append(mod)

        cls.update_stale_modules_and_instances(reloaded_mods)

        # Report errors.
        for mod, error in errors.items():
            logger.error("Failed to reload %s", mod.__name__)
            logger.error(error)

    @classmethod
    def superwrapper(cls, mods: list[ModuleType], wrapper_fxn: Callable):
        """Wrapps all functions and methods in modules in wrapper function."""
        cls.build_caches(mods)

        for mod in mods:
            updates = {}
            internal_members = list(_iter_internal_members(mod))
            for member_name, member in internal_members:
                wrapped = None
                if inspect.isfunction(member):
                    full_name = member.__module__ + "." + member.__name__
                    wrapped = wrapper_fxn(member, full_name)
                    updates[member_name] = wrapped
                if inspect.isclass(member):
                    wrapped = cls.wrap_class(member, wrapper_fxn)
                    updates[member_name] = wrapped
            mod.__dict__.update(updates)

        cls.update_stale_modules_and_instances(mods)

    @classmethod
    def update_instances(cls, old_class: type, new_class: type) -> None:
        """
        Update any instances of old_class to new_class.
        
        Some types (like metaclasses) do not support dynamic retyping.
        """
        for ref in cls._instance_cache.get(old_class, []):
            try:
                ref.__class__ = new_class
            # Failure to update an instance to a new class is
            # a considered a non-critical fail. Log it and continue.
            except:
                logger.debug("Could not update instance.")
                logger.debug(traceback.format_exc())

    @classmethod
    def update_other_modules_refs(cls, mod: ModuleType) -> None:
        """Updates any modules in sys.modules that holds copies of mod's members"""
        for _, new_member in _iter_internal_members(mod):
            key = _get_full_member_name(new_member)
            old_refs = cls._reference_cache.get(key, [])
            for (other_mod, other_member_name, _) in old_refs:
                other_mod.__dict__.update({other_member_name: new_member})

    @classmethod
    def update_stale_modules_and_instances(cls, mods: list[ModuleType]) -> None:
        """
        Updates all stale references to the updated module.

        Updates any old references to classes and functions. Updates any
        subclasses and instances of the new object.
        """
        for mod in mods:
            cls.update_other_modules_refs(mod)

            old_internal_classes = [
                obj
                for obj in cls._old_members_map[mod.__name__].values()
                if inspect.isclass(obj) and obj.__module__ == mod.__name__
            ]
            for old_class in old_internal_classes:
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
                cls.update_subclasses(old_class, new_class)
                cls.update_instances(old_class, new_class)

    @classmethod
    def update_subclasses(cls, old_class: type, new_class: type):
        """Find subclasses of old_class and update them to new_class."""
        for subclass in _get_subclasses(old_class):
            new_bases = []
            for base in subclass.__bases__:
                # If the module and class name matches, use the new class.
                if base.__module__ == new_class.__module__:
                    if base.__name__ == new_class.__name__:
                        new_bases.append(new_class)
                        continue
                new_bases.append(base)
            subclass.__bases__ = tuple(new_bases)

    @classmethod
    def wrap_class(cls, class_: type, fxn_wrapper: Callable, member_names: Optional[str] = None) -> type:
        """Wrap a class's member functions in the wrapped method and returns the class."""
        for name, member in class_.__dict__.items():
            if member_names and name not in member_names:
                continue
            full_name = class_.__module__ + "." + class_.__name__ + "." + name
            if isinstance(member, (FunctionType, BuiltinFunctionType)):
                setattr(class_, name, fxn_wrapper(member, full_name))
                continue
            # Static and class methods: do the dark magic
            if isinstance(member, (classmethod, staticmethod)):
                # Wrap the inner function and rewrap in the outer.
                inner_func = member.__func__
                method_type = type(member)
                decorated = method_type(fxn_wrapper(inner_func, full_name))
                setattr(class_, name, decorated)
                continue
            # Hopefully we don't really have any other cases
        return class_


def reload_module(mod: ModuleType) -> None:
    """Entry point for reloading a module."""
    _ModuleUpdator.superreload([mod])


def reload_modules(mods: list[ModuleType]) -> None:
    """Entry point for reloading modules."""
    _ModuleUpdator.superreload(mods)


def wrap_module(mod: ModuleType, fxn: Callable) -> None:
    """Entry point for wrapping a module.

    Function should accept the member and member_name as args. 
    ex)
        from functools import wraps
        call_count = {}
        def timer_wrap(inner_fxn, full_member_name):
            @wraps(inner_fxn)
            def wrapped(*args, **kwargs):
                global call_count
                prev_count = call_count.get(full_member_name, 0)
                call_count[full_member_name] = prev_time + 1
                return inner_fxn(*args, **kwargs)
            return wrapped
    """
    _ModuleUpdator.superwrapper([mod], fxn)


def wrap_modules(mods: list[ModuleType], fxn: Callable) -> None:
    """Entry point for wrapping modules.

    Function should accept the member and member_name as args. 
    ex)
        from functools import wraps
        call_count = {}
        def timer_wrap(inner_fxn, full_member_name):
            @wraps(inner_fxn)
            def wrapped(*args, **kwargs):
                global call_count
                prev_count = call_count.get(full_member_name, 0)
                call_count[full_member_name] = prev_time + 1
                return inner_fxn(*args, **kwargs)
            return wrapped
    """
    _ModuleUpdator.superwrapper(mods, fxn)
