# 3. Animate

Brings a NeuralFur animal to life: build a SMAL skeletal mesh, retarget existing motions onto it, export the animation as an Alembic Geometry Cache, and make the fur follow it (with physics simulation).

> **Before you start:** this repo does **not** provide any animal animations. You need your own animation `.fbx` files (animated skeletal meshes, e.g. quadruped walk/run cycles) to retarget onto the SMAL skeleton in Step 2. Without them, this tutorial cannot be completed.

> **Key concept: the "init pose":** the pose the animal held when the fur was reconstructed. The strands only line up with the body in that exact pose, so the whole workflow is built around starting the animation from it (details in Steps 2 and 3).

Overview:

```
smal.obj (init pose) ──► smal_to_fbx.py ──► <name>_smal.fbx / <name>_high_res.fbx
                                                 │
                          Unreal: retarget motions onto the SMAL skeleton
                                                 │
                          export init_pose.fbx + animated .fbx files
                                                 │
        Blender: append animation after init pose ──► animation .abc
                                                 │
        Unreal: Geometry Cache + Groom Binding + simulation
```

## Step 1 : Create the SMAL skeletal mesh

Take a SMAL mesh **fitted to the animal in init pose** : the same pose the fur was reconstructed in : included with the animal's reconstruction data. The mesh is used as the SMAL model's `v_template` : the model forward pass rebuilds the skeleton (joint positions + skinning weights) for this specific animal shape:

```bash
python -m src.blender.smal_to_fbx \
    --smal-obj data/<animal>/smal.obj \
    --furless-obj data/<animal>/furless.obj \
    --name <animal> \
    --smal-model data/smal/smal_plus.pkl \
    --out-dir output
```

Outputs:

- `<animal>_smal.fbx` : skinned SMAL-resolution skeletal mesh (init pose)
- `<animal>_high_res.fbx` : the furless mesh skinned with weights transferred from SMAL (only with `--furless-obj`)
- `<animal>.blend` : Blender scene for debugging

Requires `torch`, `smplx`, and the SMAL model file `smal_plus.pkl`. The SMAL model is not distributed with this repo : download it from the [GenZoo download page](https://genzoo.is.tue.mpg.de/download.php) (registration required) and place it in `data/smal/`.

## Step 2 : Retarget motions in Unreal

1. Import the `.fbx` from step 1 into Unreal (as a Skeletal Mesh).
2. Retarget your own animal animations (see the note at the top of this page) onto the SMAL skeleton using Unreal's IK Retargeter.
3. Export the retargeted animations as `.fbx` files (e.g. `walking.fbx`), along with the init pose as `init_pose.fbx` (the skeleton holding its rest pose). Exporting the init pose **from Unreal** — rather than reusing the Blender-side FBX — matters: the UE round-trip changes skeleton conventions (bone naming, orientations), and only FBXs exported together share an identical skeleton, which Step 3 relies on.

## Step 3 : Export the animation as Alembic (Blender)

The goal is a single animation that **starts from the init pose and interpolates into the motion**. The init pose is the pose the animal held when the fur was reconstructed: the strands only line up with the body in that exact pose. By starting the geometry cache there, the groom binding (Step 4) attaches the fur on a first frame that matches the pose the fur was authored in, and the strands then follow the surface as it deforms into the motion instead of starting misaligned. Two options:

### Option A : script

```bash
python -m src.blender.combine_motions \
    --ref-fbx <animal>_init_pose.fbx \
    --motions-dir retargeted_motions/ \
    --out-fbx combined_motion.fbx \
    --out-abc combined_motion.abc
```

The init pose is placed first on the timeline; every FBX in `--motions-dir` is appended in filename order with a one-frame gap, so Blender interpolates between clips. Exports both `.fbx` and `.abc`.

### Option B : manually in Blender

1. Import `<name>_init_pose.fbx` into Blender.
2. Import an animation (e.g. `panda_animal_run.fbx`).
3. Select the animation skeleton; in the timeline, select all keyframes, right-click → **Copy**.
4. Select the init pose skeleton, right-click on the timeline → **Paste**. Blender adds the interpolation between the init pose and the pasted keyframes automatically.
5. Delete the animation skeleton and export as **Alembic** (set the export frame range as required).


## Step 4 : Set it up in Unreal

### Animation (Geometry Cache)

Drag the animation `.abc` into Unreal. In the *Alembic Cache Import Options*:

- Import Type: **Geometry Cache** — the dropdown defaults to *Static Mesh*; make sure to change it, otherwise the animation is lost
- Scale: **(100, −100, 100)**
- Rotation: **(90, 0, 0)**

Import troubleshooting:

- **Animal appears ~100× too small** (or mirrored / lying on its side): the Scale/Rotation above were not applied. The Blender exports are in meters and Unreal works in centimeters; the conversion happens through these import settings, so re-import with them set.
- **Only a static pose plays**: if you imported a `.fbx` (instead of the `.abc`), make sure **Import Animations** is enabled in the *FBX Import Options*; without it Unreal imports just the skeletal mesh.

### Groom

Convert and import the fur as described in [1. Process](01-process.md) / [2. Import](02-import.md). Then double-click the groom asset:

- *Strands* tab → **Hair Width**: 0.02–0.05
- *Physics* tab:
  - **Enable Simulation**: True
  - **Gravity Preloading**: 1.0 if the groom interpenetrates the mesh too much
  - If the groom looks weird/noisy, try tweaking:
    - **Bend Damping/Stiffness** (0.05 worked well for the test groom, at least when static)
    - **Stretch Damping/Stiffness**

### Binding

Right-click the groom asset in the Content Browser → **Create Binding**:

- Groom Binding Type: **Geometry Cache**
- Target Geometry Cache: the imported **animation** geometry cache
- Click **Create**

### Simulation

1. Drag the Geometry Cache and the Groom into the scene. (If they don't overlap correctly, the Scale/Rotation in the Alembic import options are wrong : adjust until they match.)
2. Select the Groom actor and set its **Binding Asset** to the Groom Binding created above.
3. In the Outliner, drag the GroomActor onto the GeometryCacheActor (parent it).

Press **Play**: the animation runs and the groom follows.
