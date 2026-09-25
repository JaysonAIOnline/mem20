# Strict Naming Conventions

Consistency is non-negotiable in a real pipeline.

## 1. Object / Collection Naming

```
Prefix_AssetName_Component_Variant_LOD

Examples:
THR_Thruster_MainBody_A_LOD0
THR_Thruster_Nozzle_A_LOD0
THR_Thruster_CoolingFin_L_01
THR_Thruster_CableBundle_A
COL_THR_Thruster_Root
COL_THR_High
COL_THR_Low
COL_THR_Cutters
COL_THR_GN_Details
```

### Prefixes
| Prefix | Meaning                  |
|--------|--------------------------|
| THR_   | Thruster family          |
| COL_   | Collection               |
| CUT_   | Boolean cutter           |
| GN_    | Geometry Nodes object    |
| M_     | Material                 |
| TEX_   | Texture                  |
| BAK_   | Bake cage / high poly    |
| EXP_   | Export ready             |

## 2. Geometry Nodes Group Naming

```
GN_<Category>_<DescriptiveName>

Examples:
GN_Detail_PanelLines
GN_Detail_RivetsCircular
GN_Detail_VentRectangular
GN_Utility_AttributeTransfer
GN_Scatter_Greeble
```

## 3. Vertex Groups / Attributes

```
VG_BevelWeight
VG_Crease
VG_PanelMask
VG_RivetsMask
VG_WearMask
ATTR_PanelID
ATTR_MaterialID
```

## 4. Custom Properties (on root empty)

```
prop_scale          (float)
prop_detail_density (float 0-2)
prop_wear_amount    (float 0-1)
prop_version        (string)
prop_artist         (string)
```

## 5. Material Naming

```
M_THR_Metal_Primary
M_THR_Metal_Burnt
M_THR_Ceramic_Heatshield
M_THR_Paint_Warning
M_THR_Emissive_Glow
```

## 6. File Naming

```
THR_Thruster_Assembly_v001.blend
THR_Thruster_Assembly_v001_high.fbx
THR_Thruster_Assembly_v001_LOD0.glb
```

**Rule:** Never use spaces. Use PascalCase or snake_case consistently. Version numbers are mandatory on published files.
