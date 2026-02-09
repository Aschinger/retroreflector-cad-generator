import math
import time

from hcc_unit_cell import HccUnitCell
from pattern import Pattern, PatternLayout
from substrate import Substrate, SubstrateParams
from cad_export import export_mesh, export_step

#  ----  SETTINGS -------------------------------------------------------------
# start time measurement
t0 = time.perf_counter()
# define length of cube edge
#edge_length_mm = 0.087  # mm

# define edge length by structure height (for hexagonal cube corner shape) and calculate edge length accordingly
structure_height_mm = 0.1  # mm
edge_length_mm = round(structure_height_mm / (2 * 0.5 * math.sin(math.atan(math.sqrt(2)))*math.sqrt(2)),2)

print(f"Calculated edge length for structure height {structure_height_mm} mm: {edge_length_mm:.3f} mm")

# CALCULATIONS
face_diagonal_mm = math.sqrt(2) * edge_length_mm
cube_diagonal_mm = math.sqrt(3) * edge_length_mm
x_sep_mm = face_diagonal_mm
y_sep_mm = math.sqrt(math.pow(edge_length_mm, 2) + math.pow(face_diagonal_mm / 2, 2))
x_offset_mm = 0.5 * math.sqrt(2) * edge_length_mm   # applied to every second row
# define second rotation angle for hexagonal cube corner orientation
alpha_deg = math.degrees(math.atan(math.sqrt(2)))

# define the layout of the pattern
layout = PatternLayout(
    nx=1050,
    ny=1450,
    dx=x_sep_mm,
    dy=y_sep_mm,
    dx0=x_offset_mm,
)

# define substrate
sub_params = SubstrateParams(
    thickness=3.0,
    margin=0.5,
    edge_length_mm=edge_length_mm,
    z_extra=0.0,
    clean=True,
)

block_rows = 1  # number of rows in each block of the pattern assembly (for performance optimization, see make_pattern_assembly)

# Define limit for number of cubes to apply clipping and .step export; for large patterns,
# it can be very slow and create huge files
if layout.nx * layout.ny <= 2500:
    print(f"Warning: Large number of cubes (nx*ny={layout.nx * layout.ny}). No clipping or .step export.")
    is_small_pattern = True
else:   is_small_pattern = False

#  ----  Generate Objects -------------------------------------------------------------
print(f"Make the unit cell...")

# generate cube as unit cell
# the cube is larger as then the desired edge length to fill up empty spaces between cubes after rotation,
# but the final pattern will be cut to the desired size
scale_f = 2.0

cell = HccUnitCell(scale_f * edge_length_mm)
cell.make_cube()

# rotate 45° around Z axis and then 54.7356° around X axis
cell.rotate_corner_cube()

# cut cube and keep only the top half (in Z direction) to get a hexagonal cube corner shape
structure_height = scale_f * 0.5 * math.sin(math.radians(alpha_deg))*face_diagonal_mm
print(f'Structure height: {structure_height:.3f} mm')
cell.cut_from_top(z_plane=-structure_height, keep="top")
cube_rot_cut = cell.shape()

# generate pattern of cubes in staggered grid
print(f"Generating the pattern...")

pattern = Pattern(
    cube=cube_rot_cut,
    layout=layout,
    block_rows=block_rows,
    margin_x=0.0,
    margin_y=0.0,
)

assy, bbox_wp = pattern.build(do_clip=is_small_pattern, clean_clipped=is_small_pattern)


# add substrate as one solid to the assembly
print(f"Add substrate ...")

sub = Substrate(layout, sub_params)

substrate_wp = sub.make_cut_by_bbox(pattern_assy=assy, bbox_wp=bbox_wp)

assy_final = Substrate.wrap_with_pattern(
    pattern_assy=assy,
    substrate_wp=substrate_wp,
    top_name="pattern_with_substrate",
)

# Runtime measurement
print(f"[Runtime] Generating Pattern and Substrate: {time.perf_counter() - t0:.3f} s")

#  ----  Export -------------------------------------------------------------
# export assembly as file
print(f"Export to file ...")
file_name = f'Retroreflector_Nx{layout.nx}_Ny{layout.ny}_Pitch{edge_length_mm}_Block{block_rows}'

# export .step only if the pattern is not too large,
# as it can be very slow and create huge files; for large patterns, only export .stl mesh
if is_small_pattern:
    export_step(assy_final, f"output/{file_name}.step")

# export mesh with a tolerance of 0.005 mm (smaller tolerance means finer mesh and larger file size)
export_mesh(assy_final, f"output/{file_name}.stl", tolerance=0.005)
#export_mesh(assy_final, f"output/{file_name}.3mf", tolerance=0.005)

# final runtime measurement
print(f"[Runtime] Total: {time.perf_counter() - t0:.3f} s")