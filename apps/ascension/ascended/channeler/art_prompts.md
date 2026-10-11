# Channeler: art prompts

Rules: `../ART_GUIDE.md` (read it first; it explains sizes, the black background and the crop steps).
Files for this Ascended: `sprite_main_card.webp`, `sprite_preview_card.webp`, `sprite_battle.webp` (this folder).
Status: main card and battle sprite recreated from the established preview using the built-in image generator. Preview retained as the primary reference; its legacy portrait dimensions are unchanged. See `identity.md` for persistent design. In-game visual check remains pending.

## Design (the visual canon, keep it the same in all three sprites)

- **Role:** Support. The passive makes support effects last longer, so the design says spirit, focus, magic.
- **Concept:** a floating brass-and-iron lantern with a glass belly holding a cyan ghost flame spirit that has a small smiling face.
- **Key details:** golden rings orbiting the lantern, a pointed iron cap with a small diamond ornament, a crystal pendant hanging below, and two floating bronze gauntlet hands with cyan flames burning above them.
- **Palette:** brass and gold, dark iron, cyan, ice blue.
- **Signature glow:** cyan and ice blue (the ghost flame, hand flames, crystal, sparks).
- **Main card pose:** floating in the centre, both gauntlet hands open at its sides with cyan flames, rings orbiting, small sparks around.
- **Preview framing:** the lantern body with the smiling flame spirit, rings around it, hands as small shapes at the sides.
- **Battle pose:** hovering with the hands raised toward the right as if casting, the rings tilted.

## How to run it

1. Read `identity.md`, then upload the established `sprite_preview_card.webp` in the first message and add: "Redraw this exact character in the new format and keep the design."
2. Paste the main card prompt. Keep the complete figure, rings, flames and pendant inside y=230..800 on a 1536 x 1024 canvas; iterate until the design and crop are right.
3. Keep the existing preview when recreating the other sprites. Use it directly as the reference for the battle prompt, each starting with: "Use the character in the previous image as the exact reference: same design, colours, armour and proportions. "
4. Crop and convert with the commands in `../ART_GUIDE.md` section 6, check the checklist in section 7.

## Main card prompt (`sprite_main_card.webp`)

```text
Create the card illustration of an original game creature. Channeler is a floating brass-and-iron lantern with a glass belly holding a cyan ghost flame spirit that has a small smiling face. Key details: golden rings orbiting the lantern, a pointed iron cap with a small diamond ornament, a crystal pendant hanging below, and two floating bronze gauntlet hands with cyan flames burning above them. Colours: brass and gold, dark iron, cyan, ice blue. Signature glow: cyan and ice blue (the ghost flame, hand flames, crystal, sparks). Pose: floating in the centre, both gauntlet hands open at its sides with cyan flames, rings orbiting, small sparks around. Format: landscape 3:2 (1536 x 1024). Composition: the whole character visible and centred, filling about 85 percent of the height of the middle band, where the middle band is the middle 66 percent of the image height. Keep the top 17 percent and the bottom 17 percent as plain background only, with nothing important there, because the picture will be cropped to a wide 1.93:1 strip. No limb, weapon or effect touches the left or right edge. Background: a dark ruined forge or dungeon with distant lava glow, soft and darker toward the edges so the character stands out, never brighter than the character. Style: Chunky high-resolution pixel art in a dark-fantasy forge style: visible square pixels about 4 to 6 real pixels wide, crisp hard edges, no smooth gradients, no anti-aliasing blur, not painterly, not 3D, not photographic. Palette: charcoal and slate metal, copper and bronze trim, cracked stone, riveted plates, with glowing ember-orange light as the shared accent plus the character's own signature glow colour. One strong light source that comes from the character's own glow. Big expressive glowing eyes, a clear silhouette, a little cute and a little fierce. Avoid pure white and pure black. Never: No text, letters, numbers, logos, watermark, signature, speech bubbles, UI, card frame or border. No second character. No humans, no blood.
```

## Preview card prompt (`sprite_preview_card.webp`)

```text
Create a small square portrait icon of an original game creature. Channeler is a floating brass-and-iron lantern with a glass belly holding a cyan ghost flame spirit that has a small smiling face. Key details: golden rings orbiting the lantern, a pointed iron cap with a small diamond ornament, a crystal pendant hanging below, and two floating bronze gauntlet hands with cyan flames burning above them. Colours: brass and gold, dark iron, cyan, ice blue. Signature glow: cyan and ice blue (the ghost flame, hand flames, crystal, sparks). Framing: the lantern body with the smiling flame spirit, rings around it, hands as small shapes at the sides. Format: square 1:1 (1024 x 1024). Composition: bust to three-quarter body, head and upper body fill most of the frame, centred, eyes in the upper-middle third. Background: simplified and dark with one soft glow behind the character, no scenery detail. This icon is shown at about 150 pixels wide, so use bold shapes, strong contrast, few details, thick readable outlines and at most 6 to 8 main colours. Style: Chunky high-resolution pixel art in a dark-fantasy forge style: visible square pixels about 4 to 6 real pixels wide, crisp hard edges, no smooth gradients, no anti-aliasing blur, not painterly, not 3D, not photographic. Palette: charcoal and slate metal, copper and bronze trim, cracked stone, riveted plates, with glowing ember-orange light as the shared accent plus the character's own signature glow colour. One strong light source that comes from the character's own glow. Big expressive glowing eyes, a clear silhouette, a little cute and a little fierce. Avoid pure white and pure black. Never: No text, letters, numbers, logos, watermark, signature, speech bubbles, UI, card frame or border. No second character. No humans, no blood.
```

## Battle prompt (`sprite_battle.webp`)

```text
Create the battle sprite of an original game creature. Channeler is a floating brass-and-iron lantern with a glass belly holding a cyan ghost flame spirit that has a small smiling face. Key details: golden rings orbiting the lantern, a pointed iron cap with a small diamond ornament, a crystal pendant hanging below, and two floating bronze gauntlet hands with cyan flames burning above them. Colours: brass and gold, dark iron, cyan, ice blue. Signature glow: cyan and ice blue (the ghost flame, hand flames, crystal, sparks). Pose: hovering with the hands raised toward the right as if casting, the rings tilted. Format: square 1:1 (1024 x 1024). The single full-body figure faces RIGHT (toward the right edge), in side or three-quarter view. Background: flat pure black (#000000) everywhere outside the character, or transparent if you can; no ground, no floor line, no cast shadow, no scenery, no vignette. Glow around the character is fine. Composition: the whole body inside the image with margin, about 90 percent of the image height, feet near the bottom with about 4 percent margin, centred left to right, nothing touching an edge. Important: the darkest colour used on the character itself must be a dark slate, nothing darker than about #2a3342. Do not use pure black or near-black anywhere on the character, not even for outlines, because black pixels are removed in the game. Style: Chunky high-resolution pixel art in a dark-fantasy forge style: visible square pixels about 4 to 6 real pixels wide, crisp hard edges, no smooth gradients, no anti-aliasing blur, not painterly, not 3D, not photographic. Palette: charcoal and slate metal, copper and bronze trim, cracked stone, riveted plates, with glowing ember-orange light as the shared accent plus the character's own signature glow colour. One strong light source that comes from the character's own glow. Big expressive glowing eyes, a clear silhouette, a little cute and a little fierce. Avoid pure white and pure black. Never: No text, letters, numbers, logos, watermark, signature, speech bubbles, UI, card frame or border. No second character. No humans, no blood.
```

## Recreation notes

- Generated with the built-in image tool using the established preview as the character reference.
- Main framing correction: shrink the complete character to fit y=230..800 on a 1536 x 1024 canvas; preserve all design details and fill surrounding space with matching dim forge. Centre crop to 1536 x 796.
- Battle final: right-facing three-quarter casting pose, pure-black background, slate outlines, no floor or shadow. Resize with nearest-neighbour filtering and add black margins for a 512 x 512 lossless WebP. Transparency draft discarded because it contained coloured artifacts.
- Source PNGs: `main.png` and `battle.png`. Preview remains untouched.
