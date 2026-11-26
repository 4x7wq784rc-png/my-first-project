"""サイトごとの取得処理。各モジュールは NAME と collect() -> list[Listing] を持つ。"""
import importlib
import pkgutil


def all_sites():
    mods = []
    for m in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        mod = importlib.import_module(f"{__name__}.{m.name}")
        if hasattr(mod, "collect") and getattr(mod, "ENABLED", True):
            mods.append(mod)
    return mods
