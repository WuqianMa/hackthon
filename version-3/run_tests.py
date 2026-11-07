"""Run copied v3 mechanism tests without requiring a hyphenated import name."""
import importlib.util
from pathlib import Path
import sys
import unittest

folder=Path(__file__).resolve().parent
sys.path.insert(0,str(folder.parent))
spec=importlib.util.spec_from_file_location('version3',folder/'__init__.py',submodule_search_locations=[str(folder)])
package=importlib.util.module_from_spec(spec)
sys.modules['version3']=package
spec.loader.exec_module(package)
suite=unittest.defaultTestLoader.loadTestsFromName('version3.test_strategy')
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
