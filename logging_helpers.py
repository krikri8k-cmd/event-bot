# logging_helpers.py
from collections import Counter, defaultdict
from dataclasses import dataclass


@dataclass
class DropExample:
    title: str
    reason: str


class DropStats:
    def __init__(self, keep_limit_examples: int = 2):
        self.reasons = Counter()
        self.examples = defaultdict(list)
        self.keep_limit_examples = keep_limit_examples

    def add(self, reason: str, title: str):
        self.reasons[reason] += 1
        if len(self.examples[reason]) < self.keep_limit_examples:
            self.examples[reason].append(DropExample(title=title[:80], reason=reason))

    def summary(self, kept_by_type: dict, total: int) -> str:
        top3 = self.reasons.most_common(3)
        top_show = ", ".join(f"{r}={n}" for r, n in top3) or "-"
        lines = [
            f"found_total={total} | kept_by_type: "
            + " ".join(f"{k}={v}" for k, v in kept_by_type.items()),
            f"dropped={sum(self.reasons.values())} reasons_top3=[{top_show}]",
        ]
        for reason, _ in top3:
            examples = "; ".join(e.title for e in self.examples[reason])
            if examples:
                lines.append(f"  • {reason}: {examples}")
        return "\n".join(lines)
