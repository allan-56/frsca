import json
import os
from datetime import datetime, timezone
from typing import Optional


def _spdx_id(name: str) -> str:
    return f"SPDXRef-{name.replace('/', '-').replace(' ', '-')}"


def _hash_entry(algorithm: str, value: str) -> dict:
    return {
        "type": "Hash",
        "algorithm": algorithm,
        "hashValue": value,
    }


def _dict_entry(key: str, value) -> dict:
    return {
        "type": "DictionaryEntry",
        "key": key,
        "value": str(value),
    }


def _creation_info(created_by: str, tool: str) -> dict:
    return {
        "type": "CreationInfo",
        "created": datetime.now(timezone.utc).isoformat(),
        "createdBy": [created_by],
        "createdUsing": [tool],
        "specVersion": "3.0.1",
    }


def create_ai_package(
    name: str,
    version: str,
    download_location: str,
    sha256: str,
    supplied_by: str = "FRSCA-ML",
    description: Optional[str] = None,
    model_type: Optional[str] = None,
    domain: Optional[list] = None,
    hyperparameters: Optional[dict] = None,
    metrics: Optional[dict] = None,
    training_info: Optional[str] = None,
    safety_risk: Optional[str] = None,
    standard_compliance: Optional[list] = None,
    file_size: Optional[int] = None,
    media_type: Optional[str] = None,
    license_expression: Optional[str] = None,
) -> dict:
    spdx_id = _spdx_id(name)

    pkg = {
        "type": "AIPackage",
        "spdxId": spdx_id,
        "name": name,
        "packageVersion": version,
        "downloadLocation": download_location,
        "primaryPurpose": "model",
        "verifiedUsing": [_hash_entry("sha256", sha256)],
        "suppliedBy": supplied_by,
        "releaseTime": datetime.now(timezone.utc).isoformat(),
    }

    if description:
        pkg["summary"] = description
    if file_size:
        pkg["packageSize"] = file_size
    if media_type:
        pkg["contentType"] = media_type

    if model_type:
        pkg["typeOfModel"] = [model_type]
    if domain:
        pkg["domain"] = domain
    if hyperparameters:
        pkg["hyperparameter"] = [
            _dict_entry(k, v) for k, v in hyperparameters.items()
        ]
    if metrics:
        pkg["metric"] = [
            _dict_entry(k, v) for k, v in metrics.items()
        ]
    if training_info:
        pkg["informationAboutTraining"] = training_info
    if safety_risk:
        pkg["safetyRiskAssessment"] = safety_risk
    if standard_compliance:
        pkg["standardCompliance"] = standard_compliance

    return pkg


def create_dataset_package(
    name: str,
    version: str,
    download_location: str,
    sha256: str,
    description: Optional[str] = None,
    dataset_type: Optional[str] = None,
    has_sensitive_pii: Optional[bool] = None,
    data_preprocessing: Optional[str] = None,
    known_bias: Optional[str] = None,
) -> dict:
    spdx_id = _spdx_id(f"dataset-{name}")

    pkg = {
        "type": "DatasetPackage",
        "spdxId": spdx_id,
        "name": name,
        "packageVersion": version,
        "downloadLocation": download_location,
        "verifiedUsing": [_hash_entry("sha256", sha256)],
        "releaseTime": datetime.now(timezone.utc).isoformat(),
    }

    if description:
        pkg["summary"] = description
    if dataset_type:
        pkg["datasetType"] = dataset_type
    if has_sensitive_pii is not None:
        pkg["hasSensitivePersonalInformation"] = "yes" if has_sensitive_pii else "no"
    if data_preprocessing:
        pkg["dataPreprocessing"] = [data_preprocessing]
    if known_bias:
        pkg["knownBias"] = known_bias

    return pkg


def create_training_build(
    build_id: str,
    builder_id: str,
    start_time: str,
    end_time: str,
    source_uri: str,
    source_digest: str,
    parameters: Optional[dict] = None,
) -> dict:
    build = {
        "type": "Build",
        "spdxId": _spdx_id(f"build-{build_id}"),
        "buildId": build_id,
        "buildType": "https://frsca.dev/ml/build/v1",
        "buildStartTime": start_time,
        "buildEndTime": end_time,
        "configSourceUri": source_uri,
        "configSourceDigest": [_hash_entry("sha256", source_digest)],
    }

    if parameters:
        build["parameter"] = [
            _dict_entry(k, v) for k, v in parameters.items()
        ]

    return build


def create_spdx_document(
    document_name: str,
    ai_packages: list,
    dataset_packages: Optional[list] = None,
    builds: Optional[list] = None,
    relationships: Optional[list] = None,
    created_by: str = "FRSCA-ML",
    tool: str = "frsca-ml-provenance-generator",
) -> dict:
    doc_id = _spdx_id(document_name)

    elements = list(ai_packages)
    if dataset_packages:
        elements.extend(dataset_packages)
    if builds:
        elements.extend(builds)

    all_relationships = []
    for pkg in ai_packages:
        pkg_id = pkg["spdxId"]
        if pkg.get("verifiedUsing"):
            all_relationships.append({
                "type": "Relationship",
                "spdxId": _spdx_id(f"rel-{pkg_id}-hash"),
                "from": pkg_id,
                "relationshipType": "verifiedUsing",
                "to": pkg["verifiedUsing"][0]["hashValue"],
            })

    for ds in (dataset_packages or []):
        ds_id = ds["spdxId"]
        for pkg in ai_packages:
            all_relationships.append({
                "type": "Relationship",
                "spdxId": _spdx_id(f"rel-{ds_id}-trainedOn-{pkg['spdxId']}"),
                "from": pkg["spdxId"],
                "relationshipType": "trainedOn",
                "to": ds_id,
            })

    for build in (builds or []):
        build_id = build["spdxId"]
        for pkg in ai_packages:
            all_relationships.append({
                "type": "Relationship",
                "spdxId": _spdx_id(f"rel-{build_id}-built-{pkg['spdxId']}"),
                "from": pkg["spdxId"],
                "relationshipType": "builtBy",
                "to": build_id,
            })

    if relationships:
        all_relationships.extend(relationships)

    license_rel = []
    for pkg in ai_packages:
        license_rel.append({
            "type": "Relationship",
            "spdxId": _spdx_id(f"rel-license-{pkg['spdxId']}"),
            "from": pkg["spdxId"],
            "relationshipType": "hasDeclaredLicense",
            "to": "SPDXRef-Apache-2.0",
        })

    doc = {
        "type": "SpdxDocument",
        "spdxId": doc_id,
        "name": document_name,
        "creationInfo": _creation_info(created_by, tool),
        "profileConformance": ["core", "software", "ai", "dataset", "build"],
        "rootElement": [doc_id],
        "element": elements,
        "relationship": all_relationships + license_rel,
    }

    return doc


def generate_spdx_from_provenance(
    provenance: dict,
    model_name: str,
    model_version: str,
    model_download_url: str,
    model_sha256: str,
    dataset_name: Optional[str] = None,
    dataset_url: Optional[str] = None,
    dataset_sha256: Optional[str] = None,
) -> dict:
    pred = provenance.get("predicate", {})

    build_def = pred.get("buildDefinition", {})
    run_details = pred.get("runDetails", {})
    ml_specifics = pred.get("mlSpecifics", {})

    hyperparams = ml_specifics.get("hyperparameters", {})
    metrics = ml_specifics.get("metrics", {})
    environment = ml_specifics.get("environment", {})

    ai_pkg = create_ai_package(
        name=model_name,
        version=model_version,
        download_location=model_download_url,
        sha256=model_sha256,
        model_type=environment.get("framework", "unknown"),
        domain=["machine-learning"],
        hyperparameters=hyperparams,
        metrics=metrics,
        training_info=f"Trained with {environment.get('framework', 'unknown')} "
                      f"{environment.get('frameworkVersion', '')}",
    )

    packages = [ai_pkg]

    datasets = []
    if dataset_name and dataset_sha256:
        ds_pkg = create_dataset_package(
            name=dataset_name,
            version="1.0",
            download_location=dataset_url or "unknown",
            sha256=dataset_sha256,
        )
        datasets.append(ds_pkg)

    builder_info = run_details.get("builder", {})
    metadata = run_details.get("metadata", {})

    build = None
    if builder_info:
        build = create_training_build(
            build_id=builder_info.get("id", "unknown"),
            builder_id=builder_info.get("id", "unknown"),
            start_time=metadata.get("startedOn", ""),
            end_time=metadata.get("finishedOn", ""),
            source_uri=build_def.get("externalParameters", {}).get("datasetUrl", ""),
            source_digest="",
            parameters=hyperparams,
        )

    return create_spdx_document(
        document_name=f"{model_name}-sbom",
        ai_packages=packages,
        dataset_packages=datasets if datasets else None,
        builds=[build] if build else None,
    )
