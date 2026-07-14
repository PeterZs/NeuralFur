"""Create a SMAL skeletal mesh and export it as a UE-ready FBX.

Takes a SMAL mesh fitted to the animal in init pose : the same pose the fur
was reconstructed in  and uses it as the SMAL
model's v_template to rebuild the skeleton (joints + LBS weights) for that
specific animal shape.
Optionally also skins the high-res furless mesh by transferring the SMAL
weights onto it.

Outputs (in --out-dir):
  <name>_smal.fbx        skinned SMAL-resolution skeletal mesh (init pose)
  <name>_high_res.fbx    skinned high-res furless mesh (if --furless-obj given)
  <name>.blend           Blender scene for debugging

Import the FBX in Unreal Engine to retarget motions onto the SMAL skeleton
(see docs/03-animate.md).

Requires Blender's Python (`bpy`), plus numpy, trimesh, torch, smplx and the
SMAL model pkl:

    python -m src.blender.smal_to_fbx --smal-obj smal.obj \
        --furless-obj furless.obj --name panda \
        --smal-model data/smal/smal_plus.pkl --out-dir output
"""
import argparse
import os
from math import radians

import bpy
import numpy as np
import trimesh
from mathutils import Vector

from src.blender.smal_model import smal_fwd_pass, DEFAULT_MODEL_PATH
from src.blender.weights_transfer import transfer_weights, validate_weights


# SMAL skeleton definition (35 joints)
PARENT_IDS = [
    -1,   # 0: root
    0,    # 1
    1,    # 2
    2,    # 3
    3,    # 4
    4,    # 5
    5,    # 6
    6,    # 7
    7,    # 8
    8,    # 9
    9,    # 10
    6,    # 11
    11,   # 12
    12,   # 13
    13,   # 14
    6,    # 15
    15,   # 16
    0,    # 17
    17,   # 18
    18,   # 19
    19,   # 20
    0,    # 21
    21,   # 22
    22,   # 23
    23,   # 24
    0,    # 25
    25,   # 26
    26,   # 27
    27,   # 28
    28,   # 29
    29,   # 30
    30,   # 31
    16,   # 32
    16,   # 33
    16    # 34
]

JOINT_NAMES = {
    0: 'pelvis',
    1: 'pelvis0',
    2: 'spine',
    3: 'spine0',
    4: 'spine1',
    5: 'spine2',
    6: 'spine3',
    7: 'LLeg1',
    8: 'LLeg2',
    9: 'LLeg3',
    10: 'LFoot',
    11: 'RLeg1',
    12: 'RLeg2',
    13: 'RLeg3',
    14: 'RFoot',
    15: 'Neck',
    16: 'Head',
    17: 'LLegBack1',
    18: 'LLegBack2',
    19: 'LLegBack3',
    20: 'LFootBack',
    21: 'RLegBack1',
    22: 'RLegBack2',
    23: 'RLegBack3',
    24: 'RFootBack',
    25: 'Tail1',
    26: 'Tail2',
    27: 'Tail3',
    28: 'Tail4',
    29: 'Tail5',
    30: 'Tail6',
    31: 'Tail7',
    32: 'Mouth',
    33: 'LEar',
    34: 'REar'
}


def load_vertices_faces(obj_path):
    mesh = trimesh.load(obj_path, force='mesh')
    return mesh.vertices, mesh.faces  # (V, 3), (F, 3)


def create_mesh(vertices, faces, name):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    create_material(obj, name)
    return obj


def create_material(target_obj, name):
    if name in bpy.data.materials:
        target_obj.data.materials.append(bpy.data.materials[name])
        return

    mat = bpy.data.materials.new(name=name)
    target_obj.data.materials.append(mat)

    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    for node in nodes:
        nodes.remove(node)

    node = nodes.new('ShaderNodeBsdfPrincipled')
    node.inputs[0].default_value = (0.8, 0.8, 0.8, 1.0)
    node.inputs[7].default_value = 0.6  # Roughness

    node_output = nodes.new(type='ShaderNodeOutputMaterial')
    mat.node_tree.links.new(node.outputs[0], node_output.inputs[0])


def create_armature(joints_pos, name, num_joints=35):
    bpy.ops.object.armature_add()
    armature_object = bpy.context.selected_objects[0]
    armature_object.name = name
    armature_object.data.name = f'{name}_data'
    armature_object.location = (0, 0, 0)
    armature = armature_object.data
    armature.bones[0].name = 'root'

    print(f'Creating armature. Number of joints: {num_joints}')

    bpy.ops.object.mode_set(mode='EDIT')
    for index in range(num_joints):
        bpy.ops.armature.bone_primitive_add(name=JOINT_NAMES[index])

    # All bones initially start at the origin
    for bone in armature.edit_bones:
        bone.head = (0.0, 0.0, 0.0)
        bone.tail = (0.0, 0.0, 0.1)

    # Bone hierarchy + positions ('root' is bone 0, so SMAL joint i is bone i+1)
    for index in range(num_joints):
        parent_index = PARENT_IDS[index]
        armature.edit_bones[index + 1].parent = armature.edit_bones[parent_index + 1]
        armature.edit_bones[JOINT_NAMES[index]].translate(Vector(joints_pos[index]))

    bpy.ops.object.mode_set(mode='OBJECT')
    return armature_object


def blend_mesh_to_armature(mesh_obj, armature_obj, lbs_weights):
    # Bind mesh to armature (creates empty vertex groups per bone)
    mesh_obj.select_set(True)
    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.parent_set(type='ARMATURE_NAME')

    # Remove the 'root' vertex group (no weights)
    bpy.context.view_layer.objects.active = mesh_obj
    mesh_obj.vertex_groups.active_index = 0
    bpy.ops.object.vertex_group_remove()

    # Set skin weights
    for index, vertex_weights in enumerate(lbs_weights):
        for joint_index, joint_weight in enumerate(vertex_weights):
            if joint_weight > 0.0:
                vg = mesh_obj.vertex_groups[JOINT_NAMES[joint_index]]
                vg.add([index], joint_weight, 'REPLACE')

    mesh_obj.select_set(True)
    bpy.ops.object.shade_smooth()


def create_skeletal_mesh_using_v_template(vertices, name, model_path):
    """Run the SMAL forward pass with the given v_template and build the
    skinned mesh + armature in Blender (rotated for Unreal export)."""
    vertices, faces, joints, lbs_weights = smal_fwd_pass(v_template=vertices, model_path=model_path)
    vertices = np.array(vertices, dtype=np.float32)[0]
    joints = np.array(joints, dtype=np.float32)[0]
    mesh_obj = create_mesh(vertices, faces, name)
    armature_obj = create_armature(joints, f'{name}_armature')

    # Rotate to prepare for Unreal Engine
    for obj in (armature_obj, mesh_obj):
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        obj.rotation_euler = (radians(90), 0, 0)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)

    blend_mesh_to_armature(mesh_obj, armature_obj, lbs_weights)
    return mesh_obj, armature_obj


def export_fbx(obj_mesh, filepath, target_format='UNREAL'):
    bpy.ops.object.mode_set(mode='OBJECT')
    context = bpy.context

    armature_original = obj_mesh.parent
    skinned_mesh_original = obj_mesh

    if armature_original is None:
        print(f"Error: Mesh '{obj_mesh.name}' has no parent armature. Skipping FBX export.")
        return

    # Operate on a temporary copy of skinned mesh and armature
    bpy.ops.object.select_all(action='DESELECT')
    skinned_mesh_original.select_set(True)
    armature_original.select_set(True)
    bpy.context.view_layer.objects.active = skinned_mesh_original
    bpy.ops.object.duplicate()
    skinned_mesh = bpy.context.object
    armature = skinned_mesh.parent

    # Apply armature object location to armature root bone and skinned mesh so
    # that armature and skinned mesh are at the origin before export
    context.view_layer.objects.active = armature
    armature_offset = Vector(armature.location)
    armature.location = (0, 0, 0)
    bpy.ops.object.mode_set(mode='EDIT')
    for edit_bone in armature.data.edit_bones:
        if edit_bone.name != 'root':
            edit_bone.translate(armature_offset)

    bpy.ops.object.mode_set(mode='OBJECT')
    context.view_layer.objects.active = skinned_mesh
    mesh_location = Vector(skinned_mesh.location)
    skinned_mesh.location = mesh_location + armature_offset
    bpy.ops.object.transform_apply(location=True)

    # Bake a -90/+90 X rotation so the model imports with rotation (0, 0, 0)
    bpy.ops.object.mode_set(mode='OBJECT')

    bpy.ops.object.select_all(action='DESELECT')
    skinned_mesh.select_set(True)
    skinned_mesh.rotation_euler = (radians(-90), 0, 0)
    bpy.context.view_layer.objects.active = skinned_mesh
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    skinned_mesh.rotation_euler = (radians(90), 0, 0)
    skinned_mesh.select_set(False)

    armature.select_set(True)
    armature.rotation_euler = (radians(-90), 0, 0)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    armature.rotation_euler = (radians(90), 0, 0)

    if target_format == 'UNREAL':
        # Scale armature by 100 so the Unreal FBX importer can be used with
        # default scale 1. This ensures objects attached to the imported
        # skeleton in Unreal keep scale 1.
        armature.scale = (100, 100, 100)

        # Scale keyframed pelvis locations if available
        if armature.animation_data is not None:
            action = armature.animation_data.action
            for fcurve in action.fcurves:
                if fcurve.data_path.endswith('location'):
                    for keyframe_point in fcurve.keyframe_points:
                        keyframe_point.co[1] = keyframe_point.co[1] * 100
                        keyframe_point.handle_left[1] = keyframe_point.handle_left[1] * 100
                        keyframe_point.handle_right[1] = keyframe_point.handle_right[1] * 100

        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    skinned_mesh.select_set(True)

    # Only export the active animation (we duplicated the armature, so default
    # settings would export the animation twice). Keyframe simplification is
    # disabled so FBX animation matches any exported Alembic cache exactly.
    bpy.ops.export_scene.fbx(filepath=filepath,
                             use_selection=True,
                             apply_scale_options='FBX_SCALE_ALL',
                             use_custom_props=True,
                             add_leaf_bones=False,
                             bake_anim_use_nla_strips=False,
                             bake_anim_use_all_actions=False,
                             bake_anim_simplify_factor=0)

    print('Exported: ' + filepath)


def create_fbx(smal_obj_path, furless_obj_path=None, name='SMAL_Skeletal_Mesh',
               out_dir='output', model_path=DEFAULT_MODEL_PATH):
    os.makedirs(out_dir, exist_ok=True)

    # Remove the default cube if it exists
    if 'Cube' in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects['Cube'], do_unlink=True)

    smal_vertices, _ = load_vertices_faces(smal_obj_path)
    mesh_obj, armature_obj = create_skeletal_mesh_using_v_template(smal_vertices, name, model_path)

    # Export SMAL-resolution FBX
    export_fbx(obj_mesh=mesh_obj,
               filepath=os.path.join(out_dir, f'{name}_smal.fbx'))

    # Optionally skin & export the high-res furless mesh
    if furless_obj_path is not None:
        high_res_vertices, high_res_faces = load_vertices_faces(furless_obj_path)
        high_res_mesh_obj = create_mesh(high_res_vertices, high_res_faces, f'{name}_high_res')

        # Apply the same rotation as the SMAL mesh so both meshes are in the
        # same coordinate space for the weight transfer
        bpy.ops.object.select_all(action='DESELECT')
        high_res_mesh_obj.select_set(True)
        bpy.context.view_layer.objects.active = high_res_mesh_obj
        high_res_mesh_obj.rotation_euler = (radians(90), 0, 0)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
        high_res_mesh_obj.location = mesh_obj.location

        print('Transferring weights from SMAL to high-resolution mesh...')
        transfer_weights(mesh_obj, high_res_mesh_obj, armature_obj)
        validate_weights(high_res_mesh_obj)

        export_fbx(obj_mesh=high_res_mesh_obj,
                   filepath=os.path.join(out_dir, f'{name}_high_res.fbx'))

    # Save the Blender scene for debugging
    blend_path = os.path.join(out_dir, f'{name}.blend')
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(blend_path))
    print('Blender scene saved: ' + blend_path)


def main():
    parser = argparse.ArgumentParser(description='Create a SMAL skeletal mesh and export it as UE-ready FBX.')
    parser.add_argument('--smal-obj', type=str, required=True,
                        help='Fitted SMAL mesh in init pose')
    parser.add_argument('--furless-obj', type=str, default=None,
                        help='Optional high-res furless mesh; skinned via weight transfer')
    parser.add_argument('--name', type=str, default='SMAL_Skeletal_Mesh',
                        help='Base name for the exported assets')
    parser.add_argument('--out-dir', type=str, default='output')
    parser.add_argument('--smal-model', type=str, default=DEFAULT_MODEL_PATH,
                        help='Path to the SMAL model pkl (smal_plus.pkl)')
    args = parser.parse_args()

    create_fbx(smal_obj_path=args.smal_obj,
               furless_obj_path=args.furless_obj,
               name=args.name,
               out_dir=args.out_dir,
               model_path=args.smal_model)


if __name__ == '__main__':
    main()
