# Cindrax: art prompts

Latest battle export (2026-10-13): `sprite_battle.webp` regenerated from the established preview, preserving the magma-crystal identity. `battle_source.png` records the selected corrected source. Complete right-facing hovering silhouette, transparent background, safe crown and lower-tip margins, slate armour shadows, 512 x 512 lossless WebP. Main and preview cards are unchanged. Export and layout verification are performed with the rest of the new battle sprite set; live game reload review remains separate.

Rules: `../ART_GUIDE.md` (read it first; it explains sizes, the black background and the crop steps).
Files for this Ascended: `sprite_main_card.webp`, `sprite_preview_card.webp`, `sprite_battle.webp` (this folder).
Primary reference: sprite_preview_card.webp; see identity.md for the established visual identity. Preserve the preview while recreating main card and battle art.

Status (2026-10-12): main card and battle recreated with built-in image generation from the established preview. Main: 1536 x 796 WebP, centred crop of the generated image. Battle: 512 x 512 transparent lossless WebP, right-facing floating pose, slate shadows and copper lava recesses, resized with nearest-neighbour and padded to clear margins. Preview preserved. Layout tests passed; live game review remains pending.

Generation corrections: keep the main figure and shards within the central safe band; shrink the first composition rather than crop crown or tail. For battle, preserve the hovering anatomy and replace near-black armour and lava holes with visible slate/copper. Do not add legs, boots, ground or shadows. Use the exact visual features in `identity.md` throughout.

## Design (the visual canon, keep it the same in all three sprites)

- **Role:** Forbidden tier. Cannot be bought, only captured: the strongest and most ominous. Its passive reduces cooldowns.
- **Concept:** a hovering magma crystal fiend with a pointed segmented lower body, no legs or boots, and dark slate obsidian armour over a cracked glowing lava body, a mask-like face with yellow eyes, and tall red crystal spikes like wings and a crown.
- **Key details:** gold-trimmed obsidian shoulder and chest plates, a large red crystal set in the chest, burning claw gauntlets, floating shards of red crystal around it.
- **Palette:** obsidian black-grey, lava red and orange, crimson crystal, gold trim.
- **Signature glow:** molten red and orange with yellow eyes (lava seams, crystals, claws).
- **Main card pose:** a looming centred pose, arms spread with burning claws, crystal wings behind it, looking down at the viewer.
- **Preview framing:** head and chest with the crown of crystals, the red chest gem and yellow eyes glowing.
- **Battle pose:** a menacing clawed stance facing right, crystal wings spread behind it.

## How to run it

1. Read `identity.md`, then upload the established `sprite_preview_card.webp` in the first message and add: "Redraw this exact character in the new format and keep the design."
2. Paste the main card prompt. Iterate until the design is right.
3. In the same chat paste the preview prompt, then the battle prompt, each starting with: "Use the character in the previous image as the exact reference: same design, colours, armour and proportions. "
4. Crop and convert with the commands in `../ART_GUIDE.md` section 6, check the checklist in section 7.

## Main card prompt (`sprite_main_card.webp`)

```text
Create the card illustration of an original game creature. Cindrax is a hovering magma crystal fiend with a pointed segmented lower body, no legs or boots, and dark slate obsidian armour over a cracked glowing lava body, a mask-like face with yellow eyes, and tall red crystal spikes like wings and a crown. Key details: gold-trimmed obsidian shoulder and chest plates, a large red crystal set in the chest, burning claw gauntlets, floating shards of red crystal around it. Colours: obsidian black-grey, lava red and orange, crimson crystal, gold trim. Signature glow: molten red and orange with yellow eyes (lava seams, crystals, claws). Pose: a looming centred pose, arms spread with burning claws, crystal wings behind it, looking down at the viewer. Format: landscape 3:2 (1536 x 1024). Composition: the whole character visible and centred, filling about 85 percent of the height of the middle band, where the middle band is the middle 66 percent of the image height. Keep the top 17 percent and the bottom 17 percent as plain background only, with nothing important there, because the picture will be cropped to a wide 1.93:1 strip. No limb, weapon or effect touches the left or right edge. Background: a dark ruined forge or dungeon with distant lava glow, soft and darker toward the edges so the character stands out, never brighter than the character. Style: Chunky high-resolution pixel art in a dark-fantasy forge style: visible square pixels about 4 to 6 real pixels wide, crisp hard edges, no smooth gradients, no anti-aliasing blur, not painterly, not 3D, not photographic. Palette: charcoal and slate metal, copper and bronze trim, cracked stone, riveted plates, with glowing ember-orange light as the shared accent plus the character's own signature glow colour. One strong light source that comes from the character's own glow. Big expressive glowing eyes, a clear silhouette, a little cute and a little fierce. Avoid pure white and pure black. Never: No text, letters, numbers, logos, watermark, signature, speech bubbles, UI, card frame or border. No second character. No humans, no blood.
```

## Preview card prompt (`sprite_preview_card.webp`)

```text
Create a small square portrait icon of an original game creature. Cindrax is a hovering magma crystal fiend with a pointed segmented lower body, no legs or boots, and dark slate obsidian armour over a cracked glowing lava body, a mask-like face with yellow eyes, and tall red crystal spikes like wings and a crown. Key details: gold-trimmed obsidian shoulder and chest plates, a large red crystal set in the chest, burning claw gauntlets, floating shards of red crystal around it. Colours: obsidian black-grey, lava red and orange, crimson crystal, gold trim. Signature glow: molten red and orange with yellow eyes (lava seams, crystals, claws). Framing: head and chest with the crown of crystals, the red chest gem and yellow eyes glowing. Format: square 1:1 (1024 x 1024). Composition: bust to three-quarter body, head and upper body fill most of the frame, centred, eyes in the upper-middle third. Background: simplified and dark with one soft glow behind the character, no scenery detail. This icon is shown at about 150 pixels wide, so use bold shapes, strong contrast, few details, thick readable outlines and at most 6 to 8 main colours. Style: Chunky high-resolution pixel art in a dark-fantasy forge style: visible square pixels about 4 to 6 real pixels wide, crisp hard edges, no smooth gradients, no anti-aliasing blur, not painterly, not 3D, not photographic. Palette: charcoal and slate metal, copper and bronze trim, cracked stone, riveted plates, with glowing ember-orange light as the shared accent plus the character's own signature glow colour. One strong light source that comes from the character's own glow. Big expressive glowing eyes, a clear silhouette, a little cute and a little fierce. Avoid pure white and pure black. Never: No text, letters, numbers, logos, watermark, signature, speech bubbles, UI, card frame or border. No second character. No humans, no blood.
```

## Battle prompt (`sprite_battle.webp`)

```text
Create the battle sprite of an original game creature. Cindrax is a hovering magma crystal fiend with a pointed segmented lower body, no legs or boots, and dark slate obsidian armour over a cracked glowing lava body, a mask-like face with yellow eyes, and tall red crystal spikes like wings and a crown. Key details: gold-trimmed obsidian shoulder and chest plates, a large red crystal set in the chest, burning claw gauntlets, floating shards of red crystal around it. Colours: obsidian black-grey, lava red and orange, crimson crystal, gold trim. Signature glow: molten red and orange with yellow eyes (lava seams, crystals, claws). Pose: a menacing clawed stance facing right, crystal wings spread behind it. Format: square 1:1 (1024 x 1024). The single full-body figure faces RIGHT (toward the right edge), in side or three-quarter view. Background: flat pure black (#000000) everywhere outside the character, or transparent if you can; no ground, no floor line, no cast shadow, no scenery, no vignette. Glow around the character is fine. Composition: the whole body inside the image with margin, about 90 percent of the image height, feet near the bottom with about 4 percent margin, centred left to right, nothing touching an edge. Important: the darkest colour used on the character itself must be a dark slate, nothing darker than about #2a3342. Do not use pure black or near-black anywhere on the character, not even for outlines, because black pixels are removed in the game. Style: Chunky high-resolution pixel art in a dark-fantasy forge style: visible square pixels about 4 to 6 real pixels wide, crisp hard edges, no smooth gradients, no anti-aliasing blur, not painterly, not 3D, not photographic. Palette: charcoal and slate metal, copper and bronze trim, cracked stone, riveted plates, with glowing ember-orange light as the shared accent plus the character's own signature glow colour. One strong light source that comes from the character's own glow. Big expressive glowing eyes, a clear silhouette, a little cute and a little fierce. Avoid pure white and pure black. Never: No text, letters, numbers, logos, watermark, signature, speech bubbles, UI, card frame or border. No second character. No humans, no blood.
```

## Export size correction (2026-10-12)

Preview exported at 512 x 512 without stretching. Portrait sources use a square crop at the catalog's existing `art.focus_preview`; square sources are downscaled with nearest-neighbour sampling. Main card must be 1536 x 796 and battle 512 x 512. Read `identity.md` and inspect `sprite_preview_card.webp` before further generation.
