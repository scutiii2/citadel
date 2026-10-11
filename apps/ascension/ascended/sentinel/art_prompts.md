# Sentinel: art prompts

Rules: `../ART_GUIDE.md` (read it first; it explains sizes, the black background and the crop steps).
Files for this Ascended: `sprite_main_card.webp`, `sprite_preview_card.webp`, `sprite_battle.webp` (this folder).
Current art: the six existing sprites are copies of the first portrait, so all three need to be redrawn to the new rules.

## Design (the visual canon, keep it the same in all three sprites)

- **Role:** Defender. The passive raises its defense rating, so the design says watchful, ancient, unmovable.
- **Concept:** an armoured owl knight with a dark cracked-stone body, violet glowing eyes, tall feather tufts like horns and a dark purple feather mantle.
- **Key details:** gilded gold-trimmed plate armour, a large violet gem on the chest, small violet gems on the gauntlets and belt, a tall dark shield with a glowing violet gem and gold spikes, a sword hilt at its side.
- **Palette:** charcoal and dark grey stone, dark purple feathers, gold trim, violet gems.
- **Signature glow:** violet purple (eyes, gems, shield gem).
- **Main card pose:** standing tall and upright, the large shield held in front on the right, staring at the viewer, wings folded into the mantle.
- **Preview framing:** head and chest with the chest gem, the shield edge on the right, violet eyes glowing.
- **Battle pose:** an upright guard stance facing right, shield forward, mantle hanging behind.

## How to run it

1. Upload the current `sprite_main_card.webp` in the first message and add: "Redraw this exact character in the new format and keep the design."
2. Paste the main card prompt. Iterate until the design is right.
3. In the same chat paste the preview prompt, then the battle prompt, each starting with: "Use the character in the previous image as the exact reference: same design, colours, armour and proportions. "
4. Crop and convert with the commands in `../ART_GUIDE.md` section 6, check the checklist in section 7.

## Main card prompt (`sprite_main_card.webp`)

```text
Create the card illustration of an original game creature. Sentinel is an armoured owl knight with a dark cracked-stone body, violet glowing eyes, tall feather tufts like horns and a dark purple feather mantle. Key details: gilded gold-trimmed plate armour, a large violet gem on the chest, small violet gems on the gauntlets and belt, a tall dark shield with a glowing violet gem and gold spikes, a sword hilt at its side. Colours: charcoal and dark grey stone, dark purple feathers, gold trim, violet gems. Signature glow: violet purple (eyes, gems, shield gem). Pose: standing tall and upright, the large shield held in front on the right, staring at the viewer, wings folded into the mantle. Format: landscape 3:2 (1536 x 1024). Composition: the whole character visible and centred, filling about 85 percent of the height of the middle band, where the middle band is the middle 66 percent of the image height. Keep the top 17 percent and the bottom 17 percent as plain background only, with nothing important there, because the picture will be cropped to a wide 1.93:1 strip. No limb, weapon or effect touches the left or right edge. Background: a dark ruined forge or dungeon with distant lava glow, soft and darker toward the edges so the character stands out, never brighter than the character. Style: Chunky high-resolution pixel art in a dark-fantasy forge style: visible square pixels about 4 to 6 real pixels wide, crisp hard edges, no smooth gradients, no anti-aliasing blur, not painterly, not 3D, not photographic. Palette: charcoal and slate metal, copper and bronze trim, cracked stone, riveted plates, with glowing ember-orange light as the shared accent plus the character's own signature glow colour. One strong light source that comes from the character's own glow. Big expressive glowing eyes, a clear silhouette, a little cute and a little fierce. Avoid pure white and pure black. Never: No text, letters, numbers, logos, watermark, signature, speech bubbles, UI, card frame or border. No second character. No humans, no blood.
```

## Preview card prompt (`sprite_preview_card.webp`)

```text
Create a small square portrait icon of an original game creature. Sentinel is an armoured owl knight with a dark cracked-stone body, violet glowing eyes, tall feather tufts like horns and a dark purple feather mantle. Key details: gilded gold-trimmed plate armour, a large violet gem on the chest, small violet gems on the gauntlets and belt, a tall dark shield with a glowing violet gem and gold spikes, a sword hilt at its side. Colours: charcoal and dark grey stone, dark purple feathers, gold trim, violet gems. Signature glow: violet purple (eyes, gems, shield gem). Framing: head and chest with the chest gem, the shield edge on the right, violet eyes glowing. Format: square 1:1 (1024 x 1024). Composition: bust to three-quarter body, head and upper body fill most of the frame, centred, eyes in the upper-middle third. Background: simplified and dark with one soft glow behind the character, no scenery detail. This icon is shown at about 150 pixels wide, so use bold shapes, strong contrast, few details, thick readable outlines and at most 6 to 8 main colours. Style: Chunky high-resolution pixel art in a dark-fantasy forge style: visible square pixels about 4 to 6 real pixels wide, crisp hard edges, no smooth gradients, no anti-aliasing blur, not painterly, not 3D, not photographic. Palette: charcoal and slate metal, copper and bronze trim, cracked stone, riveted plates, with glowing ember-orange light as the shared accent plus the character's own signature glow colour. One strong light source that comes from the character's own glow. Big expressive glowing eyes, a clear silhouette, a little cute and a little fierce. Avoid pure white and pure black. Never: No text, letters, numbers, logos, watermark, signature, speech bubbles, UI, card frame or border. No second character. No humans, no blood.
```

## Battle prompt (`sprite_battle.webp`)

```text
Create the battle sprite of an original game creature. Sentinel is an armoured owl knight with a dark cracked-stone body, violet glowing eyes, tall feather tufts like horns and a dark purple feather mantle. Key details: gilded gold-trimmed plate armour, a large violet gem on the chest, small violet gems on the gauntlets and belt, a tall dark shield with a glowing violet gem and gold spikes, a sword hilt at its side. Colours: charcoal and dark grey stone, dark purple feathers, gold trim, violet gems. Signature glow: violet purple (eyes, gems, shield gem). Pose: an upright guard stance facing right, shield forward, mantle hanging behind. Format: square 1:1 (1024 x 1024). The single full-body figure faces RIGHT (toward the right edge), in side or three-quarter view. Background: flat pure black (#000000) everywhere outside the character, or transparent if you can; no ground, no floor line, no cast shadow, no scenery, no vignette. Glow around the character is fine. Composition: the whole body inside the image with margin, about 90 percent of the image height, feet near the bottom with about 4 percent margin, centred left to right, nothing touching an edge. Important: the darkest colour used on the character itself must be a dark slate, nothing darker than about #2a3342. Do not use pure black or near-black anywhere on the character, not even for outlines, because black pixels are removed in the game. Style: Chunky high-resolution pixel art in a dark-fantasy forge style: visible square pixels about 4 to 6 real pixels wide, crisp hard edges, no smooth gradients, no anti-aliasing blur, not painterly, not 3D, not photographic. Palette: charcoal and slate metal, copper and bronze trim, cracked stone, riveted plates, with glowing ember-orange light as the shared accent plus the character's own signature glow colour. One strong light source that comes from the character's own glow. Big expressive glowing eyes, a clear silhouette, a little cute and a little fierce. Avoid pure white and pure black. Never: No text, letters, numbers, logos, watermark, signature, speech bubbles, UI, card frame or border. No second character. No humans, no blood.
```
