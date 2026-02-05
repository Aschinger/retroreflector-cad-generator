import cadquery as cq
from typing import Iterable, List, Tuple
from geometry import generate_rectangle
from dataclasses import dataclass


@dataclass(frozen=True)
class PatternBBox:
    xmin: float
    xmax: float
    ymin: float
    ymax: float

def pattern_bounding_box_xy(nx: int, ny: int, dx: float, dy: float, dx0: float = 0.0) -> PatternBBox:
    if nx <= 0 or ny <= 0:
        raise ValueError("nx and ny must be > 0")
    if dx <= 0 or dy <= 0:
        raise ValueError("dx and dy must be > 0")

    x0 = 0.0
    x1 = (nx - 1) * dx

    if ny >= 2:
        x0_odd = dx0
        x1_odd = (nx - 1) * dx + dx0
        xmin = min(x0, x0_odd)
        xmax = max(x1, x1_odd)
    else:
        xmin, xmax = x0, x1

    ymin = 0.0
    ymax = (ny - 1) * dy

    return PatternBBox(xmin, xmax, ymin, ymax)


def make_bounding_box_solid(
    nx: int,
    ny: int,
    dx: float,
    dy: float,
    dx0: float = 0.0,
    margin_x: float = 0.0,
    margin_y: float = 0.0,
    z_height: float = 10000.0,
    z_center: float = 0.0,
) -> cq.Workplane:
    """
    Bounding box solid using generate_rectangle()
    """

    bb = pattern_bounding_box_xy(nx, ny, dx, dy, dx0)

    size_x = (bb.xmax - bb.xmin) + 2 * margin_x
    size_y = (bb.ymax - bb.ymin) + 2 * margin_y

    if size_x <= 0 or size_y <= 0 or z_height <= 0:
        raise ValueError("Invalid bounding box dimensions")

    center_x = 0.5 * (bb.xmin + bb.xmax)
    center_y = 0.5 * (bb.ymin + bb.ymax)

    box = generate_rectangle(size_x, size_y, z_height)
    box = box.translate((center_x, center_y, z_center))

    return box

def _bbox_contains(bb_outer: cq.BoundBox, bb_inner: cq.BoundBox) -> bool:
    return (
        bb_inner.xmin >= bb_outer.xmin and bb_inner.xmax <= bb_outer.xmax and
        bb_inner.ymin >= bb_outer.ymin and bb_inner.ymax <= bb_outer.ymax and
        bb_inner.zmin >= bb_outer.zmin and bb_inner.zmax <= bb_outer.zmax
    )

def _bbox_intersects(a: cq.BoundBox, b: cq.BoundBox) -> bool:
    return not (
        a.xmax < b.xmin or a.xmin > b.xmax or
        a.ymax < b.ymin or a.ymin > b.ymax or
        a.zmax < b.zmin or a.zmin > b.zmax
    )

def clip_pattern_only_outer_cubes(
    cube: cq.Workplane,
    nx: int,
    ny: int,
    dx: float,
    dy: float,
    dx0: float = 0.0,
    margin_x: float = 0.0,
    margin_y: float = 0.0,
    z_height: float = 10_000.0,
    z_center: float = 0.0,
    clean_clipped: bool = True,
    verbose: bool = False,
) -> cq.Workplane:

    """
    Build a cube pattern and clip ONLY cubes intersecting the bounding box boundary.

    Instead of intersecting the entire lattice with a bounding box (very slow),
    the function performs a fast bounding-box classification:

        interior cubes  → kept unchanged
        boundary cubes  → boolean intersected with box
        outside cubes   → discarded

    This reduces runtime from O(nx*ny) boolean operations to O(perimeter).

    Parameters
    ----------
    cube : cadquery.Workplane
        Base cube geometry already positioned around origin.
        Can be rotated beforehand. The function copies and translates it.

    nx : int
        Number of cube positions in X direction (columns).

    ny : int
        Number of cube positions in Y direction (rows).

    dx : float
        Pitch in X direction (distance between cube centers within a row).

    dy : float
        Pitch in Y direction (distance between rows).

    dx0 : float, optional
        Horizontal offset applied to every second row (staggered pattern).
        Row 0 has no offset, row 1 shifted by dx0, row 2 no offset, etc.

    margin_x : float, optional
        Extra margin added to bounding box in X direction.
        Typically half the cube width so the box trims cube faces instead
        of deleting entire cubes.

    margin_y : float, optional
        Extra margin added to bounding box in Y direction.
        Same purpose as margin_x.

    z_height : float, optional
        Height of the clipping box in Z direction.
        Should be larger than total pattern height to ensure full coverage.

    z_center : float, optional
        Vertical center position of the clipping box.
        Allows moving clipping plane up/down relative to pattern.

    clean_clipped : bool, optional
        If True, topology cleanup is performed on clipped cubes only.
        Recommended to avoid STEP artifacts but increases runtime slightly.

    verbose : bool, optional
        Print statistics about how many cubes were clipped vs untouched.

    Returns
    -------
    cadquery.Workplane
        Compound object containing all cubes after selective clipping.
        No fusion is performed.
    """

    if not isinstance(cube, cq.Workplane):
        raise TypeError("cube must be a cadquery.Workplane")
    if nx <= 0 or ny <= 0:
        raise ValueError("nx and ny must be > 0")
    if dx <= 0 or dy <= 0:
        raise ValueError("dx and dy must be > 0")
    if z_height <= 0:
        raise ValueError("z_height must be > 0")

    # Numeric XY bounds (placement bounds) + margins
    bb_xy = pattern_bounding_box_xy(nx, ny, dx, dy, dx0)
    xmin = bb_xy.xmin - margin_x
    xmax = bb_xy.xmax + margin_x
    ymin = bb_xy.ymin - margin_y
    ymax = bb_xy.ymax + margin_y

    cx = 0.5 * (xmin + xmax)
    cy = 0.5 * (ymin + ymax)

    # Solid box for clipping (use your generator)
    bbox_solid = generate_rectangle((xmax - xmin), (ymax - ymin), z_height).translate((cx, cy, z_center))
    bbox_wp = bbox_solid
    bbox_bb = bbox_wp.val().BoundingBox()

    base = cube.val()

    kept: List[cq.Shape] = []
    clipped_count = 0

    for j in range(ny):
        y = j * dy
        x_off = dx0 if (j % 2 == 1) else 0.0

        for i in range(nx):
            x = i * dx + x_off
            inst = base.moved(cq.Location(cq.Vector(x, y, 0.0)))

            inst_bb = inst.BoundingBox()

            # Fast classification using AABB
            if _bbox_contains(bbox_bb, inst_bb):
                kept.append(inst)
                continue

            if not _bbox_intersects(bbox_bb, inst_bb):
                # should not happen with your described bbox choice, but safe
                continue

            # Only boundary cubes get boolean intersection
            clipped = cq.Workplane("XY").newObject([inst]).intersect(bbox_wp)
            if clean_clipped:
                clipped = clipped.clean()
            kept.append(clipped.val())
            clipped_count += 1

    if verbose:
        print(f"[clip] total cubes: {nx*ny}, clipped cubes: {clipped_count}, untouched: {nx*ny - clipped_count}")

    return cq.Workplane("XY").newObject(kept)

def make_substrate_from_pattern_xy(
    pattern: cq.Workplane,
    nx: int,
    ny: int,
    dx: float,
    dy: float,
    dx0: float = 0.0,
    margin_x: float = 0.0,
    margin_y: float = 0.0,
    h: float = 5.0,
    z_offset: float = 0.0,
) -> cq.Workplane:
    """
    Create a substrate block sized to the pattern's XY bounding box (+ margins),
    with thickness h, placed below the pattern so its top face touches the
    lowest Z of the pattern, then shifted by z_offset.

    z_offset:
        Positive → moves substrate upward into the pattern
        Negative → moves substrate further downward
    """

    if not isinstance(pattern, cq.Workplane):
        raise TypeError("pattern must be a cadquery.Workplane")
    if h <= 0:
        raise ValueError("h must be > 0")

    bb_xy = pattern_bounding_box_xy(nx, ny, dx, dy, dx0)

    size_x = (bb_xy.xmax - bb_xy.xmin) + 2.0 * margin_x
    size_y = (bb_xy.ymax - bb_xy.ymin) + 2.0 * margin_y

    if size_x <= 0 or size_y <= 0:
        raise ValueError("Invalid substrate XY dimensions")

    cx = 0.5 * (bb_xy.xmin + bb_xy.xmax)
    cy = 0.5 * (bb_xy.ymin + bb_xy.ymax)

    # contact with pattern bottom
    pat_bb = pattern.val().BoundingBox()
    z_contact = pat_bb.zmin
    z_center = z_contact - h / 2.0 + z_offset

    substrate = generate_rectangle(size_x, size_y, h).translate((cx, cy, z_center))

    return substrate