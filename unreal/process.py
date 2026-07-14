#!/usr/bin/env python3
"""Convert NeuralFur data (strand PLY + furless body OBJ) to Alembic files.

Writes <ply>.abc (groom) and <obj>.abc (geometry) next to the inputs.

Usage:
    python process.py --ply fur.ply --obj furless.obj

Requires Blender's Python (the `bpy` pip module) plus numpy and trimesh.
"""
import argparse
from pathlib import Path

from src.blender.fur_ply_to_abc import process_hair
from src.blender.obj_to_abc import convert_obj_to_abc


def main():
    ap = argparse.ArgumentParser(description='Convert a strand PLY and a body OBJ to Alembic (.abc).')
    ap.add_argument('--ply', type=str, required=True, help='Fur strand PLY file')
    ap.add_argument('--obj', type=str, required=True, help='Furless body OBJ file')
    ap.add_argument('--n_strands_max', type=int, default=10000000,
                    help='Randomly subsample the groom to at most this many strands')
    args = ap.parse_args()

    ply, obj = Path(args.ply), Path(args.obj)
    process_hair(str(ply), str(ply.with_suffix('.abc')), args.n_strands_max)
    convert_obj_to_abc(str(obj), str(obj.with_suffix('.abc')))


if __name__ == '__main__':
    main()
