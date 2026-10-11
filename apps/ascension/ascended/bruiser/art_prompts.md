# Bruiser: art prompts

Rules: `../ART_GUIDE.md` (read it first; it explains sizes, the black background and the crop steps).
Files for this Ascended: `sprite_main_card.webp`, `sprite_preview_card.webp`, `sprite_battle.webp` (this folder).
Status: main, preview and battle generated using the built-in imagegen tool. Sources: `main.png`, `preview.png`, `battle.png`; final game assets are the three WebP files above. Character identity and reference priority: `identity.md`.

## Design (the visual canon, keep it the same in all three sprites)

- **Role:** Heavy attacker: the passive adds attack damage against a defending target, so the design says brute force that breaks guards.
- **Concept:** a hulking, hunched basalt brute with a tusked boar-like head, small furious amber eyes, and cracked dark-brown hide with glowing molten seams.
- **Key details:** oversized fists wrapped in rusted iron bands, one big spiked iron pauldron, heavy bone-white tusks, a glowing cracked belly plate, and embers rising from its shoulders.
- **Palette:** dark basalt brown-grey, rust orange, iron, bone white, molten amber.
- **Signature glow:** molten amber and yellow-orange (seams in its hide, eyes, ember sparks).
- **Main card pose:** rearing up with both fists raised overhead ready to smash down, tusks bared, looking at the viewer.
- **Preview framing:** the head and the massive shoulders and one fist, tusks and glowing eyes in front.
- **Battle pose:** a heavy wind-up facing right, one fist drawn back, the other held low.
- **Established reference details:** jagged basalt forehead crest, pointed warm brown ears, reddish blunt snout with two nostrils, upward-curving warm ivory tusks, three chunky toe claws, round rock-plated amber belly core. The single pauldron is on the anatomical left shoulder (viewer right in the frontal reference), with slate spikes, rust-orange edging and rivets. Read `identity.md` before every generation.

## How to run it

1. Read `identity.md` and inspect `sprite_preview_card.webp`, the primary reference for future recreations. Use `main.png` as the supporting full-body reference. Preserve the single pauldron's anatomical shoulder across poses.
2. Paste the main card prompt. Iterate until the design is right.
3. In the same chat paste the preview prompt, then the battle prompt, each starting with: "Use the character in the previous image as the exact reference: same design, colours, armour and proportions. "
4. Crop and convert with the commands in `../ART_GUIDE.md` section 6, check the checklist in section 7.

## Generation refinements used

- Main framing: the first option was too tall. The selected main keeps the exact design and raised-fists pose, shrinking the whole character into the central safe band with background above and below.
- Preview: reference `main.png`; close portrait with one cuffed fist, matching crest, snout, tusks, single pauldron and core; simplified dark amber halo.
- Battle: reference `main.png`; full-body right-facing wind-up, transparent alpha. Targeted edits lightened internal shading and contours to slate, using #3b4658 as the final requested darkest palette entry; removed detached sparks while keeping the design and pose.
- Final conversion: centre-crop main to its own width / 1.93; resize preview and battle to 512 square using nearest-neighbour sampling for crisp pixel edges; WebP quality 92 for cards, lossless WebP with alpha for battle.
- Validation: main is 1536 x 796, preview and battle are 512 x 512; battle alpha preserved. The preview was inspected at 150 x 150 (`preview_150.png`). Layout tests pass. In-game collection, details and battle inspection remains pending.

## Main card prompt (`sprite_main_card.webp`)

```text
Create the card illustration of an original game creature. Bruiser is a hulking, hunched basalt brute with a tusked boar-like head, small furious amber eyes, and cracked dark-brown hide with glowing molten seams. Key details: oversized fists wrapped in rusted iron bands, one big spiked iron pauldron, heavy bone-white tusks, a glowing cracked belly plate, and embers rising from its shoulders. Colours: dark basalt brown-grey, rust orange, iron, bone white, molten amber. Signature glow: molten amber and yellow-orange (seams in its hide, eyes, ember sparks). Pose: rearing up with both fists raised overhead ready to smash down, tusks bared, looking at the viewer. Format: landscape 3:2 (1536 x 1024). Composition: the whole character visible and centred, filling about 85 percent of the height of the middle band, where the middle band is the middle 66 percent of the image height. Keep the top 17 percent and the bottom 17 percent as plain background only, with nothing important there, because the picture will be cropped to a wide 1.93:1 strip. No limb, weapon or effect touches the left or right edge. Background: a dark ruined forge or dungeon with distant lava glow, soft and darker toward the edges so the character stands out, never brighter than the character. Style: Chunky high-resolution pixel art in a dark-fantasy forge style: visible square pixels about 4 to 6 real pixels wide, crisp hard edges, no smooth gradients, no anti-aliasing blur, not painterly, not 3D, not photographic. Palette: charcoal and slate metal, copper and bronze trim, cracked stone, riveted plates, with glowing ember-orange light as the shared accent plus the character's own signature glow colour. One strong light source that comes from the character's own glow. Big expressive glowing eyes, a clear silhouette, a little cute and a little fierce. Avoid pure white and pure black. Never: No text, letters, numbers, logos, watermark, signature, speech bubbles, UI, card frame or border. No second character. No humans, no blood.
```

## Preview card prompt (`sprite_preview_card.webp`)

```text
Create a small square portrait icon of an original game creature. Bruiser is a hulking, hunched basalt brute with a tusked boar-like head, small furious amber eyes, and cracked dark-brown hide with glowing molten seams. Key details: oversized fists wrapped in rusted iron bands, one big spiked iron pauldron, heavy bone-white tusks, a glowing cracked belly plate, and embers rising from its shoulders. Colours: dark basalt brown-grey, rust orange, iron, bone white, molten amber. Signature glow: molten amber and yellow-orange (seams in its hide, eyes, ember sparks). Framing: the head and the massive shoulders and one fist, tusks and glowing eyes in front. Format: square 1:1 (1024 x 1024). Composition: bust to three-quarter body, head and upper body fill most of the frame, centred, eyes in the upper-middle third. Background: simplified and dark with one soft glow behind the character, no scenery detail. This icon is shown at about 150 pixels wide, so use bold shapes, strong contrast, few details, thick readable outlines and at most 6 to 8 main colours. Style: Chunky high-resolution pixel art in a dark-fantasy forge style: visible square pixels about 4 to 6 real pixels wide, crisp hard edges, no smooth gradients, no anti-aliasing blur, not painterly, not 3D, not photographic. Palette: charcoal and slate metal, copper and bronze trim, cracked stone, riveted plates, with glowing ember-orange light as the shared accent plus the character's own signature glow colour. One strong light source that comes from the character's own glow. Big expressive glowing eyes, a clear silhouette, a little cute and a little fierce. Avoid pure white and pure black. Never: No text, letters, numbers, logos, watermark, signature, speech bubbles, UI, card frame or border. No second character. No humans, no blood.
```

## Battle prompt (`sprite_battle.webp`)

```text
Create the battle sprite of an original game creature. Bruiser is a hulking, hunched basalt brute with a tusked boar-like head, small furious amber eyes, and cracked dark-brown hide with glowing molten seams. Key details: oversized fists wrapped in rusted iron bands, one big spiked iron pauldron, heavy bone-white tusks, a glowing cracked belly plate, and embers rising from its shoulders. Colours: dark basalt brown-grey, rust orange, iron, bone white, molten amber. Signature glow: molten amber and yellow-orange (seams in its hide, eyes, ember sparks). Pose: a heavy wind-up facing right, one fist drawn back, the other held low. Format: square 1:1 (1024 x 1024). The single full-body figure faces RIGHT (toward the right edge), in side or three-quarter view. Background: flat pure black (#000000) everywhere outside the character, or transparent if you can; no ground, no floor line, no cast shadow, no scenery, no vignette. Glow around the character is fine. Composition: the whole body inside the image with margin, about 90 percent of the image height, feet near the bottom with about 4 percent margin, centred left to right, nothing touching an edge. Important: the darkest colour used on the character itself must be a dark slate, nothing darker than about #2a3342. Do not use pure black or near-black anywhere on the character, not even for outlines, because black pixels are removed in the game. Style: Chunky high-resolution pixel art in a dark-fantasy forge style: visible square pixels about 4 to 6 real pixels wide, crisp hard edges, no smooth gradients, no anti-aliasing blur, not painterly, not 3D, not photographic. Palette: charcoal and slate metal, copper and bronze trim, cracked stone, riveted plates, with glowing ember-orange light as the shared accent plus the character's own signature glow colour. One strong light source that comes from the character's own glow. Big expressive glowing eyes, a clear silhouette, a little cute and a little fierce. Avoid pure white and pure black. Never: No text, letters, numbers, logos, watermark, signature, speech bubbles, UI, card frame or border. No second character. No humans, no blood.
```
