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