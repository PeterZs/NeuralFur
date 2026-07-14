"""Combine an init-pose FBX with one or more animation FBXs (same skeleton)
into a single sequential animation, and export it as FBX + Alembic.

This automates the manual Blender workflow of importing the init pose,
pasting animation keyframes after it (Blender interpolates from the init pose
into the motion), and exporting an .abc geometry cache for Unreal:

    python -m src.blender.combine_motions \
        --ref-fbx panda_init_pose.fbx \
        --motions-dir retargeted_motions/ \
        --out-fbx combined_motion.fbx --out-abc combined_motion.abc

The reference FBX (init pose, including the skinned mesh) is placed first on
the timeline; every FBX in --motions-dir is appended in filename order with a
one-frame gap (so Blender interpolates between clips). The resulting .abc can
be imported in Unreal as a Geometry Cache and used as the groom binding target.
"""
import argparse
from pathlib import Path

import bpy


def import_fbx(path, global_scale=1.0):
    """Import an FBX and return the newly created objects and actions."""
    before_objs = set(bpy.data.objects)
    before_actions = set(bpy.data.actions)

    bpy.ops.import_scene.fbx(
        filepath=str(path),
        global_scale=global_scale,
        automatic_bone_orientation=True,
        use_prepost_rot=True,
    )

    new_objs = [obj for obj in bpy.data.objects if obj not in before_objs]
    new_actions = [act for act in bpy.data.actions if act not in before_actions]
    return new_objs, new_actions


def find_new_armatures(objs):
    return [o for o in objs if o.type == 'ARMATURE']


def ensure_animdata(obj):
    if obj.animation_data is None:
        obj.animation_data_create()
    return obj.animation_data


def set_scene_fps(fps):
    if fps is None:
        return
    scene = bpy.context.scene
    scene.render.fps = int(fps)
    scene.render.fps_base = 1.0


def select_only(objs):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    if objs:
        bpy.context.view_layer.objects.active = objs[0]


def delete_objects(objs):
    if not objs:
        return
    select_only(objs)
    bpy.ops.object.delete(use_global=False, confirm=False)


def combine_motions(ref_fbx: Path, motions_dir: Path, out_fbx: Path, out_abc: Path,
                    fps=None, fbx_import_scale=1.0):
    assert ref_fbx.exists() and ref_fbx.suffix.lower() == '.fbx', 'ref_fbx must be an existing .fbx file'
    assert motions_dir.exists() and motions_dir.is_dir(), 'motions_dir must be a directory'

    # Start from an empty scene (no default cube/camera/light in the export)
    bpy.ops.wm.read_homefile(use_empty=True)

    set_scene_fps(fps)

    # --- 1) Import the reference FBX and pick its armature as the master ---
    print(f'[INFO] Importing reference FBX: {ref_fbx}')
    ref_objs, ref_actions = import_fbx(ref_fbx, global_scale=fbx_import_scale)
    ref_armatures = find_new_armatures(ref_objs)
    if not ref_armatures:
        raise RuntimeError('No armature found in reference FBX.')

    master_arm = ref_armatures[0]
    print(f'[INFO] Master armature: {master_arm.name}')

    # --- 2) Import the other motions (excluding the reference file and any
    # previous output of this script that may sit in the same folder) ---
    excluded = {ref_fbx.resolve(), out_fbx.resolve()}
    file_list = sorted((f for f in motions_dir.iterdir()
                        if f.is_file() and f.suffix.lower() == '.fbx'),
                       key=lambda f: f.name.lower())
    file_list = [f for f in file_list if f.resolve() not in excluded]
    print(f'[INFO] Found {len(file_list)} additional FBX files to append.')

    imported_temp_objects = []
    per_file_actions = []

    for f in file_list:
        print(f'[INFO] Importing motion: {f.name}')
        new_objs, new_actions = import_fbx(f, global_scale=fbx_import_scale)
        imported_temp_objects.extend(new_objs)
        if not new_actions:
            print(f'[WARN] No new actions detected for {f.name}.')
        for a in new_actions:
            per_file_actions.append((f.name, a))
            print(f'  - Captured action: {a.name}  frames={list(map(int, a.frame_range))}')

    # --- 3) Build one NLA track on the master armature with sequential strips ---
    ad = ensure_animdata(master_arm)
    for tr in list(ad.nla_tracks):
        ad.nla_tracks.remove(tr)

    track = ad.nla_tracks.new()
    track.name = 'CombinedMotions'

    frame_cursor = 1

    def add_action_strip(action, label=None):
        nonlocal frame_cursor
        f0, f1 = action.frame_range
        length = int(round(f1 - f0))
        if length <= 0:
            print(f'[WARN] Action {action.name} has zero/negative length; skipping.')
            return
        strip = track.strips.new(name=(label or action.name), start=frame_cursor, action=action)
        strip.action_frame_start = f0
        strip.action_frame_end = f1
        # One-frame gap between strips so Blender interpolates between clips
        frame_cursor += length + 1

    print(f'[INFO] Adding reference actions first ({len(ref_actions)} found).')
    for a in ref_actions:
        add_action_strip(a, label=f'REF::{a.name}')

    print(f'[INFO] Adding {len(per_file_actions)} actions from motions dir.')
    for fname, act in per_file_actions:
        add_action_strip(act, label=f'{fname}::{act.name}')

    # Unlink the active action: an active action overrides the NLA stack, so
    # leaving the (static) ref-pose action assigned would freeze the export.
    ad.action = None

    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = max(1, frame_cursor)

    # Remove imported temp objects (their actions are already harvested)
    to_delete = [o for o in imported_temp_objects if o != master_arm]
    print(f'[INFO] Cleaning up {len(to_delete)} temporary objects.')
    delete_objects(to_delete)

    # --- 4) Export ---
    out_fbx.parent.mkdir(parents=True, exist_ok=True)
    out_abc.parent.mkdir(parents=True, exist_ok=True)

    print(f'[INFO] Exporting FBX -> {out_fbx}')
    bpy.ops.export_scene.fbx(
        filepath=str(out_fbx),
        use_selection=False,
        add_leaf_bones=False,
        apply_unit_scale=True,
        apply_scale_options='FBX_SCALE_ALL',
        bake_anim=True,
        bake_anim_use_all_actions=False,
        bake_anim_use_nla_strips=True,  # export the sequential NLA we built
        bake_anim_simplify_factor=0.0,
        bake_anim_step=1.0,
        object_types={'ARMATURE', 'MESH', 'EMPTY'},
        path_mode='COPY',
    )

    print(f'[INFO] Exporting Alembic -> {out_abc}')
    bpy.ops.wm.alembic_export(
        filepath=str(out_abc),
        start=bpy.context.scene.frame_start,
        end=bpy.context.scene.frame_end,
        xsamples=1,
        gsamples=1,
        selected=False,
        flatten=False,
        visible_objects_only=False,
        global_scale=1.0,
        triangulate=False,
    )

    print('[DONE] Combined motion created and exported.')


def main():
    parser = argparse.ArgumentParser(description='Combine FBX motions into one sequential FBX + Alembic.')
    parser.add_argument('--ref-fbx', type=str, required=True,
                        help='Reference/init-pose FBX (with skinned mesh); goes first on the timeline')
    parser.add_argument('--motions-dir', type=str, required=True,
                        help='Directory with animation FBXs (same skeleton) to append in filename order')
    parser.add_argument('--out-fbx', type=str, default='combined_motion.fbx')
    parser.add_argument('--out-abc', type=str, default='combined_motion.abc')
    parser.add_argument('--fps', type=int, default=None,
                        help='Scene FPS (default: keep whatever the first FBX sets)')
    parser.add_argument('--fbx-import-scale', type=float, default=1.0)
    args = parser.parse_args()

    combine_motions(Path(args.ref_fbx), Path(args.motions_dir),
                    Path(args.out_fbx), Path(args.out_abc),
                    fps=args.fps, fbx_import_scale=args.fbx_import_scale)


if __name__ == '__main__':
    main()
