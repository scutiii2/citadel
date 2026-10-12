# Scout: art prompts

Rules: `../ART_GUIDE.md` (read it first; it explains sizes, the black background and the crop steps).
Files for this Ascended: `sprite_main_card.webp`, `sprite_preview_card.webp`, `sprite_battle.webp` (this folder).
Primary identity reference: `sprite_preview_card.webp`. Read `identity.md` and inspect this established reference before every generation. Keep the existing preview; recreate the main and battle sprites to the guide's framing and dimensions.

## Design (the visual canon, keep it the same in all three sprites)

- **Role:** Starter. Fast and evasive: the passive gives it speed at the start of a battle, so the design says light, quick, alert.
- **Concept:** a fox-like four-legged creature with blue and teal feathered fur, cream chest and muzzle, a tall flame-tipped crest of feathers on its head and one huge flaming tail.
- **Key details:** amber eyes, copper bracers on its legs, a small glowing ember pendant on its chest, feathers edged with orange fire.
- **Palette:** teal and sky blue feathers, cream fur, copper bracers, orange flame.
- **Signature glow:** ember orange flames on blue-teal feathers (crest, tail tip, pendant, eyes).
- **Main card pose:** a low running stance, head turned toward the viewer with a confident smirk, tail flowing behind it.
- **Preview framing:** the head and chest, ears and flame crest up, pendant visible, smirking.
- **Battle pose:** a crouched ready-to-sprint stance facing right, tail sweeping up behind it.

## How to run it

1. Read `identity.md`, upload `sprite_preview_card.webp` as the primary reference and add: "Redraw this exact character in the new format and keep the design."
2. Paste the main card prompt. Iterate until the design is right.
3. Generate the battle sprite from the established preview reference too, starting with: "Use the character in the reference preview as the exact reference: same design, colours, armour and proportions." Keep the current preview unless a replacement is requested.
4. Crop and convert with the commands in `../ART_GUIDE.md` section 6, check the checklist in section 7.

## Main card prompt (`sprite_main_card.webp`)

```text
Create the card illustration of an original game creature. Scout is a fox-like four-legged creature with blue and teal feathered fur, cream chest and muzzle, a tall flame-tipped crest of feathers on its head and one huge flaming tail. Key details: amber eyes, copper bracers on its legs, a small glowing ember pendant on its chest, feathers edged with orange fire. Colours: teal and sky blue feathers, cream fur, copper bracers, orange flame. Signature glow: ember orange flames on blue-teal feathers (crest, tail tip, pendant, eyes). Pose: a low running stance, head turned toward the viewer with a confident smirk, tail flowing behind it. Format: landscape 3:2 (1536 x 1024). Composition: the whole character visible and centred, filling about 85 percent of the height of the middle band, where the middle band is the middle 66 percent of the image height. Keep the top 17 percent and the bottom 17 percent as plain background only, with nothing important there, because the picture will be cropped to a wide 1.93:1 strip. No limb, weapon or effect touches the left or right edge. Background: a dark ruined forge or dungeon with distant lava glow, soft and darker toward the edges so the character stands out, never brighter than the character. Style: Chunky high-resolution pixel art in a dark-fantasy forge style: visible square pixels about 4 to 6 real pixels wide, crisp hard edges, no smooth gradients, no anti-aliasing blur, not painterly, not 3D, not photographic. Palette: charcoal and slate metal, copper and bronze trim, cracked stone, riveted plates, with glowing ember-orange light as the shared accent plus the character's own signature glow colour. One strong light source that comes from the character's own glow. Big expressive glowing eyes, a clear silhouette, a little cute and a little fierce. Avoid pure white and pure black. Never: No text, letters, numbers, logos, watermark, signature, speech bubbles, UI, card frame or border. No second character. No humans, no blood.
```

## Preview card prompt (`sprite_preview_card.webp`)

```text
Create a small square portrait icon of an original game creature. Scout is a fox-like four-legged creature with blue and teal feathered fur, cream chest and muzzle, a tall flame-tipped crest of feathers on its head and one huge flaming tail. Key details: amber eyes, copper bracers on its legs, a small glowing ember pendant on its chest, feathers edged with orange fire. Colours: teal and sky blue feathers, cream fur, copper bracers, orange flame. Signature glow: ember orange flames on blue-teal feathers (crest, tail tip, pendant, eyes). Framing: the head and chest, ears and flame crest up, pendant visible, smirking. Format: square 1:1 (1024 x 1024). Composition: bust to three-quarter body, head and upper body fill most of the frame, centred, eyes in the upper-middle third. Background: simplified and dark with one soft glow behind the character, no scenery detail. This icon is shown at about 150 pixels wide, so use bold shapes, strong contrast, few details, thick readable outlines and at most 6 to 8 main colours. Style: Chunky high-resolution pixel art in a dark-fantasy forge style: visible square pixels about 4 to 6 real pixels wide, crisp hard edges, no smooth gradients, no anti-aliasing blur, not painterly, not 3D, not photographic. Palette: charcoal and slate metal, copper and bronze trim, cracked stone, riveted plates, with glowing ember-orange light as the shared accent plus the character's own signature glow colour. One strong light source that comes from the character's own glow. Big expressive glowing eyes, a clear silhouette, a little cute and a little fierce. Avoid pure white and pure black. Never: No text, letters, numbers, logos, watermark, signature, speech bubbles, UI, card frame or border. No second character. No humans, no blood.
```

## Battle prompt (`sprite_battle.webp`)

```text
Create the battle sprite of an original game creature. Scout is a fox-like four-legged creature with blue and teal feathered fur, cream chest and muzzle, a tall flame-tipped crest of feathers on its head and one huge flaming tail. Key details: amber eyes, copper bracers on its legs, a small glowing ember pendant on its chest, feathers edged with orange fire. Colours: teal and sky blue feathers, cream fur, copper bracers, orange flame. Signature glow: ember orange flames on blue-teal feathers (crest, tail tip, pendant, eyes). Pose: a crouched ready-to-sprint stance facing right, tail sweeping up behind it. Format: square 1:1 (1024 x 1024). The single full-body figure faces RIGHT (toward the right edge), in side or three-quarter view. Background: flat pure black (#000000) everywhere outside the character, or transparent if you can; no ground, no floor line, no cast shadow, no scenery, no vignette. Glow around the character is fine. Composition: the whole body inside the image with margin, about 90 percent of the image height, feet near the bottom with about 4 percent margin, centred left to right, nothing touching an edge. Important: the darkest colour used on the character itself must be a dark slate, nothing darker than about #2a3342. Do not use pure black or near-black anywhere on the character, not even for outlines, because black pixels are removed in the game. Style: Chunky high-resolution pixel art in a dark-fantasy forge style: visible square pixels about 4 to 6 real pixels wide, crisp hard edges, no smooth gradients, no anti-aliasing blur, not painterly, not 3D, not photographic. Palette: charcoal and slate metal, copper and bronze trim, cracked stone, riveted plates, with glowing ember-orange light as the shared accent plus the character's own signature glow colour. One strong light source that comes from the character's own glow. Big expressive glowing eyes, a clear silhouette, a little cute and a little fierce. Avoid pure white and pure black. Never: No text, letters, numbers, logos, watermark, signature, speech bubbles, UI, card frame or border. No second character. No humans, no blood.
```

## Export size correction (2026-10-12)

Preview exported at 512 x 512 without stretching. The original reference is retained as `preview_source.webp`. Portrait sources use a square crop at the catalog's existing `art.focus_preview`; square sources are downscaled with nearest-neighbour sampling. Main card must be 1536 x 796 and battle 512 x 512. Read `identity.md` and inspect the original reference before further generation.
