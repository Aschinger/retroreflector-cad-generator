import cadquery as cq
from pathlib import Path

def _validate_step_path(filepath: str | Path, overwrite: bool = True) -> Path:
    """
    Validate and normalize STEP export path.
    """
    if filepath is None:
        raise ValueError("filepath cannot be None")

    path = Path(filepath).expanduser()

    # Must contain filename
    if path.name == "":
        raise ValueError("filepath must include a filename")

    # Ensure extension
    if path.suffix == "":
        path = path.with_suffix(".step")
    elif path.suffix.lower() not in {".step", ".stp"}:
        raise ValueError("File extension must be .step or .stp")

    # Prevent directory misuse
    if path.exists() and path.is_dir():
        raise ValueError("filepath points to a directory, not a file")

    # Create parent directory
    path.parent.mkdir(parents=True, exist_ok=True)

    # Overwrite protection
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists")

    return path.resolve()


def export_step(shape: cq.Workplane, filepath: str | Path, overwrite: bool = True) -> Path:
    """
    Export a CadQuery shape to STEP file with path validation.
    """
    if not isinstance(shape, cq.Workplane):
        raise TypeError("shape must be a cadquery.Workplane")

    path = _validate_step_path(filepath, overwrite)

    cq.exporters.export(shape, str(path), exportType="STEP")

    return path