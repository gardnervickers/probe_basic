from qtpy.QtCore import Property

from qtpyvcp.widgets.input_widgets.line_edit import VCPLineEdit

from .expression_evaluator import ExpressionError, evaluate_number_expression


class FloatLineEdit(VCPLineEdit):
    def __init__(self, parent=None):
        super(FloatLineEdit, self).__init__(parent)
        self._default_value = 0.
        self._format_string = "{0:.3f}"
        self.editingFinished.connect(self._normalize_text)

    @Property(float)
    def default_value(self):
        return self._default_value

    @default_value.setter
    def default_value(self, value):
        self._default_value = value

    @Property(str)
    def format_string(self):
        return self._format_string

    @format_string.setter
    def format_string(self, value):
        self._format_string = value

    @Property(str)
    def inputType(self):
        return 'number:float'

    def value(self):
        return evaluate_number_expression(self.text())

    def _normalize_text(self):
        try:
            value = evaluate_number_expression(self.text())
        except ExpressionError:
            self.setText(self._format_string.format(self._default_value))
        else:
            self.setText(self._format_string.format(value))

    def focusOutEvent(self, evt):
        self._normalize_text()

        super(FloatLineEdit, self).focusOutEvent(evt)
