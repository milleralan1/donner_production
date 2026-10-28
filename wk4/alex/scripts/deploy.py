#!/usr/bin/env python3
"""Build and deploy Alex's GCP API and frontend using the Guide 7 Terraform stack."""

import argparse
import os
import re
import shutil
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
TERRAFORM_DIR = PROJECT_ROOT / "terraform_gcp" / "7_frontend"


def run(command: list[str], *, cwd: Path, capture: bool = False) -> str:
    print(f"+ {' '.join(command)}")
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=capture,
    )
    return result.stdout.strip() if capture else ""


def require_tools() -> None:
    missing = [tool for tool in ("docker", "gcloud", "terraform") if not shutil.which(tool)]
    if missing:
        raise SystemExit(f"Missing required tools: {', '.join(missing)}")


def terraform(*args: str, project_id: str, region: str, capture: bool = False) -> str:
    return run(
        [
            "terraform",
            *args,
            f"-var=project_id={project_id}",
            f"-var=region={region}",
        ],
        cwd=TERRAFORM_DIR,
        capture=capture,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deploy the GCP API and Next.js frontend from terraform_gcp/7_frontend."
    )
    parser.add_argument("--project-id", required=True, help="Google Cloud project ID")
    parser.add_argument("--region", required=True, help="GCP region used by the Terraform stack")
    parser.add_argument(
        "--clerk-publishable-key",
        help="Clerk public publishable key; may instead be set in CLERK_PUBLISHABLE_KEY",
    )
    parser.add_argument(
        "--tag",
        default="dev",
        help="Container image tag (default: dev; use immutable tags for production)",
    )
    args = parser.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", args.tag):
        parser.error("--tag must be a valid Docker image tag")
    clerk_key = args.clerk_publishable_key or os.environ.get("CLERK_PUBLISHABLE_KEY")
    if not clerk_key:
        parser.error("provide --clerk-publishable-key or set CLERK_PUBLISHABLE_KEY")
    if not (TERRAFORM_DIR / "terraform.tfvars").is_file():
        raise SystemExit(
            f"Missing {TERRAFORM_DIR / 'terraform.tfvars'}; copy the example and configure it first."
        )

    require_tools()
    run(["docker", "info"], cwd=PROJECT_ROOT, capture=True)
    active_account = run(
        ["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"],
        cwd=PROJECT_ROOT,
        capture=True,
    )
    if not active_account:
        raise SystemExit("No active gcloud account. Run `gcloud auth login` first.")
    configured_project = run(
        ["gcloud", "config", "get-value", "project"], cwd=PROJECT_ROOT, capture=True
    )
    if configured_project not in ("", "(unset)", args.project_id):
        raise SystemExit(
            f"gcloud is configured for {configured_project}, not {args.project_id}. "
            "Select the intended project before deploying."
        )

    run(["terraform", "init"], cwd=TERRAFORM_DIR)
    run(["terraform", "validate"], cwd=TERRAFORM_DIR)

    # The image repository must exist before containers can be pushed.
    terraform(
        "apply",
        "-target=google_artifact_registry_repository.app",
        project_id=args.project_id,
        region=args.region,
    )
    repository = run(
        ["terraform", "output", "-raw", "artifact_registry_repository"],
        cwd=TERRAFORM_DIR,
        capture=True,
    )
    registry_host = repository.split("/", 1)[0]
    run(["gcloud", "auth", "configure-docker", registry_host], cwd=PROJECT_ROOT)

    api_image = f"{repository}/api:{args.tag}"
    frontend_image = f"{repository}/frontend:{args.tag}"
    run(
        [
            "docker",
            "build",
            "--platform",
            "linux/amd64",
            "-f",
            "api/Dockerfile.gcp",
            "-t",
            api_image,
            ".",
        ],
        cwd=BACKEND_DIR,
    )
    run(["docker", "push", api_image], cwd=BACKEND_DIR)

    terraform(
        "apply",
        "-target=google_cloud_run_v2_service.api",
        f"-var=api_image_url={api_image}",
        project_id=args.project_id,
        region=args.region,
    )
    api_url = run(
        ["terraform", "output", "-raw", "api_url"], cwd=TERRAFORM_DIR, capture=True
    )
    if not api_url.startswith("https://"):
        raise SystemExit(f"Terraform returned an invalid API URL: {api_url!r}")

    run(
        [
            "docker",
            "build",
            "--platform",
            "linux/amd64",
            "-f",
            "Dockerfile.gcp",
            "--build-arg",
            f"NEXT_PUBLIC_API_URL={api_url}",
            "--build-arg",
            f"NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY={clerk_key}",
            "-t",
            frontend_image,
            ".",
        ],
        cwd=FRONTEND_DIR,
    )
    run(["docker", "push", frontend_image], cwd=FRONTEND_DIR)

    terraform(
        "apply",
        f"-var=api_image_url={api_image}",
        f"-var=frontend_image_url={frontend_image}",
        project_id=args.project_id,
        region=args.region,
    )
    frontend_url = run(
        ["terraform", "output", "-raw", "frontend_url"],
        cwd=TERRAFORM_DIR,
        capture=True,
    )
    frontend_origin = frontend_url.rstrip("/")
    terraform(
        "apply",
        f"-var=api_image_url={api_image}",
        f"-var=frontend_image_url={frontend_image}",
        f"-var=frontend_origin={frontend_origin}",
        project_id=args.project_id,
        region=args.region,
    )
    print(f"\nDeployment complete\nFrontend: {frontend_url}\nAPI:      {api_url}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error
