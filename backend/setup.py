"""Setup configuration for Almabani package."""
from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

setup(
    name="almabani",
    version="2.0.0",
    description="BOQ Management and Rate Matching System",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Almabani Team",
    packages=find_packages(exclude=["tests*", "*_pipeline"]),
    python_requires=">=3.8",
    install_requires=[
        "pandas>=2.0.0",
        "openpyxl>=3.1.0",
        "aiosqlite>=0.19.0",
        "openai>=1.0.0",
        "boto3>=1.35.0",
        "aioboto3>=13.0.0",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "typer>=0.9.0",
        "rich>=13.0.0",
        "python-dotenv>=1.0.0",
        "tqdm>=4.66.0",
    ],
    entry_points={
        "console_scripts": [
            "almabani=almabani.cli.main:app",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
