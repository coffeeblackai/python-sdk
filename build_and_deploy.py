#!/usr/bin/env python3
import re
import subprocess
import sys
from pathlib import Path

def read_current_version():
    """Read the current version from setup.py"""
    setup_path = Path("setup.py")
    if not setup_path.exists():
        print("Error: setup.py file not found")
        sys.exit(1)
    
    content = setup_path.read_text()
    version_match = re.search(r'version="([^"]+)"', content)
    if not version_match:
        print("Error: Could not find version in setup.py")
        sys.exit(1)
    
    return version_match.group(1)

def update_version(new_version):
    """Update the version in setup.py"""
    setup_path = Path("setup.py")
    content = setup_path.read_text()
    updated_content = re.sub(
        r'version="[^"]+"', 
        f'version="{new_version}"', 
        content
    )
    
    setup_path.write_text(updated_content)
    print(f"Updated version to {new_version} in setup.py")

def build_and_deploy():
    """Build and deploy the package"""
    print("\nBuilding the package...")
    subprocess.run(["python", "setup.py", "sdist", "bdist_wheel"], check=True)
    
    print("\nUploading to PyPI...")
    subprocess.run(["twine", "upload", "dist/*"], check=True)
    
    print("\n✅ Package successfully built and deployed!")

def main():
    current_version = read_current_version()
    print(f"Current version: {current_version}")
    
    # Ask for new version
    new_version = input(f"Enter new version (leave empty to keep {current_version}): ").strip()
    if not new_version:
        new_version = current_version
    
    # Validate semantic version format
    if not re.match(r'^\d+\.\d+\.\d+$', new_version):
        print("Warning: Version doesn't match semantic versioning (X.Y.Z)")
        proceed = input("Continue anyway? (y/n): ").lower()
        if proceed != 'y':
            print("Aborting.")
            return
    
    # Confirmation
    print("\nReady to build with the following details:")
    print(f"- Version: {new_version}")
    
    confirmation = input("\nProceed with build and deploy? (y/n): ").lower()
    if confirmation != 'y':
        print("Build and deploy canceled.")
        return
    
    # Update version in setup.py
    if new_version != current_version:
        update_version(new_version)
    
    # Build and deploy
    build_and_deploy()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation canceled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1) 