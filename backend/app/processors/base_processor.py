from abc import ABC, abstractmethod


class BaseProcessor(ABC):
    def __init__(self, source_path: str, profile: str) -> None:
        self.source_path = source_path
        self.profile = profile

    @abstractmethod
    def analyze(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def optimize(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def validate(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def generate_report(self) -> dict:
        raise NotImplementedError
