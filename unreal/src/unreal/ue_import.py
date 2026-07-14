#!/usr/bin/env python3
"""Import NeuralFur Alembic files into Unreal Engine 5.4+ and build render-ready assets.

Run inside the Unreal Editor Python environment (Output Log -> Cmd, mode "Python"):

    py "<repo>/src/unreal/ue_import.py" --groom fur.abc --geo furless.abc

The script:
  1. Imports the geometry .abc as a Geometry Cache.
  2. Imports the strands .abc as a Groom.
  3. Duplicates the hair material for the animal and assigns it to the groom.
  4. Creates a Groom Binding (Geometry Cache type) between groom and geometry.
  5. Creates a one-frame Level Sequence with both actors as spawnables
     (groom attached to the geometry), ready for Movie Render Queue.
  6. Applies the groom strand settings from GROOM_SETTINGS below.

Required plugins: Python Editor Script Plugin, Groom, Alembic Groom Importer.
"""

from pathlib import Path
import re

import unreal

# ----------------------------- CONFIG ---------------------------------------
# NOTE: this repo ships NO Unreal assets. Point the paths below at assets in
# YOUR project. Every asset is optional: if one is missing, the script logs a
# warning and continues (the animal is then imported with default materials,
# into the currently open map).

# All imported assets are created under this content folder
DEST_ROOT = '/Game/animals'

# Optional map that is loaded before importing (lighting/backdrop for rendering).
# The first existing path wins.
TEMPLATE_MAP_CANDIDATES = [
    '/Game/maps/render_map',
]

# Optional hair material that gets duplicated per animal and assigned to the groom
SOURCE_MATERIAL_CANDIDATES = [
    '/Game/materials/HairShader',
]

# Optional material assigned to the body geometry cache
BODY_MATERIAL_PATH = '/Game/materials/BodyMaterial'

# Transform applied to spawned actors: Blender [m] -> Unreal [cm] + axis flip
ROTATOR = unreal.Rotator(90.0, 0.0, 0.0)
SCALE = unreal.Vector(100.0, -100.0, 100.0)
LOCATION = unreal.Vector(0.0, 0.0, 0.0)

# Groom strand settings applied to every imported groom asset.
# NOTE: use_rt_geometry=True can crash UE when rendering hair with raytracing;
# we rasterize hair (and raytrace everything else) to avoid this.
GROOM_SETTINGS = dict(
    hair_width=0.05,               # sensible range: 0.02 - 0.05
    hair_root_scale=1.0,
    hair_tip_scale=1.0,
    hair_shadow_density=0.8,
    hair_rt_radius_scale=1.0,
    use_rt_geometry=False,
    voxelize=True,
    use_stable_rasterization=True,
    scatter_scene_lighting=False,
)

# -----------------------------------------------------------------------------


def make_hair_group_desc(s: dict) -> unreal.HairGroupDesc:
    """Build a HairGroupDesc from GROOM_SETTINGS with all override toggles enabled."""
    return unreal.HairGroupDesc(
        hair_width=s['hair_width'], hair_width_override=True,
        hair_root_scale=s['hair_root_scale'], hair_root_scale_override=True,
        hair_tip_scale=s['hair_tip_scale'], hair_tip_scale_override=True,
        hair_shadow_density=s['hair_shadow_density'], hair_shadow_density_override=True,
        hair_raytracing_radius_scale=s['hair_rt_radius_scale'], hair_raytracing_radius_scale_override=True,
        use_hair_raytracing_geometry=s['use_rt_geometry'], use_hair_raytracing_geometry_override=True,
        use_stable_rasterization=s['use_stable_rasterization'], use_stable_rasterization_override=True,
        scatter_scene_lighting=s['scatter_scene_lighting'], scatter_scene_lighting_override=True,
    )


def log(msg: str):
    unreal.log(msg)


def ensure_folder(path: str):
    if not unreal.EditorAssetLibrary.does_directory_exist(path):
        unreal.EditorAssetLibrary.make_directory(path)


def resolve_first_existing_asset(paths: list[str]) -> str | None:
    for p in paths:
        if unreal.EditorAssetLibrary.does_asset_exist(p):
            return p
    return None


def _sanitize_segment(name: str) -> str:
    """Replace characters that are illegal in Unreal asset paths with '_'."""
    s = re.sub(r'[^A-Za-z0-9_]', '_', str(name))
    return s or 'x'


def import_with_task(src_file: Path, dest_path: str, dest_name: str | None = None, options=None) -> str | None:
    task = unreal.AssetImportTask()
    task.set_editor_property('filename', str(src_file))
    task.set_editor_property('destination_path', dest_path)
    if dest_name:
        task.set_editor_property('destination_name', dest_name)
    task.set_editor_property('automated', True)
    task.set_editor_property('save', True)
    if options is not None:
        task.set_editor_property('options', options)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    paths = list(task.get_editor_property('imported_object_paths') or [])
    return paths[0] if paths else None


def import_groom(hair_abc: Path, dest_path: str, groom_name: str) -> str | None:
    conv = unreal.GroomConversionSettings(
        rotation=unreal.Vector(90.0, 0.0, 0.0),    # degrees, Euler XYZ
        scale=unreal.Vector(100.0, -100.0, 100.0)  # unit conversion + axis flip
    )
    opts = unreal.GroomImportOptions()
    opts.set_editor_property('conversion_settings', conv)
    asset_path = import_with_task(hair_abc, dest_path, groom_name, opts)
    if not asset_path:
        unreal.log_error(f'Groom import failed: {hair_abc}')
        return None
    unreal.EditorAssetLibrary.save_asset(asset_path)
    return asset_path


def import_geometry(geo_abc: Path, dest_path: str, asset_name: str) -> str | None:
    options = unreal.AbcImportSettings()
    options.set_editor_property('import_type', unreal.AlembicImportType.GEOMETRY_CACHE)

    # Maximum quality settings for position precision and texture coordinates.
    # Note: CALCULATE_MOTION_VECTORS_DURING_IMPORT caused strong face ghosting,
    # so motion vectors are disabled.
    options.geometry_cache_settings = unreal.AbcGeometryCacheSettings(
        flatten_tracks=True,
        apply_constant_topology_optimizations=False,
        motion_vectors=unreal.AbcGeometryCacheMotionVectorsImport.NO_MOTION_VECTORS,
        optimize_index_buffers=False,
        compressed_position_precision=0.01,
        compressed_texture_coordinates_number_of_bits=16)

    # Source Alembic data exported from Blender [m] -> Unreal [cm]
    options.conversion_settings = unreal.AbcConversionSettings(
        preset=unreal.AbcConversionPreset.CUSTOM,
        flip_u=False, flip_v=True,
        scale=[100.0, -100.0, 100.0],
        rotation=[90.0, 0.0, 0.0])

    return import_with_task(geo_abc, dest_path, asset_name, options)


def duplicate_material_to_animal(dest_path: str, animal: str) -> str | None:
    src_asset = resolve_first_existing_asset(SOURCE_MATERIAL_CANDIDATES)
    if not src_asset:
        unreal.log_error(f'Hair material not found. Tried: {SOURCE_MATERIAL_CANDIDATES}')
        return None
    dst_asset = f'{dest_path}/{animal}_HairShader'
    if unreal.EditorAssetLibrary.does_asset_exist(dst_asset):
        return dst_asset
    unreal.EditorAssetLibrary.duplicate_asset(src_asset, dst_asset)
    unreal.EditorAssetLibrary.save_asset(dst_asset)
    return dst_asset


def apply_groom_strands_overrides_to_asset(
    groom_asset_path: str,
    *,
    material_asset_path: str | None = None,
    hair_width: float = 0.05,
    hair_root_scale: float = 1.0,
    hair_tip_scale: float = 1.0,
    hair_shadow_density: float = 1.0,
    hair_rt_radius_scale: float = 1.0,
    use_rt_geometry: bool = False,
    voxelize: bool = True,
    use_stable_rasterization: bool = True,
    scatter_scene_lighting: bool = False,
) -> bool:
    """Write strand settings to the groom asset.

    Sets both HairGroupsRendering (asset storage) and the HairGroupDesc preview
    override, so the values show up correctly in the Groom editor UI.
    """
    g = unreal.EditorAssetLibrary.load_asset(groom_asset_path)
    if not isinstance(g, unreal.GroomAsset):
        unreal.log_error(f'Not a GroomAsset: {groom_asset_path}')
        return False

    mat = unreal.EditorAssetLibrary.load_asset(material_asset_path) if material_asset_path else None

    # --- A) Asset storage (HairGroupsRendering[0]) ---
    groups = list(g.get_editor_property('hair_groups_rendering') or [])
    if not groups:
        groups = [unreal.HairGroupsRendering()]
    r = groups[0]

    geom = unreal.HairGeometrySettings(hair_width=hair_width,
                                       hair_root_scale=hair_root_scale,
                                       hair_tip_scale=hair_tip_scale)
    r.set_editor_property('geometry_settings', geom)

    adv = unreal.HairAdvancedRenderingSettings(use_stable_rasterization=use_stable_rasterization,
                                               scatter_scene_lighting=scatter_scene_lighting)
    r.set_editor_property('advanced_settings', adv)

    for k, v in (('hair_shadow_density', hair_shadow_density),
                 ('hair_raytracing_radius_scale', hair_rt_radius_scale),
                 ('use_hair_raytracing_geometry', use_rt_geometry),
                 ('voxelize', voxelize)):
        try:
            r.set_editor_property(k, v)
        except Exception:
            pass

    if isinstance(mat, unreal.MaterialInterface):
        try:
            r.set_editor_property('material', mat)
        except Exception:
            pass

    groups[0] = r
    g.set_editor_property('hair_groups_rendering', groups)

    # --- B) Preview overrides (HairGroupDesc) so the Groom editor unlocks the sliders.
    # Property names differ between UE builds, so several candidates are tried.
    def _set_preview_desc_on_asset():
        try:
            preview = g.get_editor_property('hair_groups_preview')
        except Exception:
            return False
        if not preview:
            return False

        groups_prev = None
        holder_field = None
        for field in ('groups', 'hair_groups', 'items'):
            try:
                groups_prev = list(preview.get_editor_property(field) or [])
                holder_field = field
                break
            except Exception:
                pass
        if groups_prev is None:
            return False

        if not groups_prev:
            try:
                groups_prev = [unreal.HairGroupPreview()]
            except Exception:
                groups_prev = [{}]

        desc = unreal.HairGroupDesc(
            hair_width=hair_width, hair_width_override=True,
            hair_root_scale=hair_root_scale, hair_root_scale_override=True,
            hair_tip_scale=hair_tip_scale, hair_tip_scale_override=True,
            hair_shadow_density=hair_shadow_density, hair_shadow_density_override=True,
            hair_raytracing_radius_scale=hair_rt_radius_scale, hair_raytracing_radius_scale_override=True,
            use_hair_raytracing_geometry=use_rt_geometry, use_hair_raytracing_geometry_override=True,
            use_stable_rasterization=use_stable_rasterization, use_stable_rasterization_override=True,
            scatter_scene_lighting=scatter_scene_lighting, scatter_scene_lighting_override=True,
        )

        placed = False
        target = groups_prev[0]
        for name in ('desc', 'group_desc', 'hair_group_desc'):
            try:
                target.set_editor_property(name, desc)
                placed = True
                break
            except Exception:
                pass
        if not placed:
            groups_prev[0] = desc

        preview.set_editor_property(holder_field, groups_prev)
        g.set_editor_property('hair_groups_preview', preview)
        return True

    overrides_ok = _set_preview_desc_on_asset()
    if not overrides_ok:
        props = ', '.join(sorted(p for p in dir(g) if 'hair' in p.lower() or 'group' in p.lower()))
        unreal.log_warning(
            f'Could not set the HairGroupDesc preview overrides (hair_width_override etc.) on '
            f'{groom_asset_path}; the override toggles in the Groom editor may appear unticked, '
            f'even though the values are stored in hair_groups_rendering. '
            f'Groom asset properties on this build: {props}')

    try:
        g.modify(True)
        g.post_edit_change()
    except Exception:
        pass
    ok = unreal.EditorAssetLibrary.save_asset(groom_asset_path)
    unreal.log(f'Applied strand settings to {groom_asset_path} (ok={ok}, ui_overrides={overrides_ok})')
    return bool(ok)


def bind_groom_to_mesh(
    groom_asset_path: str,
    mesh_asset_path: str,
    dest_path: str,
    bind_name: str,
    num_interp_points: int = 100,
) -> str | None:
    """Create a GroomBindingAsset of type Geometry Cache."""
    groom = unreal.EditorAssetLibrary.load_asset(groom_asset_path)
    target_gc = unreal.EditorAssetLibrary.load_asset(mesh_asset_path)
    if not isinstance(groom, unreal.GroomAsset) or not isinstance(target_gc, unreal.GeometryCache):
        unreal.log_error('bind_groom_to_mesh: expecting a GroomAsset and a GeometryCache target')
        return None

    # Fresh asset (avoid reusing an old binding of a different type)
    pkg_path = f'{dest_path}/{bind_name}'
    if unreal.EditorAssetLibrary.does_asset_exist(pkg_path):
        unreal.EditorAssetLibrary.delete_asset(pkg_path)

    at = unreal.AssetToolsHelpers.get_asset_tools()
    fac = unreal.GroomBindingFactory()

    def setp(obj, k, v):
        try:
            obj.set_editor_property(k, v)
            return True
        except Exception:
            try:
                setattr(obj, k, v)
                return True
            except Exception:
                return False

    # Creation-time options (factory)
    setp(fac, 'groom', groom)
    setp(fac, 'target_geometry_cache', target_gc)
    setp(fac, 'binding_type', unreal.GroomBindingMeshType.GEOMETRY_CACHE)
    setp(fac, 'num_interpolation_points', num_interp_points)
    setp(fac, 'matching_section', 0)
    setp(fac, 'target_skeletal_mesh', None)
    setp(fac, 'target_static_mesh', None)

    binding = at.create_asset(bind_name, dest_path, unreal.GroomBindingAsset.static_class(), fac)
    if not binding:
        unreal.log_error('bind_groom_to_mesh: create_asset failed')
        return None
    binding = unreal.GroomBindingAsset.cast(binding)

    # Enforce again on the asset (some builds need this)
    setp(binding, 'groom', groom)
    setp(binding, 'target_geometry_cache', target_gc)
    for prop in ('binding_type', 'groom_binding_type', 'target_type'):
        if setp(binding, prop, unreal.GroomBindingMeshType.GEOMETRY_CACHE):
            break
    for prop in ('num_interpolation_points', 'num_interpolation_points_on_strands'):
        if setp(binding, prop, num_interp_points):
            break
    setp(binding, 'target_skeletal_mesh', None)
    setp(binding, 'target_static_mesh', None)

    try:
        binding.modify(True)
    except Exception:
        pass

    path = binding.get_path_name()
    unreal.EditorAssetLibrary.save_asset(path)
    unreal.log(f'GroomBinding created: {path}')
    return path


def _configure_sequence_one_frame(level_sequence: unreal.LevelSequence):
    try:
        level_sequence.set_display_rate(unreal.FrameRate(numerator=30, denominator=1))
    except Exception:
        pass
    try:
        level_sequence.set_playback_start(0)
        level_sequence.set_playback_end(1)
    except Exception:
        pass


def add_geometry_cache_spawnable(level_sequence, geo_asset_path: str, label: str, material_asset):
    geo_asset = unreal.EditorAssetLibrary.load_asset(geo_asset_path)
    if not isinstance(geo_asset, unreal.GeometryCache):
        log(f'WARN: Asset is not GeometryCache: {geo_asset_path}')
        return None

    actor = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(
        unreal.GeometryCacheActor, LOCATION)
    try:
        comp = actor.get_component_by_class(unreal.GeometryCacheComponent.static_class())
        comp.set_editor_property('looping', False)
        comp.set_editor_property('manual_tick', True)
        comp.set_editor_property('geometry_cache', geo_asset)
    except Exception:
        pass

    if material_asset:
        try:
            comp = actor.get_component_by_class(unreal.GeometryCacheComponent.static_class())
            comp.set_material(0, material_asset)
        except Exception as e:
            log(f'Warning: Could not set material on geometry cache: {e}')

    actor.set_actor_label(label)

    layer_subsystem = unreal.get_editor_subsystem(unreal.LayersSubsystem)
    layer_subsystem.add_actor_to_layer(actor, unreal.Name('animal'))

    binding = level_sequence.add_spawnable_from_instance(actor)
    unreal.get_editor_subsystem(unreal.EditorActorSubsystem).destroy_actor(actor)

    try:
        gc_track = binding.add_track(unreal.MovieSceneGeometryCacheTrack)
        gc_section = gc_track.add_section()
        gc_section.set_range(0, 1)  # one-frame section at frame 0
    except Exception:
        pass

    return binding


def add_groom_spawnable(level_sequence: unreal.LevelSequence, groom_asset_path: str, label: str,
                        material_asset_path: str | None,
                        binding_asset_path: str | None,
                        parent_binding: unreal.MovieSceneBindingProxy | None):
    groom_asset = unreal.EditorAssetLibrary.load_asset(groom_asset_path)
    if not isinstance(groom_asset, unreal.GroomAsset):
        log(f'WARN: Asset is not GroomAsset: {groom_asset_path}')
        return None

    actor = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(
        unreal.GroomActor, LOCATION)
    ga = unreal.GroomActor.cast(actor)
    gcomp = ga.get_component_by_class(unreal.GroomComponent.static_class())

    layer_subsystem = unreal.get_editor_subsystem(unreal.LayersSubsystem)
    layer_subsystem.add_actor_to_layer(actor, unreal.Name('animal'))

    if gcomp:
        try:
            gcomp.set_editor_property('groom_asset', groom_asset)
        except Exception:
            pass

        # Binding asset (critical for Geometry Cache targets)
        if binding_asset_path:
            try:
                binding_asset = unreal.EditorAssetLibrary.load_asset(binding_asset_path)
                gcomp.set_editor_property('binding_asset', binding_asset)
            except Exception:
                pass

        if material_asset_path:
            try:
                mat = unreal.EditorAssetLibrary.load_asset(material_asset_path)
                gcomp.set_material(0, mat)
            except Exception:
                pass

        # Per-instance strand overrides (HairGroupDesc): the same settings the
        # override toggles in the Groom UI control. Component overrides take
        # precedence over the asset, so no manual clicking is needed.
        try:
            gcomp.set_editor_property('groom_groups_desc', [make_hair_group_desc(GROOM_SETTINGS)])
        except Exception as e:
            log(f'WARN: could not set per-instance strand overrides: {e}')

    actor.set_actor_label(label)

    binding = level_sequence.add_spawnable_from_instance(actor)
    unreal.get_editor_subsystem(unreal.EditorActorSubsystem).destroy_actor(actor)

    # Attach the groom to the geometry cache spawnable
    if parent_binding is not None:
        try:
            attach_track = binding.add_track(unreal.MovieScene3DAttachTrack)
            attach_section = attach_track.add_section()
            parent_id = unreal.MovieSceneObjectBindingID()
            parent_id.set_editor_property('Guid', parent_binding.get_id())
            attach_section.set_constraint_binding_id(parent_id)
            attach_section.set_start_frame_bounded(False)
            attach_section.set_end_frame_bounded(False)
        except Exception:
            pass

    return binding


def process_animal(hair_abc: Path, geo_abc: Path, name: str):
    animal_display = name
    animal_safe = _sanitize_segment(name)
    dest_path = f'{DEST_ROOT}/{animal_safe}'
    ensure_folder(DEST_ROOT)
    ensure_folder(dest_path)

    log(f'Importing {animal_display} into {dest_path}: hair={hair_abc.name}, geo={geo_abc.name}')

    asset_prefix = animal_safe
    geo_asset_path = import_geometry(geo_abc, dest_path, f'{asset_prefix}_Geo')
    groom_asset_path = import_groom(hair_abc, dest_path, f'{asset_prefix}_Groom')
    mat_asset_path = duplicate_material_to_animal(dest_path, asset_prefix)

    # Create or load the Level Sequence
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    seq_asset_name = f'{asset_prefix}_Sequence'
    seq_path = f'{dest_path}/{seq_asset_name}'
    if not unreal.EditorAssetLibrary.does_asset_exist(seq_path):
        seq = asset_tools.create_asset(seq_asset_name, dest_path, unreal.LevelSequence.static_class(),
                                       unreal.LevelSequenceFactoryNew())
        if seq:
            unreal.EditorAssetLibrary.save_asset(seq.get_path_name())
    level_sequence = unreal.EditorAssetLibrary.load_asset(seq_path)
    if not isinstance(level_sequence, unreal.LevelSequence):
        log(f'ERROR: Could not load LevelSequence: {seq_path}')
        return

    _configure_sequence_one_frame(level_sequence)

    body_material = unreal.EditorAssetLibrary.load_asset(BODY_MATERIAL_PATH)
    if not body_material:
        log(f'Warning: Could not load body material: {BODY_MATERIAL_PATH}')
        body_material = None

    geo_binding = add_geometry_cache_spawnable(
        level_sequence, geo_asset_path, f'{animal_display}_GeoActor', body_material) if geo_asset_path else None

    binding_asset_path = None
    if groom_asset_path and geo_asset_path:
        binding_asset_path = bind_groom_to_mesh(groom_asset_path, geo_asset_path, dest_path,
                                                f'{asset_prefix}_GroomBinding')

    if groom_asset_path:
        add_groom_spawnable(level_sequence, groom_asset_path, f'{animal_display}_GroomActor',
                            mat_asset_path, binding_asset_path, geo_binding)
        apply_groom_strands_overrides_to_asset(groom_asset_path,
                                               material_asset_path=mat_asset_path,
                                               **GROOM_SETTINGS)

    unreal.EditorAssetLibrary.save_directory(dest_path)


def check_required_plugins() -> bool:
    """The groom Python classes only exist when the required plugins are loaded."""
    missing = [c for c in ('GroomConversionSettings', 'GroomImportOptions',
                           'GroomBindingFactory', 'AbcImportSettings')
               if not hasattr(unreal, c)]
    if missing:
        unreal.log_error(
            f'Missing Unreal classes: {", ".join(missing)}. Enable the "Groom" and '
            f'"Alembic Groom Importer" plugins (Edit -> Plugins), restart the editor, and re-run.')
        return False
    return True


def main(groom_abc: str, geo_abc: str, name: str | None = None):
    if not check_required_plugins():
        return
    hair_abc = Path(groom_abc)
    geo_abc = Path(geo_abc)
    if not hair_abc.is_file() or not geo_abc.is_file():
        unreal.log_error(f'Input file(s) not found: {hair_abc}, {geo_abc}')
        return
    name = name or f'{hair_abc.stem}__{geo_abc.stem}'

    template_map = resolve_first_existing_asset(TEMPLATE_MAP_CANDIDATES)
    if template_map:
        unreal.EditorLoadingAndSavingUtils.load_map(template_map)
    else:
        log(f'WARN: Template map not found ({TEMPLATE_MAP_CANDIDATES}); using the currently open map.')

    process_animal(hair_abc, geo_abc, name)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Import a groom/geometry ABC pair into Unreal and build a sequence.')
    parser.add_argument('--groom', type=str, required=True, help='Groom .abc (fur strands)')
    parser.add_argument('--geo', type=str, required=True, help='Geometry .abc (furless body)')
    parser.add_argument('--name', type=str, default=None,
                        help='Animal name, used as asset prefix and /Game/animals/<name> folder '
                             '(default: "<groom filename>__<geo filename>")')
    args = parser.parse_args()
    main(args.groom, args.geo, args.name)
