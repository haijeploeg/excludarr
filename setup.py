from setuptools import setup, find_packages
from excludarr.core.version import get_version

VERSION = get_version()

f = open("README.md", "r")
LONG_DESCRIPTION = f.read()
f.close()

setup(
    name="excludarr",
    version=VERSION,
    description="Exclude streaming services such as netflix from Radarr",
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    author="Haije Ploeg",
    author_email="ploeg.haije@gmail.com",
    url="https://github.com/haijeploeg/excludarr",
    license="MIT",
    packages=find_packages(exclude=["ez_setup", "tests*"]),
    install_requires=["cement==3.0.4", "pyyaml", "colorlog", "requests", "rich"],
    entry_points="""
        [console_scripts]
        excludarr = excludarr.main:main
    """,
)
