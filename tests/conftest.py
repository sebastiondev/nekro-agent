"""conftest.py — Prevent the heavy nekro_agent.__init__ from loading,
while still allowing specific sub-modules to be imported directly.

Strategy: replace nekro_agent in sys.modules with a thin package shell
*before* any test module tries to import it.
"""

import importlib
import importlib.abc
import importlib.machinery
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# 1.  Stub classes
# ---------------------------------------------------------------------------
class _StubBase:
    """A real class usable as a base class."""
    pass


class _StubModule(ModuleType):
    """Permissive module stub."""

    def __init__(self, name: str):
        super().__init__(name)
        self.__path__: list = []
        self.__file__ = f"<stub:{name}>"
        self.__all__: list = []

    def __mro_entries__(self, bases):
        return (_StubBase,)

    def __getattr__(self, name: str):
        sub_fqn = f"{self.__name__}.{name}"
        if sub_fqn in sys.modules:
            return sys.modules[sub_fqn]
        mod = _StubModule(sub_fqn)
        sys.modules[sub_fqn] = mod
        return mod

    def __call__(self, *args, **kwargs):
        return MagicMock()

    def __iter__(self):
        return iter([])


# ---------------------------------------------------------------------------
# 2.  Missing-package meta-path finder (PEP-451)
# ---------------------------------------------------------------------------
_MISSING_TOPLEVEL = {
    "nonebot", "tortoise", "jose", "passlib", "magic",
    "aiodocker", "httpx_aiohttp", "aerich",
    "aiosmtplib", "lunar_python", "chinese_calendar", "croniter",
}


class _StubLoader(importlib.abc.Loader):
    def create_module(self, spec):
        return _StubModule(spec.name)

    def exec_module(self, module):
        pass


class _StubFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        top = fullname.split(".")[0]
        if top in _MISSING_TOPLEVEL:
            return importlib.machinery.ModuleSpec(
                fullname, _StubLoader(), is_package=True
            )
        return None


sys.meta_path.insert(0, _StubFinder())


# ---------------------------------------------------------------------------
# 3.  Pre-seed nonebot stubs (needed before nekro_agent/__init__ runs)
# ---------------------------------------------------------------------------
for _n in ["nonebot", "nonebot.adapters", "nonebot.adapters.onebot",
           "nonebot.adapters.onebot.v11", "nonebot.plugin"]:
    sys.modules[_n] = _StubModule(_n)

sys.modules["nonebot"].get_app = MagicMock()
sys.modules["nonebot"].get_driver = MagicMock(side_effect=ValueError("no driver"))
sys.modules["nonebot.plugin"].PluginMetadata = type(
    "PluginMetadata", (), {"__init__": lambda self, **kw: None}
)
sys.modules["nonebot.adapters.onebot.v11"].Bot = type("Bot", (), {})


# ---------------------------------------------------------------------------
# 4.  Tortoise ORM stubs
# ---------------------------------------------------------------------------
class _TortoiseModelMeta(type):
    def __new__(mcs, name, bases, namespace, **kwargs):
        namespace.pop("Meta", None)
        return super().__new__(mcs, name, bases, namespace)


class _TortoiseModel(metaclass=_TortoiseModelMeta):
    class Meta:
        pass

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

    @classmethod
    async def get_or_none(cls, *a, **kw):
        return None

    @classmethod
    async def filter(cls, *a, **kw):
        return MagicMock()


sys.modules["tortoise"] = _StubModule("tortoise")
_tm = _StubModule("tortoise.models")
_tm.Model = _TortoiseModel
sys.modules["tortoise.models"] = _tm

class _TortoiseFields(_StubModule):
    def __getattr__(self, name):
        if name.startswith("__"):
            return super().__getattribute__(name)
        return lambda *a, **kw: MagicMock()

sys.modules["tortoise.fields"] = _TortoiseFields("tortoise.fields")
for _t in ["tortoise.fields.data", "tortoise.contrib", "tortoise.contrib.pydantic",
           "tortoise.contrib.pydantic.creator", "tortoise.queryset",
           "tortoise.exceptions", "tortoise.transactions", "tortoise.connection"]:
    sys.modules[_t] = _StubModule(_t)


# jose
sys.modules["jose"] = _StubModule("jose")
sys.modules["jose"].JWTError = type("JWTError", (Exception,), {})
sys.modules["jose.jwt"] = _StubModule("jose.jwt")
sys.modules["jose.jwt"].decode = MagicMock()
sys.modules["jose.exceptions"] = _StubModule("jose.exceptions")
sys.modules["jose.exceptions"].ExpiredSignatureError = type("ExpiredSignatureError", (Exception,), {})


# ---------------------------------------------------------------------------
# 5.  Replace nekro_agent top-level __init__ with a thin shell that
#     preserves __path__ (so sub-package imports still work) but skips
#     the heavy init code.
# ---------------------------------------------------------------------------
_NEKRO_PKG = "nekro_agent"
_pkg_path = str(Path(__file__).resolve().parent.parent / _NEKRO_PKG)

# Create a thin shell module
_shell = ModuleType(_NEKRO_PKG)
_shell.__path__ = [_pkg_path]
_shell.__file__ = str(Path(_pkg_path) / "__init__.py")
_shell.__package__ = _NEKRO_PKG
sys.modules[_NEKRO_PKG] = _shell
