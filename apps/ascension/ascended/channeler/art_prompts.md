# Channeler: art prompts

Rules: `../ART_GUIDE.md`; read `identity.md` before generation. The user's approved humanoid/armoured redesign takes precedence over the guide's older creature-only restriction.

Status (2026-10-13): battle sprite regenerated from the approved concept, shadows corrected for arena blending, and exported as a transparent 512 x 512 lossless WebP with nearest-neighbour scaling and clear margins. Full-resolution source: battle_source.png. Main-card and preview-card images remain legacy art; they were not requested in this pass. Live game reload review remains separate.

## Design

A blue-haired fantasy sorceress with a pale youthful face and luminous icy-blue eyes, sapphire hood or head covering, long layered cobalt robes, silver/blue ornamentation, blue gloves and boots, and a small bright cyan-blue spell orb held above one hand. Match the approved blue mage silhouette and modest fully covered robes. No lantern body, brass orbiting rings or detached hands.

Primary redesign reference: `battle_source.png`. Use the approved concept sheet during the initial battle generation; afterwards use this character-only source as the exact reference.

## Battle prompt (`sprite_battle.webp`)

Use the primary redesign reference as the exact character design. A blue-haired fantasy sorceress with a pale youthful face and luminous icy-blue eyes, sapphire hood or head covering, long layered cobalt robes, silver/blue ornamentation, blue gloves and boots, and a small bright cyan-blue spell orb held above one hand. Match the approved blue mage silhouette and modest fully covered robes. No lantern body, brass orbiting rings or detached hands. Right-facing three-quarter casting stance, leading hand extended to the right with a small blue spell orb, robe folds behind. Single complete full-body figure facing RIGHT, square 1024 x 1024 source, transparent background. Figure fills about 85–90 percent of the height, with clear margins around head, feet, cloak and weapons. No floor or shadow. Darkest body pixels approximately #2a3342 or lighter. Chunky high-resolution pixel art with visible square clusters, hard edges, no smooth gradients or antialiasing blur. Dark-fantasy forge style: slate metal, copper accents and the character's approved signature colours. No UI, words, labels, watermark, card frame, scenery in battle art, extra characters or gore. Export a 512 x 512 lossless WebP with nearest-neighbour scaling.

## Main-card prompt (future art pass)

Use `battle_source.png` as the exact design reference. A blue-haired fantasy sorceress with a pale youthful face and luminous icy-blue eyes, sapphire hood or head covering, long layered cobalt robes, silver/blue ornamentation, blue gloves and boots, and a small bright cyan-blue spell orb held above one hand. Match the approved blue mage silhouette and modest fully covered robes. No lantern body, brass orbiting rings or detached hands. Heroic pose with whole body and equipment visible. Landscape 1536 x 1024 source; keep all important anatomy in the middle 66 percent of the height and side margins clear. Dim ruined-forge scene, darker than the character. Chunky high-resolution pixel art with visible square clusters, hard edges, no smooth gradients or antialiasing blur. Dark-fantasy forge style: slate metal, copper accents and the character's approved signature colours. No UI, words, labels, watermark, card frame, scenery in battle art, extra characters or gore. Crop the source to 1536 x 796 for `sprite_main_card.webp`.

## Preview-card prompt (future art pass)

Use `battle_source.png` as the exact design reference. A blue-haired fantasy sorceress with a pale youthful face and luminous icy-blue eyes, sapphire hood or head covering, long layered cobalt robes, silver/blue ornamentation, blue gloves and boots, and a small bright cyan-blue spell orb held above one hand. Match the approved blue mage silhouette and modest fully covered robes. No lantern body, brass orbiting rings or detached hands. Bust to three-quarter portrait, bold readable silhouette and simplified dark background, face/helmet in the upper-middle third. Square 1024 x 1024 source, downscale to 512 x 512 for `sprite_preview_card.webp`; inspect at 150 pixels. Chunky high-resolution pixel art with visible square clusters, hard edges, no smooth gradients or antialiasing blur. Dark-fantasy forge style: slate metal, copper accents and the character's approved signature colours. No UI, words, labels, watermark, card frame, scenery in battle art, extra characters or gore.
