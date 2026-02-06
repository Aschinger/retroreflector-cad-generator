import math
import time

from geometry import generate_rectangle, rotate_hexagonal_cube_corner, cut_in_xy_plane_center, cut_at_z_plane_from_top
from cad_export import export_step

# SETTINGS
# start time measurement
t0 = time.perf_counter()
# define length of cube edge
edge_length_mm = 0.1  # mm
# define number of cubes in X and Y directions
nx=20
ny=20
# define substrate thickness
substrate_thickness_mm = 3

# CALCULATIONS
face_diagonal_mm = math.sqrt(2) * edge_length_mm
cube_diagonal_mm = math.sqrt(3) * edge_length_mm
edge_face_diagonal_mm = math.sqrt(math.pow(edge_length_mm, 2) + math.pow(face_diagonal_mm, 2))
x_sep_mm = face_diagonal_mm
y_sep_mm = math.sqrt(math.pow(edge_length_mm, 2) + math.pow(face_diagonal_mm / 2, 2))
x_offset_mm = 0.5 * math.sqrt(2) * edge_length_mm   # applied to every second row
# define second rotation angle for hexagonal cube corner orientation
alpha_deg = math.degrees(math.atan(math.sqrt(2)))
print(f'alpha_deg: {alpha_deg:.4f}°')
print(f'face_diagonal_mm: {face_diagonal_mm:.4f} mm')
print(f'edge_face_diagonal_mm: {edge_face_diagonal_mm:.4f} mm')
print(f'edge_length_mm: {edge_length_mm:.4f} mm')


# generate cube as unit cell
# the cube is larger as then the desired edge length to fill up empty spaces between cubes after rotation,
# but the final pattern will be cut to the desired size
scale_f = 2.0
cube = generate_rectangle(scale_f * edge_length_mm, scale_f * edge_length_mm, scale_f * edge_length_mm)


# rotate 45° around Z axis and then 54.7356° around X axis
cube_rot = rotate_hexagonal_cube_corner(cube)

#export_step(cube_rot, "output/test_cut_cube-rot.step")

# cut cube and keep only the top half (in Z direction) to get a hexagonal cube corner shape
cube_rot_cut = cut_at_z_plane_from_top(cube_rot, z_plane=-scale_f * 0.5 * math.sin(math.radians(alpha_deg))*face_diagonal_mm, keep="bottom")
#math.sin(math.radians(alpha_deg-45))*0.5*edge_face_diagonal_mm

export_step(cube_rot_cut, "output/test_cut.step")