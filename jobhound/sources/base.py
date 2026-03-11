from abc import ABC, abstractmethod
from jobhound.models import Job


class BaseSource(ABC):
    @abstractmethod
    def fetch(self) -> list[Job]:
        """Fetch jobs from this source. Returns empty list on error."""
        ...
