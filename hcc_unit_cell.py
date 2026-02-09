import cadquery as cq
import math
from typing import Optional


class HccUnitCell:
    """
    Hexagonal Corner Cube (HCC) unit cell generator.

    Typical workflow
    ----------------
    cell = HccUnitCell(edge_length_mm)
    cell.make_cube()
    cell.rotate_corner_cube()
    cell.cut_from_top(z_plane=-0.2)
    shape = cell.shape()
    """

    def __init__(self, edge_length_mm: float):
        """
        Parameters
        ----------
        edge_length_mm : float
            Edge length of the base cube in millimeters.
        """
        if edge_length_mm <= 0:
            raise ValueError("edge_length_mm must be > 0")

        self.edge_length_mm = edge_length_mm
        self._shape: Optional[cq.Workplane] = None

    # ------------------------------------------------------------------
    # geometry primitives
    # ------------------------------------------------------------------

    @staticmethod
    def make_box(size_x: float, size_y: float, size_z: float) -> cq.Workplane:
        """
        Create a box centered at the origin.

        This replaces the old 'generate_rectangle' function.
        """
        if size_x <= 0 or size_y <= 0 or size_z <= 0:
            raise ValueError("All dimensions must be > 0")

        return cq.Workplane("XY").box(size_x, size_y, size_z)

    def make_cube(self) -> cq.Workplane:
        """
        Create the base cube centered at the origin.
        """
        self._shape = self.make_box(
            self.edge_length_mm,
            self.edge_length_mm,
            self.edge_length_mm,
        )
        return self._shape

    # ------------------------------------------------------------------
    # transforms
    # ------------------------------------------------------------------

    def rotate_corner_cube(self) -> cq.Workplane:
        """
        Rotate cube into corner-cube optical orientation.

        Rotations:
        1) 45° around Z
        2) atan(sqrt(2)) ≈ 54.7356° around X

        This aligns one cube corner to point upward,
        forming a retroreflector unit cell.
        """
        if self._shape is None:
            raise RuntimeError("Call make_cube() first")

        shape = self._shape

        # rotate around vertical axis
        shape = shape.rotate((0, 0, 0), (0, 0, 1), 45.0)

        # tilt cube so a corner faces upward
        alpha_deg = math.degrees(math.atan(math.sqrt(2)))
        shape = shape.rotate((0, 0, 0), (1, 0, 0), alpha_deg)

        self._shape = shape
        return shape

    # ------------------------------------------------------------------
    # cutting
    # ------------------------------------------------------------------

    def cut_from_top(
        self,
        z_plane: float,
        keep: str = "bottom",
        pad_xy: float = 1.0,
        z_height: float | None = None,
        clean: bool = True,
    ) -> cq.Workplane:
        """
        Cut the unit cell using an absolute Z plane.

        Procedure
        ---------
        1) Move the highest point of the geometry to z = 0
        2) Intersect with a half-space box

        Parameters
        ----------
        z_plane : float
            Cutting plane after top is moved to z=0 (usually negative).
        keep : str
            "bottom" → keep material below plane
            "top"    → keep material above plane
        pad_xy : float
            Extra XY margin for the cutting box.
        z_height : float | None
            Height of cutting box. If None, automatically derived.
        clean : bool
            Run topology cleanup after boolean.
        """
        if self._shape is None:
            raise RuntimeError("No geometry available")

        if keep not in {"top", "bottom"}:
            raise ValueError("keep must be 'top' or 'bottom'")

        shape = self._shape
        bb = shape.val().BoundingBox()

        # Move the top of the part to z=0
        z_shift = -bb.zmax
        shifted = shape.translate((0, 0, z_shift))
        bb = shifted.val().BoundingBox()

        # Determine XY footprint of cutting box
        size_x = (bb.xmax - bb.xmin) + 2 * pad_xy
        size_y = (bb.ymax - bb.ymin) + 2 * pad_xy
        cx = 0.5 * (bb.xmin + bb.xmax)
        cy = 0.5 * (bb.ymin + bb.ymax)

        # Automatically choose cutting box height if not provided
        if z_height is None:
            z_span = bb.zmax - bb.zmin
            z_height = max(1.0, 2.0 * z_span)

        # Position half-space
        if keep == "top":
            z_center = z_plane + z_height / 2.0
        else:
            z_center = z_plane - z_height / 2.0

        cutter = self.make_box(size_x, size_y, z_height).translate((cx, cy, z_center))

        result = shifted.intersect(cutter)

        if clean:
            result = result.clean()

        self._shape = result
        return result

    # ------------------------------------------------------------------
    # access
    # ------------------------------------------------------------------

    def shape(self) -> cq.Workplane:
        """Return the current geometry."""
        if self._shape is None:
            raise RuntimeError("Geometry not generated yet")
        return self._shape