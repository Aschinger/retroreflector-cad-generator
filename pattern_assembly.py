import cadquery as cq
from typing import List
from geometry import generate_rectangle

def make_row_compound(cube: cq.Workplane, nx: int, dx: float) -> cq.Workplane:
    """
    One row as a compound (no union): cubes at x = i*dx, y=0.
    """
    base = cube.val()
    solids = [base.moved(cq.Location(cq.Vector(i * dx, 0.0, 0.0))) for i in range(nx)]
    return cq.Workplane("XY").newObject(solids)


def make_4row_compound(
    cube: cq.Workplane,
    nx: int,
    dx: float,
    dy: float,
    dx0: float = 0.0,
) -> cq.Workplane:
    """
    4 rows as one compound (no union), with stagger:
      row 0: x_off=0
      row 1: x_off=dx0
      row 2: x_off=0
      row 3: x_off=dx0
    """
    base = cube.val()
    solids: List[cq.Shape] = []

    for r in range(4):
        y = r * dy
        x_off = dx0 if (r % 2 == 1) else 0.0
        for i in range(nx):
            x = i * dx + x_off
            solids.append(base.moved(cq.Location(cq.Vector(x, y, 0.0))))

    return cq.Workplane("XY").newObject(solids)

def make_pattern_assembly(
    cube: cq.Workplane,
    nx: int,
    ny: int,
    dx: float,
    dy: float,
    dx0: float = 0.0,
):
    """
    Export a large staggered pattern as a STEP assembly by instancing a 4-row compound.

    This reduces assembly elements from (nx*ny) to approximately:
        ceil(ny/4) blocks + (optional remainder row compound)
    while keeping 'no union' behavior.
    """
    if ny <= 0 or nx <= 0:
        raise ValueError("nx and ny must be > 0")

    block4 = make_4row_compound(cube, nx=nx, dx=dx, dy=dy, dx0=dx0)

    assy = cq.Assembly(name="pattern")

    full_blocks = ny // 4
    rem = ny % 4

    # Place full 4-row blocks
    for b in range(full_blocks):
        y_off = b * 4 * dy
        assy.add(
            block4,
            name=f"block4_{b}",
            loc=cq.Location(cq.Vector(0.0, y_off, 0.0)),
        )

    # Handle remaining rows (0..3) as one smaller compound
    if rem:
        base = cube.val()
        solids: List[cq.Shape] = []
        start_row = full_blocks * 4

        for r in range(rem):
            j = start_row + r
            y = j * dy
            x_off = dx0 if (j % 2 == 1) else 0.0
            for i in range(nx):
                x = i * dx + x_off
                solids.append(base.moved(cq.Location(cq.Vector(x, y, 0.0))))

        tail = cq.Workplane("XY").newObject(solids)
        assy.add(tail, name="tail", loc=cq.Location())  # identity

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
