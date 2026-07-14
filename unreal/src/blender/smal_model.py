"""SMAL model forward pass (via smplx) used to build the skeletal mesh.

Requires `torch` and `smplx`, and the SMAL model file
(`smal_plus.pkl`) : not distributed with this repo; download it from GenZoo:
https://genzoo.is.tue.mpg.de/download.php (registration required).
"""
import smplx
import torch

DEFAULT_MODEL_PATH = 'data/smal/smal_plus.pkl'


class SMALLayer(smplx.SMPLLayer):
    NUM_JOINTS = 34
    NUM_BODY_JOINTS = 34
    SHAPE_SPACE_DIM = 145

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.vertex_joint_selector.extra_joints_idxs = torch.empty(0, dtype=torch.int32)


def smal_fwd_pass(v_template, model_path=DEFAULT_MODEL_PATH):
    """Run the SMAL model with a custom template mesh.

    Returns (vertices, faces, joints, lbs_weights) for the rest pose.
    """
    model = SMALLayer(model_path=model_path, v_template=v_template)
    output = model(v_template=v_template)
    return output.vertices, model.faces_tensor, output.joints, model.lbs_weights
