from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple, List, Optional

import cadquery as cq

from hcc_unit_cell import HccUnitCell  # adjust import path


# ----- Layout dataclass (single source of truth for nx/ny/dx/dy/dx0) --------
@dataclass(frozen=True)
class PatternBBox:
    xmin: float
    xmax: float
    ymin: float
    ymax: float


def validate_pattern_inputs(nx: int, ny: int, dx: float, dy: float) -> None:
    if nx <= 0 or ny <= 0:
        raise ValueError("nx and ny must be > 0")
    if dx <= 0 or dy <= 0:
        raise ValueError("dx and dy must be > 0")


@dataclass(frozen=True)
class PatternLayout:
    """
    Layout definition for a staggered 2D pattern.

    Only contains geometric layout parameters:
      nx, ny, dx, dy, dx0
    """
    nx: int
    ny: int
    dx: float
    dy: float
    dx0: float = 0.0
    _bbox: PatternBBox = field(init=False, repr=False)

    def __post_init__(self) -> None:
        validate_pattern_inputs(self.nx, self.ny, self.dx, self.dy)
        object.__setattr__(self, "_bbox", self._compute_bbox())

    def _compute_bbox(self) -> PatternBBox:
        x0 = 0.0
        x1 = (self.nx - 1) * self.dx

        if self.ny >= 2:
            x0_odd = self.dx0
            x1_odd = (self.nx - 1) * self.dx + self.dx0
            xmin = min(x0, x0_odd)
            xmax = max(x1, x1_odd)
        else:
            xmin, xmax = x0, x1

        ymin = 0.0
        ymax = (self.ny - 1) * self.dy
        return PatternBBox(xmin, xmax, ymin, ymax)

    @property
    def bbox(self) -> PatternBBox:
        return self._bbox

    @property
    def center_bounds_xy(self) -> Tuple[float, float, float, float]:
        return self._bbox.xmin, self._bbox.xmax, self._bbox.ymin, self._bbox.ymax


# --------- Pattern class (uses PatternLayout as the only dataclass for layout) ----------

class Pattern:
    """
    Build a staggered pattern assembly from a base cube (Workplane).

    - Uses PatternLayout as the only layout dataclass.
    - Supports block instancing (block_rows) and optional clipping by bbox.
    - Bounding box solid uses cube Z height exactly and layout XY (+ margins).
    - Uses HccUnitCell._make_box instead of geometry.generate_rectangle.
    """

    def __init__(
        self,
        cube: cq.Workplane,
        layout: PatternLayout,
        block_rows: int = 4,
        margin_x: float = 0.0,
        margin_y: float = 0.0,
    ):
        if not isinstance(cube, cq.Workplane):
            raise TypeError("cube must be cadquery.Workplane")
        if not isinstance(layout, PatternLayout):
            raise TypeError("layout must be PatternLayout")

        if not (1 <= block_rows < layout.ny):
            raise ValueError("block_rows must satisfy 1 <= block_rows < ny")
        if margin_x < 0 or margin_y < 0:
            raise ValueError("margins must be >= 0")

        self.cube = cube
        self.layout = layout
        self.block_rows = block_rows
        self.margin_x = margin_x
        self.margin_y = margin_y

        self._bbox_wp: Optional[cq.Workplane] = None

    # ---------- bbox helpers -------------------------------------------------

    @staticmethod
    def _bbox_contains(bb_outer, bb_inner) -> bool:
        return (
            bb_inner.xmin >= bb_outer.xmin and bb_inner.xmax <= bb_outer.xmax
            and bb_inner.ymin >= bb_outer.ymin and bb_inner.ymax <= bb_outer.ymax
            and bb_inner.zmin >= bb_outer.zmin and bb_inner.zmax <= bb_outer.zmax
        )

    @staticmethod
    def _bbox_intersects(a, b) -> bool:
        return not (
            a.xmax < b.xmin or a.xmin > b.xmax
            or a.ymax < b.ymin or a.ymin > b.ymax
            or a.zmax < b.zmin or a.zmin > b.zmax
        )

    @staticmethod
    def _shifted_bb(bb: cq.BoundBox, dy_off: float):
        class _BB:
            xmin = bb.xmin
            xmax = bb.xmax
            ymin = bb.ymin + dy_off
            ymax = bb.ymax + dy_off
            zmin = bb.zmin
            zmax = bb.zmax
        return _BB()

    # ------- geometry builders -------------------------------------

    def make_bounding_box_solid(self) -> cq.Workplane:
        """
        Bounding box solid:
          - XY from layout bbox (+ margin_x/margin_y)
          - Z exactly from cube height (cube BoundingBox z-span)
        """
        bb_xy = self.layout.bbox

        size_x = (bb_xy.xmax - bb_xy.xmin) + 2.0 * self.margin_x
        size_y = (bb_xy.ymax - bb_xy.ymin) + 2.0 * self.margin_y
        if size_x <= 0 or size_y <= 0:
            raise ValueError("Invalid bounding box XY dimensions")

        cx = 0.5 * (bb_xy.xmin + bb_xy.xmax)
        cy = 0.5 * (bb_xy.ymin + bb_xy.ymax)

        bb_z = self.cube.val().BoundingBox()
        z_height = bb_z.zmax - bb_z.zmin
        if z_height <= 0:
            raise ValueError("Invalid cube Z height")
        z_center = 0.5 * (bb_z.zmin + bb_z.zmax)

        box = HccUnitCell.make_box(size_x, size_y, z_height).translate((cx, cy, z_center))
        self._bbox_wp = box
        return box

    def make_nrow_compound(self, nrows: int, row_start_parity: int) -> cq.Workplane:
        """
        nrows rows as one compound (no union), with stagger.
        """
        if nrows <= 0:
            raise ValueError("nrows must be > 0")
        if row_start_parity not in (0, 1):
            raise ValueError("row_start_parity must be 0 or 1")

        base = self.cube.val()
        solids: List[cq.Shape] = []

        for r in range(nrows):
            y = r * self.layout.dy
            x_off = self.layout.dx0 if ((row_start_parity + r) & 1) else 0.0
            for i in range(self.layout.nx):
                x = i * self.layout.dx + x_off
                solids.append(base.moved(cq.Location(cq.Vector(x, y, 0.0))))

        return cq.Workplane("XY").newObject(solids)

    # ----------- assembly build --------------------------------------

    def build(
        self,
        do_clip: bool = True,
        clean_clipped: bool = True,
        verbose: bool = False,
    ) -> Tuple[cq.Assembly, cq.Workplane]:
        """
        Returns
        -------
        (cq.Assembly, cq.Workplane)
            (assembly, bounding_box_solid)
        """
        bbox_wp = self.make_bounding_box_solid()
        bbox_bb = bbox_wp.val().BoundingBox()

        nx, ny = self.layout.nx, self.layout.ny
        dx, dy, dx0 = self.layout.dx, self.layout.dy, self.layout.dx0

        full_blocks = ny // self.block_rows
        rem = ny % self.block_rows

        # reusable prototypes
        block_even = self.make_nrow_compound(self.block_rows, row_start_parity=0)
        block_odd = self.make_nrow_compound(self.block_rows, row_start_parity=1)

        # no clipping
        if not do_clip:
            assy = cq.Assembly(name="pattern")

            for b in range(full_blocks):
                start_row = b * self.block_rows
                y_off = start_row * dy
                block_wp = block_odd if (start_row & 1) else block_even
                assy.add(block_wp, name=f"block_{b}", loc=cq.Location(cq.Vector(0.0, y_off, 0.0)))

            if rem:
                start_row = full_blocks * self.block_rows
                y_off = start_row * dy
                parity = start_row & 1
                tail = self.make_nrow_compound(rem, row_start_parity=parity)
                assy.add(tail, name="tail", loc=cq.Location(cq.Vector(0.0, y_off, 0.0)))

            return assy, bbox_wp

        # clipping path
        bb_even = block_even.val().BoundingBox()
        bb_odd = block_odd.val().BoundingBox()

        out = cq.Assembly(name="pattern_clipped")
        kept = clipped = dropped = 0

        for b in range(full_blocks):
            start_row = b * self.block_rows
            y_off = start_row * dy

            use_odd = (start_row & 1) == 1
            block_wp = block_odd if use_odd else block_even
            block_bb0 = bb_odd if use_odd else bb_even
            block_bb = self._shifted_bb(block_bb0, y_off)

            if self._bbox_contains(bbox_bb, block_bb):
                out.add(block_wp, name=f"block_{b}", loc=cq.Location(cq.Vector(0.0, y_off, 0.0)))
                kept += 1
                continue

            if not self._bbox_intersects(bbox_bb, block_bb):
                dropped += 1
                continue

            placed = block_wp.translate((0.0, y_off, 0.0))
            clipped_wp = placed.intersect(bbox_wp)
            if clean_clipped:
                clipped_wp = clipped_wp.clean()

            out.add(clipped_wp, name=f"block_{b}_clipped", loc=cq.Location())
            clipped += 1

        if rem:
            start_row = full_blocks * self.block_rows
            y_off = start_row * dy
            parity = start_row & 1

            tail = self.make_nrow_compound(rem, row_start_parity=parity)
            tail_bb0 = tail.val().BoundingBox()
            tail_bb = self._shifted_bb(tail_bb0, y_off)

            if self._bbox_contains(bbox_bb, tail_bb):
                out.add(tail, name="tail", loc=cq.Location(cq.Vector(0.0, y_off, 0.0)))
                kept += 1
            elif not self._bbox_intersects(bbox_bb, tail_bb):
                dropped += 1
            else:
                placed = tail.translate((0.0, y_off, 0.0))
                clipped_wp = placed.intersect(bbox_wp)
                if clean_clipped:
                    clipped_wp = clipped_wp.clean()
                out.add(clipped_wp, name="tail_clipped", loc=cq.Location())
                clipped += 1

        if verbose:
            print(f"[assy-clip] kept={kept}, clipped={clipped}, dropped={dropped}")

        return out, bbox_wp
