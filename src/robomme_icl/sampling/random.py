"""配额和位置各自使用可复现的SHA-256随机流。"""

import hashlib
from ..specs import canonical_json

class _Stream:
    """SHA-256 计数器随机流，避免全局 RNG 和进程调度影响候选。"""

    def __init__(self, *parts):
        self.key = canonical_json(parts).encode("utf-8")
        self.counter = 0

    def integer(self) -> int:
        data = hashlib.sha256(self.key + self.counter.to_bytes(8, "big")).digest()
        self.counter += 1
        return int.from_bytes(data[:8], "big")

    def uniform(self) -> float:
        return (self.integer() >> 11) / 2**53

    def randbelow(self, n: int) -> int:
        if n <= 0:
            raise ValueError("随机整数的上界必须为正")
        cutoff = 2**64 - (2**64 % n)
        while True:
            number = self.integer()
            if number < cutoff:
                return number % n

    def shuffle(self, values: list) -> None:
        for end in range(len(values) - 1, 0, -1):
            selected = self.randbelow(end + 1)
            values[end], values[selected] = values[selected], values[end]
