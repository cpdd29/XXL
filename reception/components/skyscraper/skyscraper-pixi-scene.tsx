"use client"

import { useEffect, useRef, useState } from "react"
import type { Application, Container, Sprite, Texture } from "pixi.js"
import { cn } from "@/lib/utils"

export type SkyscraperPixiMode = "day" | "night"

type SkyscraperPixiSceneProps = {
  mode: SkyscraperPixiMode
  showGlass: boolean
  showGlow: boolean
  showStreet: boolean
  showOccluders: boolean
  className?: string
}

type SceneSettings = {
  mode: SkyscraperPixiMode
  showGlass: boolean
  showGlow: boolean
  showStreet: boolean
  showOccluders: boolean
}

type V2Manifest = {
  logical_scene_size: {
    width: number
    height: number
  }
  assets: {
    hero_day: string
    hero_night: string
  }
}

type PulseSpriteConfig = {
  sprite: Sprite
  dayAlpha: number
  nightAlpha: number
  dayTint: number
  nightTint: number
  speed: number
  phase: number
}

type StreetStripConfig = {
  sprite: Sprite
  speed: number
  minX: number
  maxX: number
  resetX: number
}

type SceneRuntime = {
  app: Application
  world: Container
  settings: SceneSettings
  logicalWidth: number
  logicalHeight: number
  viewport: {
    fitScale: number
    screenWidth: number
    screenHeight: number
  }
  pointer: {
    x: number
    y: number
  }
  targetDayAlpha: number
  targetNightAlpha: number
  dayBase: Sprite
  nightBase: Sprite
  dayAmbient: Sprite
  nightAmbient: Sprite
  glassLayer: Container
  glowLayer: Container
  streetLayer: Container
  occluderLayer: Container
  pulseSprites: PulseSpriteConfig[]
  streetStrips: StreetStripConfig[]
}

type GlowPanelDef = {
  x: number
  y: number
  width: number
  height: number
  dayAlpha: number
  nightAlpha: number
  dayTint: number
  nightTint: number
  speed: number
  phase: number
}

type StripDef = {
  x: number
  y: number
  width: number
  height: number
  dayAlpha: number
  nightAlpha: number
  dayTint: number
  nightTint: number
  speed: number
}

const MANIFEST_URL = "/skyscraper-assets-v2/meta/manifest.json"

const GLOW_PANEL_DEFS: GlowPanelDef[] = [
  { x: 296, y: 236, width: 254, height: 66, dayAlpha: 0.018, nightAlpha: 0.18, dayTint: 0x92dbff, nightTint: 0xf6c978, speed: 0.0023, phase: 0.2 },
  { x: 595, y: 264, width: 156, height: 60, dayAlpha: 0.014, nightAlpha: 0.17, dayTint: 0x8ddfff, nightTint: 0xf0c16f, speed: 0.0021, phase: 0.6 },
  { x: 316, y: 386, width: 238, height: 62, dayAlpha: 0.016, nightAlpha: 0.17, dayTint: 0x88d8ff, nightTint: 0xf4c170, speed: 0.0022, phase: 1.1 },
  { x: 597, y: 412, width: 147, height: 58, dayAlpha: 0.013, nightAlpha: 0.16, dayTint: 0x7fd4ff, nightTint: 0xefbd69, speed: 0.002, phase: 1.4 },
  { x: 336, y: 530, width: 220, height: 60, dayAlpha: 0.015, nightAlpha: 0.165, dayTint: 0x8ad8ff, nightTint: 0xf1bd6d, speed: 0.00225, phase: 1.9 },
  { x: 598, y: 554, width: 137, height: 54, dayAlpha: 0.012, nightAlpha: 0.15, dayTint: 0x82d5ff, nightTint: 0xeebb68, speed: 0.00215, phase: 2.4 },
  { x: 354, y: 678, width: 205, height: 58, dayAlpha: 0.014, nightAlpha: 0.15, dayTint: 0x89d8ff, nightTint: 0xf3c27a, speed: 0.002, phase: 2.7 },
  { x: 600, y: 700, width: 130, height: 52, dayAlpha: 0.012, nightAlpha: 0.145, dayTint: 0x84d6ff, nightTint: 0xefbc6f, speed: 0.00195, phase: 3.1 },
  { x: 375, y: 818, width: 189, height: 56, dayAlpha: 0.014, nightAlpha: 0.145, dayTint: 0x8ddfff, nightTint: 0xf0b86a, speed: 0.0019, phase: 3.5 },
  { x: 602, y: 840, width: 124, height: 50, dayAlpha: 0.011, nightAlpha: 0.138, dayTint: 0x8bdfff, nightTint: 0xeeb263, speed: 0.00185, phase: 4 },
  { x: 395, y: 961, width: 176, height: 52, dayAlpha: 0.013, nightAlpha: 0.14, dayTint: 0x8fdfff, nightTint: 0xefb567, speed: 0.00195, phase: 4.4 },
  { x: 607, y: 980, width: 117, height: 48, dayAlpha: 0.01, nightAlpha: 0.135, dayTint: 0x86dbff, nightTint: 0xe8ae5f, speed: 0.0019, phase: 4.8 },
  { x: 417, y: 1115, width: 162, height: 50, dayAlpha: 0.012, nightAlpha: 0.132, dayTint: 0x91e1ff, nightTint: 0xeeb462, speed: 0.00185, phase: 5.2 },
  { x: 615, y: 1133, width: 108, height: 46, dayAlpha: 0.01, nightAlpha: 0.128, dayTint: 0x88dcff, nightTint: 0xe2a857, speed: 0.0018, phase: 5.6 },
  { x: 348, y: 1259, width: 328, height: 96, dayAlpha: 0.026, nightAlpha: 0.19, dayTint: 0x9fe6ff, nightTint: 0xf6d49a, speed: 0.0024, phase: 6.1 },
  { x: 470, y: 1216, width: 104, height: 78, dayAlpha: 0, nightAlpha: 0.16, dayTint: 0xffffff, nightTint: 0xbfe8ff, speed: 0.0028, phase: 6.7 },
  { x: 450, y: 110, width: 34, height: 40, dayAlpha: 0.012, nightAlpha: 0.12, dayTint: 0xffffff, nightTint: 0xff8f6a, speed: 0.0058, phase: 0.3 },
  { x: 596, y: 76, width: 18, height: 28, dayAlpha: 0.01, nightAlpha: 0.11, dayTint: 0xffffff, nightTint: 0xff8f6a, speed: 0.0052, phase: 0.9 },
]

const GLASS_SHEEN_DEFS: GlowPanelDef[] = [
  { x: 474, y: 126, width: 56, height: 1108, dayAlpha: 0.16, nightAlpha: 0.055, dayTint: 0xc9efff, nightTint: 0x67b7ff, speed: 0.00125, phase: 0.4 },
  { x: 532, y: 140, width: 16, height: 1070, dayAlpha: 0.12, nightAlpha: 0.045, dayTint: 0xe8fbff, nightTint: 0x83c7ff, speed: 0.00135, phase: 1.1 },
  { x: 281, y: 194, width: 22, height: 870, dayAlpha: 0.05, nightAlpha: 0.02, dayTint: 0xe6fbff, nightTint: 0x4f94d8, speed: 0.0011, phase: 1.9 },
  { x: 653, y: 218, width: 18, height: 716, dayAlpha: 0.05, nightAlpha: 0.02, dayTint: 0xe5fbff, nightTint: 0x4e93d4, speed: 0.00105, phase: 2.7 },
  { x: 332, y: 1222, width: 278, height: 114, dayAlpha: 0.09, nightAlpha: 0.03, dayTint: 0xb7e8ff, nightTint: 0x3f7ec7, speed: 0.00155, phase: 3.8 },
]

const STREET_STRIP_DEFS: StripDef[] = [
  { x: -180, y: 1452, width: 150, height: 6, dayAlpha: 0.08, nightAlpha: 0.3, dayTint: 0xffffff, nightTint: 0xffd9b0, speed: 1.5 },
  { x: 1060, y: 1396, width: 110, height: 5, dayAlpha: 0.05, nightAlpha: 0.22, dayTint: 0xbfe8ff, nightTint: 0xffbd73, speed: -1.15 },
  { x: -260, y: 1364, width: 92, height: 4, dayAlpha: 0.04, nightAlpha: 0.18, dayTint: 0xb4dbff, nightTint: 0xffa65c, speed: 0.9 },
]

function lerp(current: number, target: number, factor: number) {
  return current + (target - current) * factor
}

function createRectSprite(
  pixi: typeof import("pixi.js"),
  color: number,
  alpha: number,
  x: number,
  y: number,
  width: number,
  height: number,
) {
  const sprite = new pixi.Sprite(pixi.Texture.WHITE)

  sprite.position.set(x, y)
  sprite.width = width
  sprite.height = height
  sprite.tint = color
  sprite.alpha = alpha
  sprite.roundPixels = true

  return sprite
}

function createTexturedSprite(
  pixi: typeof import("pixi.js"),
  texture: Texture,
  x: number,
  y: number,
  width: number,
  height: number,
) {
  const sprite = new pixi.Sprite(texture)

  sprite.position.set(x, y)
  sprite.width = width
  sprite.height = height

  return sprite
}

function createFoliageCluster(
  pixi: typeof import("pixi.js"),
  color: number,
  alpha: number,
  x: number,
  y: number,
  mirrored = false,
) {
  const cluster = new pixi.Container()
  const blocks = [
    createRectSprite(pixi, color, alpha, 0, 44, 120, 78),
    createRectSprite(pixi, color, alpha * 0.95, 20, 12, 86, 54),
    createRectSprite(pixi, color, alpha * 0.92, 96, 26, 64, 46),
    createRectSprite(pixi, color, alpha * 0.96, 32, 98, 16, 88),
    createRectSprite(pixi, color, alpha * 0.94, 78, 104, 14, 80),
  ]

  blocks.forEach((block) => {
    cluster.addChild(block)
  })

  cluster.position.set(x, y)
  cluster.scale.x = mirrored ? -1 : 1

  return cluster
}

function createCloudStrip(
  pixi: typeof import("pixi.js"),
  color: number,
  alpha: number,
  x: number,
  y: number,
  width: number,
  height: number,
) {
  const container = new pixi.Container()

  container.addChild(createRectSprite(pixi, color, alpha, 0, height * 0.28, width * 0.72, height * 0.42))
  container.addChild(createRectSprite(pixi, color, alpha * 0.92, width * 0.08, 0, width * 0.32, height * 0.36))
  container.addChild(createRectSprite(pixi, color, alpha * 0.9, width * 0.4, height * 0.08, width * 0.28, height * 0.32))
  container.addChild(createRectSprite(pixi, color, alpha * 0.86, width * 0.6, height * 0.18, width * 0.28, height * 0.28))

  container.position.set(x, y)

  return container
}

function createManifestUrls(manifest: V2Manifest) {
  return {
    day: manifest.assets.hero_day,
    night: manifest.assets.hero_night,
  }
}

function applySceneSettings(runtime: SceneRuntime) {
  const isNight = runtime.settings.mode === "night"

  runtime.targetDayAlpha = isNight ? 0 : 1
  runtime.targetNightAlpha = isNight ? 1 : 0
  runtime.glassLayer.visible = runtime.settings.showGlass
  runtime.glowLayer.visible = runtime.settings.showGlow
  runtime.streetLayer.visible = runtime.settings.showStreet
  runtime.occluderLayer.visible = runtime.settings.showOccluders
}

async function loadManifest() {
  const response = await fetch(MANIFEST_URL)

  if (!response.ok) {
    throw new Error(`Failed to load V2 manifest: ${response.status}`)
  }

  return (await response.json()) as V2Manifest
}

export function SkyscraperPixiScene({
  mode,
  showGlass,
  showGlow,
  showStreet,
  showOccluders,
  className,
}: SkyscraperPixiSceneProps) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const runtimeRef = useRef<SceneRuntime | null>(null)
  const settingsRef = useRef<SceneSettings>({
    mode,
    showGlass,
    showGlow,
    showStreet,
    showOccluders,
  })
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading")
  const [errorText, setErrorText] = useState<string | null>(null)

  useEffect(() => {
    settingsRef.current = {
      mode,
      showGlass,
      showGlow,
      showStreet,
      showOccluders,
    }

    if (runtimeRef.current) {
      runtimeRef.current.settings = settingsRef.current
      applySceneSettings(runtimeRef.current)
    }
  }, [mode, showGlass, showGlow, showStreet, showOccluders])

  useEffect(() => {
    let cancelled = false
    let resizeObserver: ResizeObserver | null = null
    let removePointerListeners: (() => void) | null = null

    async function initScene() {
      const host = hostRef.current

      if (!host) {
        return
      }

      setStatus("loading")
      setErrorText(null)

      try {
        const pixi = await import("pixi.js")
        const manifest = await loadManifest()
        const urls = createManifestUrls(manifest)
        const logicalWidth = manifest.logical_scene_size.width
        const logicalHeight = manifest.logical_scene_size.height
        const dayTexture = (await pixi.Assets.load(urls.day)) as Texture
        const nightTexture = (await pixi.Assets.load(urls.night)) as Texture

        dayTexture.source.scaleMode = "linear"
        nightTexture.source.scaleMode = "linear"

        if (cancelled) {
          return
        }

        const app = new pixi.Application()

        await app.init({
          width: logicalWidth,
          height: logicalHeight,
          backgroundAlpha: 0,
          antialias: true,
          autoDensity: true,
          resolution: Math.min(window.devicePixelRatio || 1, 2),
          preference: ["webgl", "canvas"],
          powerPreference: "high-performance",
        })

        if (cancelled) {
          app.destroy(true, { children: true })
          return
        }

        app.canvas.style.width = "100%"
        app.canvas.style.height = "100%"
        app.canvas.style.display = "block"

        host.replaceChildren(app.canvas)

        const world = new pixi.Container()
        const heroLayer = new pixi.Container()
        const glassLayer = new pixi.Container()
        const glowLayer = new pixi.Container()
        const streetLayer = new pixi.Container()
        const occluderLayer = new pixi.Container()

        app.stage.addChild(world)
        world.addChild(heroLayer)
        world.addChild(glassLayer)
        world.addChild(glowLayer)
        world.addChild(streetLayer)
        world.addChild(occluderLayer)

        const dayBase = createTexturedSprite(pixi, dayTexture, 0, 0, logicalWidth, logicalHeight)
        const nightBase = createTexturedSprite(pixi, nightTexture, 0, 0, logicalWidth, logicalHeight)
        const dayAmbient = createRectSprite(pixi, 0xcdeeff, 0.05, 0, 0, logicalWidth, logicalHeight)
        const nightAmbient = createRectSprite(pixi, 0x071425, 0.16, 0, 0, logicalWidth, logicalHeight)

        nightBase.alpha = 0

        heroLayer.addChild(dayBase)
        heroLayer.addChild(nightBase)
        heroLayer.addChild(dayAmbient)
        heroLayer.addChild(nightAmbient)

        const pulseSprites: PulseSpriteConfig[] = []
        const streetStrips: StreetStripConfig[] = []

        GLASS_SHEEN_DEFS.forEach((def) => {
          const sprite = createRectSprite(pixi, def.dayTint, 0, def.x, def.y, def.width, def.height)
          glassLayer.addChild(sprite)
          pulseSprites.push({
            sprite,
            dayAlpha: def.dayAlpha,
            nightAlpha: def.nightAlpha,
            dayTint: def.dayTint,
            nightTint: def.nightTint,
            speed: def.speed,
            phase: def.phase,
          })
        })

        GLOW_PANEL_DEFS.forEach((def) => {
          const sprite = createRectSprite(pixi, def.dayTint, 0, def.x, def.y, def.width, def.height)
          glowLayer.addChild(sprite)
          pulseSprites.push({
            sprite,
            dayAlpha: def.dayAlpha,
            nightAlpha: def.nightAlpha,
            dayTint: def.dayTint,
            nightTint: def.nightTint,
            speed: def.speed,
            phase: def.phase,
          })
        })

        const upperDayCloud = createCloudStrip(pixi, 0xffffff, 0.12, 32, 64, 210, 84)
        const upperNightCloud = createCloudStrip(pixi, 0x426289, 0.16, 742, 120, 178, 72)
        const sideDayCloud = createCloudStrip(pixi, 0xffffff, 0.09, 812, 210, 156, 64)

        glassLayer.addChild(upperDayCloud)
        glowLayer.addChild(upperNightCloud)
        glassLayer.addChild(sideDayCloud)

        const logoHalo = createRectSprite(pixi, 0xbfe8ff, 0, 454, 1218, 138, 108)
        const roofBeacon = createRectSprite(pixi, 0xff8f6a, 0, 450, 106, 42, 46)
        const rightBeacon = createRectSprite(pixi, 0xff8f6a, 0, 594, 70, 20, 34)

        glowLayer.addChild(logoHalo)
        glowLayer.addChild(roofBeacon)
        glowLayer.addChild(rightBeacon)
        pulseSprites.push({
          sprite: logoHalo,
          dayAlpha: 0,
          nightAlpha: 0.18,
          dayTint: 0xbfe8ff,
          nightTint: 0xbfe8ff,
          speed: 0.0032,
          phase: 0.8,
        })
        pulseSprites.push({
          sprite: roofBeacon,
          dayAlpha: 0.018,
          nightAlpha: 0.14,
          dayTint: 0xffffff,
          nightTint: 0xff8f6a,
          speed: 0.007,
          phase: 0.2,
        })
        pulseSprites.push({
          sprite: rightBeacon,
          dayAlpha: 0.012,
          nightAlpha: 0.12,
          dayTint: 0xffffff,
          nightTint: 0xff8f6a,
          speed: 0.0063,
          phase: 0.7,
        })

        STREET_STRIP_DEFS.forEach((def) => {
          const sprite = createRectSprite(pixi, def.dayTint, def.dayAlpha, def.x, def.y, def.width, def.height)
          streetLayer.addChild(sprite)
          pulseSprites.push({
            sprite,
            dayAlpha: def.dayAlpha,
            nightAlpha: def.nightAlpha,
            dayTint: def.dayTint,
            nightTint: def.nightTint,
            speed: 0.005,
            phase: def.y * 0.01,
          })
          streetStrips.push({
            sprite,
            speed: def.speed,
            minX: -340,
            maxX: logicalWidth + 220,
            resetX: def.speed > 0 ? -340 : logicalWidth + 220,
          })
        })

        streetLayer.addChild(createRectSprite(pixi, 0xffd7ae, 0.08, 120, 1322, 88, 130))
        streetLayer.addChild(createRectSprite(pixi, 0xffd7ae, 0.08, 792, 1276, 102, 168))
        streetLayer.addChild(createRectSprite(pixi, 0xbfe5ff, 0.05, 42, 1354, 74, 116))

        const bottomShade = createRectSprite(pixi, 0x08111d, 0.22, 0, 1290, logicalWidth, 246)
        const topShade = createRectSprite(pixi, 0x0d1827, 0.06, 0, 0, logicalWidth, 180)
        const leftFoliage = createFoliageCluster(pixi, 0x13251f, 0.36, 30, 1296)
        const rightFoliage = createFoliageCluster(pixi, 0x13251f, 0.34, 996, 1308, true)

        occluderLayer.addChild(bottomShade)
        occluderLayer.addChild(topShade)
        occluderLayer.addChild(leftFoliage)
        occluderLayer.addChild(rightFoliage)

        const runtime: SceneRuntime = {
          app,
          world,
          settings: settingsRef.current,
          logicalWidth,
          logicalHeight,
          viewport: {
            fitScale: 1,
            screenWidth: logicalWidth,
            screenHeight: logicalHeight,
          },
          pointer: {
            x: 0.5,
            y: 0.5,
          },
          targetDayAlpha: 1,
          targetNightAlpha: 0,
          dayBase,
          nightBase,
          dayAmbient,
          nightAmbient,
          glassLayer,
          glowLayer,
          streetLayer,
          occluderLayer,
          pulseSprites,
          streetStrips,
        }

        const resize = () => {
          const nextHost = hostRef.current

          if (!nextHost) {
            return
          }

          const width = nextHost.clientWidth
          const height = nextHost.clientHeight

          if (!width || !height) {
            return
          }

          app.renderer.resize(width, height)
          runtime.viewport.fitScale = Math.min(width / logicalWidth, height / logicalHeight)
          runtime.viewport.screenWidth = width
          runtime.viewport.screenHeight = height
        }

        const handlePointerMove = (event: PointerEvent) => {
          const rect = host.getBoundingClientRect()

          runtime.pointer.x = Math.min(Math.max((event.clientX - rect.left) / rect.width, 0), 1)
          runtime.pointer.y = Math.min(Math.max((event.clientY - rect.top) / rect.height, 0), 1)
        }

        const handlePointerLeave = () => {
          runtime.pointer.x = 0.5
          runtime.pointer.y = 0.5
        }

        host.addEventListener("pointermove", handlePointerMove)
        host.addEventListener("pointerleave", handlePointerLeave)
        removePointerListeners = () => {
          host.removeEventListener("pointermove", handlePointerMove)
          host.removeEventListener("pointerleave", handlePointerLeave)
        }

        applySceneSettings(runtime)
        resize()

        const startedAt = performance.now()

        app.ticker.add((ticker) => {
          const elapsed = performance.now() - startedAt
          const isNight = runtime.settings.mode === "night"
          const pulseFactor = 0.72 + Math.sin(elapsed * 0.00155) * 0.06
          const cameraScale = 1.012 + Math.sin(elapsed * 0.00022) * 0.004
          const parallaxX = (runtime.pointer.x - 0.5) * 22
          const parallaxY = (runtime.pointer.y - 0.5) * 28
          const floatX = Math.sin(elapsed * 0.00019) * 3.5
          const floatY = Math.sin(elapsed * 0.00023) * 6.5
          const scaledWidth = runtime.logicalWidth * runtime.viewport.fitScale * cameraScale
          const scaledHeight = runtime.logicalHeight * runtime.viewport.fitScale * cameraScale
          const baseX = (runtime.viewport.screenWidth - scaledWidth) / 2
          const baseY = (runtime.viewport.screenHeight - scaledHeight) / 2

          runtime.dayBase.alpha = lerp(runtime.dayBase.alpha, runtime.targetDayAlpha, 0.08)
          runtime.nightBase.alpha = lerp(runtime.nightBase.alpha, runtime.targetNightAlpha, 0.08)
          runtime.dayAmbient.alpha = lerp(runtime.dayAmbient.alpha, isNight ? 0 : 0.055, 0.08)
          runtime.nightAmbient.alpha = lerp(runtime.nightAmbient.alpha, isNight ? 0.18 : 0, 0.08)

          runtime.world.scale.set(runtime.viewport.fitScale * cameraScale)
          runtime.world.position.set(baseX + parallaxX + floatX, baseY + parallaxY + floatY)

          pulseSprites.forEach((config) => {
            const baseAlpha = isNight ? config.nightAlpha : config.dayAlpha
            const tint = isNight ? config.nightTint : config.dayTint

            config.sprite.tint = tint
            config.sprite.alpha = baseAlpha * (0.8 + Math.sin(elapsed * config.speed + config.phase) * 0.2 + pulseFactor * 0.05)
          })

          upperDayCloud.alpha = lerp(upperDayCloud.alpha, isNight ? 0 : 0.16, 0.06)
          sideDayCloud.alpha = lerp(sideDayCloud.alpha, isNight ? 0 : 0.1, 0.06)
          upperNightCloud.alpha = lerp(upperNightCloud.alpha, isNight ? 0.16 : 0, 0.06)
          upperDayCloud.x += 0.08 * ticker.deltaTime
          sideDayCloud.x -= 0.05 * ticker.deltaTime
          upperNightCloud.x -= 0.06 * ticker.deltaTime
          upperDayCloud.y = 64 + Math.sin(elapsed * 0.00034) * 4
          sideDayCloud.y = 210 + Math.sin(elapsed * 0.00029 + 1.2) * 3
          upperNightCloud.y = 120 + Math.sin(elapsed * 0.00026 + 2.1) * 5

          if (upperDayCloud.x > 86) {
            upperDayCloud.x = 32
          }

          if (sideDayCloud.x < 780) {
            sideDayCloud.x = 812
          }

          if (upperNightCloud.x < 702) {
            upperNightCloud.x = 742
          }

          if (runtime.settings.showStreet) {
            runtime.streetStrips.forEach((strip) => {
              strip.sprite.x += strip.speed * ticker.deltaTime

              if (strip.speed > 0 && strip.sprite.x > strip.maxX) {
                strip.sprite.x = strip.resetX
              }

              if (strip.speed < 0 && strip.sprite.x < strip.minX) {
                strip.sprite.x = strip.resetX
              }
            })
          }
        })

        resizeObserver = new ResizeObserver(() => {
          resize()
        })
        resizeObserver.observe(host)

        runtimeRef.current = runtime
        setStatus("ready")
      } catch (error) {
        if (cancelled) {
          return
        }

        setStatus("error")
        setErrorText(error instanceof Error ? error.message : "Pixi scene init failed")
      }
    }

    initScene()

    return () => {
      cancelled = true
      resizeObserver?.disconnect()
      removePointerListeners?.()

      if (runtimeRef.current) {
        runtimeRef.current.app.destroy(true, { children: true })
        runtimeRef.current = null
      }
    }
  }, [])

  return (
    <div
      className={cn(
        "relative h-full w-full overflow-hidden rounded-[24px]",
        "bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.16),transparent_24%),linear-gradient(180deg,rgba(6,13,22,0.02)_0%,rgba(6,13,22,0.18)_100%)]",
        className,
      )}
    >
      <div ref={hostRef} className="absolute inset-0" />

      <div className="pointer-events-none absolute inset-0 border border-white/10" />
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.06)_0%,rgba(255,255,255,0)_14%),linear-gradient(90deg,rgba(255,255,255,0.02)_0%,rgba(255,255,255,0)_12%,rgba(255,255,255,0)_88%,rgba(255,255,255,0.02)_100%)]" />

      {status !== "ready" ? (
        <div className="absolute inset-0 flex items-center justify-center bg-background/55 backdrop-blur-[2px]">
          <div className="rounded-2xl border border-border bg-card/90 px-4 py-3 text-sm text-muted-foreground shadow-sm">
            {status === "loading" ? "Hero Scene V2 装载中..." : `PixiJS 初始化失败：${errorText ?? "unknown error"}`}
          </div>
        </div>
      ) : null}
    </div>
  )
}
