---
name: holo_builder
trigger: When the user wants to build or modify holographic 3D models
freedom: high
gotchas:
  - Complex models may take time to generate
  - Export format matters for downstream use
  - Requires numpy, scipy for point cloud processing
---

action: "create", "modify", "export", "import"
model_type: "sphere", "cube", "torus", "custom", "terrain"
Uses marching_cubes for 3D mesh generation from volume data.
Returns: 3D model file path (.obj, .stl) or render preview.