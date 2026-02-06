import cadquery as cq
import math
from typing import Tuple


Vector = Tuple[float, float, float]


def generate_rectangle(a: float, b: float, c: float) -> cq.Workplane:
    """
    Create a rectangular prism centered at the origin.

    Parameters
    ----------
    a : float
        Size in X direction (mm)
    b : float
        Size in Y direction (mm)
    c : float
        Size in Z direction (mm)

    Returns
    -------
    cadquery.Workplane
        Rectangular solid
    """
    if a <= 0 or b <= 0 or c <= 0:
        raise ValueError("All dimensions must be > 0")

    return cq.Workplane("XY").box(a, b, c)

def rotate_shape(
    shape: cq.Workplane,
    axis_start: Vector,
    axis_end: Vector,
    angle_deg: float
) -> cq.Workplane:
    """
    Rotate a shape around an arbitrary axis.

    Parameters
    ----------
    shape : cadquery.Workplane
        Shape to rotate
    axis_start : (x, y, z)
        First point defining rotation axis
    axis_end : (x, y, z)
        Second point defining rotation axis
    angle_deg : float
        Rotation angle in degrees

    Returns
    -------
    cadquery.Workplane
        Rotated shape
    """

    if not isinstance(shape, cq.Workplane):
        raise TypeError("shape must be cadquery.Workplane")

    if axis_start == axis_end:
        raise ValueError("Rotation axis points must differ")

    if angle_deg == 0:
        return shape

    rotated = shape.rotate(axis_start, axis_end, angle_deg)
    return rotated

def rotate_hexagonal_cube_corner(shape: cq.Workplane) -> cq.Workplane:
    """
    Rotate 45° about Z, then 45° about X (in that order).
    """
    if not isinstance(shape, cq.Workplane):
        raise TypeError("shape must be a cadquery.Workplane")

    # determine edge length and diagonal for info
    edge_length_mm = shape.val().BoundingBox().xlen
    face_diagonal_mm = math.sqrt(2) * shape.val().BoundingBox().xlen

    # first rotate 45° around Z axis
    shape = shape.rotate((0, 0, 0), (0, 0, 1), 45.0)
    # define second rotation angle for hexagonal cube corner orientation
    alpha_deg = math.degrees(math.atan(math.sqrt(2)))
    shape = shape.rotate((0, 0, 0), (1, 0, 0), alpha_deg)
    return shape

def cut_in_xy_plane_center(
    cube_rot: cq.Workplane,
    keep: str = "top",
    z_offset: float = 0.0,
    pad_xy: float = 1.0,
    pad_z: float = 1.0,
    clean: bool = True,
) -> cq.Workplane:
    """
    Cut a rotated cube (or any solid) in half by an XY plane through its center,
    and keep one half.

    The cutting plane is z = z_center + z_offset, where z_center is computed
    from the solid's bounding box center.

    Parameters
    ----------
    cube_rot : cq.Workplane
        Solid to cut (e.g. cube rotated by arbitrary angles).
    keep : str
        "top"  -> keep z >= plane
        "bottom" -> keep z <= plane
    z_offset : float
        Offset of the cut plane relative to the solid's center plane.
        0.0 means exactly through the solid center.
    pad_xy : float
        Extra margin added to the halfspace box in X and Y.
    pad_z : float
        Extra margin added to the halfspace box height.
    clean : bool
        If True, run .clean() on the result.

    Returns
    -------
    cq.Workplane
        Cut half of the input solid.
    """
    if not isinstance(cube_rot, cq.Workplane):
        raise TypeError("cube_rot must be a cadquery.Workplane")
    if keep not in {"top", "bottom"}:
        raise ValueError("keep must be 'top' or 'bottom'")
    if pad_xy < 0 or pad_z < 0:
        raise ValueError("pad_xy and pad_z must be >= 0")

    solid = cube_rot.val()
    bb = solid.BoundingBox()

    # Bounding box center of the solid (robust even if the solid was translated)
    cx = 0.5 * (bb.xmin + bb.xmax)
    cy = 0.5 * (bb.ymin + bb.ymax)
    cz = 0.5 * (bb.zmin + bb.zmax)

    # Cut plane z = cz + z_offset
    z_plane = cz + z_offset

    # Tight halfspace box dimensions + padding
    size_x = (bb.xmax - bb.xmin) + 2.0 * pad_xy
    size_y = (bb.ymax - bb.ymin) + 2.0 * pad_xy
    size_z = (bb.zmax - bb.zmin) + 2.0 * pad_z

    # Halfspace must extend beyond the plane in the kept direction
    # Use a height that certainly covers the whole solid.
    z_height = size_z * 2.0

    if keep == "top":
        z_center = z_plane + z_height / 2.0
    else:
        z_center = z_plane - z_height / 2.0

    halfspace = generate_rectangle(size_x, size_y, z_height).translate((cx, cy, z_center))

    result = cube_rot.intersect(halfspace)
    if clean:
        result = result.clean()

    return result

import cadquery as cq


def cut_at_z_plane_from_top(
    shape: cq.Workplane,
    z_plane: float,
    keep: str = "bottom",
    pad_xy: float = 1.0,
    z_height: float | None = None,
    clean: bool = True,
) -> cq.Workplane:
    """
    Move the object so its top touches z=0, then cut at absolute z_plane.

    After shifting:
        z = 0      → original top surface
        z < 0      → inside the part

    Parameters
    ----------
    shape : cq.Workplane
        Solid to cut.
    z_plane : float
        Cutting plane position AFTER shifting top to z=0.
        (Usually negative if cutting into the part)
    keep : str
        "bottom" -> keep z <= z_plane  (material below the plane)
        "top"    -> keep z >= z_plane
    pad_xy : float
        Extra margin added to the halfspace box in X and Y.
    z_height : float | None
        Height of the halfspace box. If None, derived from shape height.
    clean : bool
        Run .clean() on result.

    Returns
    -------
    cq.Workplane
        Cut solid.
    """

    if not isinstance(shape, cq.Workplane):
        raise TypeError("shape must be cadquery.Workplane")
    if keep not in {"top", "bottom"}:
        raise ValueError("keep must be 'top' or 'bottom'")

    solid = shape.val()
    bb = solid.BoundingBox()

    # --- shift so top sits at z=0 ---
    z_shift = -bb.zmax
    print(f"Shifting shape by z={z_shift:.3f} to place top at z=0")
    shifted = shape.translate((0, 0, z_shift))

    bb = shifted.val().BoundingBox()

    # footprint
    size_x = (bb.xmax - bb.xmin) + 2 * pad_xy
    size_y = (bb.ymax - bb.ymin) + 2 * pad_xy
    cx = 0.5 * (bb.xmin + bb.xmax)
    cy = 0.5 * (bb.ymin + bb.ymax)

    # choose height
    if z_height is None:
        z_span = bb.zmax - bb.zmin
        z_height = max(1.0, 2.0 * z_span)

    # place halfspace
    if keep == "top":
        z_center = z_plane + z_height / 2.0
    else:
        z_center = z_plane - z_height / 2.0

    halfspace = generate_rectangle(size_x, size_y, z_height).translate((cx, cy, z_center))

    result = shifted.intersect(halfspace)

    if clean:
        result = result.clean()

    return result



def unify_shapes(a: cq.Workplane, b: cq.Workplane) -> cq.Workplane:
    """
    Boolean union of two shapes.

    Parameters
    ----------
    a : cadquery.Workplane
        First solid
    b : cadquery.Workplane
        Second solid

    Returns
    -------
    cadquery.Workplane
        Combined solid
    """
    if not isinstance(a, cq.Workplane) or not isinstance(b, cq.Workplane):
        raise TypeError("Both inputs must be cadquery.Workplane objects")

    # fuse the solids
    result = a.union(b)

    # clean model (important for STEP export & downstream CAD)
    result = result.clean()

    return result

def add_shapes(a: cq.Workplane, b: cq.Workplane, clean: bool = False) -> cq.Workplane:
    """
    Combine two shapes without boolean fusion (keeps separate solids).

    Parameters
    ----------
    a, b : cq.Workplane
        Shapes to combine (no union/fuse).
    clean : bool
        Optional cleanup (usually not needed for a simple compound).

    Returns
    -------
    cq.Workplane
        Workplane containing both solids as a compound.
    """
    if not isinstance(a, cq.Workplane) or not isinstance(b, cq.Workplane):
        raise TypeError("Both inputs must be cadquery.Workplane")

    solids = []
    solids.extend(a.objects)
    solids.extend(b.objects)

    wp = cq.Workplane("XY").newObject(solids)
    return wp.clean() if clean else wp
