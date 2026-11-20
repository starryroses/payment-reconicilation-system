"""Input records and public reconciliation result types."""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class ReasonCode(str, Enum):
    MATCHED = "MATCHED"
    IN_TRANSIT = "IN_TRANSIT"
    PRIOR_PERIOD_SETTLED = "PRIOR_PERIOD_SETTLED"
    OUT_OF_WINDOW = "OUT_OF_WINDOW"
    FEE_DRIFT = "FEE_DRIFT"
    OVERDUE = "OVERDUE"
    DUPLICATE_BANK = "DUPLICATE_BANK"
    DUPLICATE_LEDGER = "DUPLICATE_LEDGER"
    ORPHAN_REFUND = "ORPHAN_REFUND"
    BANK_ONLY_PAYMENT = "BANK_ONLY_PAYMENT"
    FEE_MISMATCH = "FEE_MISMATCH"
    BANK_INTEGRITY = "BANK_INTEGRITY"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"


class Verdict(str, Enum):
    RECONCILED = "RECONCILED"
    RECONCILED_WITH_EXCEPTIONS = "RECONCILED_WITH_EXCEPTIONS"
    UNEXPLAINED_DIFFERENCE = "UNEXPLAINED_DIFFERENCE"


@dataclass(frozen=True)
class LedgerRow:
    txn_ref: str
    type: str
    original_ref: str
    amount_paise: int
    fee_paise: int
    created_at: datetime


@dataclass(frozen=True)
class BankPayout:
    payout_id: str
    payout_date: date
    gross_paise: int
    fee_paise: int
    net_paise: int


@dataclass(frozen=True)
class BankLine:
    payout_id: str
    bank_line_id: str
    merchant_ref: str
    amount_paise: int
    line_type: str


@dataclass(frozen=True)
class MatchedPair:
    ledger: LedgerRow
    bank: BankLine


@dataclass
class MatchResult:
    matched: list[MatchedPair] = field(default_factory=list)
    ledger_only: list[LedgerRow] = field(default_factory=list)
    bank_only: list[BankLine] = field(default_factory=list)
    duplicate_ledger: list[LedgerRow] = field(default_factory=list)
    duplicate_bank: list[BankLine] = field(default_factory=list)
    amount_mismatches: list[MatchedPair] = field(default_factory=list)


@dataclass
class ClassificationResult:
    ledger: list[tuple[LedgerRow, ReasonCode]] = field(default_factory=list)
    bank: list[tuple[BankLine, ReasonCode]] = field(default_factory=list)
    matched: list[tuple[MatchedPair, ReasonCode]] = field(default_factory=list)


@dataclass(frozen=True)
class ExceptionItem:
    reason_code: ReasonCode
    amount_paise: int
    explanation: str
    txn_ref: str | None = None
    bank_line_id: str | None = None
    payout_id: str | None = None
    actionable: bool = True


@dataclass
class Report:
    verdict: Verdict
    ledger_net_oct_paise: int
    bank_net_paise: int
    explained_bank_net_paise: int
    residual_paise: int
    bridge_paise: dict[str, int]
    exceptions: list[ExceptionItem]
    counts: dict[ReasonCode, int]
