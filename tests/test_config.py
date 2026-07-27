from __future__ import annotations

from alertdrill import config


def test_ports_are_distinct():
    ports = [
        config.PROMETHEUS_PORT,
        config.ALERTMANAGER_PORT,
        config.RECEIVER_PORT,
        config.TARGET_PORT,
    ]
    assert len(set(ports)) == len(ports)


def test_urls_are_loopback_only():
    for url in (
        config.PROMETHEUS_URL,
        config.ALERTMANAGER_URL,
        config.RECEIVER_URL,
        config.TARGET_URL,
    ):
        assert url.startswith("http://127.0.0.1:")


def test_project_paths_resolve_inside_the_repository():
    for path in (config.LAB, config.RULES_DIR, config.CONTRACT, config.COMPOSE_FILE):
        assert config.ROOT in path.parents or path == config.ROOT


def test_images_are_version_pinned():
    """An unpinned tag would make the evidence report a version it cannot vouch for."""
    for image in (config.PROMETHEUS_IMAGE, config.ALERTMANAGER_IMAGE, config.PYTHON_BASE_IMAGE):
        assert ":" in image, image
        assert not image.endswith(":latest"), image


def test_python_base_image_matches_the_dockerfile():
    """config.py is what the evidence reports, and nothing else ties it to the Dockerfile.

    A dependency bot updating the Dockerfile alone leaves config.py naming a base image the
    stack does not run, and every check would still pass while the report lied.
    """
    dockerfile = (config.LAB / "Dockerfile").read_text(encoding="utf-8")
    declared = [
        line.split(maxsplit=1)[1].strip()
        for line in dockerfile.splitlines()
        if line.startswith("FROM ")
    ]
    assert declared, "no FROM line in the lab Dockerfile"
    assert config.PYTHON_BASE_IMAGE in declared, (
        f"config says {config.PYTHON_BASE_IMAGE}, Dockerfile says {declared}"
    )
