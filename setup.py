from setuptools import setup, find_packages

setup(
    name="codequest",
    version="1.0.0",
    description="Project Command Center - 8-bit retro project dashboard",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "codequest": [
            "themes/*.tcss",
            "web/static/**/*",
            "web/templates/*.html",
        ]
    },
    install_requires=[
        "textual>=0.40.0",
        "flask>=3.0.0",
        "pyyaml>=6.0",
        "requests>=2.31.0",
        "anthropic>=0.20.0",
    ],
    entry_points={
        "console_scripts": [
            "codequest=codequest.__main__:main",
        ],
    },
    python_requires=">=3.10",
)
