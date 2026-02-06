import math
import time

from geometry import generate_rectangle, rotate_hexagonal_cube_corner, cut_at_z_plane_from_top
from pattern_assembly import make_pattern_assembly, add_substrate
from cad_export import export_step, export_mesh

# SETTINGS
# start time measurement
t0 = time.perf_counter()
# define length of cube edge
edge_length_mm = 0.2  # mm
# define number of cubes in X and Y directions
nx=50
ny=50
# define substrate thickness
substrate_thickness_mm = 3
substrate_margin_mm = 0.5
block_rows = 10  # number of rows in each block of the pattern assembly (for performance optimization, see make_pattern_assembly)

# CALCULATIONS
face_diagonal_mm = math.sqrt(2) * edge_length_mm
cube_diagonal_mm = math.sqrt(3) * edge_length_mm
x_sep_mm = face_diagonal_mm
y_sep_mm = math.sqrt(math.pow(edge_length_mm, 2) + math.pow(face_diagonal_mm / 2, 2))
x_offset_mm = 0.5 * math.sqrt(2) * edge_length_mm   # applied to every second row
# define second rotation angle for hexagonal cube corner orientation
alpha_deg = math.degrees(math.atan(math.sqrt(2)))


# generate cube as unit cell
# the cube is larger as then the desired edge length to fill up empty spaces between cubes after rotation,
# but the final pattern will be cut to the desired size
scale_f = 2.0
cube = generate_rectangle(scale_f * edge_length_mm, scale_f * edge_length_mm, scale_f * edge_length_mm)


# rotate 45° around Z axis and then 54.7356° around X axis
cube_rot = rotate_hexagonal_cube_corner(cube)

# cut cube and keep only the top half (in Z direction) to get a hexagonal cube corner shape
cube_rot_cut = cut_at_z_plane_from_top(cube_rot, z_plane=-scale_f * 0.5 * math.sin(math.radians(alpha_deg))*face_diagonal_mm, keep="top")

# time measurement for geometry prep
print(f"[Runtime] Geometry Preparation: {time.perf_counter() - t0:.3f} s")

# generate pattern of cubes in staggered grid
print(f"Generating the pattern...")

# mage the pattern of cubes as an assembly by instancing a 4-row compound,
# which reduces the number of assembly elements and keeps 'no union' behavior
assy=make_pattern_assembly(
    cube=cube_rot_cut,
    nx=nx,
    ny=ny,
    dx=x_sep_mm,
    dy=y_sep_mm,
    dx0=x_offset_mm,
    block_rows=block_rows,  # n
)
# Runtime measurement
print(f"[Runtime] Generating Pattern: {time.perf_counter() - t0:.3f} s")

# add substrate as one solid to the assembly
print(f"Add substrate ...")

assy = add_substrate(
    assy=assy,
    thickness=substrate_thickness_mm,        # substrate thickness [mm]
    margin=substrate_margin_mm,           # extra border around pattern [mm]
    nx=nx,
    ny=ny,
    dx=x_sep_mm,
    dy=y_sep_mm,
    dx0=x_offset_mm,
    edge_length_mm=edge_length_mm,   # cube edge length
)

# export assemgly as file
print(f"Export to file ...")
file_name = f'Retroreflector_Nx{nx}_Ny{ny}_Pitch{edge_length_mm}_Block{block_rows}'
#export_step(assy, f"output/{file_name}.step")
export_mesh(assy, f"output/{file_name}.stl", tolerance=0.005)
#export_mesh(assy, f"output/{file_name}.3mf", tolerance=0.005)

# final runtime measurement
print(f"[Runtime] Total: {time.perf_counter() - t0:.3f} s")