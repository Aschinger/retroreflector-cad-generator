import cadquery as cq
from typing import List
from geometry import generate_rectangle

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

def make_nrow_union(
    cube: cq.Workplane,
    nx: int,
    nrows: int,
    dx: float,
    dy: float,
    dx0: float = 0.0,
    row_start_parity: int = 0,
    clean: bool = True,
) -> cq.Workplane:
    """
    nrows rows fused (union) into one solid, with stagger.

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

    for r in range(nrows):
        y = r * dy
        x_off = dx0 if ((row_start_parity + r) & 1) else 0.0

        for i in range(nx):
            x = i * dx + x_off
            solids.append(base.moved(cq.Location(cq.Vector(x, y, 0.0))))

    wp = cq.Workplane("XY").newObject(solids)

    # Single multi-boolean fuse (fastest reliable)
    wp = wp.union()

    if clean:
        wp = wp.clean()

    return wp

def make_pattern_assembly(
    cube: cq.Workplane,
    nx: int,
    ny: int,
    dx: float,
    dy: float,
    dx0: float = 0.0,
    block_rows: int = 4,
) -> cq.Assembly:
    """
    Fast assembly builder by instancing row-block compounds.

    Performance characteristics:
      - builds at most 3 compounds total:
          block_even, block_odd, tail(optional)
      - instances those compounds (cheap)
    """
    if not isinstance(cube, cq.Workplane):
        raise TypeError("cube must be cadquery.Workplane")
    if nx <= 0 or ny <= 0:
        raise ValueError("nx and ny must be > 0")
    if dx <= 0 or dy <= 0:
        raise ValueError("dx and dy must be > 0")
    if not (1 <= block_rows < ny):
        raise ValueError("block_rows must satisfy 1 <= block_rows < ny")

    assy = cq.Assembly(name="pattern")

    full_blocks = ny // block_rows
    rem = ny % block_rows

    # Build reusable prototypes ONCE (only two parities exist)
    block_even = make_nrow_compound(
        cube=cube, nx=nx, nrows=block_rows, dx=dx, dy=dy, dx0=dx0, row_start_parity=0
    )
    block_odd = make_nrow_compound(
        cube=cube, nx=nx, nrows=block_rows, dx=dx, dy=dy, dx0=dx0, row_start_parity=1
    )

    # Instance blocks
    for b in range(full_blocks):
        start_row = b * block_rows
        y_off = start_row * dy

        # Choose correct prototype based on start_row parity
        block = block_odd if (start_row & 1) else block_even

        assy.add(
            block,
            name=f"block_{b}",
            loc=cq.Location(cq.Vector(0.0, y_off, 0.0)),
        )

    # Tail built once (if needed), with correct start parity
    if rem:
        start_row = full_blocks * block_rows
        parity = start_row & 1

        tail = make_nrow_compound(
            cube=cube, nx=nx, nrows=rem, dx=dx, dy=dy, dx0=dx0, row_start_parity=parity
        )

        assy.add(
            tail,
            name="tail",
            loc=cq.Location(cq.Vector(0.0, start_row * dy, 0.0)),
        )
    return assy

def assembly_zmin(assy: cq.Assembly) -> float:
    """
    Minimum Z of all geometry in an Assembly (robust across CQ versions).
    """
    if not isinstance(assy, cq.Assembly):
        raise TypeError("assy must be cadquery.Assembly")

    # CQ Assembly can be converted to a single compound shape with all locations applied
    comp = assy.toCompound()
    bb = comp.BoundingBox()
    return bb.zmin

def add_substrate(
    assy: cq.Assembly,
    thickness: float,
    margin: float,
    nx: int,
    ny: int,
    dx: float,
    dy: float,
    dx0: float,
    edge_length_mm: float,
) -> cq.Assembly:

    z_top = assembly_zmin(assy)  # <- automatic contact plane

    # placement bounds in XY (centers)
    x_min = 0.0
    x_max = (nx - 1) * dx
    if ny >= 2:
        x_min = min(x_min, dx0)
        x_max = max(x_max, (nx - 1) * dx + dx0)

    y_min = 0.0
    y_max = (ny - 1) * dy

    half = 0.5 * edge_length_mm
    x_min -= (half + margin)
    x_max += (half + margin)
    y_min -= (half + margin)
    y_max += (half + margin)

    size_x = x_max - x_min
    size_y = y_max - y_min
    cx = 0.5 * (x_min + x_max)
    cy = 0.5 * (y_min + y_max)

    cz = z_top - thickness / 2.0
    substrate = generate_rectangle(size_x, size_y, thickness).translate((cx, cy, cz))

    assy.add(substrate, name="substrate", loc=cq.Location())
    return assy
