from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _recipe(target: str) -> str:
    lines = (ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith(f"{target}:"))
    recipe = [lines[start]]
    for line in lines[start + 1 :]:
        if not line:
            break
        recipe.append(line)
    return "\n".join(recipe)


def test_makefile_exposes_the_documented_non_mutating_validation_gates() -> None:
    for target in (
        "format-check",
        "lint",
        "typecheck",
        "basedpyright",
        "repository-audits",
        "test-focused",
        "test-full",
        "rust-check",
        "smoke-release",
        "version-check",
        "assets-check",
        "package-verify",
        "release-candidate",
        "check",
    ):
        assert f"{target}:" in (ROOT / "Makefile").read_text(encoding="utf-8")

    package_verify = _recipe("package-verify")
    assert 'mktemp -d "$(PACKAGE_VERIFY_ROOT)/run.XXXXXX"' in package_verify
    assert 'DIST_DIR="$$package_verify_dir"' in package_verify
    assert 'SDIST_DIR="$$package_verify_dir"' in package_verify
    assert 'WHEEL_DIR="$$package_verify_dir"' in package_verify
    assert 'rm -rf "$$package_verify_dir"' in package_verify
    assert "package-verify: build" not in package_verify

    check = _recipe("check")
    for gate in (
        "format-check",
        "static-analysis",
        "repository-audits",
        "version-check",
        "assets-check",
        "test-full",
        "smoke-release",
        "rust-check",
        "package-verify",
    ):
        assert gate in check


def test_ci_and_publish_use_shared_setup_and_canonical_verifier_routes() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    publish = (ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8")

    for workflow in (ci, publish):
        assert "uses: ./.github/actions/setup-linux" in workflow
        assert "scripts/verify_distribution.py dist/" not in workflow
        assert "make format-check" in workflow
        assert "make static-analysis" in workflow
        assert "make repository-audits" in workflow
        assert "make test-full" in workflow
        assert "make rust-check" in workflow

    assert "make package-verify" in ci
    assert "--wheel-dir dist" in publish
    assert "--sdist-dir dist" in publish


def test_macos_wheel_build_pins_the_supported_deployment_target() -> None:
    cargo_config = tomllib.loads((ROOT / ".cargo" / "config.toml").read_text(encoding="utf-8"))
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    environment = cargo_config["env"]
    assert environment["MACOSX_DEPLOYMENT_TARGET"] == {"value": "26.0", "force": True}
    for target in ("aarch64-apple-darwin", "x86_64-apple-darwin"):
        assert cargo_config["target"][target]["rustflags"] == [
            "-C",
            "link-arg=-mmacosx-version-min=26.0",
        ]
    assert ".cargo/config.toml" in pyproject["tool"]["maturin"]["include"]

    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    publish = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
    assert "MACOSX_DEPLOYMENT_TARGET := 26.0" in makefile
    assert "export MACOSX_DEPLOYMENT_TARGET" in makefile
    assert "Pin macOS deployment target" in publish
    assert 'echo "MACOSX_DEPLOYMENT_TARGET=26.0" >> "$GITHUB_ENV"' in publish


def test_documented_validation_matrix_covers_native_wheel_and_opt_in_release_gate() -> None:
    matrix = (ROOT / "docs/contribute/validation.md").read_text(encoding="utf-8")

    for required_text in (
        "canvas ABI **18**",
        "ECS ABI **6**",
        "make release-candidate",
        "Python renderer",
        "Linux x86_64",
        "macOS x86_64",
        "macOS ARM64",
        "Windows x64",
    ):
        assert required_text in matrix
