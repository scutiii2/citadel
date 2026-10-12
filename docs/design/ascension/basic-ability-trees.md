# Basic Ascended: single ability trees

Twoychi is excluded. Each of the other seven Ascended has one themed tree: four existing starting-kit roots and twelve learnable nodes (16 nodes total). Paths within a tree converge on one mastery capstone; they are not separate specialization trees.

Applied to the seven game tree files on 2026-10-12 after user approval. Existing node IDs and mechanics are retained. Some existing learning levels are raised to their prerequisite ability level (Guardian Shield Slam, Scout Twin Cuts and Mirage, Bruiser Warcry, Channeler Lantern Ward). Numbers are initial balance proposals.

Three ability slots and one passive slot still apply. Learned passives are equipment alternatives, not cumulative upgrades. Healing, regeneration, cleanse and ward affect the user; damage statuses affect the opponent. No new engine behavior is required.

Common/Rare/Unique are essence tiers, not additional ability trees. Most capstones unlock at level 30. Forbidden retains its existing higher progression and finishes at level 50; it still has only one tree.

Percentages use the existing game rules: attacks, shields, buffs, healing and bleed scale from power; slow and weaken reduce the target stat by a percentage. Status durations include the activation round. Twin Cuts and Flurry are single attacks mechanically. Execution has no enemy-health threshold multiplier. Ward prevents one lethal hit or bleed tick while active.

## Guardian — Forgeheart

A shield-bearing ember golem that repairs itself and endures prolonged fights.

Starting kit: Bulwark (Lv. 1), Rally (Lv. 10), Heavy Blow (Lv. 20), plus the catalog passive.

| Node | Level | Essence | Requires all | Behavior |
|---|---:|---|---|---|
| Shield Slam | 20 | 4 common | Heavy Blow | ATTACK 190%; cooldown 2 |
| Iron Wall | 12 | 3 common | Bulwark | DEFENSE 260%; cooldown 3 |
| Unyielding | 22 | 3 rare | Rally | SUPPORT 75%; cooldown 3; power for 3 rounds |
| Stoneskin | 15 | 3 rare | Iron Wall | Passive: `defense_rating_bonus` {"power_fraction": 0.4} |
| Ember Mend | 8 | 2 common | Bulwark | DEFENSE 160%; cooldown 2; `heal` {"percentage": 60} |
| Tempered Core | 10 | 2 common | Starting passive | Passive: `heal_bonus` {"fraction": 0.25} |
| Shield Pressure | 22 | 4 rare | Shield Slam | ATTACK 130%; cooldown 2; `weaken` {"percentage": 15, "rounds": 2} |
| Forge Breath | 24 | 4 rare | Unyielding | SUPPORT 55%; cooldown 3; power for 3 rounds; `regen` {"percentage": 25, "rounds": 3} |
| Sealed Armour | 20 | 4 rare | Stoneskin | DEFENSE 220%; cooldown 3; `cleanse` {} |
| Last Ember | 26 | 4 rare | Sealed Armour | DEFENSE 180%; cooldown 4; `ward` {"rounds": 2} |
| Steadfast | 28 | 4 rare | Tempered Core | Passive: `defense_extension` {"protected_attacks": 3, "rounds": 2} |
| Heart of the Forge | 30 | 5 unique | Ember Mend, Shield Pressure, Forge Breath, Last Ember, Steadfast | DEFENSE 300%; cooldown 4; `heal` {"percentage": 80}; `cleanse` {} |

### tree.json

```json
{
  "nodes": [
    {
      "id": "guardian_heavy_blow",
      "root": true,
      "x": 40,
      "y": 60
    },
    {
      "id": "guardian_rally",
      "root": true,
      "x": 40,
      "y": 180
    },
    {
      "id": "guardian_bulwark",
      "root": true,
      "x": 40,
      "y": 300
    },
    {
      "id": "guardian_passive",
      "root": true,
      "x": 40,
      "y": 420
    },
    {
      "id": "guardian_shield_slam",
      "kind": "ability",
      "name": "Shield Slam",
      "category": "ATTACK",
      "percentage": 190,
      "cooldown": 2,
      "unlock_level": 20,
      "requires": [
        "guardian_heavy_blow"
      ],
      "cost": {
        "tier": "common",
        "amount": 4
      },
      "x": 260,
      "y": 60
    },
    {
      "id": "guardian_iron_wall",
      "kind": "ability",
      "name": "Iron Wall",
      "category": "DEFENSE",
      "percentage": 260,
      "cooldown": 3,
      "unlock_level": 12,
      "requires": [
        "guardian_bulwark"
      ],
      "cost": {
        "tier": "common",
        "amount": 3
      },
      "x": 260,
      "y": 180
    },
    {
      "id": "guardian_unyielding",
      "kind": "ability",
      "name": "Unyielding",
      "category": "SUPPORT",
      "stat": "power",
      "duration": 3,
      "percentage": 75,
      "cooldown": 3,
      "unlock_level": 22,
      "requires": [
        "guardian_rally"
      ],
      "cost": {
        "tier": "rare",
        "amount": 3
      },
      "x": 260,
      "y": 300
    },
    {
      "id": "guardian_stoneskin",
      "kind": "passive",
      "name": "Stoneskin",
      "unlock_level": 15,
      "passive": {
        "kind": "defense_rating_bonus",
        "params": {
          "power_fraction": 0.4
        }
      },
      "requires": [
        "guardian_iron_wall"
      ],
      "cost": {
        "tier": "rare",
        "amount": 3
      },
      "x": 260,
      "y": 420
    },
    {
      "id": "guardian_ember_mend",
      "kind": "ability",
      "name": "Ember Mend",
      "unlock_level": 8,
      "requires": [
        "guardian_bulwark"
      ],
      "cost": {
        "tier": "common",
        "amount": 2
      },
      "x": 500,
      "y": 60,
      "category": "DEFENSE",
      "percentage": 160,
      "cooldown": 2,
      "effects": [
        {
          "kind": "heal",
          "percentage": 60
        }
      ]
    },
    {
      "id": "guardian_tempered_core",
      "kind": "passive",
      "name": "Tempered Core",
      "unlock_level": 10,
      "requires": [
        "guardian_passive"
      ],
      "cost": {
        "tier": "common",
        "amount": 2
      },
      "x": 500,
      "y": 180,
      "passive": {
        "kind": "heal_bonus",
        "params": {
          "fraction": 0.25
        }
      }
    },
    {
      "id": "guardian_shield_pressure",
      "kind": "ability",
      "name": "Shield Pressure",
      "unlock_level": 22,
      "requires": [
        "guardian_shield_slam"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 500,
      "y": 300,
      "category": "ATTACK",
      "percentage": 130,
      "cooldown": 2,
      "effects": [
        {
          "kind": "weaken",
          "percentage": 15,
          "rounds": 2
        }
      ]
    },
    {
      "id": "guardian_forge_breath",
      "kind": "ability",
      "name": "Forge Breath",
      "unlock_level": 24,
      "requires": [
        "guardian_unyielding"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 500,
      "y": 420,
      "category": "SUPPORT",
      "percentage": 55,
      "cooldown": 3,
      "stat": "power",
      "duration": 3,
      "effects": [
        {
          "kind": "regen",
          "percentage": 25,
          "rounds": 3
        }
      ]
    },
    {
      "id": "guardian_sealed_armour",
      "kind": "ability",
      "name": "Sealed Armour",
      "unlock_level": 20,
      "requires": [
        "guardian_stoneskin"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 740,
      "y": 60,
      "category": "DEFENSE",
      "percentage": 220,
      "cooldown": 3,
      "effects": [
        {
          "kind": "cleanse"
        }
      ]
    },
    {
      "id": "guardian_last_ember",
      "kind": "ability",
      "name": "Last Ember",
      "unlock_level": 26,
      "requires": [
        "guardian_sealed_armour"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 740,
      "y": 180,
      "category": "DEFENSE",
      "percentage": 180,
      "cooldown": 4,
      "effects": [
        {
          "kind": "ward",
          "rounds": 2
        }
      ]
    },
    {
      "id": "guardian_steadfast",
      "kind": "passive",
      "name": "Steadfast",
      "unlock_level": 28,
      "requires": [
        "guardian_tempered_core"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 740,
      "y": 300,
      "passive": {
        "kind": "defense_extension",
        "params": {
          "protected_attacks": 3,
          "rounds": 2
        }
      }
    },
    {
      "id": "guardian_heart_of_the_forge",
      "kind": "ability",
      "name": "Heart of the Forge",
      "unlock_level": 30,
      "requires": [
        "guardian_ember_mend",
        "guardian_shield_pressure",
        "guardian_forge_breath",
        "guardian_last_ember",
        "guardian_steadfast"
      ],
      "cost": {
        "tier": "unique",
        "amount": 5
      },
      "x": 1000,
      "y": 240,
      "category": "DEFENSE",
      "percentage": 300,
      "cooldown": 4,
      "effects": [
        {
          "kind": "heal",
          "percentage": 80
        },
        {
          "kind": "cleanse"
        }
      ]
    }
  ]
}
```

## Scout — Emberwind

A feathered fox that sets the pace, marks its quarry and escapes pressure.

Starting kit: Quickstep (Lv. 1), Swift Slash (Lv. 10), Evade (Lv. 20), plus the catalog passive.

| Node | Level | Essence | Requires all | Behavior |
|---|---:|---|---|---|
| Gale Step | 12 | 3 common | Quickstep | SUPPORT 140%; cooldown 3; speed for 3 rounds |
| Twin Cuts | 10 | 2 common | Swift Slash | ATTACK 90%; cooldown 1 |
| Mirage | 20 | 3 rare | Evade | DEFENSE 200%; cooldown 2 |
| Fleet Footed | 14 | 3 rare | Gale Step | Passive: `support_duration_bonus` {"rounds": 1} |
| Headstart | 20 | 4 rare | Starting passive | Passive: `battle_start_speed` {"power_fraction": 0.8} |
| Feather Feint | 12 | 3 common | Twin Cuts | ATTACK 100%; cooldown 2; `slow` {"percentage": 20, "rounds": 2} |
| Trailblaze | 16 | 3 rare | Fleet Footed | SUPPORT 90%; cooldown 3; speed for 3 rounds; `cleanse` {} |
| Ember Trail | 20 | 4 rare | Feather Feint | ATTACK 145%; cooldown 2; `mark` {"name": "trail", "rounds": 3} |
| Keen Scent | 24 | 4 rare | Headstart | Passive: `attack_bonus_vs_marked` {"mark": "trail", "power_fraction": 0.3} |
| Slipstream | 24 | 4 rare | Mirage | DEFENSE 170%; cooldown 3; `regen` {"percentage": 20, "rounds": 3} |
| Tailwind | 28 | 4 rare | Trailblaze | SUPPORT 160%; cooldown 3; speed for 3 rounds |
| Horizon Dash | 30 | 5 unique | Ember Trail, Keen Scent, Slipstream, Tailwind | ATTACK 220%; cooldown 4; `slow` {"percentage": 25, "rounds": 2}; `exposed` {"percentage": 30, "rounds": 2} |

### tree.json

```json
{
  "nodes": [
    {
      "id": "scout_quickstep",
      "root": true,
      "x": 40,
      "y": 72
    },
    {
      "id": "scout_swift_slash",
      "root": true,
      "x": 40,
      "y": 192
    },
    {
      "id": "scout_evade",
      "root": true,
      "x": 40,
      "y": 312
    },
    {
      "id": "scout_passive",
      "root": true,
      "x": 40,
      "y": 432
    },
    {
      "id": "scout_gale_step",
      "kind": "ability",
      "name": "Gale Step",
      "category": "SUPPORT",
      "stat": "speed",
      "duration": 3,
      "percentage": 140,
      "cooldown": 3,
      "unlock_level": 12,
      "requires": [
        "scout_quickstep"
      ],
      "cost": {
        "tier": "common",
        "amount": 3
      },
      "x": 260,
      "y": 72
    },
    {
      "id": "scout_twin_cuts",
      "kind": "ability",
      "name": "Twin Cuts",
      "category": "ATTACK",
      "percentage": 90,
      "cooldown": 1,
      "unlock_level": 10,
      "requires": [
        "scout_swift_slash"
      ],
      "cost": {
        "tier": "common",
        "amount": 2
      },
      "x": 260,
      "y": 192
    },
    {
      "id": "scout_mirage",
      "kind": "ability",
      "name": "Mirage",
      "category": "DEFENSE",
      "percentage": 200,
      "cooldown": 2,
      "unlock_level": 20,
      "requires": [
        "scout_evade"
      ],
      "cost": {
        "tier": "rare",
        "amount": 3
      },
      "x": 260,
      "y": 312
    },
    {
      "id": "scout_fleet_footed",
      "kind": "passive",
      "name": "Fleet Footed",
      "unlock_level": 14,
      "passive": {
        "kind": "support_duration_bonus",
        "params": {
          "rounds": 1
        }
      },
      "requires": [
        "scout_gale_step"
      ],
      "cost": {
        "tier": "rare",
        "amount": 3
      },
      "x": 260,
      "y": 432
    },
    {
      "id": "scout_headstart",
      "kind": "passive",
      "name": "Headstart",
      "unlock_level": 20,
      "passive": {
        "kind": "battle_start_speed",
        "params": {
          "power_fraction": 0.8
        }
      },
      "requires": [
        "scout_passive"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 500,
      "y": 72
    },
    {
      "id": "scout_feather_feint",
      "kind": "ability",
      "name": "Feather Feint",
      "unlock_level": 12,
      "requires": [
        "scout_twin_cuts"
      ],
      "cost": {
        "tier": "common",
        "amount": 3
      },
      "x": 500,
      "y": 192,
      "category": "ATTACK",
      "percentage": 100,
      "cooldown": 2,
      "effects": [
        {
          "kind": "slow",
          "percentage": 20,
          "rounds": 2
        }
      ]
    },
    {
      "id": "scout_trailblaze",
      "kind": "ability",
      "name": "Trailblaze",
      "unlock_level": 16,
      "requires": [
        "scout_fleet_footed"
      ],
      "cost": {
        "tier": "rare",
        "amount": 3
      },
      "x": 500,
      "y": 312,
      "category": "SUPPORT",
      "percentage": 90,
      "cooldown": 3,
      "stat": "speed",
      "duration": 3,
      "effects": [
        {
          "kind": "cleanse"
        }
      ]
    },
    {
      "id": "scout_ember_trail",
      "kind": "ability",
      "name": "Ember Trail",
      "unlock_level": 20,
      "requires": [
        "scout_feather_feint"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 500,
      "y": 432,
      "category": "ATTACK",
      "percentage": 145,
      "cooldown": 2,
      "effects": [
        {
          "kind": "mark",
          "name": "trail",
          "rounds": 3
        }
      ]
    },
    {
      "id": "scout_keen_scent",
      "kind": "passive",
      "name": "Keen Scent",
      "unlock_level": 24,
      "requires": [
        "scout_headstart"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 740,
      "y": 72,
      "passive": {
        "kind": "attack_bonus_vs_marked",
        "params": {
          "mark": "trail",
          "power_fraction": 0.3
        }
      }
    },
    {
      "id": "scout_slipstream",
      "kind": "ability",
      "name": "Slipstream",
      "unlock_level": 24,
      "requires": [
        "scout_mirage"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 740,
      "y": 192,
      "category": "DEFENSE",
      "percentage": 170,
      "cooldown": 3,
      "effects": [
        {
          "kind": "regen",
          "percentage": 20,
          "rounds": 3
        }
      ]
    },
    {
      "id": "scout_tailwind",
      "kind": "ability",
      "name": "Tailwind",
      "unlock_level": 28,
      "requires": [
        "scout_trailblaze"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 740,
      "y": 312,
      "category": "SUPPORT",
      "percentage": 160,
      "cooldown": 3,
      "stat": "speed",
      "duration": 3
    },
    {
      "id": "scout_horizon_dash",
      "kind": "ability",
      "name": "Horizon Dash",
      "unlock_level": 30,
      "requires": [
        "scout_ember_trail",
        "scout_keen_scent",
        "scout_slipstream",
        "scout_tailwind"
      ],
      "cost": {
        "tier": "unique",
        "amount": 5
      },
      "x": 1000,
      "y": 252,
      "category": "ATTACK",
      "percentage": 220,
      "cooldown": 4,
      "effects": [
        {
          "kind": "slow",
          "percentage": 25,
          "rounds": 2
        },
        {
          "kind": "exposed",
          "percentage": 30,
          "rounds": 2
        }
      ]
    }
  ]
}
```

## Striker — Sunsteel

A flame-blade salamander that opens enemy defenses and commits to a decisive strike.

Starting kit: Rending Strike (Lv. 1), Battle Focus (Lv. 10), Brace (Lv. 20), plus the catalog passive.

| Node | Level | Essence | Requires all | Behavior |
|---|---:|---|---|---|
| Flurry | 8 | 2 common | Rending Strike | ATTACK 110%; cooldown 1 |
| Execution | 20 | 4 rare | Flurry | ATTACK 260%; cooldown 3 |
| Bloodlust | 14 | 3 common | Battle Focus | SUPPORT 90%; cooldown 3; power for 2 rounds |
| Desperation | 18 | 3 rare | Starting passive | Passive: `low_hp_attack_bonus` {"hp_below": 0.7, "power_fraction": 0.25} |
| Scorching Edge | 12 | 3 common | Flurry | ATTACK 130%; cooldown 2; `bleed` {"percentage": 20, "rounds": 3} |
| Blade Temper | 12 | 3 common | Starting passive | Passive: `attack_bonus_vs_defense` {"power_fraction": 0.3} |
| Cinder Focus | 18 | 3 rare | Bloodlust | SUPPORT 65%; cooldown 3; power for 3 rounds; `cleanse` {} |
| Crossguard | 22 | 4 rare | Brace | DEFENSE 150%; cooldown 2 |
| Open the Guard | 24 | 4 rare | Scorching Edge | ATTACK 160%; cooldown 2; `exposed` {"percentage": 40, "rounds": 3} |
| Ember Recovery | 26 | 4 rare | Crossguard | DEFENSE 130%; cooldown 3; `heal` {"percentage": 50} |
| White Heat | 28 | 4 rare | Desperation | Passive: `low_hp_attack_bonus` {"hp_below": 0.4, "power_fraction": 0.45} |
| Sunsteel Cleave | 30 | 5 unique | Execution, Blade Temper, Cinder Focus, Open the Guard, Ember Recovery, White Heat | ATTACK 300%; cooldown 4; `bleed` {"percentage": 25, "rounds": 3} |

### tree.json

```json
{
  "nodes": [
    {
      "id": "striker_rending_strike",
      "root": true,
      "x": 40,
      "y": 84
    },
    {
      "id": "striker_battle_focus",
      "root": true,
      "x": 40,
      "y": 204
    },
    {
      "id": "striker_brace",
      "root": true,
      "x": 40,
      "y": 324
    },
    {
      "id": "striker_passive",
      "root": true,
      "x": 40,
      "y": 444
    },
    {
      "id": "striker_flurry",
      "kind": "ability",
      "name": "Flurry",
      "category": "ATTACK",
      "percentage": 110,
      "cooldown": 1,
      "unlock_level": 8,
      "requires": [
        "striker_rending_strike"
      ],
      "cost": {
        "tier": "common",
        "amount": 2
      },
      "x": 260,
      "y": 84
    },
    {
      "id": "striker_execution",
      "kind": "ability",
      "name": "Execution",
      "category": "ATTACK",
      "percentage": 260,
      "cooldown": 3,
      "unlock_level": 20,
      "requires": [
        "striker_flurry"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 260,
      "y": 204
    },
    {
      "id": "striker_bloodlust",
      "kind": "ability",
      "name": "Bloodlust",
      "category": "SUPPORT",
      "stat": "power",
      "duration": 2,
      "percentage": 90,
      "cooldown": 3,
      "unlock_level": 14,
      "requires": [
        "striker_battle_focus"
      ],
      "cost": {
        "tier": "common",
        "amount": 3
      },
      "x": 260,
      "y": 324
    },
    {
      "id": "striker_desperation",
      "kind": "passive",
      "name": "Desperation",
      "unlock_level": 18,
      "passive": {
        "kind": "low_hp_attack_bonus",
        "params": {
          "hp_below": 0.7,
          "power_fraction": 0.25
        }
      },
      "requires": [
        "striker_passive"
      ],
      "cost": {
        "tier": "rare",
        "amount": 3
      },
      "x": 260,
      "y": 444
    },
    {
      "id": "striker_scorching_edge",
      "kind": "ability",
      "name": "Scorching Edge",
      "unlock_level": 12,
      "requires": [
        "striker_flurry"
      ],
      "cost": {
        "tier": "common",
        "amount": 3
      },
      "x": 500,
      "y": 84,
      "category": "ATTACK",
      "percentage": 130,
      "cooldown": 2,
      "effects": [
        {
          "kind": "bleed",
          "percentage": 20,
          "rounds": 3
        }
      ]
    },
    {
      "id": "striker_blade_temper",
      "kind": "passive",
      "name": "Blade Temper",
      "unlock_level": 12,
      "requires": [
        "striker_passive"
      ],
      "cost": {
        "tier": "common",
        "amount": 3
      },
      "x": 500,
      "y": 204,
      "passive": {
        "kind": "attack_bonus_vs_defense",
        "params": {
          "power_fraction": 0.3
        }
      }
    },
    {
      "id": "striker_cinder_focus",
      "kind": "ability",
      "name": "Cinder Focus",
      "unlock_level": 18,
      "requires": [
        "striker_bloodlust"
      ],
      "cost": {
        "tier": "rare",
        "amount": 3
      },
      "x": 500,
      "y": 324,
      "category": "SUPPORT",
      "percentage": 65,
      "cooldown": 3,
      "stat": "power",
      "duration": 3,
      "effects": [
        {
          "kind": "cleanse"
        }
      ]
    },
    {
      "id": "striker_crossguard",
      "kind": "ability",
      "name": "Crossguard",
      "unlock_level": 22,
      "requires": [
        "striker_brace"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 500,
      "y": 444,
      "category": "DEFENSE",
      "percentage": 150,
      "cooldown": 2
    },
    {
      "id": "striker_open_the_guard",
      "kind": "ability",
      "name": "Open the Guard",
      "unlock_level": 24,
      "requires": [
        "striker_scorching_edge"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 740,
      "y": 84,
      "category": "ATTACK",
      "percentage": 160,
      "cooldown": 2,
      "effects": [
        {
          "kind": "exposed",
          "percentage": 40,
          "rounds": 3
        }
      ]
    },
    {
      "id": "striker_ember_recovery",
      "kind": "ability",
      "name": "Ember Recovery",
      "unlock_level": 26,
      "requires": [
        "striker_crossguard"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 740,
      "y": 204,
      "category": "DEFENSE",
      "percentage": 130,
      "cooldown": 3,
      "effects": [
        {
          "kind": "heal",
          "percentage": 50
        }
      ]
    },
    {
      "id": "striker_white_heat",
      "kind": "passive",
      "name": "White Heat",
      "unlock_level": 28,
      "requires": [
        "striker_desperation"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 740,
      "y": 324,
      "passive": {
        "kind": "low_hp_attack_bonus",
        "params": {
          "hp_below": 0.4,
          "power_fraction": 0.45
        }
      }
    },
    {
      "id": "striker_sunsteel_cleave",
      "kind": "ability",
      "name": "Sunsteel Cleave",
      "unlock_level": 30,
      "requires": [
        "striker_execution",
        "striker_blade_temper",
        "striker_cinder_focus",
        "striker_open_the_guard",
        "striker_ember_recovery",
        "striker_white_heat"
      ],
      "cost": {
        "tier": "unique",
        "amount": 5
      },
      "x": 1000,
      "y": 264,
      "category": "ATTACK",
      "percentage": 300,
      "cooldown": 4,
      "effects": [
        {
          "kind": "bleed",
          "percentage": 25,
          "rounds": 3
        }
      ]
    }
  ]
}
```

## Bruiser — Caldera

A basalt boar that cracks shields and slows foes with heavy fists.

Starting kit: Crushing Blow (Lv. 1), Guard Up (Lv. 10), Rage (Lv. 20), plus the catalog passive.

| Node | Level | Essence | Requires all | Behavior |
|---|---:|---|---|---|
| Haymaker | 14 | 4 common | Crushing Blow | ATTACK 240%; cooldown 3 |
| Iron Hide | 10 | 2 common | Guard Up | DEFENSE 180%; cooldown 2 |
| Warcry | 20 | 3 rare | Rage | SUPPORT 80%; cooldown 3; power for 3 rounds |
| Grudge | 16 | 3 rare | Starting passive | Passive: `low_hp_attack_bonus` {"hp_below": 0.6, "power_fraction": 0.3} |
| Tusk Hook | 8 | 2 common | Crushing Blow | ATTACK 140%; cooldown 2; `exposed` {"percentage": 25, "rounds": 2} |
| Basalt Heart | 12 | 3 common | Starting passive | Passive: `defense_rating_bonus` {"power_fraction": 0.3} |
| Faultline Fist | 18 | 3 rare | Haymaker | ATTACK 170%; cooldown 2; `slow` {"percentage": 20, "rounds": 2} |
| Core Reforge | 16 | 3 rare | Iron Hide | DEFENSE 170%; cooldown 3; `heal` {"percentage": 60} |
| Molten Resolve | 22 | 4 rare | Warcry | SUPPORT 65%; cooldown 3; power for 3 rounds; `cleanse` {} |
| Ruinbreaker | 24 | 4 rare | Basalt Heart | Passive: `attack_bonus_vs_defense` {"power_fraction": 0.45} |
| Cracked Earth | 28 | 4 rare | Faultline Fist | ATTACK 200%; cooldown 3; `weaken` {"percentage": 20, "rounds": 2}; `exposed` {"percentage": 35, "rounds": 2} |
| Caldera Hammer | 30 | 5 unique | Grudge, Tusk Hook, Core Reforge, Molten Resolve, Ruinbreaker, Cracked Earth | ATTACK 320%; cooldown 4; `slow` {"percentage": 30, "rounds": 2} |

### tree.json

```json
{
  "nodes": [
    {
      "id": "bruiser_crushing_blow",
      "root": true,
      "x": 40,
      "y": 96
    },
    {
      "id": "bruiser_guard_up",
      "root": true,
      "x": 40,
      "y": 216
    },
    {
      "id": "bruiser_rage",
      "root": true,
      "x": 40,
      "y": 336
    },
    {
      "id": "bruiser_passive",
      "root": true,
      "x": 40,
      "y": 456
    },
    {
      "id": "bruiser_haymaker",
      "kind": "ability",
      "name": "Haymaker",
      "category": "ATTACK",
      "percentage": 240,
      "cooldown": 3,
      "unlock_level": 14,
      "requires": [
        "bruiser_crushing_blow"
      ],
      "cost": {
        "tier": "common",
        "amount": 4
      },
      "x": 260,
      "y": 96
    },
    {
      "id": "bruiser_iron_hide",
      "kind": "ability",
      "name": "Iron Hide",
      "category": "DEFENSE",
      "percentage": 180,
      "cooldown": 2,
      "unlock_level": 10,
      "requires": [
        "bruiser_guard_up"
      ],
      "cost": {
        "tier": "common",
        "amount": 2
      },
      "x": 260,
      "y": 216
    },
    {
      "id": "bruiser_warcry",
      "kind": "ability",
      "name": "Warcry",
      "category": "SUPPORT",
      "stat": "power",
      "duration": 3,
      "percentage": 80,
      "cooldown": 3,
      "unlock_level": 20,
      "requires": [
        "bruiser_rage"
      ],
      "cost": {
        "tier": "rare",
        "amount": 3
      },
      "x": 260,
      "y": 336
    },
    {
      "id": "bruiser_grudge",
      "kind": "passive",
      "name": "Grudge",
      "unlock_level": 16,
      "passive": {
        "kind": "low_hp_attack_bonus",
        "params": {
          "hp_below": 0.6,
          "power_fraction": 0.3
        }
      },
      "requires": [
        "bruiser_passive"
      ],
      "cost": {
        "tier": "rare",
        "amount": 3
      },
      "x": 260,
      "y": 456
    },
    {
      "id": "bruiser_tusk_hook",
      "kind": "ability",
      "name": "Tusk Hook",
      "unlock_level": 8,
      "requires": [
        "bruiser_crushing_blow"
      ],
      "cost": {
        "tier": "common",
        "amount": 2
      },
      "x": 500,
      "y": 96,
      "category": "ATTACK",
      "percentage": 140,
      "cooldown": 2,
      "effects": [
        {
          "kind": "exposed",
          "percentage": 25,
          "rounds": 2
        }
      ]
    },
    {
      "id": "bruiser_basalt_heart",
      "kind": "passive",
      "name": "Basalt Heart",
      "unlock_level": 12,
      "requires": [
        "bruiser_passive"
      ],
      "cost": {
        "tier": "common",
        "amount": 3
      },
      "x": 500,
      "y": 216,
      "passive": {
        "kind": "defense_rating_bonus",
        "params": {
          "power_fraction": 0.3
        }
      }
    },
    {
      "id": "bruiser_faultline_fist",
      "kind": "ability",
      "name": "Faultline Fist",
      "unlock_level": 18,
      "requires": [
        "bruiser_haymaker"
      ],
      "cost": {
        "tier": "rare",
        "amount": 3
      },
      "x": 500,
      "y": 336,
      "category": "ATTACK",
      "percentage": 170,
      "cooldown": 2,
      "effects": [
        {
          "kind": "slow",
          "percentage": 20,
          "rounds": 2
        }
      ]
    },
    {
      "id": "bruiser_core_reforge",
      "kind": "ability",
      "name": "Core Reforge",
      "unlock_level": 16,
      "requires": [
        "bruiser_iron_hide"
      ],
      "cost": {
        "tier": "rare",
        "amount": 3
      },
      "x": 500,
      "y": 456,
      "category": "DEFENSE",
      "percentage": 170,
      "cooldown": 3,
      "effects": [
        {
          "kind": "heal",
          "percentage": 60
        }
      ]
    },
    {
      "id": "bruiser_molten_resolve",
      "kind": "ability",
      "name": "Molten Resolve",
      "unlock_level": 22,
      "requires": [
        "bruiser_warcry"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 740,
      "y": 96,
      "category": "SUPPORT",
      "percentage": 65,
      "cooldown": 3,
      "stat": "power",
      "duration": 3,
      "effects": [
        {
          "kind": "cleanse"
        }
      ]
    },
    {
      "id": "bruiser_ruinbreaker",
      "kind": "passive",
      "name": "Ruinbreaker",
      "unlock_level": 24,
      "requires": [
        "bruiser_basalt_heart"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 740,
      "y": 216,
      "passive": {
        "kind": "attack_bonus_vs_defense",
        "params": {
          "power_fraction": 0.45
        }
      }
    },
    {
      "id": "bruiser_cracked_earth",
      "kind": "ability",
      "name": "Cracked Earth",
      "unlock_level": 28,
      "requires": [
        "bruiser_faultline_fist"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 740,
      "y": 336,
      "category": "ATTACK",
      "percentage": 200,
      "cooldown": 3,
      "effects": [
        {
          "kind": "weaken",
          "percentage": 20,
          "rounds": 2
        },
        {
          "kind": "exposed",
          "percentage": 35,
          "rounds": 2
        }
      ]
    },
    {
      "id": "bruiser_caldera_hammer",
      "kind": "ability",
      "name": "Caldera Hammer",
      "unlock_level": 30,
      "requires": [
        "bruiser_grudge",
        "bruiser_tusk_hook",
        "bruiser_core_reforge",
        "bruiser_molten_resolve",
        "bruiser_ruinbreaker",
        "bruiser_cracked_earth"
      ],
      "cost": {
        "tier": "unique",
        "amount": 5
      },
      "x": 1000,
      "y": 276,
      "category": "ATTACK",
      "percentage": 320,
      "cooldown": 4,
      "effects": [
        {
          "kind": "slow",
          "percentage": 30,
          "rounds": 2
        }
      ]
    }
  ]
}
```

## Sentinel — Nightwatch

An armoured owl that watches, suppresses and survives through sustained protection.

Starting kit: Stone Guard (Lv. 1), Hold Fast (Lv. 10), Shield Bash (Lv. 20), plus the catalog passive.

| Node | Level | Essence | Requires all | Behavior |
|---|---:|---|---|---|
| Bastion | 14 | 3 rare | Stone Guard | DEFENSE 400%; cooldown 3 |
| Vigil | 12 | 3 common | Hold Fast | SUPPORT 80%; cooldown 3; power for 3 rounds |
| Pillar Strike | 20 | 3 rare | Shield Bash | ATTACK 170%; cooldown 3 |
| Watchtower | 16 | 4 rare | Bastion | Passive: `defense_extension` {"protected_attacks": 2, "rounds": 1} |
| Owl Sight | 8 | 2 common | Stone Guard | ATTACK 90%; cooldown 2; `mark` {"name": "watched", "rounds": 3} |
| Measured Response | 12 | 3 common | Starting passive | Passive: `attack_bonus_vs_marked` {"mark": "watched", "power_fraction": 0.3} |
| Quiet Watch | 18 | 3 rare | Bastion | DEFENSE 250%; cooldown 3; `regen` {"percentage": 30, "rounds": 3} |
| Clear Vigil | 18 | 3 rare | Vigil | SUPPORT 60%; cooldown 3; power for 3 rounds; `cleanse` {} |
| Pinning Bash | 24 | 4 rare | Pillar Strike | ATTACK 145%; cooldown 2; `slow` {"percentage": 25, "rounds": 2} |
| Enduring Watch | 24 | 4 rare | Watchtower | Passive: `defense_extension` {"protected_attacks": 3, "rounds": 2} |
| Night Sanctuary | 28 | 4 rare | Quiet Watch | DEFENSE 320%; cooldown 4; `ward` {"rounds": 2} |
| Eternal Vigil | 30 | 5 unique | Owl Sight, Measured Response, Clear Vigil, Pinning Bash, Enduring Watch, Night Sanctuary | DEFENSE 450%; cooldown 4; `heal` {"percentage": 70}; `cleanse` {} |

### tree.json

```json
{
  "nodes": [
    {
      "id": "sentinel_stone_guard",
      "root": true,
      "x": 40,
      "y": 108
    },
    {
      "id": "sentinel_hold_fast",
      "root": true,
      "x": 40,
      "y": 228
    },
    {
      "id": "sentinel_shield_bash",
      "root": true,
      "x": 40,
      "y": 348
    },
    {
      "id": "sentinel_passive",
      "root": true,
      "x": 40,
      "y": 468
    },
    {
      "id": "sentinel_bastion",
      "kind": "ability",
      "name": "Bastion",
      "category": "DEFENSE",
      "percentage": 400,
      "cooldown": 3,
      "unlock_level": 14,
      "requires": [
        "sentinel_stone_guard"
      ],
      "cost": {
        "tier": "rare",
        "amount": 3
      },
      "x": 260,
      "y": 108
    },
    {
      "id": "sentinel_vigil",
      "kind": "ability",
      "name": "Vigil",
      "category": "SUPPORT",
      "stat": "power",
      "duration": 3,
      "percentage": 80,
      "cooldown": 3,
      "unlock_level": 12,
      "requires": [
        "sentinel_hold_fast"
      ],
      "cost": {
        "tier": "common",
        "amount": 3
      },
      "x": 260,
      "y": 228
    },
    {
      "id": "sentinel_pillar_strike",
      "kind": "ability",
      "name": "Pillar Strike",
      "category": "ATTACK",
      "percentage": 170,
      "cooldown": 3,
      "unlock_level": 20,
      "requires": [
        "sentinel_shield_bash"
      ],
      "cost": {
        "tier": "rare",
        "amount": 3
      },
      "x": 260,
      "y": 348
    },
    {
      "id": "sentinel_watchtower",
      "kind": "passive",
      "name": "Watchtower",
      "unlock_level": 16,
      "passive": {
        "kind": "defense_extension",
        "params": {
          "protected_attacks": 2,
          "rounds": 1
        }
      },
      "requires": [
        "sentinel_bastion"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 260,
      "y": 468
    },
    {
      "id": "sentinel_owl_sight",
      "kind": "ability",
      "name": "Owl Sight",
      "unlock_level": 8,
      "requires": [
        "sentinel_stone_guard"
      ],
      "cost": {
        "tier": "common",
        "amount": 2
      },
      "x": 500,
      "y": 108,
      "category": "ATTACK",
      "percentage": 90,
      "cooldown": 2,
      "effects": [
        {
          "kind": "mark",
          "name": "watched",
          "rounds": 3
        }
      ]
    },
    {
      "id": "sentinel_measured_response",
      "kind": "passive",
      "name": "Measured Response",
      "unlock_level": 12,
      "requires": [
        "sentinel_passive"
      ],
      "cost": {
        "tier": "common",
        "amount": 3
      },
      "x": 500,
      "y": 228,
      "passive": {
        "kind": "attack_bonus_vs_marked",
        "params": {
          "mark": "watched",
          "power_fraction": 0.3
        }
      }
    },
    {
      "id": "sentinel_quiet_watch",
      "kind": "ability",
      "name": "Quiet Watch",
      "unlock_level": 18,
      "requires": [
        "sentinel_bastion"
      ],
      "cost": {
        "tier": "rare",
        "amount": 3
      },
      "x": 500,
      "y": 348,
      "category": "DEFENSE",
      "percentage": 250,
      "cooldown": 3,
      "effects": [
        {
          "kind": "regen",
          "percentage": 30,
          "rounds": 3
        }
      ]
    },
    {
      "id": "sentinel_clear_vigil",
      "kind": "ability",
      "name": "Clear Vigil",
      "unlock_level": 18,
      "requires": [
        "sentinel_vigil"
      ],
      "cost": {
        "tier": "rare",
        "amount": 3
      },
      "x": 500,
      "y": 468,
      "category": "SUPPORT",
      "percentage": 60,
      "cooldown": 3,
      "stat": "power",
      "duration": 3,
      "effects": [
        {
          "kind": "cleanse"
        }
      ]
    },
    {
      "id": "sentinel_pinning_bash",
      "kind": "ability",
      "name": "Pinning Bash",
      "unlock_level": 24,
      "requires": [
        "sentinel_pillar_strike"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 740,
      "y": 108,
      "category": "ATTACK",
      "percentage": 145,
      "cooldown": 2,
      "effects": [
        {
          "kind": "slow",
          "percentage": 25,
          "rounds": 2
        }
      ]
    },
    {
      "id": "sentinel_enduring_watch",
      "kind": "passive",
      "name": "Enduring Watch",
      "unlock_level": 24,
      "requires": [
        "sentinel_watchtower"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 740,
      "y": 228,
      "passive": {
        "kind": "defense_extension",
        "params": {
          "protected_attacks": 3,
          "rounds": 2
        }
      }
    },
    {
      "id": "sentinel_night_sanctuary",
      "kind": "ability",
      "name": "Night Sanctuary",
      "unlock_level": 28,
      "requires": [
        "sentinel_quiet_watch"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 740,
      "y": 348,
      "category": "DEFENSE",
      "percentage": 320,
      "cooldown": 4,
      "effects": [
        {
          "kind": "ward",
          "rounds": 2
        }
      ]
    },
    {
      "id": "sentinel_eternal_vigil",
      "kind": "ability",
      "name": "Eternal Vigil",
      "unlock_level": 30,
      "requires": [
        "sentinel_owl_sight",
        "sentinel_measured_response",
        "sentinel_clear_vigil",
        "sentinel_pinning_bash",
        "sentinel_enduring_watch",
        "sentinel_night_sanctuary"
      ],
      "cost": {
        "tier": "unique",
        "amount": 5
      },
      "x": 1000,
      "y": 288,
      "category": "DEFENSE",
      "percentage": 450,
      "cooldown": 4,
      "effects": [
        {
          "kind": "heal",
          "percentage": 70
        },
        {
          "kind": "cleanse"
        }
      ]
    }
  ]
}
```

## Channeler — Dawnlight

A lantern spirit that balances power buffs, cleansing and self-restoration.

Starting kit: Focus (Lv. 1), Bolt (Lv. 10), Ward (Lv. 20), plus the catalog passive.

| Node | Level | Essence | Requires all | Behavior |
|---|---:|---|---|---|
| Attunement | 12 | 3 common | Focus | SUPPORT 110%; cooldown 3; power for 3 rounds |
| Overload | 16 | 3 rare | Bolt | ATTACK 220%; cooldown 3 |
| Lantern Ward | 20 | 2 common | Ward | DEFENSE 160%; cooldown 2 |
| Afterglow | 18 | 4 rare | Starting passive | Passive: `cooldown_reduction` {"rounds": 1, "minimum": 1} |
| Kindled Mending | 8 | 2 common | Focus | SUPPORT 40%; cooldown 2; power for 3 rounds; `heal` {"percentage": 60} |
| Lantern Pulse | 12 | 3 common | Bolt | ATTACK 110%; cooldown 2; `weaken` {"percentage": 15, "rounds": 2} |
| Spirit Wick | 14 | 3 common | Starting passive | Passive: `heal_bonus` {"fraction": 0.3} |
| Purifying Light | 18 | 3 rare | Attunement | SUPPORT 65%; cooldown 3; power for 3 rounds; `cleanse` {} |
| Cyan Shelter | 24 | 4 rare | Lantern Ward | DEFENSE 190%; cooldown 3; `regen` {"percentage": 30, "rounds": 3} |
| Beacon Seal | 24 | 4 rare | Overload | ATTACK 160%; cooldown 3; `exposed` {"percentage": 35, "rounds": 3} |
| Last Light | 28 | 4 rare | Cyan Shelter | DEFENSE 150%; cooldown 4; `ward` {"rounds": 2} |
| Dawn Lantern | 30 | 5 unique | Afterglow, Kindled Mending, Lantern Pulse, Spirit Wick, Purifying Light, Beacon Seal, Last Light | SUPPORT 120%; cooldown 4; power for 3 rounds; `heal` {"percentage": 90}; `cleanse` {} |

### tree.json

```json
{
  "nodes": [
    {
      "id": "channeler_focus",
      "root": true,
      "x": 40,
      "y": 120
    },
    {
      "id": "channeler_bolt",
      "root": true,
      "x": 40,
      "y": 240
    },
    {
      "id": "channeler_ward",
      "root": true,
      "x": 40,
      "y": 360
    },
    {
      "id": "channeler_passive",
      "root": true,
      "x": 40,
      "y": 480
    },
    {
      "id": "channeler_attunement",
      "kind": "ability",
      "name": "Attunement",
      "category": "SUPPORT",
      "stat": "power",
      "duration": 3,
      "percentage": 110,
      "cooldown": 3,
      "unlock_level": 12,
      "requires": [
        "channeler_focus"
      ],
      "cost": {
        "tier": "common",
        "amount": 3
      },
      "x": 260,
      "y": 120
    },
    {
      "id": "channeler_overload",
      "kind": "ability",
      "name": "Overload",
      "category": "ATTACK",
      "percentage": 220,
      "cooldown": 3,
      "unlock_level": 16,
      "requires": [
        "channeler_bolt"
      ],
      "cost": {
        "tier": "rare",
        "amount": 3
      },
      "x": 260,
      "y": 240
    },
    {
      "id": "channeler_lantern_ward",
      "kind": "ability",
      "name": "Lantern Ward",
      "category": "DEFENSE",
      "percentage": 160,
      "cooldown": 2,
      "unlock_level": 20,
      "requires": [
        "channeler_ward"
      ],
      "cost": {
        "tier": "common",
        "amount": 2
      },
      "x": 260,
      "y": 360
    },
    {
      "id": "channeler_afterglow",
      "kind": "passive",
      "name": "Afterglow",
      "unlock_level": 18,
      "passive": {
        "kind": "cooldown_reduction",
        "params": {
          "rounds": 1,
          "minimum": 1
        }
      },
      "requires": [
        "channeler_passive"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 260,
      "y": 480
    },
    {
      "id": "channeler_kindled_mending",
      "kind": "ability",
      "name": "Kindled Mending",
      "unlock_level": 8,
      "requires": [
        "channeler_focus"
      ],
      "cost": {
        "tier": "common",
        "amount": 2
      },
      "x": 500,
      "y": 120,
      "category": "SUPPORT",
      "percentage": 40,
      "cooldown": 2,
      "stat": "power",
      "duration": 3,
      "effects": [
        {
          "kind": "heal",
          "percentage": 60
        }
      ]
    },
    {
      "id": "channeler_lantern_pulse",
      "kind": "ability",
      "name": "Lantern Pulse",
      "unlock_level": 12,
      "requires": [
        "channeler_bolt"
      ],
      "cost": {
        "tier": "common",
        "amount": 3
      },
      "x": 500,
      "y": 240,
      "category": "ATTACK",
      "percentage": 110,
      "cooldown": 2,
      "effects": [
        {
          "kind": "weaken",
          "percentage": 15,
          "rounds": 2
        }
      ]
    },
    {
      "id": "channeler_spirit_wick",
      "kind": "passive",
      "name": "Spirit Wick",
      "unlock_level": 14,
      "requires": [
        "channeler_passive"
      ],
      "cost": {
        "tier": "common",
        "amount": 3
      },
      "x": 500,
      "y": 360,
      "passive": {
        "kind": "heal_bonus",
        "params": {
          "fraction": 0.3
        }
      }
    },
    {
      "id": "channeler_purifying_light",
      "kind": "ability",
      "name": "Purifying Light",
      "unlock_level": 18,
      "requires": [
        "channeler_attunement"
      ],
      "cost": {
        "tier": "rare",
        "amount": 3
      },
      "x": 500,
      "y": 480,
      "category": "SUPPORT",
      "percentage": 65,
      "cooldown": 3,
      "stat": "power",
      "duration": 3,
      "effects": [
        {
          "kind": "cleanse"
        }
      ]
    },
    {
      "id": "channeler_cyan_shelter",
      "kind": "ability",
      "name": "Cyan Shelter",
      "unlock_level": 24,
      "requires": [
        "channeler_lantern_ward"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 740,
      "y": 120,
      "category": "DEFENSE",
      "percentage": 190,
      "cooldown": 3,
      "effects": [
        {
          "kind": "regen",
          "percentage": 30,
          "rounds": 3
        }
      ]
    },
    {
      "id": "channeler_beacon_seal",
      "kind": "ability",
      "name": "Beacon Seal",
      "unlock_level": 24,
      "requires": [
        "channeler_overload"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 740,
      "y": 240,
      "category": "ATTACK",
      "percentage": 160,
      "cooldown": 3,
      "effects": [
        {
          "kind": "exposed",
          "percentage": 35,
          "rounds": 3
        }
      ]
    },
    {
      "id": "channeler_last_light",
      "kind": "ability",
      "name": "Last Light",
      "unlock_level": 28,
      "requires": [
        "channeler_cyan_shelter"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 740,
      "y": 360,
      "category": "DEFENSE",
      "percentage": 150,
      "cooldown": 4,
      "effects": [
        {
          "kind": "ward",
          "rounds": 2
        }
      ]
    },
    {
      "id": "channeler_dawn_lantern",
      "kind": "ability",
      "name": "Dawn Lantern",
      "unlock_level": 30,
      "requires": [
        "channeler_afterglow",
        "channeler_kindled_mending",
        "channeler_lantern_pulse",
        "channeler_spirit_wick",
        "channeler_purifying_light",
        "channeler_beacon_seal",
        "channeler_last_light"
      ],
      "cost": {
        "tier": "unique",
        "amount": 5
      },
      "x": 1000,
      "y": 300,
      "category": "SUPPORT",
      "percentage": 120,
      "cooldown": 4,
      "stat": "power",
      "duration": 3,
      "effects": [
        {
          "kind": "heal",
          "percentage": 90
        },
        {
          "kind": "cleanse"
        }
      ]
    }
  ]
}
```

## Forbidden — Ruinheart

A magma crystal fiend that erodes its opponent before a long-cooldown finisher.

Starting kit: Ruin (Lv. 1), Dread Ward (Lv. 10), Ascendance (Lv. 20), plus the catalog passive.

| Node | Level | Essence | Requires all | Behavior |
|---|---:|---|---|---|
| Oblivion | 30 | 4 unique | Ruin | ATTACK 320%; cooldown 3 |
| Void Shroud | 25 | 3 unique | Dread Ward | DEFENSE 400%; cooldown 3 |
| Hollow Crown | 35 | 5 unique | Ascendance | SUPPORT 150%; cooldown 4; power for 3 rounds |
| Rime | 40 | 5 unique | Hollow Crown | Passive: `support_duration_bonus` {"rounds": 1} |
| Crystal Rend | 8 | 2 common | Ruin | ATTACK 160%; cooldown 2; `bleed` {"percentage": 25, "rounds": 3} |
| Obsidian Heart | 12 | 3 common | Starting passive | Passive: `low_hp_attack_bonus` {"hp_below": 0.5, "power_fraction": 0.35} |
| Fracture Hex | 18 | 3 rare | Crystal Rend | ATTACK 180%; cooldown 3; `exposed` {"percentage": 50, "rounds": 3} |
| Crown of Ash | 24 | 4 rare | Ascendance | SUPPORT 80%; cooldown 3; power for 3 rounds; `cleanse` {} |
| Magma Rebirth | 32 | 5 unique | Void Shroud | DEFENSE 320%; cooldown 4; `heal` {"percentage": 90} |
| Dread Dominion | 38 | 5 unique | Fracture Hex | ATTACK 210%; cooldown 3; `weaken` {"percentage": 25, "rounds": 2}; `slow` {"percentage": 20, "rounds": 2} |
| Refuse the End | 44 | 5 unique | Magma Rebirth | DEFENSE 280%; cooldown 4; `ward` {"rounds": 2} |
| Worldsplitter | 50 | 5 unique | Oblivion, Rime, Obsidian Heart, Crown of Ash, Dread Dominion, Refuse the End | ATTACK 380%; cooldown 5; `bleed` {"percentage": 30, "rounds": 3}; `exposed` {"percentage": 60, "rounds": 2} |

### tree.json

```json
{
  "nodes": [
    {
      "id": "forbidden_ruin",
      "root": true,
      "x": 40,
      "y": 132
    },
    {
      "id": "forbidden_dread_ward",
      "root": true,
      "x": 40,
      "y": 252
    },
    {
      "id": "forbidden_ascendance",
      "root": true,
      "x": 40,
      "y": 372
    },
    {
      "id": "forbidden_passive",
      "root": true,
      "x": 40,
      "y": 492
    },
    {
      "id": "forbidden_oblivion",
      "kind": "ability",
      "name": "Oblivion",
      "category": "ATTACK",
      "percentage": 320,
      "cooldown": 3,
      "unlock_level": 30,
      "requires": [
        "forbidden_ruin"
      ],
      "cost": {
        "tier": "unique",
        "amount": 4
      },
      "x": 260,
      "y": 132
    },
    {
      "id": "forbidden_void_shroud",
      "kind": "ability",
      "name": "Void Shroud",
      "category": "DEFENSE",
      "percentage": 400,
      "cooldown": 3,
      "unlock_level": 25,
      "requires": [
        "forbidden_dread_ward"
      ],
      "cost": {
        "tier": "unique",
        "amount": 3
      },
      "x": 260,
      "y": 252
    },
    {
      "id": "forbidden_hollow_crown",
      "kind": "ability",
      "name": "Hollow Crown",
      "category": "SUPPORT",
      "stat": "power",
      "duration": 3,
      "percentage": 150,
      "cooldown": 4,
      "unlock_level": 35,
      "requires": [
        "forbidden_ascendance"
      ],
      "cost": {
        "tier": "unique",
        "amount": 5
      },
      "x": 260,
      "y": 372
    },
    {
      "id": "forbidden_rime",
      "kind": "passive",
      "name": "Rime",
      "unlock_level": 40,
      "passive": {
        "kind": "support_duration_bonus",
        "params": {
          "rounds": 1
        }
      },
      "requires": [
        "forbidden_hollow_crown"
      ],
      "cost": {
        "tier": "unique",
        "amount": 5
      },
      "x": 260,
      "y": 492
    },
    {
      "id": "forbidden_crystal_rend",
      "kind": "ability",
      "name": "Crystal Rend",
      "unlock_level": 8,
      "requires": [
        "forbidden_ruin"
      ],
      "cost": {
        "tier": "common",
        "amount": 2
      },
      "x": 500,
      "y": 132,
      "category": "ATTACK",
      "percentage": 160,
      "cooldown": 2,
      "effects": [
        {
          "kind": "bleed",
          "percentage": 25,
          "rounds": 3
        }
      ]
    },
    {
      "id": "forbidden_obsidian_heart",
      "kind": "passive",
      "name": "Obsidian Heart",
      "unlock_level": 12,
      "requires": [
        "forbidden_passive"
      ],
      "cost": {
        "tier": "common",
        "amount": 3
      },
      "x": 500,
      "y": 252,
      "passive": {
        "kind": "low_hp_attack_bonus",
        "params": {
          "hp_below": 0.5,
          "power_fraction": 0.35
        }
      }
    },
    {
      "id": "forbidden_fracture_hex",
      "kind": "ability",
      "name": "Fracture Hex",
      "unlock_level": 18,
      "requires": [
        "forbidden_crystal_rend"
      ],
      "cost": {
        "tier": "rare",
        "amount": 3
      },
      "x": 500,
      "y": 372,
      "category": "ATTACK",
      "percentage": 180,
      "cooldown": 3,
      "effects": [
        {
          "kind": "exposed",
          "percentage": 50,
          "rounds": 3
        }
      ]
    },
    {
      "id": "forbidden_crown_of_ash",
      "kind": "ability",
      "name": "Crown of Ash",
      "unlock_level": 24,
      "requires": [
        "forbidden_ascendance"
      ],
      "cost": {
        "tier": "rare",
        "amount": 4
      },
      "x": 500,
      "y": 492,
      "category": "SUPPORT",
      "percentage": 80,
      "cooldown": 3,
      "stat": "power",
      "duration": 3,
      "effects": [
        {
          "kind": "cleanse"
        }
      ]
    },
    {
      "id": "forbidden_magma_rebirth",
      "kind": "ability",
      "name": "Magma Rebirth",
      "unlock_level": 32,
      "requires": [
        "forbidden_void_shroud"
      ],
      "cost": {
        "tier": "unique",
        "amount": 5
      },
      "x": 740,
      "y": 132,
      "category": "DEFENSE",
      "percentage": 320,
      "cooldown": 4,
      "effects": [
        {
          "kind": "heal",
          "percentage": 90
        }
      ]
    },
    {
      "id": "forbidden_dread_dominion",
      "kind": "ability",
      "name": "Dread Dominion",
      "unlock_level": 38,
      "requires": [
        "forbidden_fracture_hex"
      ],
      "cost": {
        "tier": "unique",
        "amount": 5
      },
      "x": 740,
      "y": 252,
      "category": "ATTACK",
      "percentage": 210,
      "cooldown": 3,
      "effects": [
        {
          "kind": "weaken",
          "percentage": 25,
          "rounds": 2
        },
        {
          "kind": "slow",
          "percentage": 20,
          "rounds": 2
        }
      ]
    },
    {
      "id": "forbidden_refuse_the_end",
      "kind": "ability",
      "name": "Refuse the End",
      "unlock_level": 44,
      "requires": [
        "forbidden_magma_rebirth"
      ],
      "cost": {
        "tier": "unique",
        "amount": 5
      },
      "x": 740,
      "y": 372,
      "category": "DEFENSE",
      "percentage": 280,
      "cooldown": 4,
      "effects": [
        {
          "kind": "ward",
          "rounds": 2
        }
      ]
    },
    {
      "id": "forbidden_worldsplitter",
      "kind": "ability",
      "name": "Worldsplitter",
      "unlock_level": 50,
      "requires": [
        "forbidden_oblivion",
        "forbidden_rime",
        "forbidden_obsidian_heart",
        "forbidden_crown_of_ash",
        "forbidden_dread_dominion",
        "forbidden_refuse_the_end"
      ],
      "cost": {
        "tier": "unique",
        "amount": 5
      },
      "x": 1000,
      "y": 312,
      "category": "ATTACK",
      "percentage": 380,
      "cooldown": 5,
      "effects": [
        {
          "kind": "bleed",
          "percentage": 30,
          "rounds": 3
        },
        {
          "kind": "exposed",
          "percentage": 60,
          "rounds": 2
        }
      ]
    }
  ]
}
```
