# Engraved capture stones

Generated with the built-in ImageGen tool on 2026-10-14. These are shared EMBLEM inventory assets, distinct from Ascended rank crests. Original transparent PNGs are retained here; game exports replace `web/src/assets/emblems/emblem_<tier>.webp`.

## Design

Dark, chipped slate stones hold an Ascended inside a recessed seal. Carvings follow the identifying geometry of each tier logo, with light inside the grooves instead of a solid gem. Higher tiers gain functional binding straps. All six share a front-facing, irregular rock silhouette, visible thickness, transparent margins, and crisp pixel art.

| Tier | Carving | Light | Restraints |
| --- | --- | --- | --- |
| Common | Square seal, four-point star, circular channel, cardinal notches | Ivory | Bare stone |
| Rare | Hexagonal star seal and branching leaf channels | Emerald | One iron strap |
| Unique | Compass cross with curved arc channels | Sapphire | Two iron straps |
| Royal | Crowned oval seal and crown channels | Violet | Two aged bronze straps |
| Legendary | Hexagonal sun and wing channels | Amber | Three bronze straps |
| Forbidden | Pointed diamond void with jagged fissures | Crimson | Heavy dark iron clamps |

## Prompt set

Common used `../tiers/tier_common.webp` as its symbol reference:

> Create the COMMON tier capture EMBLEM asset for the fantasy pixel-art game Ascension. Transform the reference metal rank crest into a completely different object: a palm-sized chunky irregular dark slate river stone, chipped and weathered, front view with slight visible thickness, isolated centered on a genuinely transparent background. Keep ONLY the simplified identifying geometry of the reference engraved deep INTO the stone face: a square central seal with a four-point star, within a simple circular channel, four cardinal notches. These are recessed chisel grooves softly glowing ivory-white, NOT a gemstone or shiny raised metal badge. The center is a deep hollow containment recess, with tiny inward-flow lines suggesting an entity can be absorbed. Mostly dark navy-gray matte rock, sparse cool edge highlights, two subtle weathering cracks. No crown, wings, laurel, external metal frame, pedestal, scene, text, labels, hands, detached particles or cast shadow outside the object. Crisp deliberate chunky pixel art, limited palette, like a hand-drawn 96px RPG inventory sprite enlarged with hard pixels, no photorealism, no blur. Readable silhouette and carving at 28px. Stone fills about 80% of square canvas with generous transparent margins. Stable inactive inventory state, subdued rune glow.

Each remaining tier used `emblem_common.png` as the material/style reference and `../tiers/tier_<tier>.webp` as the symbol reference. Substitute the tier, color and carving/restraint description from the table into this prompt:

> Create the [TIER] tier capture EMBLEM inventory sprite for Ascension. Reference 1 is the approved COMMON capture stone: match its chunky pixel art, worn dark navy-gray matte stone material, mostly round but irregular chipped rock silhouette, front view with visible thickness, centered scale and lighting. Reference 2 is this tier's rank crest: use ONLY its simplified identifying symbol as a deeply recessed chisel engraving in the rock, NOT a raised metallic crest, gemstone or jewelry. For this tier use [CARVING AND RESTRAINTS]. Restrained [COLOR] illumination INSIDE the carving, surrounding rock stays dark slate; glow confined to grooves, no external halo. Main seal is hollow and dark within, able to bind an entity; no solid giant jewel. Make the stone visibly distinct from the rank crest. Mostly rock; higher tier straps are thin functional containment restraints, never an ornate outline frame. Crisp hand-drawn pixel clusters, hard pixel edges like a 96px RPG sprite enlarged, limited palette. Readable at 28px. One object only, completely transparent background, square canvas, stone covers around 80% with safe transparent margin. No text, label, pedestal, hand, environment, detached particles, external drop shadow or photorealism. Stable inactive inventory state.

## Export and playback

Exports use RGBA, nearest-neighbor downsampling to 256 × 256, and lossless WebP. Preserve alpha and the full square canvas. The UI displays the stones at 28–84px with `image-rendering: pixelated`.

`EmCaptureStone.vue` adds the active core, incoming particles, resistance fissures, sealing ring, and two escaping fragments. `battleCues.ts` defines the throw → absorb → three resistance beats → still → caught/open sequence. Outcomes come from the server. Reduced-motion playback retains static glow and split-state cues without particle, shake or flash animations.
