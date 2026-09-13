"""Merge named decoration layers without changing document text or undo state."""
class EditorDecorationManager:
    def __init__(self, editor):
        self.editor = editor
        self.layers = {}

    def set(self, layer, selections):
        self.layers[layer] = list(selections)
        self.editor.setExtraSelections([selection for values in self.layers.values() for selection in values])
