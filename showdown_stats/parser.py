from __future__ import annotations

import datetime as dt
import logging
from dataclasses import asdict
from typing import Dict, List, Optional, Tuple

from .models import (
    BattleParseResult,
    BattleState,
    BattleSummaryRow,
    DamageAttribution,
    EntityRef,
    EventRow,
    HPSnapshot,
    MoveContext,
    PendingDelayedAttack,
    PendingWish,
    PokemonState,
    PokemonSummaryRow,
    SideCondition,
)

LOGGER = logging.getLogger(__name__)

HAZARD_NAMES = {
    "Stealth Rock",
    "Spikes",
    "Toxic Spikes",
    "Sticky Web",
    "G-Max Steelsurge",
}
SELF_KO_MOVES = {"Explosion", "Self-Destruct", "Misty Explosion", "Final Gambit", "Memento"}
FUTURE_MOVES = {"Future Sight", "Doom Desire"}
PROTECTIVE_MOVES = {
    "Protect",
    "Detect",
    "King's Shield",
    "Spiky Shield",
    "Baneful Bunker",
    "Silk Trap",
}
TRAPPING_MOVES = {
    "Bind",
    "Clamp",
    "Fire Spin",
    "Infestation",
    "Magma Storm",
    "Sand Tomb",
    "Whirlpool",
    "Wrap",
}
WEATHER_DAMAGE_CAUSES = {"Sandstorm", "Hail"}
STATUS_DAMAGE_MAP = {"psn": "poison", "tox": "toxic poison", "brn": "burn"}


def counter_total(counter: Dict[str, int]) -> int:
    return sum(counter.values())


class BattleParser:
    """Stateful parser for Pokemon Showdown protocol logs."""

    def __init__(self, debug: bool = False) -> None:
        self.debug = debug
        self.state: BattleState
        self.events: List[EventRow]
        self.warnings: List[str]
        self.move_context: Optional[MoveContext]
        self.sequence_index: int
        self.weather_source: Dict[str, Optional[str]]
        self.terrain_source: Dict[str, Optional[str]]
        self.pending_delayed_attacks: List[PendingDelayedAttack]
        self.pending_wishes: Dict[str, PendingWish]
        self.pending_faint_attribution: Dict[str, DamageAttribution]
        self.pending_switch_source: Optional[str]
        self.current_delayed_source: Optional[str]
        self.last_move_user: Optional[str]

    def parse(
        self,
        text: str,
        *,
        battle_id: str,
        replay_url: str = "",
        metadata: Optional[Dict[str, object]] = None,
    ) -> BattleParseResult:
        metadata = metadata or {}
        self.state = BattleState(
            battle_id=battle_id or str(metadata.get("id") or "unknown-battle"),
            replay_url=replay_url,
            battle_format=str(metadata.get("format") or ""),
        )
        self.events = []
        self.warnings = []
        self.move_context = None
        self.sequence_index = 0
        self.weather_source = {"name": "", "source_id": None}
        self.terrain_source = {"name": "", "source_id": None}
        self.pending_delayed_attacks = []
        self.pending_wishes = {}
        self.pending_faint_attribution = {}
        self.pending_switch_source = None
        self.current_delayed_source = None
        self.last_move_user = None
        self._ingest_metadata(metadata)

        for raw_line in text.splitlines():
            raw_line = raw_line.rstrip("\n")
            if not raw_line:
                continue
            if raw_line.startswith(">"):
                self._parse_room_header(raw_line)
                continue
            if not raw_line.startswith("|"):
                continue
            self.sequence_index += 1
            try:
                self._parse_protocol_line(raw_line)
            except Exception as exc:  # pragma: no cover - exercised only by malformed inputs
                self._warn(f"Failed to parse line: {raw_line} ({exc})")
                self._emit_event(
                    event_type="unparsed",
                    raw_line=raw_line,
                    cause="parse_error",
                    cause_detail=str(exc),
                )

        self._finalize_move_context()
        self._finalize_active_turns()
        pokemon_rows = self._build_pokemon_rows()
        battle_row = BattleSummaryRow(
            battle_id=self.state.battle_id,
            replay_url=self.state.replay_url,
            format=self.state.battle_format,
            player_1=self.state.sides["p1"].player_name,
            player_2=self.state.sides["p2"].player_name,
            winner=self.state.winner,
            turns=self.state.current_turn,
            date=self.state.battle_date,
        )
        return BattleParseResult(
            battle_id=self.state.battle_id,
            replay_url=self.state.replay_url,
            events=self.events,
            pokemon_rows=pokemon_rows,
            battle_row=battle_row,
            warnings=self.warnings,
        )

    def _ingest_metadata(self, metadata: Dict[str, object]) -> None:
        timestamp = metadata.get("uploadtime")
        if timestamp:
            try:
                self.state.battle_date = dt.datetime.utcfromtimestamp(int(timestamp)).isoformat()
            except Exception:
                self.state.battle_date = str(timestamp)

    def _parse_room_header(self, raw_line: str) -> None:
        battle_name = raw_line[1:].strip()
        if battle_name and self.state.battle_id == "unknown-battle":
            self.state.battle_id = battle_name

    def _parse_protocol_line(self, raw_line: str) -> None:
        parts = raw_line.split("|")
        tag = parts[1] if len(parts) > 1 else ""
        args = parts[2:]

        handler = getattr(self, f"_handle_{self._sanitize_tag(tag)}", None)
        if handler:
            handler(args, raw_line)
        else:
            self._handle_unknown(tag, args, raw_line)

    @staticmethod
    def _sanitize_tag(tag: str) -> str:
        return tag.replace("-", "_").replace(":", "_") or "blank"

    def _handle_unknown(self, tag: str, args: List[str], raw_line: str) -> None:
        self._emit_event(
            event_type=tag or "unknown",
            raw_line=raw_line,
            cause="unhandled_event",
            cause_detail="|".join(args),
        )

    def _handle_player(self, args: List[str], raw_line: str) -> None:
        if len(args) < 2:
            self._warn(f"Malformed player line: {raw_line}")
            return
        side = args[0]
        player_name = args[1]
        self.state.sides.setdefault(side, self.state.sides["p1"].__class__(side))
        self.state.sides[side].player_name = player_name
        self._emit_event(
            event_type="player",
            player=player_name,
            raw_line=raw_line,
            cause=side,
        )

    def _handle_teamsize(self, args: List[str], raw_line: str) -> None:
        self._emit_event(event_type="teamsize", raw_line=raw_line, cause_detail="|".join(args))

    def _handle_gen(self, args: List[str], raw_line: str) -> None:
        self._emit_event(event_type="gen", raw_line=raw_line, cause_detail="|".join(args))

    def _handle_t_(self, args: List[str], raw_line: str) -> None:
        if args:
            try:
                self.state.battle_date = dt.datetime.utcfromtimestamp(int(args[0])).isoformat()
            except Exception:
                self.state.battle_date = args[0]
        self._emit_event(event_type="timestamp", raw_line=raw_line, cause_detail="|".join(args))

    def _handle_tier(self, args: List[str], raw_line: str) -> None:
        self.state.battle_format = args[0] if args else self.state.battle_format
        self._emit_event(event_type="format", raw_line=raw_line, cause=self.state.battle_format)

    def _handle_rule(self, args: List[str], raw_line: str) -> None:
        self._emit_event(event_type="rule", raw_line=raw_line, cause_detail="|".join(args))

    def _handle_poke(self, args: List[str], raw_line: str) -> None:
        if len(args) < 2:
            self._warn(f"Malformed poke line: {raw_line}")
            return
        side = args[0]
        species = self._parse_species_from_details(args[1])
        self.state.sides[side].preview_species.append(species)
        self._emit_event(
            event_type="team_preview",
            player=self.state.sides[side].player_name,
            target=species,
            target_species=species,
            raw_line=raw_line,
            cause=side,
        )

    def _handle_switch(self, args: List[str], raw_line: str) -> None:
        self._handle_switch_like("switch", args, raw_line, forced=False)

    def _handle_drag(self, args: List[str], raw_line: str) -> None:
        self._handle_switch_like("drag", args, raw_line, forced=True)

    def _handle_replace(self, args: List[str], raw_line: str) -> None:
        self._handle_switch_like("replace", args, raw_line, forced=False, is_replace=True)

    def _handle_switch_like(
        self,
        event_type: str,
        args: List[str],
        raw_line: str,
        *,
        forced: bool,
        is_replace: bool = False,
    ) -> None:
        if len(args) < 3:
            self._warn(f"Malformed switch line: {raw_line}")
            return
        entity = self._parse_entity(args[0])
        details = args[1]
        hp_snapshot = self._parse_hp_snapshot(args[2])
        mon = self._resolve_pokemon_for_switch(entity, details)
        mon.last_hp = mon.current_hp
        mon.current_hp = hp_snapshot
        mon.current_status = hp_snapshot.status or ""
        if not is_replace:
            self._withdraw_slot_if_needed(entity.side or "", entity.slot)
            mon.summary.switches_in += 1
        mon.active = True
        mon.active_slot = entity.slot
        mon.fainted = False
        mon.active_since_turn = self.state.current_turn
        self.state.sides[mon.side].active_slots[entity.slot or "a"] = mon.mon_id
        self._emit_event(
            event_type=event_type,
            player=self.state.sides[mon.side].player_name,
            target=mon.nickname,
            target_species=mon.species,
            new_hp=hp_snapshot.raw,
            hp_type=hp_snapshot.hp_type,
            raw_line=raw_line,
            cause="forced" if forced else ("replace" if is_replace else "switch"),
            cause_detail=self._label_mon(self.pending_switch_source) if forced and self.pending_switch_source else "",
        )
        self.pending_switch_source = None

    def _handle_move(self, args: List[str], raw_line: str) -> None:
        self._finalize_move_context()
        if len(args) < 2:
            self._warn(f"Malformed move line: {raw_line}")
            return
        entity = self._parse_entity(args[0])
        move_name = args[1]
        source_id = self._resolve_active_mon_from_entity(entity)
        target_token = args[2] if len(args) > 2 else ""
        target_entity = self._parse_entity(target_token) if target_token else EntityRef(token="")
        target_id = self._resolve_active_mon_from_entity(target_entity) if target_token else None
        if not source_id:
            self._warn(f"Unknown move source in line: {raw_line}")
            return
        source_mon = self.state.pokemon[source_id]
        source_mon.summary.moves_used += 1
        self.last_move_user = source_id
        self.move_context = MoveContext(
            user_id=source_id,
            user_side=source_mon.side,
            move=move_name,
            target_token=target_token,
            target_id=target_id,
            turn=self.state.current_turn,
            raw_line=raw_line,
        )
        if move_name in SELF_KO_MOVES:
            source_mon.volatile_sources["self_ko_move"] = source_id
        if move_name == "Wish":
            self.pending_wishes[source_mon.side] = PendingWish(
                source_id=source_id,
                side=source_mon.side,
                turn_set=self.state.current_turn,
            )
        if move_name in FUTURE_MOVES:
            self.pending_delayed_attacks.append(
                PendingDelayedAttack(
                    move=move_name,
                    source_id=source_id,
                    target_side=target_entity.side,
                    target_slot=target_entity.slot,
                    turn_set=self.state.current_turn,
                )
            )
        if move_name == "Court Change":
            self._swap_side_conditions()
        self._emit_event(
            event_type="move",
            player=self.state.sides[source_mon.side].player_name,
            source=source_mon.nickname,
            source_species=source_mon.species,
            target=self._label_mon(target_id) if target_id else target_entity.name,
            target_species=self._species_of(target_id),
            move=move_name,
            raw_line=raw_line,
            cause="move",
        )

    def _handle_turn(self, args: List[str], raw_line: str) -> None:
        self._finalize_move_context()
        if args:
            self.state.current_turn = int(args[0])
        self._emit_event(event_type="turn", raw_line=raw_line, cause_detail="|".join(args))

    def _handle_win(self, args: List[str], raw_line: str) -> None:
        self._finalize_move_context()
        self.state.winner = args[0] if args else ""
        self._emit_event(event_type="win", raw_line=raw_line, cause=self.state.winner)

    def _handle_faint(self, args: List[str], raw_line: str) -> None:
        if not args:
            self._warn(f"Malformed faint line: {raw_line}")
            return
        entity = self._parse_entity(args[0])
        mon_id = self._resolve_active_mon_from_entity(entity)
        if not mon_id:
            mon_id = self._resolve_pokemon_fallback(entity)
        if not mon_id:
            self._warn(f"Could not resolve fainted Pokemon: {raw_line}")
            return
        mon = self.state.pokemon[mon_id]
        mon.fainted = True
        mon.active = False
        mon.summary.deaths += 1
        self._close_active_window(mon)
        if mon.active_slot and self.state.sides[mon.side].active_slots.get(mon.active_slot) == mon.mon_id:
            del self.state.sides[mon.side].active_slots[mon.active_slot]
        attribution = self.pending_faint_attribution.pop(mon_id, None)
        if attribution:
            mon.summary.fainted_by = "self" if attribution.is_self_damage else (attribution.source_label or attribution.cause or "unknown")
            if self._should_credit_ko(attribution, mon_id):
                source_mon = self.state.pokemon[attribution.source_id]
                source_mon.summary.kos += 1
                if attribution.is_direct:
                    source_mon.summary.direct_kos += 1
                else:
                    source_mon.summary.indirect_kos += 1
        elif self.move_context and self.move_context.user_id == mon_id and self.move_context.move in SELF_KO_MOVES:
            mon.summary.fainted_by = "self"
        self._emit_event(
            event_type="faint",
            player=self.state.sides[mon.side].player_name,
            target=mon.nickname,
            target_species=mon.species,
            source=attribution.source_label if attribution else "",
            source_species=attribution.source_species if attribution else "",
            move=attribution.move if attribution else "",
            cause=attribution.cause if attribution else ("self" if mon.summary.fainted_by == "self" else "unknown"),
            cause_detail=attribution.cause_detail if attribution else "",
            is_direct=bool(attribution and attribution.is_direct),
            is_residual=bool(attribution and attribution.is_residual),
            is_hazard=bool(attribution and attribution.is_hazard),
            is_recoil=bool(attribution and attribution.is_recoil),
            is_self_damage=bool(attribution and attribution.is_self_damage),
            raw_line=raw_line,
        )

    def _handle__damage(self, args: List[str], raw_line: str) -> None:
        self._handle_hp_change(args, raw_line, is_heal=False)

    def _handle__heal(self, args: List[str], raw_line: str) -> None:
        self._handle_hp_change(args, raw_line, is_heal=True)

    def _handle_hp_change(self, args: List[str], raw_line: str, *, is_heal: bool) -> None:
        if len(args) < 2:
            self._warn(f"Malformed HP line: {raw_line}")
            return
        entity = self._parse_entity(args[0])
        mon_id = self._resolve_active_mon_from_entity(entity) or self._resolve_pokemon_fallback(entity)
        if not mon_id:
            self._warn(f"Could not resolve HP target: {raw_line}")
            return
        mon = self.state.pokemon[mon_id]
        old_snapshot = mon.current_hp
        new_snapshot = self._parse_hp_snapshot(args[1])
        mon.last_hp = old_snapshot
        mon.current_hp = new_snapshot
        mon.current_status = new_snapshot.status or mon.current_status
        extras = args[2:]
        attribution = self._infer_hp_change_attribution(mon_id, old_snapshot, new_snapshot, extras, is_heal=is_heal)
        amount, amount_pct = self._hp_delta(old_snapshot, new_snapshot, is_heal=is_heal)
        attribution.amount = amount
        attribution.amount_pct = amount_pct
        if amount_pct is not None:
            if is_heal:
                mon.summary.healing_received_pct += amount_pct
            else:
                mon.summary.damage_taken_pct += amount_pct
                if attribution.is_direct:
                    mon.summary.hits_taken += 1
                    mon.summary.direct_damage_taken_pct += amount_pct
                else:
                    mon.summary.indirect_damage_taken_pct += amount_pct
                if attribution.is_hazard:
                    mon.summary.hazard_damage_taken_pct += amount_pct
                if attribution.is_recoil or attribution.is_self_damage:
                    mon.summary.recoil_taken_pct += amount_pct
                if self._should_credit_damage_to_source(attribution, mon_id):
                    source_mon = self.state.pokemon[attribution.source_id]
                    source_mon.summary.damage_dealt_pct += amount_pct
                    if attribution.is_direct:
                        source_mon.summary.direct_damage_dealt_pct += amount_pct
                    else:
                        source_mon.summary.indirect_damage_dealt_pct += amount_pct
                    if attribution.is_hazard:
                        source_mon.summary.hazard_damage_dealt_pct += amount_pct
                    if attribution.is_residual:
                        source_mon.summary.residual_damage_dealt_pct += amount_pct
        if not is_heal and amount_pct is not None and new_snapshot.fainted:
            self.pending_faint_attribution[mon_id] = attribution
        self._emit_event(
            event_type="heal" if is_heal else "damage",
            player=self.state.sides[mon.side].player_name,
            source=attribution.source_label,
            source_species=attribution.source_species,
            target=mon.nickname,
            target_species=mon.species,
            move=attribution.move,
            ability=attribution.cause_detail if attribution.cause == "ability" else "",
            item=attribution.cause_detail if attribution.cause == "item" else "",
            amount=self._format_amount(amount_pct),
            old_hp=old_snapshot.raw if old_snapshot else "",
            new_hp=new_snapshot.raw,
            hp_type=new_snapshot.hp_type if new_snapshot.hp_type != "unknown" else (old_snapshot.hp_type if old_snapshot else "unknown"),
            cause=attribution.cause,
            cause_detail=attribution.cause_detail,
            is_direct=attribution.is_direct,
            is_residual=attribution.is_residual,
            is_hazard=attribution.is_hazard,
            is_recoil=attribution.is_recoil,
            is_self_damage=attribution.is_self_damage,
            is_healing=is_heal,
            raw_line=raw_line,
        )

    def _handle__status(self, args: List[str], raw_line: str) -> None:
        if len(args) < 2:
            self._warn(f"Malformed status line: {raw_line}")
            return
        entity = self._parse_entity(args[0])
        mon_id = self._resolve_active_mon_from_entity(entity) or self._resolve_pokemon_fallback(entity)
        if not mon_id:
            return
        mon = self.state.pokemon[mon_id]
        status = args[1]
        source_id, cause, cause_detail = self._infer_status_source(mon_id, status, args[2:])
        mon.current_status = status
        is_rest_self_status = source_id == mon_id and cause == "move" and cause_detail == "Rest"
        if not is_rest_self_status:
            mon.summary.add_counter(mon.summary.statuses_received, status)
        if source_id and source_id in self.state.pokemon and not is_rest_self_status:
            source_mon = self.state.pokemon[source_id]
            source_mon.summary.add_counter(source_mon.summary.statuses_inflicted, status)
        mon.status_sources[status] = source_id
        self._mark_move_landed_for_secondary_effect(source_id)
        self._emit_event(
            event_type="status",
            player=self.state.sides[mon.side].player_name,
            source=self._label_mon(source_id),
            source_species=self._species_of(source_id),
            target=mon.nickname,
            target_species=mon.species,
            cause=cause,
            cause_detail=cause_detail,
            raw_line=raw_line,
        )

    def _handle__curestatus(self, args: List[str], raw_line: str) -> None:
        if len(args) < 2:
            return
        entity = self._parse_entity(args[0])
        mon_id = self._resolve_active_mon_from_entity(entity) or self._resolve_pokemon_fallback(entity)
        if not mon_id:
            return
        mon = self.state.pokemon[mon_id]
        cured_status = args[1]
        if mon.current_status == cured_status:
            mon.current_status = ""
        self._emit_event(
            event_type="curestatus",
            player=self.state.sides[mon.side].player_name,
            target=mon.nickname,
            target_species=mon.species,
            cause=cured_status,
            raw_line=raw_line,
        )

    def _handle__boost(self, args: List[str], raw_line: str) -> None:
        self._handle_boost_like("boost", args, raw_line, sign=1)

    def _handle__unboost(self, args: List[str], raw_line: str) -> None:
        self._handle_boost_like("unboost", args, raw_line, sign=-1)

    def _handle__setboost(self, args: List[str], raw_line: str) -> None:
        self._handle_boost_like("setboost", args, raw_line, sign=1)

    def _handle_boost_like(self, event_type: str, args: List[str], raw_line: str, *, sign: int) -> None:
        if len(args) < 3:
            return
        entity = self._parse_entity(args[0])
        mon_id = self._resolve_active_mon_from_entity(entity) or self._resolve_pokemon_fallback(entity)
        if not mon_id:
            return
        mon = self.state.pokemon[mon_id]
        stages = self._safe_int(args[2], 1)
        if self.move_context and self.move_context.user_id in self.state.pokemon:
            if self.move_context.user_id == mon_id:
                mon.summary.boosts_received += abs(stages * sign)
            else:
                self.state.pokemon[self.move_context.user_id].summary.boosts_given += abs(stages * sign)
                mon.summary.boosts_received += abs(stages * sign)
                self.move_context.landed_any = True
        self._emit_event(
            event_type=event_type,
            player=self.state.sides[mon.side].player_name,
            source=self._label_mon(self.move_context.user_id) if self.move_context else "",
            source_species=self._species_of(self.move_context.user_id) if self.move_context else "",
            target=mon.nickname,
            target_species=mon.species,
            amount=str(stages * sign),
            cause=args[1],
            raw_line=raw_line,
        )

    def _handle__clearboost(self, args: List[str], raw_line: str) -> None:
        self._emit_event(event_type="clearboost", raw_line=raw_line, cause_detail="|".join(args))

    def _handle__clearallboost(self, args: List[str], raw_line: str) -> None:
        self._emit_event(event_type="clearallboost", raw_line=raw_line, cause_detail="|".join(args))

    def _handle__sidestart(self, args: List[str], raw_line: str) -> None:
        if len(args) < 2:
            return
        side = self._parse_side_token(args[0])
        detail = self._strip_prefix(args[1], "move: ")
        setter_id = self._infer_effect_source(args[2:]) or (self.move_context.user_id if self.move_context else None)
        side_state = self.state.sides[side]
        side_state.side_conditions[detail] = SideCondition(name=detail, setter_id=setter_id, source_move=detail)
        if setter_id and setter_id in self.state.pokemon and detail in HAZARD_NAMES:
            self.state.pokemon[setter_id].summary.add_counter(self.state.pokemon[setter_id].summary.hazards_set, detail)
            self._mark_move_landed_for_secondary_effect(setter_id)
        self._emit_event(
            event_type="sidestart",
            player=side_state.player_name,
            source=self._label_mon(setter_id),
            source_species=self._species_of(setter_id),
            cause=detail,
            raw_line=raw_line,
        )

    def _handle__sideend(self, args: List[str], raw_line: str) -> None:
        if len(args) < 2:
            return
        side = self._parse_side_token(args[0])
        detail = self._strip_prefix(args[1], "move: ")
        side_state = self.state.sides[side]
        removed = side_state.side_conditions.pop(detail, None)
        remover_id = self._infer_effect_source(args[2:]) or (self.move_context.user_id if self.move_context else None)
        if remover_id and remover_id in self.state.pokemon and detail in HAZARD_NAMES:
            self.state.pokemon[remover_id].summary.add_counter(self.state.pokemon[remover_id].summary.hazards_removed, detail)
            self._mark_move_landed_for_secondary_effect(remover_id)
        self._emit_event(
            event_type="sideend",
            player=side_state.player_name,
            source=self._label_mon(remover_id),
            source_species=self._species_of(remover_id),
            cause=detail,
            cause_detail=self._label_mon(removed.setter_id) if removed and removed.setter_id else "",
            raw_line=raw_line,
        )

    def _handle__fieldstart(self, args: List[str], raw_line: str) -> None:
        if not args:
            return
        detail = self._strip_prefix(args[0], "move: ")
        source_id = self._infer_effect_source(args[1:]) or (self.move_context.user_id if self.move_context else None)
        self.terrain_source = {"name": detail, "source_id": source_id}
        self._emit_event(
            event_type="fieldstart",
            source=self._label_mon(source_id),
            source_species=self._species_of(source_id),
            cause=detail,
            raw_line=raw_line,
        )

    def _handle__fieldend(self, args: List[str], raw_line: str) -> None:
        detail = self._strip_prefix(args[0], "move: ") if args else ""
        if self.terrain_source.get("name") == detail:
            self.terrain_source = {"name": "", "source_id": None}
        self._emit_event(event_type="fieldend", cause=detail, raw_line=raw_line)

    def _handle__weather(self, args: List[str], raw_line: str) -> None:
        if not args:
            return
        weather = args[0]
        source_id = self._infer_effect_source(args[1:]) or (self.move_context.user_id if self.move_context else None)
        if weather in {"none", ""}:
            self.weather_source = {"name": "", "source_id": None}
        else:
            self.weather_source = {"name": weather, "source_id": source_id}
            self._mark_move_landed_for_secondary_effect(source_id)
        self._emit_event(
            event_type="weather",
            source=self._label_mon(source_id),
            source_species=self._species_of(source_id),
            cause=weather,
            raw_line=raw_line,
        )

    def _handle__ability(self, args: List[str], raw_line: str) -> None:
        if len(args) < 2:
            return
        entity = self._parse_entity(args[0])
        mon_id = self._resolve_active_mon_from_entity(entity) or self._resolve_pokemon_fallback(entity)
        if not mon_id:
            return
        ability = args[1]
        mon = self.state.pokemon[mon_id]
        mon.revealed_ability = ability
        mon.summary.abilities_revealed.add(ability)
        self._emit_event(
            event_type="ability",
            player=self.state.sides[mon.side].player_name,
            target=mon.nickname,
            target_species=mon.species,
            ability=ability,
            raw_line=raw_line,
        )

    def _handle__item(self, args: List[str], raw_line: str) -> None:
        self._handle_item_reveal(args, raw_line, consumed=False)

    def _handle__enditem(self, args: List[str], raw_line: str) -> None:
        self._handle_item_reveal(args, raw_line, consumed=True)

    def _handle_item_reveal(self, args: List[str], raw_line: str, *, consumed: bool) -> None:
        if len(args) < 2:
            return
        entity = self._parse_entity(args[0])
        mon_id = self._resolve_active_mon_from_entity(entity) or self._resolve_pokemon_fallback(entity)
        if not mon_id:
            return
        item = args[1]
        mon = self.state.pokemon[mon_id]
        mon.revealed_item = "" if consumed else item
        if self.move_context and self.move_context.user_id != mon_id and consumed:
            self.state.pokemon[self.move_context.user_id].summary.items_removed += 1
            self.move_context.landed_any = True
        self._emit_event(
            event_type="enditem" if consumed else "item",
            player=self.state.sides[mon.side].player_name,
            source=self._label_mon(self.move_context.user_id) if self.move_context else "",
            source_species=self._species_of(self.move_context.user_id) if self.move_context else "",
            target=mon.nickname,
            target_species=mon.species,
            item=item,
            cause="item_consumed" if consumed else "item_revealed",
            raw_line=raw_line,
        )

    def _handle__activate(self, args: List[str], raw_line: str) -> None:
        if len(args) < 2:
            return
        entity = self._parse_entity(args[0])
        target_id = self._resolve_active_mon_from_entity(entity) or self._resolve_pokemon_fallback(entity)
        detail = self._strip_prefix(args[1], "move: ")
        if detail in FUTURE_MOVES and target_id:
            delayed = self._pop_delayed_attack(detail, self.state.pokemon[target_id].side, self.state.pokemon[target_id].active_slot)
            self.current_delayed_source = delayed.source_id if delayed else None
        if detail in PROTECTIVE_MOVES and target_id and self.move_context:
            self.move_context.landed_any = True
        self._emit_event(
            event_type="activate",
            target=self._label_mon(target_id),
            target_species=self._species_of(target_id),
            cause=detail,
            raw_line=raw_line,
        )

    def _handle__start(self, args: List[str], raw_line: str) -> None:
        if len(args) < 2:
            return
        entity = self._parse_entity(args[0])
        mon_id = self._resolve_active_mon_from_entity(entity) or self._resolve_pokemon_fallback(entity)
        detail = self._strip_prefix(args[1], "move: ")
        source_id = self._infer_effect_source(args[2:]) or (self.move_context.user_id if self.move_context else None)
        if mon_id and detail:
            if detail == "Leech Seed":
                self.state.pokemon[mon_id].volatile_sources["Leech Seed"] = source_id
            elif detail == "Salt Cure":
                self.state.pokemon[mon_id].volatile_sources["Salt Cure"] = source_id
            elif detail in TRAPPING_MOVES or detail == "partiallytrapped":
                self.state.pokemon[mon_id].volatile_sources["partiallytrapped"] = source_id
                self.state.pokemon[mon_id].volatile_sources["partiallytrapped_move"] = detail
            elif detail == "Nightmare":
                self.state.pokemon[mon_id].volatile_sources["Nightmare"] = source_id
            elif detail == "Confusion":
                self.state.pokemon[mon_id].volatile_sources["confusion"] = source_id
            elif detail == "Curse":
                self.state.pokemon[mon_id].volatile_sources["Curse"] = source_id
            elif detail == "Substitute":
                self.state.pokemon[mon_id].volatile_sources["Substitute"] = source_id or mon_id
        self._mark_move_landed_for_secondary_effect(source_id)
        self._emit_event(
            event_type="start",
            source=self._label_mon(source_id),
            source_species=self._species_of(source_id),
            target=self._label_mon(mon_id),
            target_species=self._species_of(mon_id),
            cause=detail,
            raw_line=raw_line,
        )

    def _handle__end(self, args: List[str], raw_line: str) -> None:
        if len(args) < 2:
            return
        entity = self._parse_entity(args[0])
        mon_id = self._resolve_active_mon_from_entity(entity) or self._resolve_pokemon_fallback(entity)
        detail = self._strip_prefix(args[1], "move: ")
        if mon_id and detail:
            self.state.pokemon[mon_id].volatile_sources.pop(detail, None)
            if detail in {"partiallytrapped", "Substitute"}:
                self.state.pokemon[mon_id].volatile_sources.pop("partiallytrapped_move", None)
        self._emit_event(
            event_type="end",
            target=self._label_mon(mon_id),
            target_species=self._species_of(mon_id),
            cause=detail,
            raw_line=raw_line,
        )

    def _handle__terastallize(self, args: List[str], raw_line: str) -> None:
        if len(args) < 2:
            return
        entity = self._parse_entity(args[0])
        mon_id = self._resolve_active_mon_from_entity(entity) or self._resolve_pokemon_fallback(entity)
        self._emit_event(
            event_type="terastallize",
            target=self._label_mon(mon_id),
            target_species=self._species_of(mon_id),
            cause=args[1],
            raw_line=raw_line,
        )

    def _handle__mega(self, args: List[str], raw_line: str) -> None:
        if not args:
            return
        entity = self._parse_entity(args[0])
        mon_id = self._resolve_active_mon_from_entity(entity) or self._resolve_pokemon_fallback(entity)
        if not mon_id:
            return
        new_species = self._extract_species_from_args(args[1:])
        if new_species:
            self._update_pokemon_species(mon_id, new_species)
        self._emit_event(
            event_type="mega",
            target=self._label_mon(mon_id),
            target_species=self._species_of(mon_id),
            item=args[1] if len(args) > 1 and "Mega" not in args[1] else "",
            cause="mega",
            cause_detail="|".join(args[1:]),
            raw_line=raw_line,
        )

    def _handle__formechange(self, args: List[str], raw_line: str) -> None:
        self._handle_species_change_event("formechange", args, raw_line)

    def _handle_detailschange(self, args: List[str], raw_line: str) -> None:
        self._handle_species_change_event("detailschange", args, raw_line)

    def _handle__miss(self, args: List[str], raw_line: str) -> None:
        if self.move_context:
            self.move_context.missed = True
            self.state.pokemon[self.move_context.user_id].summary.misses += 1
        target_id = None
        if len(args) > 1:
            target_entity = self._parse_entity(args[1])
            target_id = self._resolve_active_mon_from_entity(target_entity) or self._resolve_pokemon_fallback(target_entity)
            if target_id and self.move_context and target_id != self.move_context.user_id:
                self.state.pokemon[target_id].summary.moves_dodged += 1
        self._emit_event(
            event_type="miss",
            source=self._label_mon(self.move_context.user_id) if self.move_context else "",
            source_species=self._species_of(self.move_context.user_id) if self.move_context else "",
            target=self._label_mon(target_id) if target_id else (args[1] if len(args) > 1 else ""),
            target_species=self._species_of(target_id),
            move=self.move_context.move if self.move_context else "",
            raw_line=raw_line,
        )

    def _handle__fail(self, args: List[str], raw_line: str) -> None:
        if self.move_context:
            self.move_context.failed = True
        self._emit_event(event_type="fail", raw_line=raw_line, cause_detail="|".join(args))

    def _handle__immune(self, args: List[str], raw_line: str) -> None:
        self._emit_event(event_type="immune", raw_line=raw_line, cause_detail="|".join(args))

    def _handle__crit(self, args: List[str], raw_line: str) -> None:
        target_id = self._resolve_event_target_id(args)
        if self.move_context and self.move_context.user_id in self.state.pokemon:
            self.state.pokemon[self.move_context.user_id].summary.crits += 1
        if target_id and target_id in self.state.pokemon:
            self.state.pokemon[target_id].summary.crits_taken += 1
        self._emit_event(
            event_type="crit",
            source=self._label_mon(self.move_context.user_id) if self.move_context else "",
            source_species=self._species_of(self.move_context.user_id) if self.move_context else "",
            target=self._label_mon(target_id),
            target_species=self._species_of(target_id),
            move=self.move_context.move if self.move_context else "",
            raw_line=raw_line,
            cause_detail="|".join(args),
        )

    def _handle__supereffective(self, args: List[str], raw_line: str) -> None:
        target_id = self._resolve_event_target_id(args)
        if target_id and target_id in self.state.pokemon:
            self.state.pokemon[target_id].summary.super_effective_hits_taken += 1
        self._emit_event(
            event_type="supereffective",
            source=self._label_mon(self.move_context.user_id) if self.move_context else "",
            source_species=self._species_of(self.move_context.user_id) if self.move_context else "",
            target=self._label_mon(target_id),
            target_species=self._species_of(target_id),
            move=self.move_context.move if self.move_context else "",
            raw_line=raw_line,
            cause_detail="|".join(args),
        )

    def _handle__resisted(self, args: List[str], raw_line: str) -> None:
        target_id = self._resolve_event_target_id(args)
        if target_id and target_id in self.state.pokemon:
            self.state.pokemon[target_id].summary.resisted_hits_taken += 1
        self._emit_event(
            event_type="resisted",
            source=self._label_mon(self.move_context.user_id) if self.move_context else "",
            source_species=self._species_of(self.move_context.user_id) if self.move_context else "",
            target=self._label_mon(target_id),
            target_species=self._species_of(target_id),
            move=self.move_context.move if self.move_context else "",
            raw_line=raw_line,
            cause_detail="|".join(args),
        )

    def _handle__hitcount(self, args: List[str], raw_line: str) -> None:
        count = self._safe_int(args[1], 0) if len(args) > 1 else 0
        if self.move_context and count:
            self.move_context.hits = max(self.move_context.hits, count)
            self.move_context.landed_any = True
        self._emit_event(event_type="hitcount", amount=str(count), raw_line=raw_line)

    def _resolve_pokemon_for_switch(self, entity: EntityRef, details: str) -> PokemonState:
        species = self._parse_species_from_details(details)
        nickname = entity.name or species
        side = entity.side or "p1"
        side_state = self.state.sides[side]

        existing = self._find_side_pokemon(side, nickname, species)
        if existing:
            mon = self.state.pokemon[existing]
            if species and mon.species != species:
                mon.species = species
            if nickname:
                mon.nickname = nickname
            return mon

        team_position = self._match_preview_position(side_state, species)
        mon_id = f"{self.state.battle_id}:{side}:{team_position or len(side_state.team) + 1}:{nickname}"
        mon = PokemonState(
            mon_id=mon_id,
            side=side,
            nickname=nickname,
            species=species,
            team_position=team_position or len(side_state.team) + 1,
        )
        self.state.pokemon[mon_id] = mon
        side_state.team.append(mon_id)
        return mon

    def _match_preview_position(self, side_state, species: str) -> int:
        matches = [idx + 1 for idx, name in enumerate(side_state.preview_species) if name == species]
        used_positions = {self.state.pokemon[mon_id].team_position for mon_id in side_state.team}
        for position in matches:
            if position not in used_positions:
                return position
        return len(side_state.team) + 1

    def _find_side_pokemon(self, side: str, nickname: str, species: str) -> Optional[str]:
        side_state = self.state.sides[side]
        exact_inactive_matches: List[str] = []
        species_inactive_matches: List[str] = []

        for mon_id in side_state.team:
            mon = self.state.pokemon[mon_id]
            if mon.species == species and not mon.active:
                species_inactive_matches.append(mon_id)
                if mon.nickname == nickname:
                    exact_inactive_matches.append(mon_id)

        if exact_inactive_matches:
            return exact_inactive_matches[0]
        if species_inactive_matches:
            return species_inactive_matches[0]
        return None

    def _withdraw_slot_if_needed(self, side: str, slot: Optional[str]) -> None:
        if not side or not slot:
            return
        current_id = self.state.sides[side].active_slots.get(slot)
        if not current_id:
            return
        mon = self.state.pokemon[current_id]
        self._close_active_window(mon)
        mon.active = False
        mon.active_slot = None

    def _close_active_window(self, mon: PokemonState) -> None:
        if mon.active_since_turn is None:
            return
        turns = max(1, self.state.current_turn - mon.active_since_turn + 1)
        mon.summary.turns_active += turns
        mon.active_since_turn = None

    def _finalize_active_turns(self) -> None:
        for mon in self.state.pokemon.values():
            if mon.active:
                self._close_active_window(mon)
                mon.active = False

    def _resolve_active_mon_from_entity(self, entity: EntityRef) -> Optional[str]:
        if not entity.side:
            return None
        if entity.slot and entity.slot in self.state.sides[entity.side].active_slots:
            return self.state.sides[entity.side].active_slots[entity.slot]
        return self._resolve_pokemon_fallback(entity)

    def _resolve_pokemon_fallback(self, entity: EntityRef) -> Optional[str]:
        if not entity.side:
            return None
        side_state = self.state.sides[entity.side]
        nickname_matches: List[str] = []
        for mon_id in side_state.team:
            mon = self.state.pokemon[mon_id]
            if entity.name and mon.nickname == entity.name:
                nickname_matches.append(mon_id)
        if len(nickname_matches) == 1:
            return nickname_matches[0]
        normalized_name = self._normalize_species_name(entity.name) if entity.name else ""
        species_matches: List[str] = []
        for mon_id in side_state.team:
            mon = self.state.pokemon[mon_id]
            if normalized_name and mon.species == normalized_name:
                species_matches.append(mon_id)
        if len(species_matches) == 1:
            return species_matches[0]
        return None

    def _handle_species_change_event(self, event_type: str, args: List[str], raw_line: str) -> None:
        if len(args) < 2:
            return
        entity = self._parse_entity(args[0])
        mon_id = self._resolve_active_mon_from_entity(entity) or self._resolve_pokemon_fallback(entity)
        if not mon_id:
            return
        new_species = self._parse_species_from_details(args[1])
        self._update_pokemon_species(mon_id, new_species)
        self._emit_event(
            event_type=event_type,
            target=self._label_mon(mon_id),
            target_species=self._species_of(mon_id),
            cause=event_type,
            cause_detail=args[1],
            raw_line=raw_line,
        )

    def _update_pokemon_species(self, mon_id: str, new_species: str) -> None:
        normalized = self._normalize_species_name(new_species)
        if not normalized:
            return
        self.state.pokemon[mon_id].species = normalized

    def _parse_entity(self, token: str) -> EntityRef:
        token = token.strip()
        if not token:
            return EntityRef(token="")
        if ": " not in token:
            if token.startswith("p") and len(token) >= 2:
                if len(token) >= 3 and token[2].isalpha():
                    return EntityRef(token=token, side=token[:2], slot=token[2], name=token)
                return EntityRef(token=token, side=token[:2], name=token)
            return EntityRef(token=token, name=token)
        head, name = token.split(": ", 1)
        side = head[:2] if len(head) >= 2 and head[0] == "p" else None
        slot = head[2] if len(head) >= 3 else None
        return EntityRef(token=token, side=side, slot=slot, name=name)

    def _parse_side_token(self, token: str) -> str:
        token = token.strip()
        if token.startswith("p1"):
            return "p1"
        if token.startswith("p2"):
            return "p2"
        return token[:2]

    def _parse_hp_snapshot(self, raw: str) -> HPSnapshot:
        raw = raw.strip()
        if not raw:
            return HPSnapshot(raw="")
        pieces = raw.split()
        hp_piece = pieces[0]
        status = pieces[1] if len(pieces) > 1 else None
        if hp_piece == "0":
            return HPSnapshot(raw=raw, current=0.0, maximum=100.0, hp_type="percent", status=status, fainted=True)
        if hp_piece == "0/0":
            return HPSnapshot(raw=raw, current=0.0, maximum=0.0, hp_type="unknown", status=status, fainted=True)
        if hp_piece == "0" or hp_piece == "fnt" or raw.endswith("fnt"):
            return HPSnapshot(raw=raw, current=0.0, maximum=100.0, hp_type="percent", status=status, fainted=True)
        if hp_piece == "0/100":
            return HPSnapshot(raw=raw, current=0.0, maximum=100.0, hp_type="percent", status=status, fainted=True)
        if hp_piece == "0/100.0":
            return HPSnapshot(raw=raw, current=0.0, maximum=100.0, hp_type="percent", status=status, fainted=True)
        if hp_piece == "0" or hp_piece == "0 fnt":
            return HPSnapshot(raw=raw, current=0.0, maximum=100.0, hp_type="percent", status=status, fainted=True)
        if hp_piece == "0" or raw == "0 fnt":
            return HPSnapshot(raw=raw, current=0.0, maximum=100.0, hp_type="percent", status=status, fainted=True)
        if hp_piece == "0" or raw == "0":
            return HPSnapshot(raw=raw, current=0.0, maximum=100.0, hp_type="percent", status=status, fainted=True)
        if hp_piece == "0" or raw.endswith(" fnt"):
            return HPSnapshot(raw=raw, current=0.0, maximum=100.0, hp_type="percent", status=status, fainted=True)
        if hp_piece == "0" or hp_piece == "fnt":
            return HPSnapshot(raw=raw, current=0.0, maximum=100.0, hp_type="percent", status=status, fainted=True)
        if hp_piece == "0" or hp_piece == "0/100":
            return HPSnapshot(raw=raw, current=0.0, maximum=100.0, hp_type="percent", status=status, fainted=True)
        if hp_piece == "fnt":
            return HPSnapshot(raw=raw, current=0.0, maximum=100.0, hp_type="percent", status=status, fainted=True)
        if hp_piece == "0" or "fnt" in pieces:
            return HPSnapshot(raw=raw, current=0.0, maximum=100.0, hp_type="percent", status=status, fainted=True)
        if "/" in hp_piece:
            current_text, max_text = hp_piece.split("/", 1)
            try:
                current = float(current_text)
                maximum = float(max_text)
                hp_type = "percent" if maximum == 100 else "exact"
                return HPSnapshot(
                    raw=raw,
                    current=current,
                    maximum=maximum,
                    hp_type=hp_type,
                    status=status,
                    fainted=current <= 0,
                )
            except ValueError:
                return HPSnapshot(raw=raw, status=status, fainted="fnt" in pieces)
        return HPSnapshot(raw=raw, status=status, fainted="fnt" in pieces)

    def _parse_annotations(self, extras: List[str]) -> Dict[str, List[str] | str]:
        parsed: Dict[str, List[str] | str] = {"from": "", "of": "", "wisher": "", "via": []}
        for extra in extras:
            extra = extra.strip()
            if extra.startswith("[from] "):
                parsed["from"] = extra[7:]
            elif extra.startswith("[of] "):
                parsed["of"] = extra[5:]
            elif extra.startswith("[wisher] "):
                parsed["wisher"] = extra[9:]
            else:
                cast = parsed.setdefault("via", [])
                assert isinstance(cast, list)
                cast.append(extra)
        return parsed

    def _infer_hp_change_attribution(
        self,
        target_id: str,
        old_snapshot: Optional[HPSnapshot],
        new_snapshot: HPSnapshot,
        extras: List[str],
        *,
        is_heal: bool,
    ) -> DamageAttribution:
        annotations = self._parse_annotations(extras)
        from_text = str(annotations.get("from") or "")
        of_text = str(annotations.get("of") or "")
        wisher = str(annotations.get("wisher") or "")
        target_mon = self.state.pokemon[target_id]
        source_id = self._resolve_annotation_source(of_text)

        if is_heal:
            if from_text == "move: Wish":
                source_id = self._resolve_annotation_source(wisher) or self.pending_wishes.get(target_mon.side, PendingWish("", target_mon.side, 0)).source_id
                return self._build_attribution(source_id, move="Wish", cause="move", cause_detail="Wish", is_healing=True)
            if from_text == "Leech Seed":
                source_id = source_id or target_mon.volatile_sources.get("Leech Seed")
                return self._build_attribution(source_id, move="Leech Seed", cause="move", cause_detail="Leech Seed", is_healing=True)
            if from_text.startswith("move: "):
                move_name = self._strip_prefix(from_text, "move: ")
                source_id = source_id or (self.move_context.user_id if self.move_context else None)
                return self._build_attribution(source_id, move=move_name, cause="move", cause_detail=move_name, is_healing=True)
            if from_text.startswith("item: "):
                return self._build_attribution(target_id, item=self._strip_prefix(from_text, "item: "), cause="item", cause_detail=self._strip_prefix(from_text, "item: "), is_healing=True)
            if from_text.startswith("ability: "):
                return self._build_attribution(source_id or target_id, ability=self._strip_prefix(from_text, "ability: "), cause="ability", cause_detail=self._strip_prefix(from_text, "ability: "), is_healing=True)
            if from_text == "Grassy Terrain":
                source_id = source_id or self.terrain_source.get("source_id")
                return self._build_attribution(source_id, cause="terrain", cause_detail="Grassy Terrain", is_healing=True)
            return self._build_attribution(source_id or target_id, cause="healing", cause_detail=from_text or "unknown", is_healing=True)

        if from_text in HAZARD_NAMES:
            setter = self.state.sides[target_mon.side].side_conditions.get(from_text)
            source_id = source_id or (setter.setter_id if setter else None)
            return self._build_attribution(source_id, move=from_text, cause="hazard", cause_detail=from_text, is_residual=True, is_hazard=True)
        if from_text == "move: Future Sight":
            source_id = source_id or self.current_delayed_source
            return self._build_attribution(source_id, move="Future Sight", cause="move", cause_detail="Future Sight", is_direct=True)
        if from_text == "move: Doom Desire":
            source_id = source_id or self.current_delayed_source
            return self._build_attribution(source_id, move="Doom Desire", cause="move", cause_detail="Doom Desire", is_direct=True)
        if from_text.startswith("ability: "):
            ability = self._strip_prefix(from_text, "ability: ")
            source_id = source_id or self._infer_contact_punish_source(target_id)
            return self._build_attribution(source_id, ability=ability, cause="ability", cause_detail=ability, is_residual=True)
        if from_text.startswith("item: "):
            item = self._strip_prefix(from_text, "item: ")
            if item == "Life Orb":
                source_id = target_id
            else:
                source_id = source_id or self._infer_contact_punish_source(target_id)
            return self._build_attribution(
                source_id,
                item=item,
                cause="item",
                cause_detail=item,
                is_residual=True,
                is_recoil=item == "Life Orb",
                is_self_damage=item == "Life Orb",
            )
        if from_text in WEATHER_DAMAGE_CAUSES:
            source_id = source_id or self.weather_source.get("source_id")
            return self._build_attribution(source_id, cause="weather", cause_detail=from_text, is_residual=True)
        if from_text in {"psn", "tox", "brn"}:
            source_id = target_mon.status_sources.get(from_text) or source_id
            return self._build_attribution(source_id, cause="status", cause_detail=STATUS_DAMAGE_MAP.get(from_text, from_text), is_residual=True)
        if from_text == "Leech Seed":
            source_id = source_id or target_mon.volatile_sources.get("Leech Seed")
            return self._build_attribution(source_id, move="Leech Seed", cause="move", cause_detail="Leech Seed", is_residual=True)
        if from_text == "Salt Cure":
            source_id = source_id or target_mon.volatile_sources.get("Salt Cure")
            return self._build_attribution(source_id, move="Salt Cure", cause="move", cause_detail="Salt Cure", is_residual=True)
        if from_text == "Curse":
            source_id = source_id or target_mon.volatile_sources.get("Curse")
            return self._build_attribution(source_id, move="Curse", cause="move", cause_detail="Curse", is_residual=True)
        if from_text == "Nightmare":
            source_id = source_id or target_mon.volatile_sources.get("Nightmare")
            return self._build_attribution(source_id, move="Nightmare", cause="move", cause_detail="Nightmare", is_residual=True)
        if from_text == "confusion":
            source_id = target_id
            return self._build_attribution(source_id, cause="self", cause_detail="confusion", is_residual=True, is_self_damage=True)
        if from_text == "Recoil":
            source_id = target_id
            move_name = self.move_context.move if self.move_context and self.move_context.user_id == target_id else ""
            return self._build_attribution(source_id, move=move_name, cause="recoil", cause_detail="Recoil", is_residual=True, is_recoil=True, is_self_damage=True)
        if from_text == "move: Belly Drum":
            return self._build_attribution(target_id, move="Belly Drum", cause="self", cause_detail="Belly Drum", is_residual=True, is_self_damage=True)
        if from_text in {"High Jump Kick", "Jump Kick"} or from_text.startswith("move: High Jump Kick") or from_text.startswith("move: Jump Kick"):
            move_name = self._strip_prefix(from_text, "move: ")
            return self._build_attribution(target_id, move=move_name, cause="crash", cause_detail=move_name, is_residual=True, is_self_damage=True)
        if from_text == "move: Struggle":
            return self._build_attribution(target_id, move="Struggle", cause="recoil", cause_detail="Struggle", is_residual=True, is_recoil=True, is_self_damage=True)
        if from_text == "move: Pain Split":
            source_id = source_id or (self.move_context.user_id if self.move_context else None)
            return self._build_attribution(source_id, move="Pain Split", cause="move", cause_detail="Pain Split", is_direct=False, is_residual=True)
        if from_text == "move: Substitute":
            return self._build_attribution(target_id, move="Substitute", cause="self", cause_detail="Substitute", is_residual=True, is_self_damage=True)
        if target_mon.volatile_sources.get("partiallytrapped") and from_text == "":
            source_id = target_mon.volatile_sources.get("partiallytrapped")
            move_name = target_mon.volatile_sources.get("partiallytrapped_move", "partial trap")
            return self._build_attribution(source_id, move=move_name, cause="move", cause_detail=str(move_name), is_residual=True)
        if self.move_context and self.move_context.user_id != target_id:
            self.move_context.hits += 1
            self.move_context.landed_any = True
            if self.move_context.move in {"Roar", "Whirlwind", "Dragon Tail", "Circle Throw"}:
                self.pending_switch_source = self.move_context.user_id
                self.move_context.caused_switch = True
            return self._build_attribution(self.move_context.user_id, move=self.move_context.move, cause="move", cause_detail=self.move_context.move, is_direct=True)
        return self._build_attribution(None, cause="unknown", cause_detail=from_text or "unattributed", is_residual=bool(from_text))

    def _infer_status_source(self, target_id: str, status: str, extras: List[str]) -> Tuple[Optional[str], str, str]:
        annotations = self._parse_annotations(extras)
        from_text = str(annotations.get("from") or "")
        source_id = self._resolve_annotation_source(str(annotations.get("of") or ""))
        if from_text == "move: Toxic Spikes":
            return self._toxic_spikes_setter(target_id), "hazard", "Toxic Spikes"
        if from_text.startswith("move: "):
            move_name = self._strip_prefix(from_text, "move: ")
            return source_id or (self.move_context.user_id if self.move_context else None), "move", move_name
        if from_text.startswith("ability: "):
            ability = self._strip_prefix(from_text, "ability: ")
            return source_id or self._infer_contact_punish_source(target_id), "ability", ability
        if not from_text and status in {"psn", "tox"}:
            setter_id = self._toxic_spikes_setter(target_id)
            if setter_id:
                return setter_id, "hazard", "Toxic Spikes"
        if self.move_context and self.move_context.user_id != target_id:
            return self.move_context.user_id, "move", self.move_context.move
        return source_id, "unknown", status

    def _toxic_spikes_setter(self, target_id: str) -> Optional[str]:
        target_side = self.state.pokemon[target_id].side
        setter = self.state.sides[target_side].side_conditions.get("Toxic Spikes")
        return setter.setter_id if setter else None

    def _build_attribution(
        self,
        source_id: Optional[str],
        *,
        move: str = "",
        ability: str = "",
        item: str = "",
        cause: str = "",
        cause_detail: str = "",
        is_direct: bool = False,
        is_residual: bool = False,
        is_hazard: bool = False,
        is_recoil: bool = False,
        is_self_damage: bool = False,
        is_healing: bool = False,
    ) -> DamageAttribution:
        return DamageAttribution(
            source_id=source_id,
            source_label=self._label_mon(source_id) if source_id else ("self" if is_self_damage else "unknown"),
            source_species=self._species_of(source_id),
            player=self._player_of(source_id),
            move=move,
            cause=cause,
            cause_detail=ability or item or cause_detail,
            is_direct=is_direct,
            is_residual=is_residual,
            is_hazard=is_hazard,
            is_recoil=is_recoil,
            is_self_damage=is_self_damage,
            is_healing=is_healing,
        )

    def _hp_delta(
        self,
        old_snapshot: Optional[HPSnapshot],
        new_snapshot: HPSnapshot,
        *,
        is_heal: bool,
    ) -> Tuple[Optional[float], Optional[float]]:
        if not old_snapshot or old_snapshot.current is None or new_snapshot.current is None:
            return None, None
        delta = (new_snapshot.current - old_snapshot.current) if is_heal else (old_snapshot.current - new_snapshot.current)
        if delta < 0:
            delta = 0
        if old_snapshot.hp_type == "exact" and old_snapshot.maximum:
            return delta, (delta / old_snapshot.maximum) * 100
        if old_snapshot.hp_type == "percent":
            return delta, delta
        if new_snapshot.hp_type == "exact" and new_snapshot.maximum:
            return delta, (delta / new_snapshot.maximum) * 100
        if new_snapshot.hp_type == "percent":
            return delta, delta
        return delta, None

    def _resolve_annotation_source(self, token: str) -> Optional[str]:
        if not token:
            return None
        return self._resolve_active_mon_from_entity(self._parse_entity(token)) or self._resolve_pokemon_fallback(self._parse_entity(token))

    def _infer_effect_source(self, extras: List[str]) -> Optional[str]:
        annotations = self._parse_annotations(extras)
        source = self._resolve_annotation_source(str(annotations.get("of") or ""))
        if source:
            return source
        if self.move_context:
            return self.move_context.user_id
        return None

    def _infer_contact_punish_source(self, target_id: str) -> Optional[str]:
        if self.move_context and self.move_context.user_id == target_id and self.move_context.target_id:
            return self.move_context.target_id
        return None

    def _mark_move_landed_for_secondary_effect(self, source_id: Optional[str]) -> None:
        if self.move_context and source_id and self.move_context.user_id == source_id:
            self.move_context.landed_any = True

    def _finalize_move_context(self) -> None:
        if not self.move_context:
            return
        mon = self.state.pokemon.get(self.move_context.user_id)
        if mon and self.move_context.landed_any:
            mon.summary.hits_landed += self.move_context.hits or 1
        self.move_context = None
        self.current_delayed_source = None

    def _build_pokemon_rows(self) -> List[PokemonSummaryRow]:
        rows: List[PokemonSummaryRow] = []
        winner_side = ""
        for side, side_state in self.state.sides.items():
            if side_state.player_name and side_state.player_name == self.state.winner:
                winner_side = side
                break
        for side in ("p1", "p2"):
            for mon_id in self.state.sides[side].team:
                mon = self.state.pokemon[mon_id]
                result = "win" if winner_side and winner_side == mon.side else ("loss" if winner_side else "unknown")
                rows.append(
                    PokemonSummaryRow(
                        battle_id=self.state.battle_id,
                        player=self.state.sides[mon.side].player_name,
                        pokemon_nickname=mon.nickname,
                        species=mon.species,
                        team_position=mon.team_position,
                        result=result,
                        turns_active=mon.summary.turns_active,
                        switches_in=mon.summary.switches_in,
                        moves_used=mon.summary.moves_used,
                        hits_landed=mon.summary.hits_landed,
                        hits_taken=mon.summary.hits_taken,
                        misses=mon.summary.misses,
                        moves_dodged=mon.summary.moves_dodged,
                        crits=mon.summary.crits,
                        crits_taken=mon.summary.crits_taken,
                        super_effective_hits_taken=mon.summary.super_effective_hits_taken,
                        resisted_hits_taken=mon.summary.resisted_hits_taken,
                        damage_dealt_pct=round(mon.summary.damage_dealt_pct, 2),
                        direct_damage_dealt_pct=round(mon.summary.direct_damage_dealt_pct, 2),
                        indirect_damage_dealt_pct=round(mon.summary.indirect_damage_dealt_pct, 2),
                        hazard_damage_dealt_pct=round(mon.summary.hazard_damage_dealt_pct, 2),
                        residual_damage_dealt_pct=round(mon.summary.residual_damage_dealt_pct, 2),
                        damage_taken_pct=round(mon.summary.damage_taken_pct, 2),
                        direct_damage_taken_pct=round(mon.summary.direct_damage_taken_pct, 2),
                        indirect_damage_taken_pct=round(mon.summary.indirect_damage_taken_pct, 2),
                        hazard_damage_taken_pct=round(mon.summary.hazard_damage_taken_pct, 2),
                        recoil_taken_pct=round(mon.summary.recoil_taken_pct, 2),
                        healing_received_pct=round(mon.summary.healing_received_pct, 2),
                        kos=mon.summary.kos,
                        direct_kos=mon.summary.direct_kos,
                        indirect_kos=mon.summary.indirect_kos,
                        deaths=mon.summary.deaths,
                        fainted_by=mon.summary.fainted_by,
                        status_inflicted=counter_total(mon.summary.statuses_inflicted),
                        status_received=counter_total(mon.summary.statuses_received),
                        hazards_set=counter_total(mon.summary.hazards_set),
                        hazards_removed=counter_total(mon.summary.hazards_removed),
                        boosts_given=mon.summary.boosts_given,
                        boosts_received=mon.summary.boosts_received,
                        items_removed=mon.summary.items_removed,
                        abilities_revealed="; ".join(sorted(mon.summary.abilities_revealed)),
                    )
                )
        return rows

    def _emit_event(self, **kwargs) -> None:
        event = EventRow(
            battle_id=self.state.battle_id,
            replay_url=self.state.replay_url,
            turn=self.state.current_turn,
            event_type=kwargs.get("event_type", ""),
            player=kwargs.get("player", ""),
            source=kwargs.get("source", ""),
            source_species=kwargs.get("source_species", ""),
            target=kwargs.get("target", ""),
            target_species=kwargs.get("target_species", ""),
            move=kwargs.get("move", ""),
            ability=kwargs.get("ability", ""),
            item=kwargs.get("item", ""),
            amount=kwargs.get("amount", ""),
            old_hp=kwargs.get("old_hp", ""),
            new_hp=kwargs.get("new_hp", ""),
            hp_type=kwargs.get("hp_type", "unknown"),
            cause=kwargs.get("cause", ""),
            cause_detail=kwargs.get("cause_detail", ""),
            is_direct=kwargs.get("is_direct", False),
            is_residual=kwargs.get("is_residual", False),
            is_hazard=kwargs.get("is_hazard", False),
            is_recoil=kwargs.get("is_recoil", False),
            is_self_damage=kwargs.get("is_self_damage", False),
            is_healing=kwargs.get("is_healing", False),
            raw_line=kwargs.get("raw_line", ""),
        )
        self.events.append(event)
        if self.debug and event.cause in {"unknown", "healing"} and event.raw_line:
            LOGGER.debug("Event attribution: %s", asdict(event))

    def _warn(self, message: str) -> None:
        self.warnings.append(message)
        if self.debug:
            LOGGER.warning(message)

    @staticmethod
    def _strip_prefix(value: str, prefix: str) -> str:
        return value[len(prefix) :] if value.startswith(prefix) else value

    @staticmethod
    def _parse_species_from_details(details: str) -> str:
        raw_species = details.split(",", 1)[0].strip()
        return BattleParser._normalize_species_name(raw_species)

    @staticmethod
    def _normalize_species_name(species: str) -> str:
        species = species.strip()
        if species.endswith("-Tera"):
            return species[: -len("-Tera")]
        return species

    @staticmethod
    def _extract_species_from_args(args: List[str]) -> str:
        for value in args:
            candidate = value.split(",", 1)[0].strip()
            if "Mega" in candidate or candidate.endswith("-Primal"):
                return candidate
        return ""

    @staticmethod
    def _safe_int(value: str, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return default

    @staticmethod
    def _format_amount(value: Optional[float]) -> str:
        if value is None:
            return ""
        return f"{value:.2f}".rstrip("0").rstrip(".")

    def _label_mon(self, mon_id: Optional[str]) -> str:
        if mon_id and mon_id in self.state.pokemon:
            return self.state.pokemon[mon_id].nickname
        return ""

    def _resolve_event_target_id(self, args: List[str]) -> Optional[str]:
        if not args:
            return None
        entity = self._parse_entity(args[0])
        return self._resolve_active_mon_from_entity(entity) or self._resolve_pokemon_fallback(entity)

    def _should_credit_damage_to_source(self, attribution: DamageAttribution, target_id: str) -> bool:
        if not attribution.source_id or attribution.source_id not in self.state.pokemon:
            return False
        if attribution.is_self_damage:
            return False
        if attribution.source_id == target_id:
            return False
        return True

    def _should_credit_ko(self, attribution: DamageAttribution, fainted_mon_id: str) -> bool:
        if not attribution.source_id or attribution.source_id not in self.state.pokemon:
            return False
        if attribution.is_self_damage:
            return False
        if attribution.source_id == fainted_mon_id:
            return False
        return True

    def _species_of(self, mon_id: Optional[str]) -> str:
        if mon_id and mon_id in self.state.pokemon:
            return self.state.pokemon[mon_id].species
        return ""

    def _player_of(self, mon_id: Optional[str]) -> str:
        if mon_id and mon_id in self.state.pokemon:
            return self.state.sides[self.state.pokemon[mon_id].side].player_name
        return ""

    def _swap_side_conditions(self) -> None:
        left = self.state.sides["p1"].side_conditions
        right = self.state.sides["p2"].side_conditions
        self.state.sides["p1"].side_conditions, self.state.sides["p2"].side_conditions = right, left

    def _pop_delayed_attack(self, move: str, target_side: Optional[str], target_slot: Optional[str]) -> Optional[PendingDelayedAttack]:
        for idx, pending in enumerate(self.pending_delayed_attacks):
            if pending.move != move:
                continue
            if target_side and pending.target_side and pending.target_side != target_side:
                continue
            if target_slot and pending.target_slot and pending.target_slot != target_slot:
                continue
            return self.pending_delayed_attacks.pop(idx)
        return None
