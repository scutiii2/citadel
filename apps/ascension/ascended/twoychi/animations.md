# Twoychi animation sheet

Generated with the built-in image generation tool. Reference: sprite_battle.webp (primary) and sprite_preview_card.webp (supporting).

Files:
- spreadsheet_animation.webp: 1280 x 1920 lossless atlas with alpha, 4 columns x 6 rows of 320 x 320 frames.
- animations.json: the grid and each state's row, frame count, frame time and loop. The game reads it.

Rows top to bottom: idle, attack, defend, support, flee, catch. Frames play left to right. Idle and flee loop; other rows play once, then return to idle. Catch is a catching action: Aya receives a water orb, then draws it into her hands. It does not depict Twoychi being captured.

Each cell is 320 x 320 with transparent padding. Anchor is (160,296), measured from the cell top-left. Draw all frames at the same anchor. Mirror the entire cell horizontally for left-facing opponents; mirror the anchor too. Use nearest-neighbour scaling to preserve pixel edges.

The source had uneven row spacing; extraction and padding repacked all 24 frames into equal cells without rescaling the artwork. This is generated frame artwork with small pose/design variation. Review the preview at battle scale when integrating; it is not a rigged animation.

The battle arena plays the sheet (`web/src/components/ui/AnimatedSprite.vue`); `sprite_battle.webp` stays as the fallback and the reference art.

## Generation prompt

Create a production sprite animation sheet for Twoychi, using the first attached battle sprite as the main design reference and the second as supporting colours only. REAL transparent alpha background.

OUTPUT EXACT GRID: 1536 wide x 2304 high, portrait 2:3. FOUR columns, SIX rows, TWENTY FOUR equal square cells, each 384x384. No headers, labels, grid lines, borders, gutters or extra frames. Every cell contains the COMPLETE SAME full-body character group, rendered at exactly the same scale and anchored at the same point: feet baseline y=355 within each cell, group centre x=190. All sprites and water effects stay inside their own cell with 20px safe transparent padding. Never overlap adjacent cells. Camera fixed; no perspective or scale changes. Sheet must be usable by slicing a uniform 4x6 grid. Repeated character appearance identical across all 24 cells.

DESIGN: Twoychi is one partnered creature with Aya and Troy, BOTH always visible in EVERY cell. Calm kind human-looking young adult Aya with loose dark brown hair, pale cyan-grey eyes, OFF-WHITE tunic and royal BLUE panels/trim/sash/trousers, visibly mended sleeve, simple boots. Behind her the SAME larger half-transparent cyan-white female water spirit, same pale face, drifting cyan-white hair, glass-translucent glowing palms; spirit mirrors each action, never hides Aya. Beside Aya's feet the SAME small sturdy long-coated SHIH TZU dog Troy, off-white and DARK SLATE black-patch coat, white blaze, dark mask/ears, short FLAT muzzle, round eyes, dark nose, white plume tail curled over back. No wolf or bear forms. All face RIGHT in side/three-quarter view.

ANIMATION rows in EXACT order from top to bottom, four chronological frames left to right:
ROW 1 IDLE, looping: neutral ready hands and calm dog; slight inhale/raised chest and water orb rises; exhale/orb descends and dog blink; return nearly to first pose. Very subtle hair/sash/water drift.
ROW 2 ATTACK: windup pulling low orb back; forward hand accelerates toward right; full rightward extension releases distinct thin cyan-white water crescent, Troy lunges a little right; recoil to ready stance. No massive water wall.
ROW 3 DEFEND: hands raise; a curved cyan water shield forms on RIGHT in front of Aya and dog; shield peaks thicker, Aya braced and Troy crouches; shield subsides, recover.
ROW 4 SUPPORT: hands cup small orb at waist; orb rises between palms; gentle cyan water droplets float toward right and restorative glow encircles Troy; hands lower and glow subsides. Water-based support, no crosses/hearts/text.
ROW 5 FLEE, looping run cycle facing RIGHT: Aya leans forward, Troy starts trotting; rightward run stride A, sash/hair trail left; opposite run stride B with dog airborne stride; returning stride toward first. Keep group fixed inside cell; game moves whole group, do not translate across sheet. Spirit trails behind Aya.
ROW 6 CATCH = PERFORM CATCHING action, not being captured: hands reach OPEN toward incoming small water orb on RIGHT; hands receive orb; palms close gently around orb drawing it to chest; lower caught orb safely. Troy tracks orb with eyes and small head movement. Do NOT cage, dissolve or capture Twoychi.

STYLE: chunky high resolution PIXEL ART, visible crisp square pixel clusters 4–6 pixels, sharp stepped silhouettes, simplified bold readable forms, limited discrete colour bands. Not painterly, photo, 3D or smooth vector. No blur/antialiasing/smooth gradients. Each cell's character group should occupy about 85% cell height including spirit, with whole spirit hair, Aya boots and Troy paws visible. Water glow lights characters, no other lighting. All character colours including dark fur, eyes, nose, hair shadows and outlines no darker than #2a3342; use slate instead of black and off-white instead of pure white.
BACKGROUND: fully transparent alpha, no ground, no shadows, no floor, scenery, vignette, background glow panel or checkerboard painted in. No text, letters, numbers, logos, watermark, signatures, labels, frame or UI. No additional characters.
Most important: exact FOUR BY SIX uniform grid, visibly different chronological poses within each row, consistent character design and anchored feet, all 24 cells filled.

## Background correction

Remove all blue-grey background between sprites to real alpha transparency, preserving the 4 x 6 action grid. Final PNG alpha was checked from decoded pixels. Repacked cell padding is fully transparent.

