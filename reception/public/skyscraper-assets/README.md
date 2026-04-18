# Skyscraper Assets

This directory stores the first-pass static assets for the `visualization/skyscraper` route.

Scope of this batch:

- scene-safe placeholder assets
- layered SVG files for rapid integration
- manifest and palette metadata

These files are not final production art. They are intended to:

- unblock PixiJS scene assembly
- preserve the layer split defined in `SKYSCRAPER_PIXEL_IMPLEMENTATION_PLAN.md`
- make later replacement with polished art straightforward

Primary layer order:

1. `backgrounds/sky-*.svg`
2. `backgrounds/city-*-backdrop.svg`
3. `modules/building-shell-base.svg`
4. `modules/interior-room-kit-*.svg`
5. `modules/glass-*.svg`
6. `modules/rooftop-kit.svg`
7. `foreground/street-kit.svg`
8. `characters/*.svg`
9. `fx/*.svg`
10. `foreground/occluders-atlas.svg`
11. `ui/scene-panel-frame.svg`
