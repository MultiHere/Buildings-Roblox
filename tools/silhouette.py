"""Silhouette match between the reference (white background) and a render (white or transparent background).

usage: python tools/silhouette.py ref/building1_ref_small.png out/building01/ref_cam.png [--out diff.png]
Both masks are cropped to their own bounding box and resized to the same size, so framing and scale do not matter,
only shape. Prints IoU (1.0 = same outline) and the bbox aspect of each. --out writes a diff image:
grey = both, red = only the reference, blue = only the render.
"""
import argparse

import numpy as np
from PIL import Image

SIZE = (400, 266)


def mask(path, white=235):
    im = Image.open(path).convert("RGBA")
    a = np.asarray(im).astype(np.int16)
    solid = a[..., 3] > 20
    not_white = (a[..., :3] < white).any(axis=2)
    m = solid & not_white
    ys, xs = np.nonzero(m)
    if len(xs) == 0:
        raise SystemExit(f"empty mask: {path}")
    box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    crop = Image.fromarray((m * 255).astype(np.uint8)).crop(box).resize(SIZE, Image.BILINEAR)
    aspect = (box[2] - box[0]) / (box[3] - box[1])
    return np.asarray(crop) > 127, aspect


def main():
    p = argparse.ArgumentParser()
    p.add_argument("ref")
    p.add_argument("render")
    p.add_argument("--out")
    args = p.parse_args()
    r, ra = mask(args.ref)
    o, oa = mask(args.render)
    iou = (r & o).sum() / max(1, (r | o).sum())
    print(f"silhouette IoU {iou:.3f}  aspect ref {ra:.2f} render {oa:.2f}")
    if args.out:
        img = np.full(r.shape + (3,), 255, np.uint8)
        img[r & o] = (150, 150, 150)
        img[r & ~o] = (220, 40, 40)
        img[~r & o] = (40, 80, 230)
        Image.fromarray(img).save(args.out)


if __name__ == "__main__":
    main()
