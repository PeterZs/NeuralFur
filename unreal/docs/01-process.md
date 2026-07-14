# 1. Process : NeuralFur outputs → Alembic

Converts the [NeuralFur](https://github.com/Vanessik/NeuralFur) data into Alembic (`.abc`) files that Unreal Engine can import.

## Input data

Each animal needs two files, both part of the NeuralFur data:

| File | Content |
|---|---|
| strands `.ply` | The reconstructed fur strands: a flat list of vertices, **100 points per strand** |
| furless `.obj` | The furless body mesh |

## Run

```bash
python process.py --ply <strands>.ply --obj <furless>.obj
```

Options:

- `--n_strands_max <N>` : randomly subsample the groom to at most N strands (useful to keep editor performance manageable while testing).

This writes, next to each input file:

- `<strands>.abc` : the groom (fur strands with the `groom_group_id` attribute, single frame)
- `<furless>.abc` : the body geometry (single frame)

## Individual conversions

`process.py` just calls these two scripts, which can also be run directly:

```bash
# Fur strands PLY -> groom ABC
python -m src.blender.fur_ply_to_abc --ply_fname fur.ply [--obj_fname furless.obj] [--n_strands_max 500000]

# Body OBJ -> geometry ABC
python -m src.blender.obj_to_abc --input furless.obj
```

`--obj_fname` optionally snaps every strand root exactly onto the body surface before export (useful if the strands float slightly off the mesh).

## What the fur conversion does

1. Loads the PLY vertices and reshapes them to `(n_strands, 100, 3)`.
2. Optionally attaches strand origins to the body surface.
3. Swaps the Y/Z axes (and negates Y) to match what the Unreal groom importer expects.
4. Builds one Blender `POLY` curve object holding all strands and tags it with `groom_group_id = 0`, which makes Unreal's Alembic Groom importer recognise it as a groom.
5. Exports a single-frame Alembic file.

Next step: [2. Import into Unreal Engine](02-import.md)
