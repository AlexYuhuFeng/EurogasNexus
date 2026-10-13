"""Customer wheel selection; development generators remain source-checkout only."""

from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.errors import SetupError


class CustomerBuildPy(build_py):
    """Exclude executable simulation producers from every distributable wheel."""

    def find_package_modules(self, package, package_dir):
        return [
            module
            for module in super().find_package_modules(package, package_dir)
            if (module[0], module[1])
            != ("eurogas_nexus.ingestion", "simulated_market_prices")
        ]

    def run(self):
        super().run()
        # An incremental build can retain a previous simulator in build/lib.
        # Refuse that build instead of silently shipping stale excluded code.
        ingestion = Path(self.build_lib) / "eurogas_nexus/ingestion"
        stale = list(ingestion.glob("simulated_market_prices.*"))
        stale.extend((ingestion / "__pycache__").glob("simulated_market_prices.*"))
        if stale:
            raise SetupError("Stale simulator in build output; use a fresh build directory")


setup(cmdclass={"build_py": CustomerBuildPy})
