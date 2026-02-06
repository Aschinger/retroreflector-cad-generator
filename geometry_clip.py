import cadquery as cq
from geometry import generate_rectangle
from pattern_assembly import make_nrow_compound
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

def clip_pattern_assembly_by_bbox(
    cube: cq.Workplane,
    nx: int,
    ny: int,
    dx: float,
    dy: float,
    dx0: float = 0.0,
    block_rows: int = 4,
    margin_x: float = 0.0,
    margin_y: float = 0.0,
    z_height: float = 10_000.0,
    z_center: float = 0.0,
    clean_clipped: bool = True,
    verbose: bool = False,
) -> Tuple[cq.Assembly, cq.Workplane]:
    """
    Returns
    -------
    (cq.Assembly, cq.Workplane)
        (clipped_assembly, bounding_box_solid)
    """
    if not isinstance(cube, cq.Workplane):
        raise TypeError("cube must be cadquery.Workplane")
    if nx <= 0 or ny <= 0:
        raise ValueError("nx and ny must be > 0")
    if dx <= 0 or dy <= 0:
        raise ValueError("dx and dy must be > 0")
    if not (1 <= block_rows < ny):
        raise ValueError("block_rows must satisfy 1 <= block_rows < ny")
    if z_height <= 0:
        raise ValueError("z_height must be > 0")

    # --- clipping solid (Workplane) and its AABB ---
    bbox_wp = make_bounding_box_solid(
        nx=nx, ny=ny, dx=dx, dy=dy, dx0=dx0,
        margin_x=margin_x, margin_y=margin_y,
        z_height=z_height, z_center=z_center,
    )
    bbox_bb = bbox_wp.val().BoundingBox()

    # --- build reusable block prototypes once (no union inside) ---
    block_even = make_nrow_compound(
        cube=cube, nx=nx, nrows=block_rows, dx=dx, dy=dy, dx0=dx0, row_start_parity=0
    )
    block_odd = make_nrow_compound(
        cube=cube, nx=nx, nrows=block_rows, dx=dx, dy=dy, dx0=dx0, row_start_parity=1
    )

    bb_even = block_even.val().BoundingBox()
    bb_odd = block_odd.val().BoundingBox()

    out = cq.Assembly(name="pattern_clipped")

    full_blocks = ny // block_rows
    rem = ny % block_rows

    kept = clipped = dropped = 0

    def _shifted_bb(bb: cq.BoundBox, dy_off: float):
        class _BB:
            xmin = bb.xmin
            xmax = bb.xmax
            ymin = bb.ymin + dy_off
            ymax = bb.ymax + dy_off
            zmin = bb.zmin
            zmax = bb.zmax
        return _BB()  # lightweight with same attributes

    for b in range(full_blocks):
        start_row = b * block_rows
        y_off = start_row * dy

        use_odd = (start_row & 1) == 1
        block_wp = block_odd if use_odd else block_even
        block_bb0 = bb_odd if use_odd else bb_even
        block_bb = _shifted_bb(block_bb0, y_off)

        if _bbox_contains(bbox_bb, block_bb):
            out.add(block_wp, name=f"block_{b}", loc=cq.Location(cq.Vector(0.0, y_off, 0.0)))
            kept += 1
            continue

        if not _bbox_intersects(bbox_bb, block_bb):
            dropped += 1
            continue

        placed = block_wp.translate((0.0, y_off, 0.0))
        clipped_wp = placed.intersect(bbox_wp)
        if clean_clipped:
            clipped_wp = clipped_wp.clean()

        out.add(clipped_wp, name=f"block_{b}_clipped", loc=cq.Location())
        clipped += 1

    if rem:
        start_row = full_blocks * block_rows
        y_off = start_row * dy
        parity = start_row & 1

        tail = make_nrow_compound(
            cube=cube, nx=nx, nrows=rem, dx=dx, dy=dy, dx0=dx0, row_start_parity=parity
        )
        tail_bb0 = tail.val().BoundingBox()
        tail_bb = _shifted_bb(tail_bb0, y_off)

        if _bbox_contains(bbox_bb, tail_bb):
            out.add(tail, name="tail", loc=cq.Location(cq.Vector(0.0, y_off, 0.0)))
            kept += 1
        elif not _bbox_intersects(bbox_bb, tail_bb):
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