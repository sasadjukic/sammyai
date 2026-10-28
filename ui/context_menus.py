"""Surface-scoped menu contributions, layered onto native Qt and spelling actions."""


class ContextMenuRegistry:
    def __init__(self):
        self._providers = {}

    def register(self, surface, provider):
        self._providers.setdefault(surface, []).append(provider)

    def create(self, widget, surface, position):
        spelling = getattr(widget, "spell_check", None)
        menu = (spelling.create_context_menu(position) if spelling else
                widget.createStandardContextMenu())
        for provider in self._providers.get(surface, ()):
            provider(menu, widget)
        return menu


def show_text_context_menu(widget, event, surface):
    menu = widget.context_menus.create(widget, surface, widget.cursorForPosition(event.pos()).position())
    menu.exec(event.globalPos())
    menu.deleteLater()
