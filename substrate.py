from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import cadquery as cq

from pattern import PatternLayout


@dataclass(frozen=True)
class SubstrateParams:
    thickness: float
    margin: float
    edge_length_mm: float  # used as fallback footprint half-size
    z_extra: float = 0.0
    clean: bool = True
    move_by_bbox_height: bool = False
    move_direction: str = "down"  # "down" or "up"
    use_unitcell_bbox_for_footprint: bool = False  # prefer real geometry if available


class Substrate:
    """
    Substrate generator and assembly wrapper.

    Geometry:
      - substrate outer XY = pattern center bounds expanded by (half_footprint + margin)
      - cut opening using bbox_wp (optionally Z-extended by z_extra)

    Z placement:
      - contact plane is pattern assembly zmin
      - substrate is placed at (z_top - thickness/2) but in this implementation
        it is shifted upward by bbox_height before cutting (legacy behavior),
        then shifted back by bbox_height (optional).
    """

    def __init__(self, layout: PatternLayout, params: SubstrateParams):
        if not isinstance(layout, PatternLayout):
            raise TypeError("layout must be PatternLayout")

        if params.thickness <= 0:
            raise ValueError("thickness must be > 0")
        if params.margin < 0:
            raise ValueError("margin must be >= 0")
        if params.edge_length_mm <= 0:
            raise ValueError("edge_length_mm must be > 0")
        if params.move_direction not in {"down", "up"}:
            raise ValueError("move_direction must be 'down' or 'up'")
        if params.z_extra < 0:
            raise ValueError("z_extra must be >= 0")

        self.layout = layout
        self.p = params

    @staticmethod
    def _make_box(size_x: float, size_y: float, size_z: float) -> cq.Workplane:
        """Local primitive to avoid coupling to HccUnitCell internals."""
        if size_x <= 0 or size_y <= 0 or size_z <= 0:
            raise ValueError("All box dimensions must be > 0")
        return cq.Workplane("XY").box(size_x, size_y, size_z)

    @staticmethod
    def assembly_zmin_zmax(assy: cq.Assembly) -> Tuple[float, float]:
        """Minimum and maximum Z of all geometry in an Assembly."""
        if not isinstance(assy, cq.Assembly):
            raise TypeError("assy must be cadquery.Assembly")
        bb = assy.toCompound().BoundingBox()
        return bb.zmin, bb.zmax

    def make_cut_by_bbox(
        self,
        pattern_assy: cq.Assembly,
        bbox_wp: cq.Workplane,
        unitcell_wp: cq.Workplane | None = None,
    ) -> cq.Workplane:
        """
        Create substrate and cut out bbox_wp.

        unitcell_wp (optional):
            If provided and use_unitcell_bbox_for_footprint=True, the substrate expansion
            uses half of unitcell_wp BoundingBox x/y extents instead of edge_length_mm/2.
        """
        if not isinstance(pattern_assy, cq.Assembly):
            raise TypeError("pattern_assy must be cadquery.Assembly")
        if not isinstance(bbox_wp, cq.Workplane):
            raise TypeError("bbox_wp must be cadquery.Workplane")

        # Contact plane: bottom of current assembly geometry
        zmin, _ = self.assembly_zmin_zmax(pattern_assy)
        z_top = zmin

        # Layout bounds (centers)
        x_min, x_max, y_min, y_max = self.layout.center_bounds_xy

        # Determine half-footprint used to expand from center grid to full part coverage
        if self.p.use_unitcell_bbox_for_footprint and unitcell_wp is not None:
            bb_uc = unitcell_wp.val().BoundingBox()
            half_x = 0.5 * bb_uc.xlen
            half_y = 0.5 * bb_uc.ylen
        else:
            half_x = half_y = 0.5 * self.p.edge_length_mm

        x_min -= (half_x + self.p.margin)
        x_max += (half_x + self.p.margin)
        y_min -= (half_y + self.p.margin)
        y_max += (half_y + self.p.margin)

        size_x = x_max - x_min
        size_y = y_max - y_min
        cx = 0.5 * (x_min + x_max)
        cy = 0.5 * (y_min + y_max)

        # bbox info
        bb = bbox_wp.val().BoundingBox()
        bbox_height = bb.zmax - bb.zmin
        if bbox_height <= 0:
            raise ValueError("bbox height must be > 0")

        # Place substrate (legacy: shifted upward by bbox height for cutting)
        cz_shifted = z_top - self.p.thickness / 2.0 + bbox_height
        substrate = self._make_box(size_x, size_y, self.p.thickness).translate((cx, cy, cz_shifted))

        # Cutter derived from bbox, extended in Z if desired
        cutter = (
            cq.Workplane("XY")
            .box(bb.xlen, bb.ylen, bb.zlen + self.p.z_extra, centered=(True, True, True))
            .translate((
                0.5 * (bb.xmin + bb.xmax),
                0.5 * (bb.ymin + bb.ymax),
                0.5 * (bb.zmin + bb.zmax),
            ))
        )

        # Optional safety: ensure overlap (AABB) before doing a potentially expensive cut
        sb = substrate.val().BoundingBox()
        overlaps = not (
            sb.xmax < bb.xmin or sb.xmin > bb.xmax or
            sb.ymax < bb.ymin or sb.ymin > bb.ymax or
            sb.zmax < bb.zmin or sb.zmin > bb.zmax
        )
        if not overlaps:
            # likely a placement mistake; better to fail loudly
            raise ValueError("Substrate does not overlap bbox cutter (check bbox Z and substrate shift).")

        substrate_cut = substrate.cut(cutter)
        if self.p.clean:
            substrate_cut = substrate_cut.clean()

        # Optional move after cutting
        if self.p.move_by_bbox_height:
            dz = -bbox_height if self.p.move_direction == "down" else bbox_height
            substrate_cut = substrate_cut.translate((0.0, 0.0, dz))

        return substrate_cut

    @staticmethod
    def wrap_with_pattern(
        pattern_assy: cq.Assembly,
        substrate_wp: cq.Workplane,
        pattern_name: str = "pattern",
        substrate_name: str = "substrate",
        top_name: str = "pattern_with_substrate",
    ) -> cq.Assembly:
        """Wrap pattern + substrate into a top assembly."""
        if not isinstance(pattern_assy, cq.Assembly):
            raise TypeError("pattern_assy must be cadquery.Assembly")
        if not isinstance(substrate_wp, cq.Workplane):
            raise TypeError("substrate_wp must be cadquery.Workplane")

        top = cq.Assembly(name=top_name)
        top.add(pattern_assy, name=pattern_name, loc=cq.Location())
        top.add(substrate_wp, name=substrate_name, loc=cq.Location())
        return top
