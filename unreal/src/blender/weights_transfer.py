"""Transfer skinning weights from the (low-res) SMAL mesh to a high-res mesh
(e.g. the furless NeuralFur body), producing a UE-friendly rig (max 4
influences per vertex, normalized)."""
import bpy


def transfer_weights(low_mesh, high_mesh, low_arm):
    if not low_mesh or not high_mesh or not low_arm:
        raise RuntimeError(f'Could not find low_mesh({low_mesh}), high_mesh({high_mesh}), low_arm({low_arm}).')

    # Ensure rest pose for transfer
    prev_pose = low_arm.data.pose_position
    low_arm.data.pose_position = 'REST'

    # Make sure the high mesh has no old weights or armature modifiers
    bpy.context.view_layer.objects.active = high_mesh
    for vg in list(high_mesh.vertex_groups):
        high_mesh.vertex_groups.remove(vg)

    for m in list(high_mesh.modifiers):
        if m.type in {'ARMATURE', 'DATA_TRANSFER'}:
            high_mesh.modifiers.remove(m)

    # Ensure the high mesh has all vertex groups that exist on the low mesh
    for vg in low_mesh.vertex_groups:
        if vg.name not in [g.name for g in high_mesh.vertex_groups]:
            high_mesh.vertex_groups.new(name=vg.name)

    # Data Transfer: copy vertex group weights
    dt = high_mesh.modifiers.new('WT_Transfer', 'DATA_TRANSFER')
    dt.object = low_mesh
    dt.use_vert_data = True
    dt.data_types_verts = {'VGROUP_WEIGHTS'}
    dt.vert_mapping = 'POLY_NEAREST'   # robust when topology differs
    dt.mix_mode = 'REPLACE'
    dt.mix_factor = 1.0

    bpy.ops.object.modifier_apply(modifier=dt.name)

    # Normalize & limit to 4 weights (UE-friendly)
    bpy.ops.object.vertex_group_limit_total(group_select_mode='ALL', limit=4)
    bpy.ops.object.vertex_group_normalize_all(lock_active=False)

    # Add Armature modifier pointing to the same armature as the low-res mesh
    arm_mod = high_mesh.modifiers.new('Armature', 'ARMATURE')
    arm_mod.object = low_arm
    arm_mod.use_vertex_groups = True

    high_mesh.parent = low_arm
    high_mesh.parent_type = 'OBJECT'

    low_arm.data.pose_position = prev_pose

    # Select only the armature + high mesh (ready for export)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    low_arm.select_set(True)
    high_mesh.select_set(True)
    bpy.context.view_layer.objects.active = low_arm


def validate_weights(mesh_obj):
    """Validate that vertex weights are normalized and within UE limits."""
    print(f'Validating weights for {mesh_obj.name}...')

    issues = []
    for vertex in mesh_obj.data.vertices:
        total_weight = sum(group.weight for group in vertex.groups)
        if abs(total_weight - 1.0) > 0.01:
            issues.append(f'Vertex {vertex.index}: total weight = {total_weight:.3f}')
        if len(vertex.groups) > 4:
            issues.append(f'Vertex {vertex.index}: {len(vertex.groups)} influences (>4)')

    if issues:
        print(f'Found {len(issues)} weight issues:')
        for issue in issues[:10]:
            print(f'  {issue}')
        if len(issues) > 10:
            print(f'  ... and {len(issues) - 10} more')
    else:
        print('Weight validation passed!')

    return len(issues) == 0
