from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class SqState:
    fecha_modelo: Optional[str] = None   # "YYYY-MM-DD"
    a0: Optional[float] = None
    a1: Optional[float] = None
    quiet_days: List[str] = field(default_factory=list)  # ["YYYY-MM-DD", ...]
    n_quiet: Optional[int] = None

SQ_STATE = SqState()