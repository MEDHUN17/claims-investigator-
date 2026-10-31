# Credits and licenses (Verity frontend)

## Required visual libraries

| Library | URL | License | What we use it for |
|---|---|---|---|
| react-three-fiber (`@react-three/fiber` 9.8.2, `@react-three/drei` 10.7.9, `three` 0.187.0) | https://github.com/pmndrs/react-three-fiber | MIT (all three) | 3D hatchback with damage-zone rings in the Investigation tab (`components/fx/Vehicle3D.tsx`). Also the renderer ShaderGradient runs on. |
| liquid-glass-js (vendored, dashersw) | https://github.com/dashersw/liquid-glass-js | MIT (Copyright 2025 Armagan Amcalar; `src/vendor/liquid-glass/LICENSE`) | WebGL refraction behind the sealed-approval / VOID card and the Drop bar (`components/fx/LiquidGlass.tsx`). Vendored at commit 78cb6cc because the npm package `liquid-glass-js` is an unrelated fork (eamonliu), not this repo. Local edits: html2canvas read from `window`, ES export. Uses `html2canvas-pro` (MIT) for the page snapshot. |
| ShaderGradient (`@shadergradient/react` 2.4.20) | https://github.com/ruucm/shadergradient | MIT | Quiet animated backdrop behind the Queue hero, dark theme only (`components/fx/QueueBackdrop*.tsx`). |
| liquid-logo (Paper Shaders) | https://github.com/paper-design/liquid-logo | Repo: PolyForm Shield 1.0.0. Package we install, `@paper-design/shaders-react` 0.0.82: Apache-2.0 | Liquid-metal Verity mark in the header and the Queue hero (`components/fx/VerityLogo*.tsx`). `@paper-design/liquid-logo` is **not published on npm** (404). liquid-logo is a Next.js demo app built on the Paper Shaders `LiquidMetal` shader, so we use that published, Apache-2.0 shader package directly with our own mark (`src/assets/verity-mark.svg`). None of the liquid-logo repository source is copied. |

PolyForm Shield forbids using the code to build a product that competes with the licensor; since we vendor no liquid-logo source, only the Apache-2.0 package applies to us.

## Existing libraries

- shadcn-style primitives (own implementations in `components/ui/`, patterns from shadcn/ui, MIT) with `clsx` (MIT) and `tailwind-merge` (MIT)
- motion (MIT), lucide-react (ISC), react-router (MIT), TanStack Query (MIT), Tailwind CSS (MIT)
- react-pdf (MIT) for the evidence viewer
- react-resizable-panels (MIT)
- Inter Variable and JetBrains Mono Variable via `@fontsource-variable` (SIL OFL 1.1)

Licenses verified with `npm view <pkg> license` on 2026-10-31. Verify again before redistribution.
