from __future__ import annotations

import unittest

from showdown_stats.parser import BattleParser


class BattleParserTests(unittest.TestCase):
    def parse_battle(self, log: str):
        parser = BattleParser(debug=False)
        return parser.parse(log.strip(), battle_id="test-battle")

    def find_row(self, result, nickname: str):
        for row in result.pokemon_rows:
            if row.pokemon_nickname == nickname:
                return row
        raise AssertionError(f"Could not find Pokemon row for {nickname}")

    def test_direct_damage_and_direct_ko(self):
        result = self.parse_battle(
            """
|player|p1|Alice|
|player|p2|Bob|
|switch|p1a: Sparky|Pikachu, M|100/100
|switch|p2a: Bulby|Bulbasaur, M|100/100
|turn|1
|move|p1a: Sparky|Thunderbolt|p2a: Bulby
|-damage|p2a: Bulby|0 fnt
|faint|p2a: Bulby
|win|Alice
            """
        )
        sparky = self.find_row(result, "Sparky")
        bulby = self.find_row(result, "Bulby")
        self.assertEqual(sparky.direct_kos, 1)
        self.assertEqual(sparky.kos, 1)
        self.assertEqual(round(sparky.direct_damage_dealt_pct, 2), 100.0)
        self.assertEqual(bulby.deaths, 1)
        self.assertEqual(bulby.fainted_by, "Sparky")
        self.assertEqual(bulby.hits_taken, 1)

    def test_hazard_damage_is_credited_to_setter(self):
        result = self.parse_battle(
            """
|player|p1|Alice|
|player|p2|Bob|
|switch|p1a: Chomp|Garchomp, M|100/100
|switch|p2a: Corvi|Corviknight, M|100/100
|turn|1
|move|p1a: Chomp|Stealth Rock|p2a: Corvi
|-sidestart|p2: Bob|move: Stealth Rock
|turn|2
|switch|p2a: Volc|Volcarona, F|100/100
|-damage|p2a: Volc|50/100|[from] Stealth Rock
|win|Alice
            """
        )
        chomp = self.find_row(result, "Chomp")
        volc = self.find_row(result, "Volc")
        self.assertEqual(chomp.hazards_set, 1)
        self.assertEqual(round(chomp.hazard_damage_dealt_pct, 2), 50.0)
        self.assertEqual(round(volc.hazard_damage_taken_pct, 2), 50.0)

    def test_poison_residual_is_credited_to_inflictor(self):
        result = self.parse_battle(
            """
|player|p1|Alice|
|player|p2|Bob|
|switch|p1a: Bliss|Blissey, F|100/100
|switch|p2a: Tusk|Great Tusk|100/100
|turn|1
|move|p1a: Bliss|Toxic|p2a: Tusk
|-status|p2a: Tusk|tox
|turn|2
|-damage|p2a: Tusk|88/100 tox|[from] tox
|win|Alice
            """
        )
        bliss = self.find_row(result, "Bliss")
        tusk = self.find_row(result, "Tusk")
        self.assertEqual(bliss.status_inflicted, 1)
        self.assertEqual(round(bliss.residual_damage_dealt_pct, 2), 12.0)

    def test_leech_seed_tracks_residual_damage_and_healing(self):
        result = self.parse_battle(
            """
|player|p1|Alice|
|player|p2|Bob|
|switch|p1a: Ferro|Ferrothorn, M|70/100
|switch|p2a: Rotom|Rotom-Wash|100/100
|turn|1
|move|p1a: Ferro|Leech Seed|p2a: Rotom
|-start|p2a: Rotom|move: Leech Seed
|turn|2
|-damage|p2a: Rotom|88/100|[from] Leech Seed
|-heal|p1a: Ferro|82/100|[from] Leech Seed|[of] p2a: Rotom
|win|Alice
            """
        )
        ferro = self.find_row(result, "Ferro")
        rotom = self.find_row(result, "Rotom")
        self.assertEqual(round(ferro.residual_damage_dealt_pct, 2), 12.0)
        self.assertEqual(round(ferro.healing_received_pct, 2), 12.0)

    def test_recoil_and_rocky_helmet_are_classified(self):
        result = self.parse_battle(
            """
|player|p1|Alice|
|player|p2|Bob|
|switch|p1a: Champ|Machamp, M|100/100
|switch|p2a: Ferro|Ferrothorn, M|100/100
|turn|1
|move|p1a: Champ|Close Combat|p2a: Ferro
|-damage|p2a: Ferro|60/100
|-damage|p1a: Champ|83/100|[from] item: Rocky Helmet|[of] p2a: Ferro
|turn|2
|move|p1a: Champ|Double-Edge|p2a: Ferro
|-damage|p2a: Ferro|0 fnt
|faint|p2a: Ferro
|-damage|p1a: Champ|50/100|[from] Recoil
|win|Alice
            """
        )
        champ = self.find_row(result, "Champ")
        ferro = self.find_row(result, "Ferro")
        self.assertEqual(round(champ.damage_dealt_pct, 2), 100.0)
        self.assertEqual(round(champ.recoil_taken_pct, 2), 33.0)
        self.assertEqual(round(ferro.indirect_damage_dealt_pct, 2), 17.0)

    def test_recoil_self_ko_does_not_award_self_a_kill(self):
        result = self.parse_battle(
            """
|player|p1|Alice|
|player|p2|Bob|
|switch|p1a: Tauros|Tauros, M|100/100
|switch|p2a: Gengar|Gengar|30/100
|turn|1
|move|p1a: Tauros|Double-Edge|p2a: Gengar
|-damage|p2a: Gengar|0 fnt
|faint|p2a: Gengar
|-damage|p1a: Tauros|0 fnt|[from] Recoil
|faint|p1a: Tauros
|win|Alice
            """
        )
        tauros = self.find_row(result, "Tauros")
        gengar = self.find_row(result, "Gengar")
        self.assertEqual(tauros.kos, 1)
        self.assertEqual(tauros.direct_kos, 1)
        self.assertEqual(tauros.indirect_kos, 0)
        self.assertEqual(tauros.fainted_by, "self")
        self.assertEqual(round(tauros.damage_dealt_pct, 2), 30.0)
        self.assertEqual(gengar.deaths, 1)

    def test_multi_hit_move_counts_multiple_hits(self):
        result = self.parse_battle(
            """
|player|p1|Alice|
|player|p2|Bob|
|switch|p1a: Cinci|Cinccino, F|100/100
|switch|p2a: Chomp|Garchomp, M|100/100
|turn|1
|move|p1a: Cinci|Bullet Seed|p2a: Chomp
|-damage|p2a: Chomp|85/100
|-damage|p2a: Chomp|70/100
|-hitcount|p2a: Chomp|2
|win|Alice
            """
        )
        cinci = self.find_row(result, "Cinci")
        chomp = self.find_row(result, "Chomp")
        self.assertEqual(cinci.moves_used, 1)
        self.assertEqual(cinci.hits_landed, 2)
        self.assertEqual(round(cinci.direct_damage_dealt_pct, 2), 30.0)
        self.assertEqual(chomp.hits_taken, 2)

    def test_future_sight_credits_original_user(self):
        result = self.parse_battle(
            """
|player|p1|Alice|
|player|p2|Bob|
|switch|p1a: Bro|Slowbro|100/100
|switch|p2a: Ape|Annihilape|100/100
|turn|1
|move|p1a: Bro|Future Sight|p2a: Ape
|turn|3
|-activate|p2a: Ape|move: Future Sight
|-damage|p2a: Ape|40/100|[from] move: Future Sight
|win|Alice
            """
        )
        bro = self.find_row(result, "Bro")
        ape = self.find_row(result, "Ape")
        self.assertEqual(round(bro.direct_damage_dealt_pct, 2), 60.0)
        self.assertEqual(round(ape.direct_damage_taken_pct, 2), 60.0)

    def test_doubles_spread_damage_hits_both_targets(self):
        result = self.parse_battle(
            """
|player|p1|Alice|
|player|p2|Bob|
|switch|p1a: Ttar|Tyranitar, M|100/100
|switch|p1b: Amoonguss|Amoonguss, F|100/100
|switch|p2a: Zap|Zapdos|100/100
|switch|p2b: Chi|Chi-Yu|100/100
|turn|1
|move|p1a: Ttar|Rock Slide|p2a: Zap
|-damage|p2a: Zap|70/100
|-damage|p2b: Chi|55/100
|win|Alice
            """
        )
        ttar = self.find_row(result, "Ttar")
        zap = self.find_row(result, "Zap")
        chi = self.find_row(result, "Chi")
        self.assertEqual(ttar.hits_landed, 2)
        self.assertEqual(round(ttar.direct_damage_dealt_pct, 2), 75.0)
        self.assertEqual(zap.hits_taken, 1)
        self.assertEqual(chi.hits_taken, 1)

    def test_substitute_counts_as_a_successful_move(self):
        result = self.parse_battle(
            """
|player|p1|Alice|
|player|p2|Bob|
|switch|p1a: Kyu|Kyurem|100/100
|switch|p2a: Glow|Slowking-Galar|100/100
|turn|1
|move|p1a: Kyu|Substitute|p1a: Kyu
|-start|p1a: Kyu|Substitute
|-damage|p1a: Kyu|75/100|[from] move: Substitute
|win|Alice
            """
        )
        kyu = self.find_row(result, "Kyu")
        self.assertEqual(kyu.moves_used, 1)
        self.assertEqual(kyu.hits_landed, 1)
        self.assertEqual(round(kyu.recoil_taken_pct, 2), 25.0)

    def test_self_ko_move_marks_user_as_self_fainted(self):
        result = self.parse_battle(
            """
|player|p1|Alice|
|player|p2|Bob|
|switch|p1a: Weez|Weezing|100/100
|switch|p2a: Sash|Alakazam|100/100
|turn|1
|move|p1a: Weez|Misty Explosion|p2a: Sash
|-damage|p2a: Sash|0 fnt
|faint|p2a: Sash
|faint|p1a: Weez
|win|Alice
            """
        )
        weez = self.find_row(result, "Weez")
        sash = self.find_row(result, "Sash")
        self.assertEqual(weez.direct_kos, 1)
        self.assertEqual(weez.fainted_by, "self")
        self.assertEqual(sash.deaths, 1)

    def test_tera_only_species_suffix_is_normalized(self):
        result = self.parse_battle(
            """
|player|p1|Alice|
|player|p2|Bob|
|poke|p1|Ogerpon-Teal, F|
|switch|p1a: Ivy|Ogerpon-Teal-Tera, F|100/100
|switch|p2a: Treads|Iron Treads|100/100
|turn|1
|move|p1a: Ivy|Horn Leech|p2a: Treads
|-damage|p2a: Treads|60/100
|win|Alice
            """
        )
        ivy = self.find_row(result, "Ivy")
        self.assertEqual(ivy.species, "Ogerpon-Teal")

    def test_mega_evolution_updates_species_for_summary(self):
        result = self.parse_battle(
            """
|player|p1|Alice|
|player|p2|Bob|
|poke|p1|Scizor, M|
|switch|p1a: Claw|Scizor, M|100/100
|switch|p2a: Clef|Clefable, F|100/100
|turn|1
|move|p1a: Claw|Bullet Punch|p2a: Clef
|-mega|p1a: Claw|Scizor-Mega|Scizorite
|detailschange|p1a: Claw|Scizor-Mega, M
|-damage|p2a: Clef|70/100
|win|Alice
            """
        )
        claw = self.find_row(result, "Claw")
        self.assertEqual(claw.species, "Scizor-Mega")

    def test_same_nickname_different_species_are_kept_separate(self):
        result = self.parse_battle(
            """
|player|p1|Alice|
|player|p2|Bob|
|poke|p1|Pikachu, M|
|poke|p1|Charizard, M|
|switch|p1a: Hero|Pikachu, M|100/100
|switch|p2a: Blob|Blissey, F|100/100
|turn|1
|switch|p1a: Hero|Charizard, M|100/100
|win|Alice
            """
        )
        hero_rows = [row for row in result.pokemon_rows if row.player == "Alice" and row.pokemon_nickname == "Hero"]
        self.assertEqual(len(hero_rows), 2)
        self.assertEqual({row.species for row in hero_rows}, {"Pikachu", "Charizard"})

    def test_crits_misses_and_effectiveness_taken_are_tracked(self):
        result = self.parse_battle(
            """
|player|p1|Alice|
|player|p2|Bob|
|switch|p1a: Aero|Aerodactyl|100/100
|switch|p2a: Buzz|Buzzwole|100/100
|turn|1
|move|p1a: Aero|Stone Edge|p2a: Buzz
|-crit|p2a: Buzz
|-supereffective|p2a: Buzz
|-damage|p2a: Buzz|40/100
|turn|2
|move|p2a: Buzz|Ice Punch|p1a: Aero
|-resisted|p1a: Aero
|-damage|p1a: Aero|80/100
|turn|3
|move|p1a: Aero|Stone Edge|p2a: Buzz
|-miss|p1a: Aero|p2a: Buzz
|win|Alice
            """
        )
        aero = self.find_row(result, "Aero")
        buzz = self.find_row(result, "Buzz")
        self.assertEqual(aero.crits, 1)
        self.assertEqual(aero.misses, 1)
        self.assertEqual(aero.resisted_hits_taken, 1)
        self.assertEqual(buzz.moves_dodged, 1)
        self.assertEqual(buzz.crits_taken, 1)
        self.assertEqual(buzz.super_effective_hits_taken, 1)

    def test_resisted_hits_taken_counts_each_resisted_hit(self):
        result = self.parse_battle(
            """
|player|p1|Alice|
|player|p2|Bob|
|switch|p1a: Scizor|Scizor|100/100
|switch|p2a: Fini|Tapu Fini|100/100
|turn|1
|move|p2a: Fini|Water Shuriken|p1a: Scizor
|-resisted|p1a: Scizor
|-damage|p1a: Scizor|95/100
|-resisted|p1a: Scizor
|-damage|p1a: Scizor|90/100
|-hitcount|p1a: Scizor|2
|win|Alice
            """
        )
        scizor = self.find_row(result, "Scizor")
        self.assertEqual(scizor.resisted_hits_taken, 2)
        self.assertEqual(scizor.hits_taken, 2)


if __name__ == "__main__":
    unittest.main()
