import { mkdirSync, writeFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const WIDTH = 1024
const HEIGHT = 1536

const floors = [
  {
    id: "f7",
    top: 178,
    bottom: 334,
    front: { x: 246, y: 212, w: 360, h: 94 },
    side: { nearX: 646, farX: 814, y: 232, h: 84, slant: 22 },
    frontLayout: "meeting",
    sideLayout: "pods",
  },
  {
    id: "f6",
    top: 334,
    bottom: 488,
    front: { x: 246, y: 368, w: 360, h: 90 },
    side: { nearX: 648, farX: 814, y: 388, h: 82, slant: 22 },
    frontLayout: "open",
    sideLayout: "openSide",
  },
  {
    id: "f5",
    top: 490,
    bottom: 644,
    front: { x: 248, y: 524, w: 358, h: 88 },
    side: { nearX: 650, farX: 814, y: 542, h: 80, slant: 20 },
    frontLayout: "studio",
    sideLayout: "focus",
  },
  {
    id: "f4",
    top: 646,
    bottom: 798,
    front: { x: 248, y: 680, w: 358, h: 86 },
    side: { nearX: 652, farX: 814, y: 698, h: 78, slant: 20 },
    frontLayout: "operations",
    sideLayout: "meetingSmall",
  },
  {
    id: "f3",
    top: 802,
    bottom: 952,
    front: { x: 250, y: 836, w: 356, h: 84 },
    side: { nearX: 654, farX: 814, y: 852, h: 76, slant: 18 },
    frontLayout: "green",
    sideLayout: "pods",
  },
  {
    id: "f2",
    top: 958,
    bottom: 1108,
    front: { x: 252, y: 992, w: 354, h: 82 },
    side: { nearX: 656, farX: 814, y: 1008, h: 74, slant: 18 },
    frontLayout: "executive",
    sideLayout: "support",
  },
  {
    id: "f1",
    top: 1114,
    bottom: 1262,
    front: { x: 252, y: 1148, w: 354, h: 82 },
    side: { nearX: 658, farX: 814, y: 1164, h: 72, slant: 18 },
    frontLayout: "lab",
    sideLayout: "focus",
  },
]

const lobby = {
  top: 1262,
  bottom: 1418,
  front: { x: 204, y: 1286, w: 434, h: 112 },
  side: { nearX: 640, farX: 826, y: 1302, h: 104, slant: 18 },
}

const themes = {
  day: {
    id: "day",
    skyTop: "#56c6ff",
    skyBottom: "#eef8ff",
    skylineBase: "#afc6de",
    skylineMid: "#d9edff",
    skylineWindow: "#f8fdff",
    skylineAccent: "#93aecd",
    cloud: "#ffffff",
    cloudShadow: "#d7edf8",
    haze: "#ffffff",
    towerFrame: "#6f7786",
    towerFrameDark: "#4a5261",
    towerFrameSoft: "#8c97a6",
    slabTop: "#7d8696",
    slabFace: "#5c6474",
    slabShadow: "#424a59",
    beamHighlight: "#adb7c5",
    frontGlassTop: "#d7f7ff",
    frontGlassBottom: "#7bcfff",
    sideGlassTop: "#c9f2ff",
    sideGlassBottom: "#66bfe7",
    frontGlassTint: "#95dcff",
    sideGlassTint: "#82cde8",
    shaftFrame: "#4f6075",
    shaftGlassTop: "#9ce9ff",
    shaftGlassBottom: "#35b8f2",
    shaftInner: "#d8fbff",
    officeBack: "#edf7ff",
    officeFloor: "#d7c4a4",
    officeShadow: "#c2b091",
    wood: "#9e744a",
    woodDark: "#795635",
    chair: "#566172",
    chairDark: "#394352",
    monitor: "#71cfff",
    monitorAlt: "#8ce0ff",
    partition: "#b7c4d2",
    person: "#556679",
    personAlt: "#6e7f91",
    plantLeaf: "#5ea14f",
    plantLeafDark: "#3b7b40",
    planter: "#8a6d4d",
    warmLight: "#ffd39b",
    warmSoft: "#fff0d3",
    coolLight: "#d6fbff",
    equipment: "#7a838f",
    helicopterBody: "#dfe7f0",
    helicopterShadow: "#7f8fa1",
    helicopterWindow: "#6fcfff",
    rooftopLeaf: "#79b55e",
    rooftopLeafDark: "#4b8a46",
    helipadLine: "#f2d97d",
    antenna: "#596273",
    warning: "#ffffff",
    road: "#72798a",
    roadDark: "#5f6678",
    sidewalk: "#dfd7cb",
    curb: "#b8b0a4",
    crosswalk: "#f7f9fc",
    plaza: "#ddd7cb",
    treeShadow: "#2f5732",
    treeTrunk: "#715638",
    carA: "#d74e3a",
    carB: "#5f82c3",
    carGlass: "#e4f9ff",
    lamp: "#f8deb0",
    logo: "#92ecff",
    logoDim: "#356074",
    vignette: "#7bb7d5",
    streetGlow: "#f7d8ad",
    moon: "#ffffff",
    moonGlow: "#ffffff",
    labelFill: "#ffffff",
    labelLine: "#98a8ba",
  },
  night: {
    id: "night",
    skyTop: "#061324",
    skyBottom: "#11263d",
    skylineBase: "#101e31",
    skylineMid: "#1c334e",
    skylineWindow: "#f1bc72",
    skylineAccent: "#274260",
    cloud: "#162b44",
    cloudShadow: "#0b1a2a",
    haze: "#243b5f",
    towerFrame: "#2c3340",
    towerFrameDark: "#181f29",
    towerFrameSoft: "#3d4553",
    slabTop: "#363f4e",
    slabFace: "#232b38",
    slabShadow: "#111722",
    beamHighlight: "#4f5b6f",
    frontGlassTop: "#1c3652",
    frontGlassBottom: "#112033",
    sideGlassTop: "#17314a",
    sideGlassBottom: "#0d1828",
    frontGlassTint: "#244866",
    sideGlassTint: "#1f3850",
    shaftFrame: "#243142",
    shaftGlassTop: "#4dbeff",
    shaftGlassBottom: "#135887",
    shaftInner: "#9de6ff",
    officeBack: "#201a16",
    officeFloor: "#4a3323",
    officeShadow: "#2f2118",
    wood: "#7d573a",
    woodDark: "#5c4028",
    chair: "#313640",
    chairDark: "#1c2128",
    monitor: "#5ab7ff",
    monitorAlt: "#8addff",
    partition: "#5f4f43",
    person: "#0f1115",
    personAlt: "#20242a",
    plantLeaf: "#243c24",
    plantLeafDark: "#182916",
    planter: "#5f4a36",
    warmLight: "#f3bc72",
    warmSoft: "#ffd9ab",
    coolLight: "#96dfff",
    equipment: "#4c5462",
    helicopterBody: "#4c5660",
    helicopterShadow: "#2a3138",
    helicopterWindow: "#8cdfff",
    rooftopLeaf: "#203521",
    rooftopLeafDark: "#132414",
    helipadLine: "#f0b85c",
    antenna: "#6d7685",
    warning: "#ff7b63",
    road: "#151d28",
    roadDark: "#0b1018",
    sidewalk: "#2c2f36",
    curb: "#525760",
    crosswalk: "#9fa4ad",
    plaza: "#2b2e35",
    treeShadow: "#0d160e",
    treeTrunk: "#403020",
    carA: "#293648",
    carB: "#5b677c",
    carGlass: "#a9dcff",
    lamp: "#f1c37a",
    logo: "#bfe8ff",
    logoDim: "#39546d",
    vignette: "#050b14",
    streetGlow: "#f0b46a",
    moon: "#f3dd8d",
    moonGlow: "#f6dba5",
    labelFill: "#fff5e8",
    labelLine: "#866342",
  },
}

function attrs(values) {
  return Object.entries(values)
    .filter(([, value]) => value !== undefined && value !== null && value !== false)
    .map(([key, value]) => `${key}="${String(value)}"`)
    .join(" ")
}

function tag(name, values = {}, children = "") {
  const attributeText = attrs(values)
  const start = attributeText ? `<${name} ${attributeText}` : `<${name}`

  if (children === null) {
    return `${start} />`
  }

  return `${start}>${children}</${name}>`
}

function rect(x, y, width, height, fill, extra = {}) {
  return tag("rect", { x, y, width, height, fill, ...extra }, null)
}

function roundedRect(x, y, width, height, radius, fill, extra = {}) {
  return tag("rect", { x, y, width, height, rx: radius, ry: radius, fill, ...extra }, null)
}

function circle(cx, cy, r, fill, extra = {}) {
  return tag("circle", { cx, cy, r, fill, ...extra }, null)
}

function ellipse(cx, cy, rx, ry, fill, extra = {}) {
  return tag("ellipse", { cx, cy, rx, ry, fill, ...extra }, null)
}

function polygon(points, fill, extra = {}) {
  return tag(
    "polygon",
    {
      points: points.map(([x, y]) => `${x},${y}`).join(" "),
      fill,
      ...extra,
    },
    null,
  )
}

function line(x1, y1, x2, y2, stroke, width, extra = {}) {
  return tag("line", { x1, y1, x2, y2, stroke, "stroke-width": width, ...extra }, null)
}

function path(d, fill, extra = {}) {
  return tag("path", { d, fill, ...extra }, null)
}

function group(children, extra = {}) {
  return tag("g", extra, children)
}

function sideWindowPoints(side) {
  return [
    [side.nearX, side.y],
    [side.farX, side.y + side.slant],
    [side.farX, side.y + side.h + side.slant],
    [side.nearX, side.y + side.h],
  ]
}

function sideFacePoints(top, bottom, farTop, farBottom) {
  return [
    [640, top + 20],
    [farTop, top + 48],
    [farBottom, bottom + 20],
    [640, bottom],
  ]
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function renderStars() {
  const stars = [
    [92, 110, 1.3],
    [156, 164, 1.1],
    [282, 72, 1.2],
    [364, 138, 1.1],
    [418, 58, 1.4],
    [578, 112, 1.2],
    [662, 86, 1.1],
    [720, 144, 1.3],
    [834, 94, 1.2],
    [918, 138, 1.1],
  ]

  return group(
    stars.map(([cx, cy, r]) => circle(cx, cy, r, "#dbe8ff", { opacity: 0.82 })).join(""),
    { opacity: 0.9 },
  )
}

function renderCloud(theme, x, y, scale, opacity = 1) {
  const fill = theme.cloud
  const shadow = theme.cloudShadow

  return group(
    [
      ellipse(x + 54 * scale, y + 42 * scale, 72 * scale, 30 * scale, shadow, { opacity: 0.46 }),
      ellipse(x + 26 * scale, y + 30 * scale, 34 * scale, 26 * scale, fill),
      ellipse(x + 64 * scale, y + 22 * scale, 46 * scale, 32 * scale, fill),
      ellipse(x + 104 * scale, y + 34 * scale, 44 * scale, 28 * scale, fill),
      ellipse(x + 146 * scale, y + 36 * scale, 28 * scale, 22 * scale, fill),
      rect(x + 20 * scale, y + 30 * scale, 132 * scale, 30 * scale, fill),
    ].join(""),
    { opacity },
  )
}

function renderSky(mode, theme) {
  const haze = mode === "day"
    ? [
        ellipse(788, 122, 150, 96, theme.haze, { opacity: 0.26 }),
        ellipse(242, 214, 108, 68, theme.haze, { opacity: 0.12 }),
      ].join("")
    : [
        ellipse(154, 120, 78, 78, theme.moonGlow, { opacity: 0.14 }),
        circle(132, 110, 34, theme.moon, { opacity: 0.98 }),
        circle(144, 104, 26, theme.skyTop),
      ].join("")

  return [
    rect(0, 0, WIDTH, HEIGHT, `url(#${theme.id}-sky)`),
    haze,
    mode === "night" ? renderStars() : "",
    renderCloud(theme, 18, 82, 1.2, mode === "day" ? 0.92 : 0.6),
    renderCloud(theme, 840, 116, 1.1, mode === "day" ? 0.92 : 0.54),
    renderCloud(theme, 804, 324, 0.74, mode === "day" ? 0.6 : 0.3),
  ].join("")
}

function renderCityBlock(theme, x, y, width, height, topStyle, lit = false) {
  const body = rect(x, y, width, height, topStyle)
  const crown = rect(x + width * 0.22, y - 18, width * 0.56, 18, theme.skylineAccent, { opacity: 0.9 })
  const windows = []

  for (let row = 0; row < 12; row += 1) {
    for (let column = 0; column < Math.floor(width / 22); column += 1) {
      if ((row + column) % 3 === 1) {
        continue
      }

      const windowX = x + 10 + column * 18
      const windowY = y + 18 + row * 28

      if (windowX + 8 > x + width - 8 || windowY + 10 > y + height - 10) {
        continue
      }

      windows.push(
        rect(
          windowX,
          windowY,
          clamp(width / 12, 7, 12),
          lit ? 10 : 9,
          lit ? theme.skylineWindow : theme.skylineMid,
          { opacity: lit ? 0.82 : 0.6 },
        ),
      )
    }
  }

  return group([body, crown, group(windows.join(""), { opacity: lit ? 1 : 0.56 })].join(""), {
    opacity: lit ? 1 : 0.78,
  })
}

function renderFarCity(mode, theme) {
  const lit = mode === "night"

  return group(
    [
      renderCityBlock(theme, 8, 656, 88, 362, theme.skylineBase, lit),
      renderCityBlock(theme, 86, 470, 124, 560, theme.skylineBase, lit),
      renderCityBlock(theme, 198, 584, 74, 446, theme.skylineBase, lit),
      renderCityBlock(theme, 786, 448, 118, 590, theme.skylineBase, lit),
      renderCityBlock(theme, 886, 540, 108, 494, theme.skylineBase, lit),
      renderCityBlock(theme, 722, 612, 72, 424, theme.skylineBase, lit),
      path(
        "M0 1074 L0 746 C74 782 120 820 170 890 C222 964 286 994 360 966 C432 938 486 864 550 858 C628 850 696 920 758 954 C820 988 894 958 962 876 C992 838 1016 812 1024 806 L1024 1074 Z",
        mode === "day" ? "#95aecb" : "#112338",
        { opacity: mode === "day" ? 0.52 : 0.62 },
      ),
      rect(0, 1044, WIDTH, 72, mode === "day" ? "#7d9f71" : "#0f2017", {
        opacity: mode === "day" ? 0.54 : 0.5,
      }),
    ].join(""),
  )
}

function renderDesk(theme, x, y, width, scale = 1, monitorColor = theme.monitor) {
  const deskHeight = 10 * scale
  const legWidth = 4 * scale
  const chairX = x + width * 0.42

  return group(
    [
      rect(x, y, width, deskHeight, theme.wood),
      rect(x + 2 * scale, y + deskHeight, legWidth, 14 * scale, theme.woodDark),
      rect(x + width - legWidth - 2 * scale, y + deskHeight, legWidth, 14 * scale, theme.woodDark),
      rect(x + 6 * scale, y - 15 * scale, width * 0.32, 12 * scale, monitorColor),
      rect(x + width * 0.46, y - 13 * scale, width * 0.24, 10 * scale, theme.monitorAlt),
      rect(chairX, y + 11 * scale, 14 * scale, 10 * scale, theme.chair),
      rect(chairX + 4 * scale, y + 21 * scale, 6 * scale, 10 * scale, theme.chairDark),
    ].join(""),
  )
}

function renderMeetingTable(theme, x, y, width, height) {
  return group(
    [
      rect(x, y, width, height, theme.wood),
      rect(x + 6, y + height, 6, 16, theme.woodDark),
      rect(x + width - 12, y + height, 6, 16, theme.woodDark),
      rect(x - 14, y + 4, 10, height - 8, theme.chair),
      rect(x - 14, y + height + 10, 10, height - 8, theme.chair),
      rect(x + width + 4, y + 4, 10, height - 8, theme.chair),
      rect(x + width + 4, y + height + 10, 10, height - 8, theme.chair),
      rect(x + 20, y + 8, width - 40, 8, theme.monitorAlt, { opacity: 0.5 }),
    ].join(""),
  )
}

function renderPlanter(theme, x, y, scale = 1) {
  return group(
    [
      rect(x, y + 20 * scale, 18 * scale, 10 * scale, theme.planter),
      ellipse(x + 9 * scale, y + 10 * scale, 12 * scale, 12 * scale, theme.plantLeafDark),
      ellipse(x + 5 * scale, y + 8 * scale, 6 * scale, 10 * scale, theme.plantLeaf),
      ellipse(x + 12 * scale, y + 6 * scale, 8 * scale, 12 * scale, theme.plantLeaf),
      ellipse(x + 15 * scale, y + 12 * scale, 7 * scale, 10 * scale, theme.plantLeafDark),
    ].join(""),
  )
}

function renderPerson(theme, x, y, scale = 1, alt = false) {
  const fill = alt ? theme.personAlt : theme.person

  return group(
    [
      circle(x + 5 * scale, y + 5 * scale, 5 * scale, fill),
      rect(x + 1 * scale, y + 12 * scale, 8 * scale, 16 * scale, fill),
      rect(x - 1 * scale, y + 28 * scale, 4 * scale, 10 * scale, fill),
      rect(x + 7 * scale, y + 28 * scale, 4 * scale, 10 * scale, fill),
    ].join(""),
  )
}

function renderCabinet(theme, x, y, width, height, lit = false) {
  return group(
    [
      rect(x, y, width, height, theme.partition),
      rect(x + 4, y + 6, width - 8, 4, lit ? theme.warmLight : theme.towerFrameSoft, { opacity: 0.7 }),
      rect(x + 4, y + 18, width - 8, 4, theme.towerFrameDark, { opacity: 0.4 }),
      rect(x + 4, y + 30, width - 8, 4, theme.towerFrameDark, { opacity: 0.34 }),
    ].join(""),
  )
}

function renderServerRack(theme, x, y, width, height) {
  const lights = []

  for (let row = 0; row < 5; row += 1) {
    lights.push(rect(x + 8, y + 8 + row * 14, width - 16, 4, theme.monitorAlt, { opacity: 0.55 }))
  }

  return group(
    [
      rect(x, y, width, height, theme.towerFrameDark),
      rect(x + 4, y + 4, width - 8, height - 8, theme.towerFrame, { opacity: 0.26 }),
      lights.join(""),
    ].join(""),
  )
}

function renderLounge(theme, box) {
  return [
    roundedRect(box.x + 26, box.y + box.h - 34, 76, 18, 6, theme.woodDark, { opacity: 0.44 }),
    roundedRect(box.x + 132, box.y + box.h - 34, 76, 18, 6, theme.woodDark, { opacity: 0.44 }),
    roundedRect(box.x + 52, box.y + box.h - 66, 132, 24, 8, theme.partition),
    roundedRect(box.x + 84, box.y + box.h - 104, 66, 14, 7, theme.wood),
    renderPlanter(theme, box.x + 20, box.y + box.h - 78, 1.1),
    renderPlanter(theme, box.x + box.w - 36, box.y + box.h - 78, 1.1),
  ].join("")
}

function renderNightLabel(theme, x, y, width) {
  return group(
    [
      roundedRect(x, y, width, 18, 6, theme.labelFill, { opacity: 0.96 }),
      rect(x + 10, y + 5, width - 20, 3, theme.labelLine),
      rect(x + 10, y + 10, width - 34, 3, theme.labelLine),
    ].join(""),
    { opacity: 0.92 },
  )
}

function renderInteriorLayout(variant, box, theme, mode, side = false) {
  const content = [
    rect(box.x, box.y, box.w, box.h, theme.officeBack),
    rect(box.x, box.y + box.h - 22, box.w, 22, theme.officeFloor),
    rect(box.x, box.y + box.h - 12, box.w, 12, theme.officeShadow, { opacity: 0.45 }),
    rect(box.x, box.y, box.w, 5, theme.warmSoft, { opacity: mode === "day" ? 0.42 : 0.18 }),
  ]

  switch (variant) {
    case "meeting":
      content.push(
        renderMeetingTable(theme, box.x + 84, box.y + box.h - 72, 108, 20),
        renderCabinet(theme, box.x + 26, box.y + 24, 54, 38, false),
        renderCabinet(theme, box.x + box.w - 86, box.y + 24, 54, 38, false),
        rect(box.x + 112, box.y + 20, 86, 20, theme.monitorAlt),
        renderPerson(theme, box.x + 112, box.y + box.h - 82, 0.9),
        renderPerson(theme, box.x + 168, box.y + box.h - 82, 0.9, true),
        renderPlanter(theme, box.x + box.w - 32, box.y + box.h - 64, 1),
      )
      break
    case "open":
      for (let index = 0; index < 3; index += 1) {
        content.push(renderDesk(theme, box.x + 26 + index * 84, box.y + box.h - 46, 52, 1))
      }

      for (let index = 0; index < 2; index += 1) {
        content.push(renderDesk(theme, box.x + 60 + index * 96, box.y + box.h - 82, 56, 0.92))
      }

      content.push(
        renderPerson(theme, box.x + 102, box.y + box.h - 82, 0.8),
        renderPerson(theme, box.x + 188, box.y + box.h - 82, 0.8, true),
        renderPlanter(theme, box.x + 14, box.y + box.h - 64, 1),
        renderPlanter(theme, box.x + box.w - 30, box.y + box.h - 64, 1),
      )
      break
    case "studio":
      content.push(
        rect(box.x + 28, box.y + 18, 78, 14, theme.monitorAlt),
        rect(box.x + 124, box.y + 18, 84, 14, theme.monitor),
        renderDesk(theme, box.x + 38, box.y + box.h - 46, 64, 1),
        renderDesk(theme, box.x + 124, box.y + box.h - 46, 64, 1),
        renderDesk(theme, box.x + 208, box.y + box.h - 46, 48, 1),
        renderCabinet(theme, box.x + box.w - 56, box.y + 26, 34, 50, true),
        renderPerson(theme, box.x + 156, box.y + box.h - 84, 0.8),
      )
      break
    case "operations":
      content.push(
        rect(box.x + 36, box.y + 20, box.w - 72, 18, theme.monitorAlt),
        rect(box.x + 48, box.y + 44, box.w - 96, 10, theme.monitor, { opacity: 0.84 }),
        renderDesk(theme, box.x + 44, box.y + box.h - 46, 60, 1, theme.monitorAlt),
        renderDesk(theme, box.x + 126, box.y + box.h - 46, 60, 1, theme.monitorAlt),
        renderDesk(theme, box.x + 208, box.y + box.h - 46, 40, 1, theme.monitorAlt),
        renderServerRack(theme, box.x + box.w - 54, box.y + 24, 34, 54),
        renderPerson(theme, box.x + 104, box.y + box.h - 84, 0.8),
        renderPerson(theme, box.x + 188, box.y + box.h - 84, 0.8, true),
      )
      break
    case "green":
      content.push(
        renderLounge(theme, box),
        renderDesk(theme, box.x + 206, box.y + box.h - 46, 44, 1),
        renderPerson(theme, box.x + 214, box.y + box.h - 84, 0.8),
        renderPlanter(theme, box.x + 108, box.y + box.h - 72, 1.2),
      )
      break
    case "executive":
      content.push(
        renderMeetingTable(theme, box.x + 98, box.y + box.h - 66, 82, 18),
        renderDesk(theme, box.x + 38, box.y + box.h - 44, 54, 1.02),
        renderCabinet(theme, box.x + box.w - 62, box.y + 22, 34, 52, true),
        rect(box.x + 96, box.y + 22, 72, 14, theme.monitorAlt),
        renderPlanter(theme, box.x + 14, box.y + box.h - 60, 1),
        renderPerson(theme, box.x + 56, box.y + box.h - 82, 0.86, true),
      )
      break
    case "lab":
      content.push(
        rect(box.x + 28, box.y + 22, 102, 14, theme.monitorAlt),
        rect(box.x + 146, box.y + 22, 76, 14, theme.monitor),
        renderDesk(theme, box.x + 36, box.y + box.h - 44, 58, 1),
        renderDesk(theme, box.x + 110, box.y + box.h - 44, 58, 1),
        renderCabinet(theme, box.x + 202, box.y + 24, 50, 58, true),
        renderServerRack(theme, box.x + box.w - 44, box.y + 30, 26, 52),
      )
      break
    case "pods":
      content.push(
        roundedRect(box.x + 24, box.y + box.h - 62, 52, 28, 6, theme.partition),
        roundedRect(box.x + 92, box.y + box.h - 62, 52, 28, 6, theme.partition),
        roundedRect(box.x + 160, box.y + box.h - 62, 52, 28, 6, theme.partition),
        roundedRect(box.x + 228, box.y + box.h - 62, 38, 28, 6, theme.partition),
        rect(box.x + 34, box.y + box.h - 54, 30, 10, theme.monitorAlt),
        rect(box.x + 102, box.y + box.h - 54, 30, 10, theme.monitorAlt),
        rect(box.x + 170, box.y + box.h - 54, 30, 10, theme.monitorAlt),
        renderPlanter(theme, box.x + box.w - 28, box.y + box.h - 64, 0.9),
      )
      break
    case "openSide":
      content.push(
        renderDesk(theme, box.x + 12, box.y + box.h - 40, 44, 0.9),
        renderDesk(theme, box.x + 64, box.y + box.h - 48, 44, 0.9),
        renderDesk(theme, box.x + 116, box.y + box.h - 40, 34, 0.9),
        renderPlanter(theme, box.x + box.w - 22, box.y + box.h - 52, 0.75),
      )
      break
    case "focus":
      content.push(
        roundedRect(box.x + 18, box.y + box.h - 58, 36, 28, 6, theme.partition),
        roundedRect(box.x + 66, box.y + box.h - 58, 36, 28, 6, theme.partition),
        roundedRect(box.x + 114, box.y + box.h - 58, 32, 28, 6, theme.partition),
        rect(box.x + 24, box.y + box.h - 48, 24, 10, theme.monitorAlt),
        rect(box.x + 72, box.y + box.h - 48, 24, 10, theme.monitorAlt),
        renderCabinet(theme, box.x + box.w - 28, box.y + 20, 20, 40, true),
      )
      break
    case "meetingSmall":
      content.push(
        renderMeetingTable(theme, box.x + 28, box.y + box.h - 58, 78, 16),
        rect(box.x + 42, box.y + 20, 72, 12, theme.monitorAlt),
        renderPlanter(theme, box.x + box.w - 22, box.y + box.h - 52, 0.8),
      )
      break
    case "support":
      content.push(
        renderDesk(theme, box.x + 16, box.y + box.h - 38, 40, 0.88),
        renderDesk(theme, box.x + 64, box.y + box.h - 44, 40, 0.88),
        renderServerRack(theme, box.x + 114, box.y + 18, 28, 46),
      )
      break
    default:
      content.push(renderDesk(theme, box.x + 26, box.y + box.h - 42, box.w * 0.34, 1))
  }

  if (mode === "night") {
    const glowAlpha = side
      ? (variant === "support" || variant === "focus" ? 0.1 : 0.13)
      : (variant === "meeting" || variant === "green" || variant === "executive" || variant === "lab" ? 0.22 : 0.18)

    content.push(rect(box.x, box.y, box.w, box.h, theme.warmLight, { opacity: glowAlpha }))

    if (!side && (variant === "meeting" || variant === "operations" || variant === "green" || variant === "executive")) {
      content.push(renderNightLabel(theme, box.x + 46, box.y + 18, 112))
    }
  } else {
    content.push(rect(box.x, box.y, box.w, box.h, theme.coolLight, { opacity: 0.08 }))
  }

  return content.join("")
}

function renderWindowFrame(theme, box, side = false) {
  const strips = []

  if (side) {
    strips.push(
      line(box.nearX + 42, box.y + 4, box.nearX + 42, box.y + box.h - 4, theme.beamHighlight, 3, { opacity: 0.45 }),
      line(box.nearX + 96, box.y + 8, box.nearX + 96, box.y + box.h - 8, theme.beamHighlight, 3, { opacity: 0.36 }),
      line(box.nearX + 136, box.y + 10, box.nearX + 136, box.y + box.h - 10, theme.beamHighlight, 2.5, { opacity: 0.28 }),
    )
  } else {
    for (let index = 1; index <= 4; index += 1) {
      strips.push(line(box.x + index * (box.w / 5), box.y + 4, box.x + index * (box.w / 5), box.y + box.h - 4, theme.beamHighlight, 3, { opacity: 0.34 }))
    }

    strips.push(line(box.x, box.y + box.h - 28, box.x + box.w, box.y + box.h - 28, theme.beamHighlight, 3, { opacity: 0.26 }))
  }

  return group(strips.join(""), { opacity: 0.92 })
}

function renderGlassReflection(theme, box, side = false, mode = "day") {
  if (side) {
    return group(
      [
        polygon(
          [
            [box.nearX + 18, box.y + 8],
            [box.nearX + 70, box.y + 16],
            [box.nearX + 56, box.y + box.h - 12],
            [box.nearX + 12, box.y + box.h - 18],
          ],
          "#ffffff",
          { opacity: mode === "day" ? 0.12 : 0.04 },
        ),
        polygon(
          [
            [box.nearX + 112, box.y + 10],
            [box.nearX + 144, box.y + 14],
            [box.nearX + 134, box.y + box.h - 14],
            [box.nearX + 106, box.y + box.h - 20],
          ],
          "#ffffff",
          { opacity: mode === "day" ? 0.08 : 0.03 },
        ),
      ].join(""),
    )
  }

  return group(
    [
      rect(box.x + 18, box.y + 8, 18, box.h - 18, "#ffffff", { opacity: mode === "day" ? 0.12 : 0.03 }),
      rect(box.x + 104, box.y + 10, 10, box.h - 22, "#ffffff", { opacity: mode === "day" ? 0.07 : 0.025 }),
      rect(box.x + box.w - 28, box.y + 6, 14, box.h - 16, "#ffffff", { opacity: mode === "day" ? 0.08 : 0.02 }),
    ].join(""),
  )
}

function renderFloor(theme, mode, floor, index) {
  const farTop = 848 - index * 3
  const farBottom = 804 - index * 2
  const frontFace = rect(216, floor.top, 424, floor.bottom - floor.top, theme.towerFrame)
  const frontInset = rect(228, floor.top + 14, 400, floor.bottom - floor.top - 24, theme.towerFrameDark, { opacity: 0.2 })
  const sideFace = polygon(sideFacePoints(floor.top, floor.bottom, farTop, farBottom), theme.slabFace)
  const sideEdge = polygon(
    [
      [640, floor.top + 20],
      [farTop, floor.top + 42],
      [farTop, floor.top + 58],
      [640, floor.top + 36],
    ],
    theme.slabTop,
  )
  const floorLip = polygon(
    [
      [216, floor.top],
      [640, floor.top],
      [640, floor.top + 20],
      [216, floor.top + 20],
    ],
    theme.slabTop,
  )
  const frontShadow = rect(216, floor.bottom - 10, 424, 10, theme.slabShadow, { opacity: 0.55 })
  const frontGlass = rect(floor.front.x, floor.front.y, floor.front.w, floor.front.h, `url(#${theme.id}-front-glass)`, {
    opacity: mode === "day" ? 0.7 : 0.55,
  })
  const sideGlass = polygon(sideWindowPoints(floor.side), `url(#${theme.id}-side-glass)`, {
    opacity: mode === "day" ? 0.72 : 0.56,
  })
  const clips = [
    tag(
      "clipPath",
      { id: `${theme.id}-front-${floor.id}` },
      rect(floor.front.x, floor.front.y, floor.front.w, floor.front.h, "#ffffff"),
    ),
    tag(
      "clipPath",
      { id: `${theme.id}-side-${floor.id}` },
      polygon(sideWindowPoints(floor.side), "#ffffff"),
    ),
  ]
  const frontInterior = group(
    renderInteriorLayout(
      floor.frontLayout,
      { x: floor.front.x, y: floor.front.y, w: floor.front.w, h: floor.front.h },
      theme,
      mode,
    ),
    { "clip-path": `url(#${theme.id}-front-${floor.id})` },
  )
  const sideInterior = group(
    renderInteriorLayout(
      floor.sideLayout,
      {
        x: floor.side.nearX,
        y: floor.side.y + 2,
        w: floor.side.farX - floor.side.nearX,
        h: floor.side.h,
      },
      theme,
      mode,
      true,
    ),
    { "clip-path": `url(#${theme.id}-side-${floor.id})` },
  )
  const frontFrame = renderWindowFrame(theme, floor.front, false)
  const sideFrame = renderWindowFrame(theme, floor.side, true)

  return {
    defs: clips.join(""),
    body: [
      frontFace,
      frontInset,
      sideFace,
      sideEdge,
      frontInterior,
      sideInterior,
      frontGlass,
      sideGlass,
      renderGlassReflection(theme, floor.front, false, mode),
      renderGlassReflection(theme, floor.side, true, mode),
      frontFrame,
      sideFrame,
      floorLip,
      frontShadow,
      line(216, floor.top + 20, 640, floor.top + 20, theme.slabShadow, 4, { opacity: 0.3 }),
    ].join(""),
  }
}

function renderCore(theme, mode) {
  const glass = rect(478, 124, 62, 1268, `url(#${theme.id}-shaft-glass)`, {
    opacity: mode === "day" ? 0.92 : 0.82,
  })
  const inner = []

  for (let index = 0; index < 17; index += 1) {
    const y = 148 + index * 74
    inner.push(
      rect(486, y, 46, 46, theme.shaftInner, { opacity: mode === "day" ? 0.5 : 0.22 }),
      rect(496, y + 10, 7, 22, theme.monitorAlt, { opacity: mode === "day" ? 0.38 : 0.52 }),
      rect(510, y + 10, 7, 22, theme.monitorAlt, { opacity: mode === "day" ? 0.38 : 0.52 }),
    )
  }

  return group(
    [
      rect(468, 108, 82, 1288, theme.shaftFrame),
      rect(474, 114, 70, 1276, theme.towerFrameDark, { opacity: 0.24 }),
      glass,
      group(inner.join(""), { opacity: 0.92 }),
      line(509, 126, 509, 1378, "#ffffff", 3, { opacity: mode === "day" ? 0.28 : 0.16 }),
      line(484, 132, 484, 1384, "#ffffff", 2, { opacity: mode === "day" ? 0.18 : 0.08 }),
      rect(456, 76, 106, 72, theme.towerFrame),
      rect(474, 88, 70, 48, theme.towerFrameDark, { opacity: 0.5 }),
      rect(490, 100, 38, 20, theme.monitorAlt, { opacity: mode === "day" ? 0.5 : 0.7 }),
      rect(474, 1388, 76, 14, theme.slabShadow, { opacity: 0.46 }),
    ].join(""),
  )
}

function renderRoof(theme, mode) {
  const deckTop = polygon(
    [
      [198, 112],
      [706, 112],
      [852, 148],
      [344, 148],
    ],
    mode === "day" ? "#c7d0dd" : "#2b3340",
  )
  const deckFace = polygon(
    [
      [198, 112],
      [344, 148],
      [326, 188],
      [182, 154],
    ],
    theme.slabFace,
  )
  const deckFront = polygon(
    [
      [344, 148],
      [852, 148],
      [812, 188],
      [326, 188],
    ],
    theme.slabTop,
  )
  const helipad = group(
    [
      polygon(
        [
          [228, 126],
          [376, 126],
          [430, 152],
          [282, 152],
        ],
        mode === "day" ? "#6b727e" : "#1e2530",
      ),
      line(292, 140, 370, 140, theme.helipadLine, 4, { opacity: 0.95 }),
      line(330, 126, 330, 154, theme.helipadLine, 4, { opacity: 0.95 }),
      polygon(
        [
          [280, 118],
          [332, 106],
          [376, 118],
          [346, 130],
          [298, 130],
        ],
        theme.helicopterBody,
      ),
      ellipse(332, 116, 22, 11, theme.helicopterBody),
      ellipse(316, 116, 8, 5, theme.helicopterWindow),
      line(254, 112, 404, 112, theme.helicopterShadow, 3),
      line(332, 100, 332, 126, theme.helicopterShadow, 3),
      line(288, 130, 270, 144, theme.helicopterShadow, 3),
      line(364, 130, 382, 146, theme.helicopterShadow, 3),
      line(286, 142, 312, 142, theme.helicopterShadow, 3),
      line(350, 142, 376, 142, theme.helicopterShadow, 3),
    ].join(""),
  )
  const garden = group(
    [
      polygon(
        [
          [412, 150],
          [596, 150],
          [646, 172],
          [462, 172],
        ],
        mode === "day" ? "#b8a27b" : "#4f402d",
      ),
      rect(446, 138, 130, 14, theme.woodDark),
      renderPlanter(theme, 430, 132, 1.1),
      renderPlanter(theme, 514, 132, 1.1),
      renderPlanter(theme, 590, 140, 1),
      roundedRect(484, 152, 64, 10, 4, theme.wood, { opacity: 0.86 }),
    ].join(""),
  )
  const equipment = group(
    [
      rect(620, 124, 64, 34, theme.equipment),
      rect(690, 128, 48, 30, theme.equipment),
      rect(744, 128, 42, 28, theme.equipment),
      rect(648, 102, 38, 24, theme.towerFrame),
      rect(770, 90, 18, 60, theme.antenna),
      rect(776, 62, 6, 28, theme.antenna),
      circle(779, 56, 6, theme.warning, { opacity: mode === "day" ? 0.74 : 0.98 }),
    ].join(""),
  )
  const rooftopRoom = group(
    [
      rect(462, 80, 74, 44, theme.towerFrame),
      rect(474, 90, 50, 28, theme.monitorAlt, { opacity: mode === "day" ? 0.7 : 0.54 }),
      rect(494, 62, 8, 18, theme.antenna),
      circle(498, 56, 5, theme.warning, { opacity: mode === "day" ? 0.72 : 0.94 }),
    ].join(""),
  )

  return group(
    [
      deckTop,
      deckFace,
      deckFront,
      line(222, 120, 692, 120, theme.beamHighlight, 3, { opacity: 0.52 }),
      line(348, 152, 842, 152, theme.beamHighlight, 3, { opacity: 0.38 }),
      helipad,
      garden,
      equipment,
      rooftopRoom,
    ].join(""),
  )
}

function renderLobby(theme, mode) {
  const frontClipId = `${theme.id}-front-lobby`
  const sideClipId = `${theme.id}-side-lobby`
  const frontFace = rect(202, lobby.top, 438, lobby.bottom - lobby.top, theme.towerFrame)
  const sideFace = polygon(
    [
      [640, lobby.top + 12],
      [838, lobby.top + 38],
      [820, lobby.bottom + 10],
      [640, lobby.bottom],
    ],
    theme.slabFace,
  )
  const frontInterior = group(
    [
      rect(lobby.front.x, lobby.front.y, lobby.front.w, lobby.front.h, theme.officeBack),
      rect(lobby.front.x, lobby.front.y + 74, lobby.front.w, 38, theme.plaza),
      rect(394, 1320, 118, 98, theme.towerFrameDark),
      rect(414, 1338, 78, 54, theme.warmSoft, { opacity: mode === "day" ? 0.46 : 0.36 }),
      rect(222, 1294, 122, 86, theme.frontGlassTint, { opacity: 0.22 }),
      rect(560, 1294, 56, 86, theme.frontGlassTint, { opacity: 0.22 }),
      renderDesk(theme, 436, 1312, 62, 1.08),
      renderDesk(theme, 510, 1306, 52, 1),
      renderPerson(theme, 470, 1294, 0.88),
      renderPerson(theme, 538, 1298, 0.82, true),
    ].join(""),
    { "clip-path": `url(#${frontClipId})` },
  )
  const sideInterior = group(
    [
      rect(lobby.side.nearX, lobby.side.y + 2, lobby.side.farX - lobby.side.nearX, lobby.side.h, theme.officeBack),
      rect(lobby.side.nearX, lobby.side.y + lobby.side.h - 22, lobby.side.farX - lobby.side.nearX, 22, theme.officeFloor),
      renderDesk(theme, 654, 1326, 50, 1),
      renderDesk(theme, 720, 1312, 50, 1),
      renderPerson(theme, 690, 1298, 0.8, true),
      renderPlanter(theme, 786, 1330, 0.8),
      rect(lobby.side.nearX, lobby.side.y + 2, lobby.side.farX - lobby.side.nearX, lobby.side.h, theme.warmLight, {
        opacity: mode === "day" ? 0.07 : 0.14,
      }),
    ].join(""),
    { "clip-path": `url(#${sideClipId})` },
  )

  return {
    defs: [
      tag("clipPath", { id: frontClipId }, rect(lobby.front.x, lobby.front.y, lobby.front.w, lobby.front.h, "#ffffff")),
      tag(
        "clipPath",
        { id: sideClipId },
        polygon(sideWindowPoints(lobby.side), "#ffffff"),
      ),
    ].join(""),
    body: group(
      [
        frontFace,
        sideFace,
        frontInterior,
        sideInterior,
        rect(lobby.front.x, lobby.front.y, lobby.front.w, lobby.front.h, `url(#${theme.id}-front-glass)`, {
          opacity: mode === "day" ? 0.72 : 0.52,
        }),
        polygon(sideWindowPoints(lobby.side), `url(#${theme.id}-side-glass)`, {
          opacity: mode === "day" ? 0.74 : 0.54,
        }),
        renderGlassReflection(theme, lobby.front, false, mode),
        renderGlassReflection(theme, lobby.side, true, mode),
        renderWindowFrame(theme, lobby.front, false),
        renderWindowFrame(theme, lobby.side, true),
        rect(398, 1320, 96, 98, theme.towerFrameDark),
        rect(424, 1346, 42, 72, mode === "day" ? "#ead2b2" : "#3f3124"),
        rect(472, 1346, 22, 72, mode === "day" ? "#ead2b2" : "#3f3124"),
        roundedRect(448, 1246, 120, 76, 12, mode === "day" ? "#263a4b" : "#162536"),
        rect(470, 1264, 10, 34, theme.logo),
        rect(486, 1254, 10, 44, theme.logo),
        rect(502, 1242, 10, 56, theme.logo),
        rect(518, 1254, 10, 44, theme.logo),
        rect(534, 1264, 10, 34, theme.logo),
        rect(458, 1304, 100, 8, theme.logoDim),
        rect(390, 1410, 118, 8, theme.slabShadow, { opacity: 0.5 }),
        rect(406, 1394, 86, 12, mode === "day" ? "#d4b287" : "#5f452f"),
      ].join(""),
    ),
  }
}

function renderStreet(theme, mode) {
  return group(
    [
      path("M0 1392 L180 1312 L348 1274 L348 1536 L0 1536 Z", theme.road),
      path("M348 1274 L760 1278 L1024 1368 L1024 1536 L348 1536 Z", theme.road),
      path("M760 1278 L1024 1368 L1024 1536 L742 1536 Z", theme.roadDark, { opacity: 0.48 }),
      path("M174 1312 L348 1274 L760 1278 L750 1330 L318 1338 Z", theme.sidewalk),
      path("M760 1278 L882 1312 L892 1360 L750 1330 Z", theme.sidewalk),
      path("M142 1342 L310 1298 L318 1338 L150 1378 Z", theme.plaza),
      rect(0, 1464, WIDTH, 72, theme.roadDark, { opacity: 0.42 }),
      path("M18 1476 L118 1476 L110 1494 L8 1494 Z", theme.crosswalk, { opacity: 0.92 }),
      path("M142 1476 L242 1476 L234 1494 L132 1494 Z", theme.crosswalk, { opacity: 0.92 }),
      path("M866 1420 L972 1448 L968 1460 L860 1432 Z", theme.crosswalk, { opacity: 0.72 }),
      path("M854 1444 L940 1468 L936 1480 L848 1456 Z", theme.crosswalk, { opacity: 0.72 }),
      line(748, 1330, 884, 1360, theme.curb, 4, { opacity: 0.84 }),
      line(172, 1312, 144, 1398, theme.curb, 4, { opacity: 0.84 }),
      line(104, 1442, 208, 1412, theme.crosswalk, 3, { opacity: 0.28 }),
      line(774, 1406, 898, 1442, theme.crosswalk, 3, { opacity: 0.16 }),
      mode === "night"
        ? ellipse(88, 1462, 52, 12, theme.streetGlow, { opacity: 0.18 })
        : "",
      mode === "night"
        ? ellipse(904, 1418, 60, 12, theme.streetGlow, { opacity: 0.16 })
        : "",
    ].join(""),
  )
}

function renderTree(theme, x, y, scale = 1) {
  return group(
    [
      rect(x + 22 * scale, y + 48 * scale, 10 * scale, 34 * scale, theme.treeTrunk),
      ellipse(x + 26 * scale, y + 42 * scale, 32 * scale, 26 * scale, theme.treeShadow),
      ellipse(x + 14 * scale, y + 34 * scale, 20 * scale, 18 * scale, theme.plantLeaf),
      ellipse(x + 38 * scale, y + 28 * scale, 24 * scale, 18 * scale, theme.plantLeafDark),
      ellipse(x + 26 * scale, y + 18 * scale, 28 * scale, 22 * scale, theme.plantLeaf),
    ].join(""),
  )
}

function renderLampPost(theme, x, y, scale = 1, lit = false) {
  return group(
    [
      rect(x + 4 * scale, y, 6 * scale, 56 * scale, theme.antenna),
      rect(x, y - 8 * scale, 14 * scale, 10 * scale, lit ? theme.lamp : theme.towerFrameSoft, {
        opacity: lit ? 0.9 : 0.54,
      }),
      lit ? ellipse(x + 7 * scale, y + 2 * scale, 26 * scale, 10 * scale, theme.streetGlow, { opacity: 0.14 }) : "",
    ].join(""),
  )
}

function renderCar(theme, x, y, bodyColor, scale = 1) {
  return group(
    [
      roundedRect(x, y, 84 * scale, 28 * scale, 12 * scale, bodyColor),
      roundedRect(x + 18 * scale, y - 14 * scale, 38 * scale, 18 * scale, 8 * scale, bodyColor),
      rect(x + 24 * scale, y - 10 * scale, 14 * scale, 10 * scale, theme.carGlass),
      rect(x + 42 * scale, y - 10 * scale, 12 * scale, 10 * scale, theme.carGlass),
      circle(x + 18 * scale, y + 30 * scale, 8 * scale, theme.towerFrameDark),
      circle(x + 64 * scale, y + 30 * scale, 8 * scale, theme.towerFrameDark),
      rect(x + 4 * scale, y + 10 * scale, 8 * scale, 4 * scale, theme.streetGlow, { opacity: 0.88 }),
    ].join(""),
  )
}

function renderForeground(theme, mode) {
  const people = [
    renderPerson(theme, 178, 1418, 0.74, true),
    renderPerson(theme, 232, 1430, 0.7),
    renderPerson(theme, 320, 1444, 0.72, true),
    renderPerson(theme, 814, 1394, 0.74),
    renderPerson(theme, 902, 1420, 0.72, true),
  ].join("")

  return group(
    [
      renderTree(theme, 84, 1348, 1.2),
      renderTree(theme, 154, 1362, 1.02),
      renderTree(theme, 788, 1354, 1.14),
      renderTree(theme, 860, 1340, 1.06),
      renderLampPost(theme, 132, 1366, 1, mode === "night"),
      renderLampPost(theme, 908, 1366, 1, mode === "night"),
      renderCar(theme, 620, 1486, theme.carA, 1.08),
      renderCar(theme, 880, 1432, mode === "day" ? "#ffffff" : theme.carB, 0.94),
      renderCar(theme, 32, 1498, mode === "day" ? "#6f7e90" : "#243142", 0.86),
      people,
      mode === "night"
        ? ellipse(736, 1506, 88, 16, theme.streetGlow, { opacity: 0.12 })
        : "",
      mode === "night"
        ? ellipse(944, 1456, 78, 16, theme.streetGlow, { opacity: 0.12 })
        : "",
      rect(0, 0, WIDTH, HEIGHT, theme.vignette, { opacity: mode === "day" ? 0.08 : 0.18 }),
    ].join(""),
  )
}

function renderDefs(theme) {
  return tag(
    "defs",
    {},
    [
      tag(
        "linearGradient",
        { id: `${theme.id}-sky`, x1: "0", y1: "0", x2: "0", y2: "1" },
        [
          tag("stop", { offset: "0%", "stop-color": theme.skyTop }, null),
          tag("stop", { offset: "58%", "stop-color": theme.skyBottom }, null),
          tag("stop", { offset: "100%", "stop-color": theme.skyBottom }, null),
        ].join(""),
      ),
      tag(
        "linearGradient",
        { id: `${theme.id}-front-glass`, x1: "0", y1: "0", x2: "0", y2: "1" },
        [
          tag("stop", { offset: "0%", "stop-color": theme.frontGlassTop }, null),
          tag("stop", { offset: "55%", "stop-color": theme.frontGlassTint }, null),
          tag("stop", { offset: "100%", "stop-color": theme.frontGlassBottom }, null),
        ].join(""),
      ),
      tag(
        "linearGradient",
        { id: `${theme.id}-side-glass`, x1: "0", y1: "0", x2: "1", y2: "1" },
        [
          tag("stop", { offset: "0%", "stop-color": theme.sideGlassTop }, null),
          tag("stop", { offset: "62%", "stop-color": theme.sideGlassTint }, null),
          tag("stop", { offset: "100%", "stop-color": theme.sideGlassBottom }, null),
        ].join(""),
      ),
      tag(
        "linearGradient",
        { id: `${theme.id}-shaft-glass`, x1: "0", y1: "0", x2: "0", y2: "1" },
        [
          tag("stop", { offset: "0%", "stop-color": theme.shaftGlassTop }, null),
          tag("stop", { offset: "100%", "stop-color": theme.shaftGlassBottom }, null),
        ].join(""),
      ),
    ].join(""),
  )
}

function renderBuilding(mode, theme) {
  const floorFragments = floors.map((floor, index) => renderFloor(theme, mode, floor, index))
  const lobbyFragment = renderLobby(theme, mode)
  const clipDefs = floorFragments.map((fragment) => fragment.defs).join("") + lobbyFragment.defs
  const buildingShadow = polygon(
    [
      [180, 172],
      [626, 172],
      [850, 224],
      [822, 1440],
      [562, 1470],
      [198, 1420],
    ],
    "#000000",
    { opacity: mode === "day" ? 0.14 : 0.3 },
  )
  const leftEdge = polygon(
    [
      [194, 180],
      [216, 180],
      [216, 1418],
      [194, 1402],
    ],
    theme.towerFrameDark,
  )
  const mainBody = [
    rect(216, 180, 424, 1238, theme.towerFrame),
    leftEdge,
    polygon(
      [
        [640, 180],
        [850, 224],
        [820, 1418],
        [640, 1418],
      ],
      theme.slabFace,
    ),
  ].join("")

  return group(
    [
      buildingShadow,
      mainBody,
      renderRoof(theme, mode),
      floorFragments.map((fragment) => fragment.body).join(""),
      lobbyFragment.body,
      renderCore(theme, mode),
      tag("defs", {}, clipDefs),
      line(216, 180, 640, 180, theme.beamHighlight, 4, { opacity: 0.42 }),
      line(640, 180, 850, 224, theme.beamHighlight, 4, { opacity: 0.24 }),
      rect(212, 1418, 430, 12, theme.slabShadow, { opacity: 0.54 }),
    ].join(""),
  )
}

function createScene(mode) {
  const theme = themes[mode]

  return [
    `<?xml version="1.0" encoding="UTF-8"?>`,
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${WIDTH} ${HEIGHT}" width="${WIDTH}" height="${HEIGHT}" shape-rendering="geometricPrecision">`,
    renderDefs(theme),
    renderSky(mode, theme),
    renderFarCity(mode, theme),
    renderStreet(theme, mode),
    renderBuilding(mode, theme),
    renderForeground(theme, mode),
    `</svg>`,
  ].join("")
}

const currentFile = fileURLToPath(import.meta.url)
const receptionDir = dirname(dirname(currentFile))
const outputDir = join(receptionDir, "public", "skyscraper-assets-v2", "base")

mkdirSync(outputDir, { recursive: true })

writeFileSync(join(outputDir, "tower-hero-day.svg"), createScene("day"), "utf8")
writeFileSync(join(outputDir, "tower-hero-night.svg"), createScene("night"), "utf8")
