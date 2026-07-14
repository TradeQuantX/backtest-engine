"""
AST-based import integrity test.

Validates that every __init__.py in src/backtest_engine exports only names
that are actually defined or imported in that module. Catches typos like
RateLimitBucket vs TokenBucket before they ship.
"""

import ast
import importlib.util
import sys
from pathlib import Path

import pytest


def find_init_files(root: Path) -> list[Path]:
    """Find all __init__.py files under src/backtest_engine."""
    return list(root.rglob("__init__.py"))


def get_module_exports(init_file: Path) -> set[str]:
    """
    Parse __init__.py with AST and return the set of names in __all__.
    If no __all__, return all public names (not starting with _).
    """
    source = init_file.read_text()
    tree = ast.parse(source, filename=str(init_file))
    
    exports = set()
    has_all = False
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    has_all = True
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                exports.add(elt.value)
    
    if not has_all:
        # No __all__: collect all top-level names that don't start with _
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    name = alias.asname or alias.name.split(".")[-1]
                    if not name.startswith("_"):
                        exports.add(name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not node.name.startswith("_"):
                    exports.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and not target.id.startswith("_"):
                        exports.add(target.id)
    
    return exports


def get_module_defined_names(init_file: Path) -> set[str]:
    """
    Get all names actually defined/imported in the module by executing it.
    This catches names imported from submodules.
    """
    # Convert file path to module name
    # e.g., src/backtest_engine/data_provider/interfaces/__init__.py -> backtest_engine.data_provider.interfaces
    # e.g., src/backtest_engine/__init__.py -> backtest_engine
    rel_path = init_file.relative_to(Path("src"))
    module_parts = list(rel_path.with_suffix("").parts)
    if module_parts[-1] == "__init__":
        module_parts = module_parts[:-1]
    module_name = ".".join(module_parts)
    
    try:
        module = importlib.import_module(module_name)
        # Get all public attributes
        return {name for name in dir(module) if not name.startswith("_")}
    except Exception as e:
        # If import fails, return empty set (test will fail with missing exports)
        print(f"Import failed for {module_name}: {e}")
        return set()


@pytest.mark.parametrize("init_file", find_init_files(Path("src/backtest_engine")))
def test_init_exports_exist(init_file: Path):
    """
    Every name in __all__ (or every public name if no __all__) must be
    actually defined/imported in the module.
    """
    exports = get_module_exports(init_file)
    if not exports:
        pytest.skip(f"No exports found in {init_file}")
    
    defined = get_module_defined_names(init_file)
    
    missing = exports - defined
    assert not missing, (
        f"{init_file} exports names that don't exist: {sorted(missing)}. "
        f"Defined names: {sorted(defined)}"
    )


def test_no_duplicate_exports():
    """
    Ensure no name is exported by multiple __init__.py files at the SAME level.
    Re-exports from parent packages are expected and allowed.
    Only checks names that are explicitly in __all__ (not imported stdlib names).
    """
    all_exports = {}
    for init_file in find_init_files(Path("src/backtest_engine")):
        exports = get_module_exports(init_file)
        for name in exports:
            if name in all_exports:
                all_exports[name].append(init_file)
            else:
                all_exports[name] = [init_file]
    
    # Only flag duplicates at the same package depth (same parent directory)
    # Re-exports from parent to child are expected
    duplicates = {}
    for name, files in all_exports.items():
        if len(files) > 1:
            # Check if they're at different depths (parent/child relationship)
            depths = [len(f.parts) for f in files]
            if len(set(depths)) == 1:
                # Same depth = actual collision
                duplicates[name] = files
    
    # Filter out standard library names that are commonly imported
    stdlib_names = {"datetime", "asyncio", "Optional", "Any", "Path", "List", "Dict", "Set", "Tuple", "Union"}
    
    # Filter out intentional re-exports from interfaces to sub-packages
    # These are defined in interfaces/ and re-exported by cache/, storage/, etc.
    intentional_reexports = {
        "CacheEntry", "CacheProtocol",  # from interfaces.cache -> cache/
        "ReadResult", "WriteResult", "StorageConfig", "StorageProtocol",  # from interfaces.storage -> storage/
    }
    
    filtered_duplicates = {
        k: v for k, v in duplicates.items() 
        if k not in stdlib_names and k not in intentional_reexports
    }
    
    assert not filtered_duplicates, f"Duplicate exports at same package level: {filtered_duplicates}"


if __name__ == "__main__":
    # Allow running standalone for quick debugging
    for init_file in find_init_files(Path("src/backtest_engine")):
        exports = get_module_exports(init_file)
        defined = get_module_defined_names(init_file)
        missing = exports - defined
        if missing:
            print(f"❌ {init_file}: missing {missing}")
        else:
            print(f"✅ {init_file}: all {len(exports)} exports valid")