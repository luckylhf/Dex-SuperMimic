# Source reference geometry

## LAFAN local geometry

The user generates `lafan1_surfaces.json` locally from Ubisoft's official `fbx/model_skeleton.fbx` (SHA256 `3d9349b5ec686248be6ab73ea3b918f486016a0d22e4b4b80d5418c8f3a608aa`) using `dex-sm data prepare-lafan-geometry`. Bone-local surfaces use dominant skin weights, with extra fingers folded into the original BVH Hand. Shoe landmarks and the sole normal are fixed reference-surface measurements. The extractor uses ufbx commit `5955c5c0b042ac2dc6f32955ab206aaec0620cfc`, checked by source-file hashes.

The default output is `data/lafan1/local_geometry/lafan1_surfaces.json` under `DEX_SUPERMIMIC_ROOT` or the working directory. `DEX_LAFAN_GEOMETRY` selects a custom file. Runtime validates its source hash and geometry schema, and includes its content hash in the LAFAN conversion identity. Git, sdist and wheel rules exclude the FBX, bind vertices and generated JSON. Preparation instructions are in `data/lafan1/README.md`.

The original model and local derivatives are subject to Ubisoft's CC BY-NC-ND 4.0 license. Sharing adapted material requires separate authorization. [Ubisoft LAFAN1 license](https://github.com/ubisoft/ubisoft-laforge-animation-dataset/blob/master/license.txt)

## NVIDIA SOMA geometry

soma_surfaces.json is derived locally from NVIDIA soma_base_skel_minimal.usd (SHA256 4074b8d830f53af246b4d93d1871af38c8825e6b6b6bbaf034d4612673c89266), using its geometry bind and skeleton bind transforms. Official SOMA foot landmark configuration remains separate and unchanged.

The surfaces are rigid per-bone convex-envelope approximations of the reference skins. Contact interpretation uses geometric inference. The SOMA JSON is packaged with the existing NVIDIA notices. The reference USD remains in the user's local research materials.
