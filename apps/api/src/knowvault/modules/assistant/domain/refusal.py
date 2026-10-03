"""Recognising the NO_ANSWER marker while an answer streams."""

from knowvault.modules.assistant.domain.model import NO_ANSWER


class RefusalDetector:
    """Holds back the start of a reply until it is clear whether it is the NO_ANSWER marker.

    The model is told to reply with only the marker when its sources are not enough. The
    marker must never reach the user, so text is released only once it cannot be the marker
    any more; afterwards it passes through unchanged.
    """

    def __init__(self) -> None:
        self._held = ""
        self._decided = False
        self.refused = False

    def feed(self, text: str) -> str:
        """Returns the part of `text` that may be shown now."""
        if self.refused:
            return ""
        if self._decided:
            return text
        self._held += text
        start = self._held.lstrip()
        if start.startswith(NO_ANSWER):
            self.refused = True
            return ""
        if NO_ANSWER.startswith(start):
            return ""  # still possibly the marker (or only whitespace so far)
        self._decided = True
        self._held = ""
        return start

    def finish(self) -> str:
        """Call when the stream ends; returns any held text. An empty reply is a refusal."""
        if self.refused or self._decided:
            return ""
        start = self._held.strip()
        self._held = ""
        if not start:
            self.refused = True
        return start


def mentions_no_answer(text: str) -> bool:
    """True when a reply that began normally still gave up (e.g. "Sorry. NO_ANSWER")."""
    return NO_ANSWER in text
