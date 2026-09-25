# Stage 6 – Materials System

## Goals
- Fully PBR
- Procedural where possible + texture support
- Driven by Geometry Nodes attributes (panel ID, wear masks, curvature)
- Easy art direction (wear amount linked to root empty)

## Core Materials

| Name                        | Use Case                     | Key Features                          |
|-----------------------------|------------------------------|---------------------------------------|
| M_THR_Metal_Primary         | Main body                    | Anisotropic optional, edge wear       |
| M_THR_Metal_Burnt           | Exhaust / heat areas         | Darkened, emissive heat, roughness    |
| M_THR_Ceramic_Heatshield    | Nozzle tiles                 | High roughness, subtle variation      |
| M_THR_Paint_Warning         | Warning stripes / labels     | Masked paint layer                    |
| M_THR_Emissive_Glow         | Status lights / thruster glow| Strength controlled by custom prop    |

## Layered Material Approach

Use a single complex shader or multiple materials with attributes:

1. Base metal
2. Paint layer (masked)
3. Dirt / grime (from AO + cavity)
4. Edge wear (from curvature or bevel weight attribute)
5. Heat gradient (proximity to nozzle or manual attribute)

## Attribute Workflow
From Geometry Nodes:
- Store Named Attribute → `ATTR_WearMask`
- Store Named Attribute → `ATTR_PanelID`
- In Shader Editor: Attribute node → use as mix factor

## Linking to Root Empty
Use Drivers or simple Python to push `prop_wear_amount` into material node values so one slider controls global wear.

## Texture Naming
```
TEX_THR_Metal_Albedo_4k.png
TEX_THR_Metal_Normal_4k.png
TEX_THR_Metal_Roughness_4k.png
TEX_THR_AO_4k.png
TEX_THR_Curvature_4k.png
```
