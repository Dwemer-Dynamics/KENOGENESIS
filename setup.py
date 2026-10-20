"""Include the maintained source guides in wheel installs without duplicating them in source."""
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

ROOT = Path(__file__).parent
GUIDES = [ROOT / "README.md", *(ROOT / "docs").glob("*.md")]


class BuildWithGuides(build_py):
    """Keep installed in-app documentation identical to the repository guides."""

    def run(self):
        super().run()
        destination = Path(self.build_lib) / "kenogenesis" / "docs"
        destination.mkdir(parents=True, exist_ok=True)
        for guide in GUIDES:
            self.copy_file(str(guide), str(destination / guide.name))

    def get_outputs(self, include_bytecode=1):
        return [*super().get_outputs(include_bytecode),
                *(str(Path(self.build_lib) / "kenogenesis" / "docs" / p.name) for p in GUIDES)]


setup(cmdclass={"build_py": BuildWithGuides})
