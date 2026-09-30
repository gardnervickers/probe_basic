"""Prevent non-editable controls from being mistaken for virtual-input targets."""
from functools import wraps

from qtpy.QtWidgets import QAbstractButton, QLabel


def protect_virtual_input(manager_class):
    """Guard old QtPyVCP managers without changing focus or input providers.

    Older managers infer editability from text()/setText(), which buttons and
    labels also expose. Read-only spinboxes can also reach the numeric branch
    before the manager checks isReadOnly(). Keep those controls out of every
    provider, including explicitly requested input types.
    """
    original = manager_class.activateVirtualInput
    if getattr(original, '_probe_basic_editable_only', False):
        return False

    @wraps(original)
    def activate(self, widget, input_type=None):
        if widget is None or isinstance(widget, (QAbstractButton, QLabel)):
            return
        is_read_only = getattr(widget, 'isReadOnly', None)
        if callable(is_read_only) and is_read_only():
            return
        return original(self, widget, input_type)

    activate._probe_basic_editable_only = True
    manager_class.activateVirtualInput = activate
    return True


def install_virtual_input_guard():
    # Called after VCPMainWindow initialization, when QtPyVCP's configuration
    # and plugin lifecycle have already been established.
    from qtpyvcp.plugins.virtual_input_manager import VirtualInputManager
    protect_virtual_input(VirtualInputManager)
