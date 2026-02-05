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
    z_height: float = 10_000.0,
    clean: bool = True,
) -> cq.Workplane:
    """
    Cut a rotated cube by the XY-plane through its center and keep one half.

    Assumptions:
      - The cube is centered at the origin before rotation.
      - Rotation axes pass through the origin, so the cube center remains at z=0.

    Parameters
    ----------
    cube_rot : cq.Workplane
        Rotated cube (e.g., output of rotate_hexagonal_cube_corner()).
    keep : str
        Which half to keep: "top" (z >= z_offset) or "bottom" (z <= z_offset).
    z_offset : float
        Moves the cutting plane to z = z_offset (default 0.0).
    z_height : float
        Height of the half-space box used for intersection (must be large enough).
    clean : bool
        If True, runs .clean() on the result.

    Returns
    -------
    cq.Workplane
        The cut cube half (cube_rot_cut).
    """
    if not isinstance(cube_rot, cq.Workplane):
        raise TypeError("cube_rot must be a cadquery.Workplane")
    if keep not in {"top", "bottom"}:
        raise ValueError("keep must be 'top' or 'bottom'")
    if z_height <= 0:
        raise ValueError("z_height must be > 0")

    # Use the rotated cube's own XY extents for a safe cutting box footprint.
    bb = cube_rot.val().BoundingBox()
    size_x = (bb.xmax - bb.xmin) * 2.0
    size_y = (bb.ymax - bb.ymin) * 2.0

    # Create a large "half-space" box and intersect with the cube.
    # Center the box so that its top or bottom face lies on the cutting plane z=z_offset.
    if keep == "top":
        z_center = z_offset + z_height / 2.0
    else:  # keep == "bottom"
        z_center = z_offset - z_height / 2.0

    halfspace = generate_rectangle(size_x, size_y, z_height).translate((0.0, 0.0, z_center))

    cube_rot_cut = cube_rot.intersect(halfspace)
    if clean:
        cube_rot_cut = cube_rot_cut.clean()

    return cube_rot_cut

def pattern_cubes_staggered(
    cube: cq.Workplane,
    nx: int,
    ny: int,
    dx: float,
    dy: float,
    dx0: float = 0.0,
    fuse: bool = True,
    clean: bool = True,
) -> cq.Workplane:
    """
    Create a staggered 2D pattern of cubes (or any solid Workplane), efficiently.

    Pattern:
      - Row j at y = j*dy
      - x offset = dx0 for every second row (j odd), else 0
      - x positions: i*dx + x_offset

    Efficiency:
      - Builds a list of transformed solids
      - Fuses once at the end using combineSolids() (avoids O(N^2) union)

    Parameters
    ----------
    cube : cq.Workplane
        Base solid (typically already rotated)
    nx, ny : int
        Count in x and y
    dx, dy : float
        Pitch in x and y
    dx0 : float
        Additional x offset applied to every second row
    fuse : bool
        If True, fuse into a single solid where possible
    clean : bool
        If True, runs .clean() on the result (recommended for STEP)

    Returns
    -------
    cq.Workplane
        Pattern as a fused solid (or a compound if not fusable/disjoint)
    """
    if not isinstance(cube, cq.Workplane):
        raise TypeError("cube must be a cadquery.Workplane")
    if nx <= 0 or ny <= 0:
        raise ValueError("nx and ny must be > 0")
    if dx <= 0 or dy <= 0:
        raise ValueError("dx and dy must be > 0")

    base = cube.val()  # underlying Solid

    solids = []
    for j in range(ny):
        x_off = dx0 if (j % 2 == 1) else 0.0
        y = j * dy
        # print(f"Processing row {j + 1} of {ny}.")
        for i in range(nx):
            x = i * dx + x_off
            loc = cq.Location(cq.Vector(x, y, 0.0))
            solids.append(base.moved(loc))

    print(f"[Pattern] Generating new objects in workplane...")
    wp = cq.Workplane("XY").newObject(solids)

    if fuse:
        # Fast fuse in one go; avoids repeated boolean unions
        print(f"[Pattern] Fusing {len(solids)} solids...")
        wp = wp.union()

    if clean:
        wp = wp.clean()

    return wp


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
