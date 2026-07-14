"""Convert a body OBJ mesh to a single-frame Alembic (.abc) file.

The .abc can be imported in Unreal Engine as a Geometry Cache, which is the
mesh type a groom can be bound to.

    python -m src.blender.obj_to_abc --input furless.obj
"""
import os.path as osp
import argparse

import bpy


def convert_obj_to_abc(input_path: str, out_path: str | None = None) -> str:
    in_path = osp.abspath(input_path)
    out_path = out_path or (osp.splitext(in_path)[0] + '.abc')

    # Clean scene
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

    # Import OBJ (Blender 3.x+)
    bpy.ops.wm.obj_import(filepath=in_path)

    # Smooth shading
    for obj in bpy.context.selected_objects:
        if obj.type == 'MESH':
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.shade_smooth()

    # Export Alembic (single frame)
    bpy.ops.wm.alembic_export(filepath=out_path, start=1, end=1)

    print(f'Wrote: {out_path}')
    return out_path


def main():
    parser = argparse.ArgumentParser(description='Convert OBJ to ABC in Blender')
    parser.add_argument('--input', '-i', type=str, required=True, help='Input OBJ file path')
    parser.add_argument('--out', '-o', type=str, default=None, help='Output Alembic file path')
    args = parser.parse_args()

    convert_obj_to_abc(args.input, args.out)


if __name__ == '__main__':
    main()
