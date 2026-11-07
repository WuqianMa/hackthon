"""Optional residual candidate interface. Providers never write final CSV rows.

An agent can later populate a cached provider or help develop a deterministic parser.
The default CLI registers no providers and never calls an agent.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Iterable

from .io import digest


@dataclass(frozen=True)
class Evidence:
    path: str                 # relative to the selected phase folder
    sha256: str
    description: str


@dataclass(frozen=True)
class ProposedAllocation:
    item_id: str
    paid_cents: int           # actual cash attributed to this item, in item currency
    deduction_reason: str = ""


@dataclass(frozen=True)
class Candidate:
    bank_txn_id: str
    allocations: tuple
    evidence: tuple
    method: str
    returned: bool = False


class CandidateProvider(Protocol):
    def propose(self, transaction: dict, catalog) -> Iterable[Candidate]:
        ...


def evidence_is_valid(evidence, phase):
    if not evidence:
        return False
    phase = Path(phase).resolve()
    for e in evidence:
        p = (phase / e.path).resolve()
        if phase not in p.parents or "golden" in p.name.lower() or not p.is_file():
            return False
        if not e.description.strip() or digest(p) != e.sha256:
            return False
    return True
