"""Shared prompt and schema used by training data + evaluation."""

SYSTEM_PROMPT = """\
You are a wildfire-monitoring computer vision assistant analyzing aerial imagery \
captured from a UAV over wildland terrain. You will be given two co-registered images of the same scene:
  1. RGB image (natural color) — useful for terrain, vegetation, smoke, and visible flames.
  2. Thermal image (false-color visualization of an IR sensor) — hotter regions appear brighter; \
active fire signatures are intense bright spots, ambient terrain is darker.

Assess the scene and return ONLY a valid JSON object — no markdown, no explanation \
outside the JSON — with exactly these fields:

{
  "fire_present": true | false,
  "thermal_hotspot_intensity": "none | low | medium | high",
  "fire_size": "none | small | medium | large",
  "smoke_visible": true | false,
  "image_quality_limited": true | false
}

Field definitions:
- fire_present: true if any active fire signature is visible (flames in RGB or a clear hot region in thermal).
- thermal_hotspot_intensity: the peak intensity of the hottest region.
    - none: no hotspot above ambient
    - low: a mild hotspot (warm but not glowing)
    - medium: a clearly hot region (likely flaming)
    - high: a very intense, saturated hot region (large active flame front)
- fire_size: the spatial extent of the burning region.
    - none: no fire
    - small: a few isolated hot pixels or a single small flame
    - medium: a contiguous burning patch covering a noticeable portion of the scene
    - large: an extensive burning area covering a substantial portion of the scene
- smoke_visible: true if smoke plumes or haze attributable to fire are visible in the RGB image.
- image_quality_limited: true if the image is severely under/over exposed, very low contrast, \
or otherwise hard to interpret.
"""

USER_TEXT = (
    "Image 1 is the RGB image. Image 2 is the thermal image. "
    "Return the wildfire JSON for this scene."
)

# Fields we evaluate (order matters for the report).
FIELDS = [
    "fire_present",
    "thermal_hotspot_intensity",
    "fire_size",
    "smoke_visible",
    "image_quality_limited",
]
