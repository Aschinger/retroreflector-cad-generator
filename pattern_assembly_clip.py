from typing import Tuple, List

import cadquery as cq


from geometry import generate_rectangle
from pattern_layout import pattern_bounding_box_xy, validate_block_rows, validate_pattern_inputs


def make_bounding_box_solid(
        cube: cq.Workplane,
        nx: int,
        ny: int,
        dx: float,
        dy: float,
        dx0: float = 0.0,
        margin_x: float = 0.0,
        margin_y: float = 0.0,
) -> cq.Workplane:
    """
    Bounding box solid in XY from layout (+ margins) and in Z exactly from cube height.
    """
    if not isinstance(cube, cq.Workplane):
        raise TypeError("cube must be cadquery.Workplane")

    bb_xy = pattern_bounding_box_xy(nx, ny, dx, dy, dx0)

    size_x = (bb_xy.xmax - bb_xy.xmin) + 2.0 * margin_x
    size_y = (bb_xy.ymax - bb_xy.ymin) + 2.0 * margin_y
    if size_x <= 0 or size_y <= 0:
        raise ValueError("Invalid bounding box XY dimensions")

    cx = 0.5 * (bb_xy.xmin + bb_xy.xmax)
    cy = 0.5 * (bb_xy.ymin + bb_xy.ymax)

    bb_z = cube.val().BoundingBox()
    z_height = bb_z.zmax - bb_z.zmin
    if z_height <= 0:
        raise ValueError("Invalid cube Z height")
    z_center = 0.5 * (bb_z.zmin + bb_z.zmax)

    box = generate_rectangle(size_x, size_y, z_height).translate((cx, cy, z_center))
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

def make_nrow_compound(
    cube: cq.Workplane,
    nx: int,
    nrows: int,
    dx: float,
    dy: float,
    dx0: float = 0.0,
    row_start_parity: int = 0,
) -> cq.Workplane:
    """
    nrows rows as one compound (no union), with stagger.
    row_start_parity:
        0 -> first row has x_off = 0
        1 -> first row has x_off = dx0
    """
    if not isinstance(cube, cq.Workplane):
        raise TypeError("cube must be cadquery.Workplane")
    if nx <= 0 or nrows <= 0:
        raise ValueError("nx and nrows must be > 0")
    if dx <= 0 or dy <= 0:
        raise ValueError("dx and dy must be > 0")
    if row_start_parity not in (0, 1):
        raise ValueError("row_start_parity must be 0 or 1")

    base = cube.val()
    solids: List[cq.Shape] = []

    # Tight loop; avoid extra work
    for r in range(nrows):
        y = r * dy
        x_off = dx0 if ((row_start_parity + r) & 1) else 0.0

        for i in range(nx):
            x = i * dx + x_off
            solids.append(base.moved(cq.Location(cq.Vector(x, y, 0.0))))

    return cq.Workplane("XY").newObject(solids)

def make_pattern(
    cube: cq.Workplane,
    nx: int,
    ny: int,
    dx: float,
    dy: float,
    dx0: float = 0.0,
    block_rows: int = 4,
    margin_x: float = 0.0,
    margin_y: float = 0.0,
    clean_clipped: bool = True,
    verbose: bool = False,
    do_clip: bool = True,
) -> Tuple[cq.Assembly, cq.Workplane]:
    """
    If do_clip is False, returns the unmodified pattern assembly plus the bbox solid.

    Returns
    -------
    (cq.Assembly, cq.Workplane)
        (assembly, bounding_box_solid)
    """
    if not isinstance(cube, cq.Workplane):
        raise TypeError("cube must be cadquery.Workplane")

    validate_pattern_inputs(nx, ny, dx, dy)
    validate_block_rows(block_rows, ny)

    # --- bbox solid (always computed/returned) ---
    bbox_wp = make_bounding_box_solid(
        cube=cube,
        nx=nx, ny=ny, dx=dx, dy=dy, dx0=dx0,
        margin_x=margin_x, margin_y=margin_y,
    )
    bbox_bb = bbox_wp.val().BoundingBox()

    # --- build reusable block prototypes once (no union inside) ---
    block_even = make_nrow_compound(
        cube=cube, nx=nx, nrows=block_rows, dx=dx, dy=dy, dx0=dx0, row_start_parity=0
    )
    block_odd = make_nrow_compound(
        cube=cube, nx=nx, nrows=block_rows, dx=dx, dy=dy, dx0=dx0, row_start_parity=1
    )

    # If no clipping: just build the normal pattern assembly (fast path)
    if not do_clip:
        assy = cq.Assembly(name="pattern")
        full_blocks = ny // block_rows
        rem = ny % block_rows

        for b in range(full_blocks):
            start_row = b * block_rows
            y_off = start_row * dy
            block_wp = block_odd if (start_row & 1) else block_even
            assy.add(block_wp, name=f"block_{b}", loc=cq.Location(cq.Vector(0.0, y_off, 0.0)))

        if rem:
            start_row = full_blocks * block_rows
            y_off = start_row * dy
            parity = start_row & 1
            tail = make_nrow_compound(
                cube=cube, nx=nx, nrows=rem, dx=dx, dy=dy, dx0=dx0, row_start_parity=parity
            )
            assy.add(tail, name="tail", loc=cq.Location(cq.Vector(0.0, y_off, 0.0)))

        return assy, bbox_wp

    # --- clipping path ---
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
        return _BB()

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