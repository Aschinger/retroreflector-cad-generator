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


def export_step(obj: cq.Workplane | cq.Assembly, filepath: str | Path, overwrite: bool = True) -> Path:
    """
    Export a CadQuery object to STEP.

    - Workplane → solid STEP (single part)
    - Assembly  → assembly STEP (instances preserved)

    Parameters
    ----------
    obj : cadquery.Workplane | cadquery.Assembly
        Object to export
    filepath : str | Path
        Output STEP path
    overwrite : bool
        Allow overwriting existing file

    Returns
    -------
    Path
        Written file path
    """

    path = _validate_step_path(filepath, overwrite)

    # Assembly export (IMPORTANT: different exporter)
    if isinstance(obj, cq.Assembly):
        obj.export(str(path))   # uses assembly exporter
        return path

    # Solid export
    if isinstance(obj, cq.Workplane):
        cq.exporters.export(obj, str(path), exportType="STEP")
        return path

    raise TypeError("obj must be cadquery.Workplane or cadquery.Assembly")