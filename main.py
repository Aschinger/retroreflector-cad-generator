import math
import time

from geometry import generate_rectangle, rotate_hexagonal_cube_corner, cut_in_xy_plane_center, pattern_cubes_staggered, add_shapes, unify_shapes
from geometry_clip import clip_pattern_only_outer_cubes,  make_substrate_from_pattern_xy
from cad_export import export_step

# SETTINGS
# start time measurement
t0 = time.perf_counter()
# define length of cube edge
edge_length_mm = 0.1  # mm
# define number of cubes in X and Y directions
nx=200
ny=200
# define substrate thickness
substrate_thickness_mm = 3

# CALCULATIONS
face_diagonal_mm = math.sqrt(2) * edge_length_mm
x_sep_mm = face_diagonal_mm
y_sep_mm = math.sqrt(math.pow(edge_length_mm, 2) + math.pow(face_diagonal_mm / 2, 2))
x_offset_mm = 0.5 * math.sqrt(2) * edge_length_mm   # applied to every second row


# generate cube as unit cell
# the cube is larger as then the desired edge length to fill up empty spaces between cubes after rotation,
# but the final pattern will be cut to the desired size
cube = generate_rectangle(2*edge_length_mm, 2 * edge_length_mm, 2*edge_length_mm)


# rotate 45° around Z axis and then 54.7356° around X axis
cube_rot = rotate_hexagonal_cube_corner(cube)

# cut cube and keep only the top half (in Z direction) to get a hexagonal cube corner shape
cube_rot_cut = cut_in_xy_plane_center(cube_rot, keep="top", z_offset=0.05)

# time measurement for geometry prep
print(f"[Runtime] Geometry Preparation: {time.perf_counter() - t0:.3f} s")

# generate pattern of cubes in staggered grid
print(f"Generating the pattern...")
pattern = pattern_cubes_staggered(
    cube=cube_rot_cut,
    nx=nx,
    ny=ny,
    dx=x_sep_mm,
    dy=y_sep_mm,
    dx0=x_offset_mm,
    fuse=False,
    clean=True,
)


# time measurement for pattern generation
print(f"[Runtime] Pattern generation: {time.perf_counter() - t0:.3f} s")

# make bounding box and cut pattern to fit within it (for neatness and to avoid export issues)
print(f"Clip the pattern...")
clipped = clip_pattern_only_outer_cubes(
    pattern,
    nx=nx, ny=ny, dx=x_sep_mm, dy=y_sep_mm, dx0=x_offset_mm,
    margin_x=0.0,# edge_length_mm/2,
    margin_y=0.0,#edge_length_mm/2
)

# time measurement for pattern generation
print(f"[Runtime] Clipp Pattern: {time.perf_counter() - t0:.3f} s")

# generate substrate
print(f"Generate a substrate...")
substrate = make_substrate_from_pattern_xy(
    pattern,
    nx=nx, ny=ny, dx=x_sep_mm, dy=y_sep_mm, dx0=x_offset_mm,
    margin_x= 10 * edge_length_mm,
    margin_y=10 * edge_length_mm,
    h= substrate_thickness_mm,
    z_offset=0.0
)

# combine pattern and substrate
print(f"Fuse pattern and substrate...")
#model = unify_shapes(clipped, substrate)
model = add_shapes(pattern, substrate)

# time measurement for substrate generation adn fusion
print(f"[Runtime] Make and combine substrate: {time.perf_counter() - t0:.3f} s")

# export to STEP file
print(f"Start export to file...")
written_path = export_step(model, "output/model.step", overwrite=True)
written_path = export_step(clipped, "output/clipped.step", overwrite=True)
print(f"STEP file written to: {written_path}")

# final runtime measurement
print(f"[Runtime] Total: {time.perf_counter() - t0:.3f} s")