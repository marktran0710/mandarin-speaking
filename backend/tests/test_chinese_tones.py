"""Compatibility facade; implementation is split into bounded parts."""
from tests.support.module_loader import load_module_parts

load_module_parts(globals(), __file__)
