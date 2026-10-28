#!/usr/bin/env python3
"""Destroy only the GCP Guide 7 API/frontend Terraform stack."""

import argparse
import shutil
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TERRAFORM_DIR = PROJECT_ROOT / "terraform_gcp" / "7_frontend"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Destroy the GCP frontend/API stack only; other GCP layers are unaffected."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the script confirmation (Terraform still asks for confirmation).",
    )
    args = parser.parse_args()

    if not shutil.which("terraform"):
        raise SystemExit("Terraform is required.")
    if not (TERRAFORM_DIR / "terraform.tfvars").is_file():
        raise SystemExit(
            f"Missing {TERRAFORM_DIR / 'terraform.tfvars'}; this script will not guess a target project."
        )

    print(
        "This destroys only terraform_gcp/7_frontend resources. "
        "It does not destroy Cloud SQL, agent, ingestion, or researcher resources."
    )
    if not args.yes and input("Type 'yes' to continue: ").strip().lower() != "yes":
        raise SystemExit("Cancelled.")

    try:
        subprocess.run(["terraform", "destroy"], cwd=TERRAFORM_DIR, check=True)
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error


if __name__ == "__main__":
    main()
