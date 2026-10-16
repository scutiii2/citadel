# Mini game wallpaper prompt

Reusable prompt for generating the card wallpaper of any mini game in Ember's Games page.
Fill in the three `{{...}}` slots, paste the whole block into your image generator.

## Prompt

```
Create a wallpaper-style key art image for a video game called "{{GAME NAME}}".

Game: {{ONE SENTENCE: genre, setting, what the player does}}
Mood and palette: {{e.g. dark fantasy, deep indigo and warm gold}}
Main subject: {{the single focal element, e.g. a lone tower above clouds}}

Technical requirements:
- Aspect ratio exactly 16:10, 1280 x 800 pixels (landscape).
- Composition: place the main subject in the upper-middle of the frame, horizontally
  centered or slightly off-center. Keep the bottom 35% of the image visually calm
  and darker (sky, ground, fog or empty space); a title bar will cover it.
- Keep the top-left and top-right corners (about 20% width, 15% height each) free
  of important detail; a version chip and a Play button sit there.
- No text, no logos, no watermarks, no UI elements, no borders, no frame.
- Flat or painterly illustration, strong silhouette, high contrast, readable when
  shrunk to 300 x 188 pixels.
- Subject must survive a center crop: nothing important within 6% of any edge.
```

## Output spec (what Ember needs)

| Item | Value |
|---|---|
| Aspect ratio | 16:10 (the card crops with `object-fit: cover`) |
| Master size | 1280 x 800 px |
| Card display size | up to 300 x 188 px, so 600 x 375 px is already sharp on 2x screens |
| Format | `.webp` (or `.png` / `.jpg`; `.svg` also works) |
| File size | under 200 KB |
| Safe zone | subject in the upper 65%, away from the edges |

Export a smaller copy if the generator gives a larger image:

```bash
magick wallpaper.png -resize 1280x800^ -gravity center -extent 1280x800 -quality 82 wallpaper.webp
```

## Where it goes

1. Save the file in the game's own served assets folder, for example
   `apps/ascension/web/public/assets/wallpaper.webp`. The game must serve it publicly
   (Ascension serves everything under `/assets/*`).
2. Point the game's `manifest.json` at it, relative to the game URL:
   `"wallpaper": "assets/wallpaper.webp"` (an absolute http(s) URL also works,
   at most 300 characters).
3. Rebuild the game's web UI so the file lands in `dist/assets/`.
4. In Ember's admin game registry press Refresh on the game. Ember stores the
   resolved URL and the card shows the image.

If the image does not load, Ember falls back to a tile with the game's first letter.
Check that the game's origin is listed in `EMBER_GAME_ORIGINS` (CSP `img-src`).
