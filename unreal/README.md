# NeuralFur → Unreal Engine

Toolkit for **processing, importing, and animating** furry animals reconstructed with [NeuralFur](https://github.com/Vanessik/NeuralFur) in **Unreal Engine 5.4+**.

Starting from a NeuralFur reconstruction (the fur-strand `.ply` and the furless body `.obj`), this toolkit converts them to Alembic, imports them into Unreal as a Groom bound to a Geometry Cache, and optionally animates them via the SMAL skeleton.

## Documentation

| Step | Doc | What it covers |
|---|---|---|
| 1 | [Process](docs/01-process.md) | Convert strand PLY + body OBJ → Alembic |
| 2 | [Import](docs/02-import.md) | Automated UE import: Groom, Geometry Cache, Binding, Sequence |
| 3 | [Animate](docs/03-animate.md) | SMAL skeletal mesh, motion retargeting, fur simulation |

## Requirements

**Software**

- Python 3.11 with the `bpy` (Blender 4.x) pip module, or run the Blender scripts with Blender's bundled Python
- Unreal Engine **5.4+** with plugins: *Python Editor Script Plugin*, *Groom*, *Alembic Groom Importer*. These must be enabled in your project as described in [docs/02-import.md](docs/02-import.md), otherwise the import script fails (e.g. `AttributeError: module 'unreal' has no attribute 'GroomConversionSettings'`)

**Python packages**

```bash
pip install -r requirements.txt
```

The animation step ([docs/03-animate.md](docs/03-animate.md)) additionally needs `torch`, `smplx`, and the SMAL model file (`smal_plus.pkl`). The SMAL model is not distributed with this repo : download it from the [GenZoo download page](https://genzoo.is.tue.mpg.de/download.php) (registration required) and place it in `data/smal/`.

## Quickstart

```bash
# 1. Convert NeuralFur outputs to Alembic files (Groom <strands>.abc + Animal <furless>.abc)
python process.py --ply <strands>.ply --obj <furless>.obj
```

Then, inside the Unreal Editor (Output Log → Cmd mode):

```bash
# 2. Import the animal and build a render-ready sequence
py "<repo>/src/unreal/ue_import.py" --groom <strands>.abc --geo <furless>.abc
```

To animate the animal and make the fur follow, see [docs/03-animate.md](docs/03-animate.md).

## Layout

```
process.py                          PLY + OBJ → ABC
src/
├── blender/                        Run with Blender's Python (bpy)
│   ├── fur_ply_to_abc.py           Strand PLY → groom ABC
│   ├── obj_to_abc.py               Body OBJ → geometry ABC
│   ├── smal_to_fbx.py              SMAL fit → UE-ready skeletal mesh FBX
│   ├── smal_model.py               SMAL model forward pass (torch/smplx)
│   ├── weights_transfer.py         SMAL → high-res mesh weight transfer
│   └── combine_motions.py          Init pose + motion FBXs → one FBX/ABC
└── unreal/                         Run inside the Unreal Editor (py ...)
    └── ue_import.py                Import ABCs, build bindings & sequences
docs/                               Step-by-step documentation
```
