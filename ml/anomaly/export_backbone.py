#!/usr/bin/env python3
"""Exports ImageNet-pretrained backbones to ONNX patch-feature extractors.

Output: (N, D, H, W), the concatenation of two mid-level stages with a 3x3 local average, as in
PatchCore. Mid-level features keep spatial detail while staying robust to small shifts.

    python ml/anomaly/export_backbone.py --arch resnet18 --size 256 --out backend/storage/models/anomaly/resnet18_256.onnx
"""
import argparse
import os

import torch
import torch.nn.functional as F
import torchvision.models as tv


class PatchFeatures(torch.nn.Module):
    def __init__(self, arch: str):
        super().__init__()
        if arch == "resnet18":
            net = tv.resnet18(weights=tv.ResNet18_Weights.IMAGENET1K_V1)
        elif arch == "resnet50":
            net = tv.resnet50(weights=tv.ResNet50_Weights.IMAGENET1K_V2)
        elif arch == "wide_resnet50_2":
            net = tv.wide_resnet50_2(weights=tv.Wide_ResNet50_2_Weights.IMAGENET1K_V1)
        else:
            raise ValueError(arch)
        self.stem = torch.nn.Sequential(net.conv1, net.bn1, net.relu, net.maxpool, net.layer1)
        self.layer2, self.layer3 = net.layer2, net.layer3

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        l2 = self.layer2(self.stem(x))
        l3 = self.layer3(l2)
        l2 = F.avg_pool2d(l2, 3, 1, 1)
        l3 = F.avg_pool2d(l3, 3, 1, 1)
        l3 = F.interpolate(l3, size=(l2.shape[2], l2.shape[3]), mode="bilinear", align_corners=False)
        return torch.cat([l2, l3], dim=1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arch", default="resnet18")
    ap.add_argument("--size", type=int, default=256)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    model = PatchFeatures(args.arch).eval()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    dummy = torch.zeros(1, 3, args.size, args.size)
    torch.onnx.export(
        model, (dummy,), args.out, input_names=["image"], output_names=["features"], opset_version=17,
        dynamic_axes={"image": {0: "batch"}, "features": {0: "batch"}}, dynamo=False,
    )
    print("exported", args.out, os.path.getsize(args.out) // 1024, "KiB", tuple(model(dummy).shape))


if __name__ == "__main__":
    main()
