"""Convert NeuralFur strand PLY files to Alembic (.abc) grooms for Unreal Engine.

The input PLY stores the fur as a flat list of vertices, where every strand has
a fixed number of points (100 by default for NeuralFur outputs). The script:

1. Loads the strands and reshapes them to (n_strands, points_per_strand, 3).
2. Optionally snaps strand roots onto the body ("scalp") mesh surface.
3. Converts from the NeuralFur/Blender axis convention to the one expected by
   the Unreal groom importer.
4. Exports a single-frame Alembic file with the `groom_group_id` attribute so
   Unreal recognises it as a groom.

Run with Blender's Python (either `blender --background --python ...` or the
`bpy` pip module):

    python -m src.blender.fur_ply_to_abc --ply_fname fur.ply
"""
import os
import os.path as osp
import argparse

import bpy
import numpy as np
import trimesh

POINTS_PER_STRAND = 100  # NeuralFur exports 100 points per strand


def clean_scene():
    for o in bpy.context.scene.objects:
        o.select_set(True)
    bpy.ops.object.delete()
    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)
    for block in bpy.data.materials:
        if block.users == 0:
            bpy.data.materials.remove(block)
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.object.select_by_type(type='CURVE')
    bpy.ops.object.delete()


def attach_origins_to_scalp(scalp_path, strands):
    """Shift each strand so its root lies exactly on the scalp mesh surface."""
    scalp = trimesh.load_mesh(scalp_path)
    origins = strands[:, 0, :]
    proximity = trimesh.proximity.ProximityQuery(scalp)
    closest, _, _ = proximity.on_surface(origins)
    shift = (closest - origins).reshape(-1, 1, 3)
    return strands + shift


def create_hair(name: str, strands: np.ndarray):
    curve_data = bpy.data.curves.new('hair', type='CURVE')
    curve_data.dimensions = '3D'
    curve_data.resolution_u = 1
    for strand in strands:
        polyline = curve_data.splines.new('POLY')
        polyline.points.add(len(strand) - 1)
        for i, (x, y, z) in enumerate(strand):
            polyline.points[i].co = (x, y, z, i)
    curve_obj = bpy.data.objects.new(name, curve_data)
    bpy.data.scenes[0].collection.objects.link(curve_obj)
    return bpy.data.objects[name]


def import_hair_from_ply(ply_fname, n_strands_target, obj_fname=None,
                         points_per_strand=POINTS_PER_STRAND):
    strands = np.array(trimesh.load(ply_fname).vertices)
    print(f'Loaded {strands.shape[0]} vertices from {ply_fname}')
    strands = strands.reshape(-1, points_per_strand, 3)

    if obj_fname is not None:
        strands = attach_origins_to_scalp(obj_fname, strands)

    if strands.shape[0] > n_strands_target:
        sampled_idx = np.random.choice(strands.shape[0], n_strands_target, replace=False)
        strands = strands[sampled_idx, ...]

    # NeuralFur/Blender axes -> groom axes expected by the Unreal importer
    strands = strands[:, :, [0, 2, 1]]
    strands[:, :, 1] *= -1

    return create_hair('Hair', strands)


def export_hair_object_as_alembic_for_unreal(hair_object_name, out_fname):
    obj = bpy.data.objects[hair_object_name]
    bpy.context.view_layer.objects.active = obj
    obj = bpy.context.active_object

    # Mark the object as a groom for the Unreal Alembic Groom importer
    obj['groom_group_id'] = 0
    obj['groom_group_id_AbcGeomScope'] = 'con'

    out_dir = osp.dirname(out_fname)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    bpy.ops.wm.alembic_export(filepath=out_fname, start=1, end=1, export_hair=False, export_particles=False,
                              orcos=False, xsamples=1, gsamples=1, sh_open=0.0, sh_close=1.0, selected=False,
                              visible_objects_only=False, flatten=False, uvs=False, packuv=False, normals=False,
                              vcolors=False, face_sets=False, subdiv_schema=False, apply_subdiv=False,
                              curves_as_mesh=False, use_instancing=True, global_scale=1.0, triangulate=False,
                              quad_method='SHORTEST_DIAGONAL', ngon_method='BEAUTY', export_custom_properties=True,
                              as_background_job=False, evaluation_mode='RENDER', init_scene_frame_range=True)


def process_hair(ply_fname, out_abc_fname, n_strands_max, obj_fname=None,
                 points_per_strand=POINTS_PER_STRAND):
    clean_scene()
    import_hair_from_ply(ply_fname, n_strands_target=n_strands_max, obj_fname=obj_fname,
                         points_per_strand=points_per_strand)
    export_hair_object_as_alembic_for_unreal(hair_object_name='Hair', out_fname=out_abc_fname)
    print(f'Wrote: {out_abc_fname}')


def main():
    parser = argparse.ArgumentParser(description='Convert a NeuralFur strand PLY to an Alembic groom.')
    parser.add_argument('--ply_fname', type=str, required=True,
                        help='Input strand PLY (flat vertex list, fixed points per strand)')
    parser.add_argument('--obj_fname', type=str, default=None,
                        help='Optional body/scalp OBJ; strand roots are snapped onto its surface')
    parser.add_argument('--out_abc_fname', type=str, default=None,
                        help='Output .abc path (default: next to the input PLY)')
    parser.add_argument('--n_strands_max', type=int, default=99000000,
                        help='Randomly subsample to at most this many strands')
    parser.add_argument('--points_per_strand', type=int, default=POINTS_PER_STRAND)
    args = parser.parse_args()

    out_abc_fname = args.out_abc_fname or args.ply_fname.replace('.ply', '.abc')
    process_hair(args.ply_fname, out_abc_fname, args.n_strands_max, args.obj_fname,
                 args.points_per_strand)


if __name__ == '__main__':
    main()
