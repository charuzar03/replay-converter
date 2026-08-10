from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


def clean_text(value: Optional[str]) -> str:
    return (value or "").strip()


@dataclass
class EntityRef:
    token: str
    side: Optional[str] = None
    slot: Optional[str] = None
    name: str = ""


@dataclass
class HPSnapshot:
    raw: str
    current: Optional[float] = None
    maximum: Optional[float] = None
    hp_type: str = "unknown"
    status: Optional[str] = None
    fainted: bool = False

    @property
    def current_percent(self) -> Optional[float]:
        if self.current is None:
            return None
        if self.hp_type == "percent":
            return self.current
        if self.hp_type == "exact" and self.maximum:
            return (self.current / self.maximum) * 100
        return None


@dataclass
class EventRow:
    battle_id: str
    replay_url: str
    turn: int
    event_type: str
    player: str = ""
    source: str = ""
    source_species: str = ""
    target: str = ""
    target_species: str = ""
    move: str = ""
    ability: str = ""
    item: str = ""
    amount: str = ""
    old_hp: str = ""
    new_hp: str = ""
    hp_type: str = "unknown"
    cause: str = ""
    cause_detail: str = ""
    is_direct: bool = False
    is_residual: bool = False
    is_hazard: bool = False
    is_recoil: bool = False
    is_self_damage: bool = False
    is_healing: bool = False
    raw_line: str = ""

    @classmethod
    def columns(cls) -> List[str]:
        return [
            "battle_id",
            "replay_url",
            "turn",
            "event_type",
            "player",
            "source",
            "source_species",
            "target",
            "target_species",
            "move",
            "ability",
            "item",
            "amount",
            "old_hp",
            "new_hp",
            "hp_type",
            "cause",
            "cause_detail",
            "is_direct",
            "is_residual",
            "is_hazard",
            "is_recoil",
            "is_self_damage",
            "is_healing",
            "raw_line",
        ]

    def to_csv_row(self) -> Dict[str, object]:
        return {column: getattr(self, column) for column in self.columns()}


@dataclass
class DamageAttribution:
    source_id: Optional[str] = None
    source_label: str = "unknown"
    source_species: str = ""
    player: str = ""
    move: str = ""
    cause: str = ""
    cause_detail: str = ""
    is_direct: bool = False
    is_residual: bool = False
    is_hazard: bool = False
    is_recoil: bool = False
    is_self_damage: bool = False
    is_healing: bool = False
    amount: Optional[float] = None
    amount_pct: Optional[float] = None


@dataclass
class MoveContext:
    user_id: str
    user_side: str
    move: str
    target_token: str = ""
    target_id: Optional[str] = None
    turn: int = 0
    hits: int = 0
    landed_any: bool = False
    missed: bool = False
    failed: bool = False
    caused_switch: bool = False
    raw_line: str = ""


@dataclass
class PendingDelayedAttack:
    move: str
    source_id: str
    target_side: Optional[str]
    target_slot: Optional[str]
    turn_set: int


@dataclass
class PendingWish:
    source_id: str
    side: str
    turn_set: int


@dataclass
class SideCondition:
    name: str
    setter_id: Optional[str] = None
    source_move: str = ""


@dataclass
class PokemonSummary:
    moves_used: int = 0
    hits_landed: int = 0
    hits_taken: int = 0
    misses: int = 0
    moves_dodged: int = 0
    crits: int = 0
    crits_taken: int = 0
    super_effective_hits_taken: int = 0
    resisted_hits_taken: int = 0
    damage_dealt_pct: float = 0.0
    direct_damage_dealt_pct: float = 0.0
    indirect_damage_dealt_pct: float = 0.0
    hazard_damage_dealt_pct: float = 0.0
    residual_damage_dealt_pct: float = 0.0
    damage_taken_pct: float = 0.0
    direct_damage_taken_pct: float = 0.0
    indirect_damage_taken_pct: float = 0.0
    hazard_damage_taken_pct: float = 0.0
    recoil_taken_pct: float = 0.0
    healing_received_pct: float = 0.0
    kos: int = 0
    direct_kos: int = 0
    indirect_kos: int = 0
    deaths: int = 0
    fainted_by: str = ""
    switches_in: int = 0
    turns_active: int = 0
    boosts_given: int = 0
    boosts_received: int = 0
    items_removed: int = 0
    statuses_inflicted: Dict[str, int] = field(default_factory=dict)
    statuses_received: Dict[str, int] = field(default_factory=dict)
    hazards_set: Dict[str, int] = field(default_factory=dict)
    hazards_removed: Dict[str, int] = field(default_factory=dict)
    abilities_revealed: Set[str] = field(default_factory=set)

    def add_counter(self, counter: Dict[str, int], key: str, amount: int = 1) -> None:
        counter[key] = counter.get(key, 0) + amount


@dataclass
class PokemonState:
    mon_id: str
    side: str
    nickname: str
    species: str
    team_position: int = 0
    current_hp: Optional[HPSnapshot] = None
    last_hp: Optional[HPSnapshot] = None
    current_status: str = ""
    active: bool = False
    active_slot: Optional[str] = None
    active_since_turn: Optional[int] = None
    fainted: bool = False
    revealed_item: str = ""
    revealed_ability: str = ""
    volatile_sources: Dict[str, Optional[str]] = field(default_factory=dict)
    status_sources: Dict[str, Optional[str]] = field(default_factory=dict)
    summary: PokemonSummary = field(default_factory=PokemonSummary)


@dataclass
class SideState:
    side: str
    player_name: str = ""
    team: List[str] = field(default_factory=list)
    preview_species: List[str] = field(default_factory=list)
    active_slots: Dict[str, str] = field(default_factory=dict)
    side_conditions: Dict[str, SideCondition] = field(default_factory=dict)


@dataclass
class BattleState:
    battle_id: str
    replay_url: str = ""
    battle_format: str = ""
    current_turn: int = 0
    winner: str = ""
    battle_date: str = ""
    sides: Dict[str, SideState] = field(
        default_factory=lambda: {"p1": SideState("p1"), "p2": SideState("p2")}
    )
    pokemon: Dict[str, PokemonState] = field(default_factory=dict)


@dataclass
class BattleSummaryRow:
    battle_id: str
    replay_url: str
    format: str = ""
    player_1: str = ""
    player_2: str = ""
    winner: str = ""
    turns: int = 0
    date: str = ""

    @classmethod
    def columns(cls) -> List[str]:
        return [
            "battle_id",
            "replay_url",
            "format",
            "player_1",
            "player_2",
            "winner",
            "turns",
            "date",
        ]

    def to_csv_row(self) -> Dict[str, object]:
        return {column: getattr(self, column) for column in self.columns()}


@dataclass
class PokemonSummaryRow:
    battle_id: str
    player: str
    pokemon_nickname: str
    species: str
    team_position: int
    result: str
    turns_active: int
    switches_in: int
    moves_used: int
    hits_landed: int
    hits_taken: int
    misses: int
    moves_dodged: int
    crits: int
    crits_taken: int
    super_effective_hits_taken: int
    resisted_hits_taken: int
    damage_dealt_pct: float
    direct_damage_dealt_pct: float
    indirect_damage_dealt_pct: float
    hazard_damage_dealt_pct: float
    residual_damage_dealt_pct: float
    damage_taken_pct: float
    direct_damage_taken_pct: float
    indirect_damage_taken_pct: float
    hazard_damage_taken_pct: float
    recoil_taken_pct: float
    healing_received_pct: float
    kos: int
    direct_kos: int
    indirect_kos: int
    deaths: int
    fainted_by: str
    status_inflicted: int
    status_received: int
    hazards_set: int
    hazards_removed: int
    boosts_given: int
    boosts_received: int
    items_removed: int
    abilities_revealed: str

    @classmethod
    def columns(cls) -> List[str]:
        return [
            "battle_id",
            "player",
            "pokemon_nickname",
            "species",
            "team_position",
            "result",
            "turns_active",
            "switches_in",
            "moves_used",
            "hits_landed",
            "hits_taken",
            "misses",
            "moves_dodged",
            "crits",
            "crits_taken",
            "super_effective_hits_taken",
            "resisted_hits_taken",
            "damage_dealt_pct",
            "direct_damage_dealt_pct",
            "indirect_damage_dealt_pct",
            "hazard_damage_dealt_pct",
            "residual_damage_dealt_pct",
            "damage_taken_pct",
            "direct_damage_taken_pct",
            "indirect_damage_taken_pct",
            "hazard_damage_taken_pct",
            "recoil_taken_pct",
            "healing_received_pct",
            "kos",
            "direct_kos",
            "indirect_kos",
            "deaths",
            "fainted_by",
            "status_inflicted",
            "status_received",
            "hazards_set",
            "hazards_removed",
            "boosts_given",
            "boosts_received",
            "items_removed",
            "abilities_revealed",
        ]

    def to_csv_row(self) -> Dict[str, object]:
        return {column: getattr(self, column) for column in self.columns()}


@dataclass
class BattleParseResult:
    battle_id: str
    replay_url: str
    events: List[EventRow]
    pokemon_rows: List[PokemonSummaryRow]
    battle_row: BattleSummaryRow
    warnings: List[str] = field(default_factory=list)
