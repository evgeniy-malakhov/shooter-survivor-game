class EventBuffer:
    def __init__(self) -> None:
        self._events: list = []

    def emit(self, event) -> None:
        self._events.append(event)

    def drain(self):
        events = self._events
        self._events = []
        return events