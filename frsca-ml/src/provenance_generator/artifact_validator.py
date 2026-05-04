import hashlib
import json
import os
from typing import Optional


SAFETENSORS_MAGIC = b"sf_tensors"

KNOWN_EXTENSIONS = {
    ".safetensors": "application/vnd.safetensors",
    ".bin": "application/x-pytorch",
    ".pt": "application/x-pytorch",
    ".pth": "application/x-pytorch",
    ".onnx": "application/onnx",
    ".h5": "application/x-hdf5",
    ".pb": "application/x-tensorflow",
    ".tflite": "application/x-tflite",
    ".gguf": "application/x-gguf",
    ".pkl": "application/x-pickle",
    ".joblib": "application/x-joblib",
}


def compute_file_hash(filepath: str, algorithm: str = "sha256") -> str:
    h = hashlib.new(algorithm)
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_artifact_type(filepath: str) -> Optional[str]:
    ext = os.path.splitext(filepath)[1].lower()
    if ext in KNOWN_EXTENSIONS:
        return KNOWN_EXTENSIONS[ext]

    try:
        with open(filepath, "rb") as f:
            header = f.read(8)
            if header.startswith(SAFETENSORS_MAGIC):
                return "application/vnd.safetensors"
    except Exception:
        pass

    return None


def validate_safetensors_header(filepath: str) -> dict:
    result = {
        "valid": False,
        "filepath": filepath,
        "format": "safetensors",
        "header_size": 0,
        "tensor_count": 0,
        "tensor_names": [],
        "total_bytes": 0,
        "error": None,
    }

    try:
        with open(filepath, "rb") as f:
            header_size_bytes = f.read(8)
            if len(header_size_bytes) < 8:
                result["error"] = "File too small to contain safetensors header"
                return result

            header_size = int.from_bytes(header_size_bytes, byteorder="little")

            if header_size > 100 * 1024 * 1024:
                result["error"] = f"Header size {header_size} exceeds 100MB limit"
                return result

            header_json = f.read(header_size)
            if len(header_json) < header_size:
                result["error"] = "File truncated: header shorter than declared"
                return result

            header = json.loads(header_json)

            tensors = {k: v for k, v in header.items() if k != "__metadata__"}
            result["header_size"] = header_size
            result["tensor_count"] = len(tensors)
            result["tensor_names"] = list(tensors.keys())[:20]

            total_bytes = 0
            for name, info in tensors.items():
                if "data_offsets" in info:
                    offsets = info["data_offsets"]
                    if len(offsets) == 2:
                        total_bytes += offsets[1] - offsets[0]

            result["total_bytes"] = total_bytes
            result["valid"] = True

            if "__metadata__" in header:
                result["metadata"] = header["__metadata__"]

    except json.JSONDecodeError as e:
        result["error"] = f"Invalid JSON in header: {e}"
    except Exception as e:
        result["error"] = str(e)

    return result


def validate_artifact(filepath: str) -> dict:
    if not os.path.exists(filepath):
        return {"valid": False, "error": f"File not found: {filepath}"}

    file_hash = compute_file_hash(filepath)
    file_size = os.path.getsize(filepath)
    artifact_type = detect_artifact_type(filepath)

    result = {
        "filepath": filepath,
        "filename": os.path.basename(filepath),
        "size_bytes": file_size,
        "sha256": file_hash,
        "artifact_type": artifact_type,
        "valid": True,
        "format_validation": None,
    }

    if artifact_type == "application/vnd.safetensors":
        result["format_validation"] = validate_safetensors_header(filepath)
        if not result["format_validation"]["valid"]:
            result["valid"] = False
            result["error"] = result["format_validation"]["error"]

    return result


def scan_output_directory(output_dir: str) -> list:
    artifacts = []
    for root, _, files in os.walk(output_dir):
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            artifact_type = detect_artifact_type(fpath)
            if artifact_type:
                validation = validate_artifact(fpath)
                artifacts.append(validation)
    return artifacts


def generate_provenance_with_artifacts(
    base_predicate: dict,
    output_dir: str,
) -> dict:
    artifacts = scan_output_directory(output_dir)

    artifact_records = []
    for art in artifacts:
        record = {
            "name": art["filename"],
            "uri": f"file://{art['filepath']}",
            "digest": {"sha256": art["sha256"]},
            "sizeBytes": art["size_bytes"],
            "mediaType": art["artifact_type"],
        }
        if art.get("format_validation", {}).get("tensor_count"):
            record["tensorCount"] = art["format_validation"]["tensor_count"]
        artifact_records.append(record)

    predicate = dict(base_predicate)
    predicate.setdefault("predicate", {})
    predicate["predicate"]["outputArtifacts"] = artifact_records

    return predicate
