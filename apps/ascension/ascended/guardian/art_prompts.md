# Guardian: art prompts

Rules: `../ART_GUIDE.md`; read `identity.md` before generation. The user's approved humanoid/armoured redesign takes precedence over the guide's older creature-only restriction.

Status (2026-10-13): battle sprite regenerated from the approved concept, shadows corrected for arena blending, and exported as a transparent 512 x 512 lossless WebP with nearest-neighbour scaling and clear margins. Full-resolution source: battle_source.png. Main-card and preview-card images remain legacy art; they were not requested in this pass. Live game reload review remains separate.

## Design

A sturdy fully armoured fantasy knight, with a closed silver/slate helmet, narrow glowing amber visor, layered silver plate and copper-gold trim, broad angular blue kite shield bearing a simple gold cross, blue cloth tabard and a straight steel sword. Compact heroic proportions, broad shoulders, strong boots. No exposed human face, no furnace belly or golem flame crown.

Primary redesign reference: `battle_source.png`. Use the approved concept sheet during the initial battle generation; afterwards use this character-only source as the exact reference.

## Battle prompt (`sprite_battle.webp`)

Use the primary redesign reference as the exact character design. A sturdy fully armoured fantasy knight, with a closed silver/slate helmet, narrow glowing amber visor, layered silver plate and copper-gold trim, broad angular blue kite shield bearing a simple gold cross, blue cloth tabard and a straight steel sword. Compact heroic proportions, broad shoulders, strong boots. No exposed human face, no furnace belly or golem flame crown. Right-facing three-quarter defensive stance, shield leading toward the right, sword held ready behind it. Single complete full-body figure facing RIGHT, square 1024 x 1024 source, transparent background. Figure fills about 85–90 percent of the height, with clear margins around head, feet, cloak and weapons. No floor or shadow. Darkest body pixels approximately #2a3342 or lighter. Chunky high-resolution pixel art with visible square clusters, hard edges, no smooth gradients or antialiasing blur. Dark-fantasy forge style: slate metal, copper accents and the character's approved signature colours. No UI, words, labels, watermark, card frame, scenery in battle art, extra characters or gore. Export a 512 x 512 lossless WebP with nearest-neighbour scaling.

## Main-card prompt (future art pass)

Use `battle_source.png` as the exact design reference. A sturdy fully armoured fantasy knight, with a closed silver/slate helmet, narrow glowing amber visor, layered silver plate and copper-gold trim, broad angular blue kite shield bearing a simple gold cross, blue cloth tabard and a straight steel sword. Compact heroic proportions, broad shoulders, strong boots. No exposed human face, no furnace belly or golem flame crown. Heroic pose with whole body and equipment visible. Landscape 1536 x 1024 source; keep all important anatomy in the middle 66 percent of the height and side margins clear. Dim ruined-forge scene, darker than the character. Chunky high-resolution pixel art with visible square clusters, hard edges, no smooth gradients or antialiasing blur. Dark-fantasy forge style: slate metal, copper accents and the character's approved signature colours. No UI, words, labels, watermark, card frame, scenery in battle art, extra characters or gore. Crop the source to 1536 x 796 for `sprite_main_card.webp`.

## Preview-card prompt (future art pass)

Use `battle_source.png` as the exact design reference. A sturdy fully armoured fantasy knight, with a closed silver/slate helmet, narrow glowing amber visor, layered silver plate and copper-gold trim, broad angular blue kite shield bearing a simple gold cross, blue cloth tabard and a straight steel sword. Compact heroic proportions, broad shoulders, strong boots. No exposed human face, no furnace belly or golem flame crown. Bust to three-quarter portrait, bold readable silhouette and simplified dark background, face/helmet in the upper-middle third. Square 1024 x 1024 source, downscale to 512 x 512 for `sprite_preview_card.webp`; inspect at 150 pixels. Chunky high-resolution pixel art with visible square clusters, hard edges, no smooth gradients or antialiasing blur. Dark-fantasy forge style: slate metal, copper accents and the character's approved signature colours. No UI, words, labels, watermark, card frame, scenery in battle art, extra characters or gore.
