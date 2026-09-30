from qtpy.QtCore import Property

from qtpyvcp.widgets.input_widgets.line_edit import VCPLineEdit

from .expression_evaluator import ExpressionError, evaluate_integer_expression


class IntLineEdit(VCPLineEdit):
    def __init__(self, parent=None):
        super(IntLineEdit, self).__init__(parent)
        self._default_value = 0
        self.editingFinished.connect(self._normalize_text)

    @Property(int)
    def default_value(self):
        return self._default_value

    @default_value.setter
    def default_value(self, value):
        self._default_value = value

    @Property(str)
    def inputType(self):
        return 'number:int'

    def value(self):
        return evaluate_integer_expression(self.text())

    def _normalize_text(self):
        try:
            value = self.value() if self.text() else self._default_value
        except ExpressionError:
            value = self._default_value
        self.setText('{:d}'.format(value))

    def focusOutEvent(self, evt):
        self._normalize_text()
        super(IntLineEdit, self).focusOutEvent(evt)
