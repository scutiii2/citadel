# Striker: art prompts

Rules: `../ART_GUIDE.md` (read it first; it explains sizes, the black background and the crop steps).
Files for this Ascended: `sprite_main_card.webp`, `sprite_preview_card.webp`, `sprite_battle.webp` (this folder).
Current art: main card and battle use the recreated Striker sprites and source PNGs from commit `27b4c23`; preview is resized from the established square reference. All three exports now match the guide dimensions. In-game visual review is pending.

## Design (the visual canon, keep it the same in all three sprites)

- **Role:** Starter. Attacker: the passive adds attack when it is low on health, so the design says fierce, reckless, a fighter.
- **Concept:** a small armoured salamander-dragon warrior with red scaly skin, an orange belly, a flame mane running down its head and a long flaming tail.
- **Key details:** steel pauldrons and gauntlets with bronze trim, a dark scarf at the neck, big amber eyes, and a broad glowing blade in its hand.
- **Palette:** crimson red, orange, steel grey, bronze, dark brown scarf.
- **Signature glow:** fire orange and crimson (mane, tail flame, blade glow, eyes).
- **Main card pose:** a low aggressive lunge with the glowing blade held ready on the right, tail flame curling behind, glancing at the viewer.
- **Preview framing:** head and armoured shoulders, flame mane up, the blade tip glowing in front.
- **Battle pose:** a forward lunge facing right, blade held out ahead, tail flame behind.

## How to run it

1. Read `identity.md` and upload `preview_source.webp` in the first message and add: "Redraw this exact character in the new format and keep the design."
2. Paste the main card prompt. Iterate until the design is right.
3. In the same chat paste the preview prompt, then the battle prompt, each starting with: "Use the character in the previous image as the exact reference: same design, colours, armour and proportions. "
4. Crop and convert with the commands in `../ART_GUIDE.md` section 6, check the checklist in section 7.

## Main card prompt (`sprite_main_card.webp`)

```text
Create the card illustration of an original game creature. Striker is a small armoured salamander-dragon warrior with red scaly skin, an orange belly, a flame mane running down its head and a long flaming tail. Key details: steel pauldrons and gauntlets with bronze trim, a dark scarf at the neck, big amber eyes, and a broad glowing blade in its hand. Colours: crimson red, orange, steel grey, bronze, dark brown scarf. Signature glow: fire orange and crimson (mane, tail flame, blade glow, eyes). Pose: a low aggressive lunge with the glowing blade held ready on the right, tail flame curling behind, glancing at the viewer. Format: landscape 3:2 (1536 x 1024). Composition: the whole character visible and centred, filling about 85 percent of the height of the middle band, where the middle band is the middle 66 percent of the image height. Keep the top 17 percent and the bottom 17 percent as plain background only, with nothing important there, because the picture will be cropped to a wide 1.93:1 strip. No limb, weapon or effect touches the left or right edge. Background: a dark ruined forge or dungeon with distant lava glow, soft and darker toward the edges so the character stands out, never brighter than the character. Style: Chunky high-resolution pixel art in a dark-fantasy forge style: visible square pixels about 4 to 6 real pixels wide, crisp hard edges, no smooth gradients, no anti-aliasing blur, not painterly, not 3D, not photographic. Palette: charcoal and slate metal, copper and bronze trim, cracked stone, riveted plates, with glowing ember-orange light as the shared accent plus the character's own signature glow colour. One strong light source that comes from the character's own glow. Big expressive glowing eyes, a clear silhouette, a little cute and a little fierce. Avoid pure white and pure black. Never: No text, letters, numbers, logos, watermark, signature, speech bubbles, UI, card frame or border. No second character. No humans, no blood.
```

## Preview card prompt (`sprite_preview_card.webp`)

```text
Create a small square portrait icon of an original game creature. Striker is a small armoured salamander-dragon warrior with red scaly skin, an orange belly, a flame mane running down its head and a long flaming tail. Key details: steel pauldrons and gauntlets with bronze trim, a dark scarf at the neck, big amber eyes, and a broad glowing blade in its hand. Colours: crimson red, orange, steel grey, bronze, dark brown scarf. Signature glow: fire orange and crimson (mane, tail flame, blade glow, eyes). Framing: head and armoured shoulders, flame mane up, the blade tip glowing in front. Format: square 1:1 (1024 x 1024). Composition: bust to three-quarter body, head and upper body fill most of the frame, centred, eyes in the upper-middle third. Background: simplified and dark with one soft glow behind the character, no scenery detail. This icon is shown at about 150 pixels wide, so use bold shapes, strong contrast, few details, thick readable outlines and at most 6 to 8 main colours. Style: Chunky high-resolution pixel art in a dark-fantasy forge style: visible square pixels about 4 to 6 real pixels wide, crisp hard edges, no smooth gradients, no anti-aliasing blur, not painterly, not 3D, not photographic. Palette: charcoal and slate metal, copper and bronze trim, cracked stone, riveted plates, with glowing ember-orange light as the shared accent plus the character's own signature glow colour. One strong light source that comes from the character's own glow. Big expressive glowing eyes, a clear silhouette, a little cute and a little fierce. Avoid pure white and pure black. Never: No text, letters, numbers, logos, watermark, signature, speech bubbles, UI, card frame or border. No second character. No humans, no blood.
```

## Battle prompt (`sprite_battle.webp`)

```text
Create the battle sprite of an original game creature. Striker is a small armoured salamander-dragon warrior with red scaly skin, an orange belly, a flame mane running down its head and a long flaming tail. Key details: steel pauldrons and gauntlets with bronze trim, a dark scarf at the neck, big amber eyes, and a broad glowing blade in its hand. Colours: crimson red, orange, steel grey, bronze, dark brown scarf. Signature glow: fire orange and crimson (mane, tail flame, blade glow, eyes). Pose: a forward lunge facing right, blade held out ahead, tail flame behind. Format: square 1:1 (1024 x 1024). The single full-body figure faces RIGHT (toward the right edge), in side or three-quarter view. Background: flat pure black (#000000) everywhere outside the character, or transparent if you can; no ground, no floor line, no cast shadow, no scenery, no vignette. Glow around the character is fine. Composition: the whole body inside the image with margin, about 90 percent of the image height, feet near the bottom with about 4 percent margin, centred left to right, nothing touching an edge. Important: the darkest colour used on the character itself must be a dark slate, nothing darker than about #2a3342. Do not use pure black or near-black anywhere on the character, not even for outlines, because black pixels are removed in the game. Style: Chunky high-resolution pixel art in a dark-fantasy forge style: visible square pixels about 4 to 6 real pixels wide, crisp hard edges, no smooth gradients, no anti-aliasing blur, not painterly, not 3D, not photographic. Palette: charcoal and slate metal, copper and bronze trim, cracked stone, riveted plates, with glowing ember-orange light as the shared accent plus the character's own signature glow colour. One strong light source that comes from the character's own glow. Big expressive glowing eyes, a clear silhouette, a little cute and a little fierce. Avoid pure white and pure black. Never: No text, letters, numbers, logos, watermark, signature, speech bubbles, UI, card frame or border. No second character. No humans, no blood.
```

## Export size correction (2026-10-12)

Preview exported at 512 x 512 without stretching. The original reference is retained as `preview_source.webp`. Portrait sources use a square crop at the catalog's existing `art.focus_preview`; square sources are downscaled with nearest-neighbour sampling. Main card must be 1536 x 796 and battle 512 x 512. Read `identity.md` and inspect the original reference before further generation.
