# Ascended art guide (ruleset for ChatGPT)

How to make the three sprites of an Ascended with ChatGPT image generation so every Ascended looks like it
belongs to the same game. Each Ascended has its own `art_prompts.md` (in its folder) with three ready-to-paste
prompts, and an `identity.md` recording its persistent visual identity and reference images. This guide controls
style, sizes and framing; `identity.md` controls the character design. Keep `art_prompts.md` consistent with both.
When a prompt and this guide disagree, this guide wins and the prompt gets fixed.

Where files go: everything for one Ascended lives in `ascended/<id>/` (see `../AGENTS.md`). The finished files are
`sprite_main_card.webp`, `sprite_preview_card.webp` and `sprite_battle.webp` in that folder.

### Identity record (`identity.md`)

- Before creating, recreating or editing any sprite, read this guide, the Ascended's `identity.md` and its
  `art_prompts.md`, then inspect the reference images named in `identity.md`.
- If `identity.md` does not exist, create it in `ascended/<id>/` before generating sprites. For an existing
  Ascended, derive it from the established art and design notes; use the existing preview card as the primary
  reference when recreating other sprites for consistency. For a new Ascended, record the intended design and
  identify its reference image once the design is established.
- Record the defining anatomy, face, proportions, silhouette, colours, signature glow, armour, clothing, weapons
  and distinctive features. Name the primary and supporting reference images and state what must stay consistent
  across poses and framing.
- Update `identity.md` when an intentional redesign or newly established detail makes it incomplete or outdated,
  and update the design notes and prompts in `art_prompts.md` to match. Pose, crop and background changes alone do
  not change the character's identity. Do not rewrite the identity to legitimise accidental generation drift;
  correct the sprite instead.

## 1. The three sprites

| File | Used for | Shape the game shows | Ask ChatGPT for | Deliver as |
|---|---|---|---|---|
| `sprite_main_card.webp` | Art window of the full card (details dialog, starter screen) | Wide, 897 x 464, about 1.93 : 1 | 1536 x 1024 (3 : 2) | crop to 1536 x 796, WebP |
| `sprite_preview_card.webp` | Small card in the collection, shop offers, starter list (about 150 px wide) | Almost square, about 1 : 1 | 1024 x 1024 (1 : 1) | 512 x 512, WebP |
| `sprite_battle.webp` | The fighter in the battle arena (drawn about 230 px tall; the wild one is mirrored by the game) | Free-standing figure | 1024 x 1024 (1 : 1) | 512 x 512, WebP |

The card frame (`ascended_common_front_template.png`, grey metal with a header, stats and three ability slots)
is drawn by the game on top of the art. Never draw a card frame, border or any text in the art.

## 2. Style bible (applies to all three)

- **Medium:** chunky high-resolution pixel art. Visible square pixels about 4 to 6 real pixels wide, hard crisp
  edges, no smooth gradients, no anti-aliasing blur. Not painterly, not 3D, not photographic, not vector.
- **World:** a dark-fantasy forge. Charcoal and slate metal, copper and bronze trim, cracked stone, riveted plates,
  runes, lava glow. The shared accent is ember-orange light. Every Ascended also has one signature glow colour
  (listed in its `art_prompts.md`) that is used for its eyes, gems, flames or core.
- **Character:** armoured or elemental creature, a clear silhouette you can read at 150 px, big expressive glowing
  eyes (a little cute, a little fierce), a glowing gem, core or flame as the focal point. Creatures, constructs and
  spirits; faces are allowed.
- **Light:** one strong light that comes from the character's own glow, lighting nearby metal and stone. The rest is
  dark and moody.
- **Colour discipline:** one dominant colour family per Ascended plus ember orange. Avoid pure white and pure black.
- **Consistency:** the same character design in all three sprites: same colours, same armour, same gems, same
  proportions. Only the framing and pose change.

## 3. Never

No text, letters, numbers, logos, watermarks, signatures, speech bubbles, UI, card frames or borders. No second
character. No ordinary humans. No blood or gore. No cropping of the character by the image edge (except where a rule below
says otherwise). No realistic or 3D rendering.

## 4. Rules per sprite

### 4.1 Main card (`sprite_main_card.webp`)
- Landscape 3 : 2. The game shows a 1.93 : 1 band, so keep everything important inside the middle 66 percent of the
  height. The top 17 percent and bottom 17 percent are plain background only; they are cut off.
- Whole character visible, centred, filling about 85 percent of that middle band. A little overlap with the side
  background is fine; limbs and weapons must not touch the left or right edge.
- Scene background: a dark ruined forge or dungeon with distant lava glow, soft and darker toward the edges so the
  character stands out. The background must not be brighter than the character.
- Pose: the character's best "hero" pose (see its prompt).

### 4.2 Preview card (`sprite_preview_card.webp`)
- Square. Shown at about 150 px wide, so design for tiny sizes: bold shapes, strong contrast, few details, at most
  6 to 8 main colours, thick readable outlines.
- Bust to three-quarter body. Head and upper body fill most of the frame, centred, eyes in the upper-middle third.
- Simplified background: dark, with one soft glow behind the character. No scenery detail.
- Test: shrink it to 150 px. If you cannot tell who it is at a glance, make the shapes bigger and the details fewer.

### 4.3 Battle (`sprite_battle.webp`)
- Square, single full-body figure facing RIGHT (toward the right edge), side or three-quarter view, in a
  battle-ready pose. The game mirrors it for the wild side, so it faces left there. Do not make a second, left-facing
  version.
- No background: a flat pure black (#000000) background, or a transparent one if ChatGPT can produce it. No ground,
  no floor line, no cast shadow, no scenery, no vignette. Glow around the character is fine.
- The game blends the sprite with a "lighten" effect, which makes very dark pixels disappear into the dark arena.
  So the darkest colour on the character itself must be a dark slate (nothing darker than about #2a3342). Never use
  pure black inside the character, not even for outlines.
- Whole body inside the image with margin: about 90 percent of the image height, feet near the bottom with about 4
  percent margin, centred left to right. Nothing touches an edge.

## 5. Working with ChatGPT

Before step 1, read or create the Ascended's `identity.md` as described above. Use its character details and
reference priority for every generation prompt, including additional sprites beyond the three standard files.

1. Start a new chat per Ascended. Paste the main prompt from its `art_prompts.md` first. Iterate until the character
   is right. This is the reference for the other two.
2. In the same chat, ask for the preview and the battle sprite with the other two prompts. Start each with: "Use the
   character in the previous image as the exact reference: same design, colours, armour and proportions."
3. For an Ascended that already has art, upload the primary reference specified in `identity.md` in the first
   message and say "redraw this exact character in the new format, keep the design". When recreating the main card
   or battle sprite from an established preview, use `sprite_preview_card.webp` as that reference.
4. ChatGPT cannot make every size. It makes 1536 x 1024, 1024 x 1024 or 1024 x 1536. Ask for the nearest and crop
   afterwards (section 6).
5. Fix-up lines that work, one at a time:
   - "Remove all text and letters."
   - "Make the pixels chunkier and the shapes simpler."
   - "Shrink the character so nothing touches the edge."
   - "Replace the background with flat pure black."
   - "Make the eyes and gem glow stronger."
   - "Keep everything else exactly the same."
6. Generate two or three options and pick the one that reads best small.

## 6. After ChatGPT: crop, resize, convert

Save ChatGPT's PNGs next to the target, then (ImageMagick, `magick`):

```bash
# main card: centre crop to the 1.93 : 1 band, then WebP
magick main.png -gravity center -crop 1536x796+0+0 +repage -quality 92 sprite_main_card.webp
# preview: square, 512
magick preview.png -resize 512x512 -quality 92 sprite_preview_card.webp
# battle: square, 512, lossless so the edges stay crisp
magick battle.png -resize 512x512 -define webp:lossless=true sprite_battle.webp
```

Do not upscale a small image. If the main card image is not 1536 wide, crop to its own width divided by 1.93.

Then run the layout test: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_ascended_layout.py`.
Rebuild is not needed: the game serves the files from this folder, and a reload shows the new art. If a crop looks
off, tune `art.focus` (main card) and `art.focus_preview` (preview) in the Ascended's `catalog.json`, 0 to 100,
default 50.

## 7. Delivery checklist

- [ ] Same character in all three sprites.
- [ ] `identity.md` exists in the Ascended's folder, was read before generation, and matches the established
      character and reference images; update it and `art_prompts.md` if necessary.
- [ ] No text, frame, border, watermark.
- [ ] Main card: whole character inside the middle band, readable after the 1.93 : 1 crop.
- [ ] Preview: recognisable at 150 px.
- [ ] Battle: faces right, flat black or transparent background, no ground, nothing darker than dark slate on the
      character, nothing touching the edges.
- [ ] Files named exactly `sprite_main_card.webp`, `sprite_preview_card.webp`, `sprite_battle.webp`, in the
      Ascended's own folder.
- [ ] Looked at in the game (collection, details, battle) after a reload.

## 8. A new Ascended

1. Make `ascended/<id>/` with its `catalog.json` (see the other Ascended).
2. Create `identity.md` with the intended visual identity, defining features and consistency rules. After the
   character design is established, record the primary reference image and refine the identity details.
3. Copy another Ascended's `art_prompts.md`, then rewrite its "Design" section (concept, colours, signature glow,
   details, poses). Keep the three prompts' structure: they are built from sections 2 to 4 of this guide.
4. Make the three sprites using `identity.md`, update it and the prompts when necessary, check section 7, and add
   the entry to the prompts file's "Status" line.

## 9. Animation sheet (optional, `spreadsheet_animation.webp` + `animations.json`)

`animations.json` is the source of truth: the grid, each state's row, frame count, frame time and loop. The game reads it.
These rules cover what the JSON cannot say.

- Lossless WebP atlas with alpha. Every cell has the same size (Twoychi: 320 x 320, 4 columns x 6 rows) with transparent padding.
- Rows, top to bottom, are the states in `animations.json` (Twoychi: idle, attack, defend, support, flee, catch). Frames play left to right.
  Idle and flee loop; the other rows play once, then return to idle.
- Draw every frame on the same anchor, measured from the cell's top-left (Twoychi: 160, 296). Mirror the whole cell
  horizontally for left-facing opponents, and mirror the anchor too.
- Scale with nearest-neighbour only, to keep the pixel edges. Repack generated rows into equal cells without rescaling the art.
- The sheet is generated frame art with small pose variation, not a rigged animation. Review it at battle scale.
- `sprite_battle.webp` stays as the fallback and the reference art. The arena plays the sheet
  (`web/src/components/ui/AnimatedSprite.vue`).
- Twoychi's catch row is a catching action: Aya receives a water orb and draws it into her hands. It does not show Twoychi being captured.
